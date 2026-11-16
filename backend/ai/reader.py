"""
ai/reader.py — чтение рецепта по фото через Gemini API.

Использование из консоли (для проверки):
    cd backend
    venv\\Scripts\\activate
    python -m ai.reader test_photos/recept1.jpg

Использование из кода:
    from ai.reader import read_prescription
    drugs = read_prescription(image_bytes)
"""

import io
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image

# Загружаем переменные из backend/.env
load_dotenv()

# Максимальный размер фото — 8 МБ
MAX_PHOTO_BYTES = 8 * 1024 * 1024

# Допустимые форматы входного файла
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic"}


# Сколько раз всего спрашиваем Gemini, если ответ — не JSON (1 запрос + 1 повтор)
MAX_ATTEMPTS = 2

# Сообщение для человека, если Gemini дважды ответил не JSON
UNREADABLE_MESSAGE = {
    "ru": "Не удалось прочитать, переснимите рецепт",
    "kk": "Оқу мүмкін болмады, рецептті қайта суретке түсіріңіз",
}


class UnreadableResponseError(Exception):
    """Gemini ответил не JSON (даже после повтора). Фото нужно переснять."""

    def __init__(self):
        # По умолчанию сообщение на русском; main.py берёт нужный язык из UNREADABLE_MESSAGE
        super().__init__(UNREADABLE_MESSAGE["ru"])


# Коды ответа Gemini, при которых стоит подождать и повторить: 503 (перегрузка), 429 (лимит запросов)
OVERLOAD_CODES = (503, 429)

# Сколько раз всего пробуем основную модель при перегрузке
OVERLOAD_ATTEMPTS = 3

# Пауза в секундах после 1-й и после 2-й неудачной попытки
OVERLOAD_PAUSES = (2, 4)

# Сообщение для человека, если Gemini перегружен
OVERLOADED_MESSAGE = {
    "ru": "Сервис распознавания перегружен, попробуйте через минуту",
    "kk": "Тану сервисі шамадан тыс жүктелген, бір минуттан кейін қайталап көріңіз",
}


class GeminiOverloadedError(Exception):
    """Gemini перегружен (503/429): основная и запасная модель не ответили."""

    def __init__(self):
        super().__init__(OVERLOADED_MESSAGE["ru"])


# Сообщение для человека, если файл не открывается как изображение
INVALID_IMAGE_MESSAGE = {
    "ru": "Это не фото рецепта, выберите другое изображение",
    "kk": "Бұл рецепт суреті емес, басқа сурет таңдаңыз",
}


class InvalidImageError(Exception):
    """Файл не удалось открыть как изображение (битый файл или не картинка)."""

    def __init__(self):
        super().__init__(INVALID_IMAGE_MESSAGE["ru"])


class MissingApiKeyError(EnvironmentError):
    """В .env не задан GEMINI_API_KEY.

    Отдельный класс нужен, чтобы сервер не путал эту ошибку с другими OSError
    (например, «файл не картинка»): в Python EnvironmentError и OSError — одно и то же.
    """


def _load_prompt() -> str:
    """Читает инструкцию для Gemini из prompt.txt."""
    # Путь к prompt.txt находится в той же папке, что и этот файл
    prompt_path = Path(__file__).parent / "prompt.txt"
    return prompt_path.read_text(encoding="utf-8")


def _convert_to_jpeg(image_bytes: bytes) -> bytes:
    """
    Конвертирует изображение в JPEG.
    Нужно для HEIC и PNG — Gemini лучше всего работает с JPEG.
    Фото нигде не сохраняется, только в памяти.
    """
    try:
        # Открываем изображение из байтов (не из файла!)
        img = Image.open(io.BytesIO(image_bytes))

        # Переводим в RGB — JPEG не поддерживает прозрачность (RGBA)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")

        # Сохраняем обратно в байты как JPEG
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=85)
    except (OSError, Image.DecompressionBombError) as e:
        # Pillow бросает UnidentifiedImageError (это OSError), если файл не картинка,
        # и OSError, если картинка обрезана или повреждена
        print(f"[reader] Не удалось открыть изображение: {e}")
        raise InvalidImageError() from e
    return output.getvalue()


def _validate_json(text: str, strict: bool = False) -> list:
    """
    Проверяет, что ответ Gemini — это правильный JSON-массив.
    Возвращает список лекарств или [] если что-то пошло не так.

    strict=True: если ответ не JSON-массив, бросаем UnreadableResponseError
    (так read_prescription узнаёт, что нужен повтор). Пустой массив [] — это
    нормальный ответ «лекарств на фото нет», а не ошибка.
    """
    # Иногда модель добавляет ```json ... ``` — убираем это
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Убираем первую строку (```json) и последнюю (```)
        text = "\n".join(lines[1:-1]).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[reader] Ошибка разбора JSON: {e}")
        print(f"[reader] Ответ модели: {text[:200]}")
        if strict:
            raise UnreadableResponseError()
        return []

    # Проверяем что это список
    if not isinstance(data, list):
        print(f"[reader] Ответ не является списком: {type(data)}")
        if strict:
            raise UnreadableResponseError()
        return []

    # Проверяем каждый элемент — должны быть обязательные поля
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        # Поле name обязательно
        if "name" not in item:
            continue
        # Добавляем все нужные поля, если их нет — None
        drug = {
            "name": item.get("name"),
            "form": item.get("form"),
            "dose": item.get("dose"),
            "frequency": item.get("frequency"),
            "duration": item.get("duration"),
            # sure по умолчанию False — лучше перестраховаться
            "sure": bool(item.get("sure", False)),
        }
        result.append(drug)

    return result


def _ask_gemini(client, model_name, contents):
    """
    Один вопрос к Gemini с защитой от перегрузки.

    1. Основную модель пробуем до OVERLOAD_ATTEMPTS раз (паузы 2 и 4 секунды),
       если Gemini отвечает 503 или 429.
    2. Если всё ещё перегружен, один раз пробуем запасную модель из GEMINI_FALLBACK_MODEL.
    3. Если и она не ответила, бросаем GeminiOverloadedError.
    Любая другая ошибка (неверный ключ, плохой запрос) сразу уходит наверх, без повторов.
    Подробности ошибок пишем только в лог сервера (print), пользователь их не видит.
    """
    for attempt in range(1, OVERLOAD_ATTEMPTS + 1):
        try:
            return client.models.generate_content(model=model_name, contents=contents)
        except genai_errors.APIError as e:
            if e.code not in OVERLOAD_CODES:
                raise
            print(f"[reader] Gemini перегружен, модель {model_name}, "
                  f"попытка {attempt} из {OVERLOAD_ATTEMPTS}: {e}")
            # после последней попытки пауза не нужна
            if attempt < OVERLOAD_ATTEMPTS:
                time.sleep(OVERLOAD_PAUSES[attempt - 1])

    # Основная модель не отвечает: пробуем запасную (если она задана и отличается)
    fallback_model = os.getenv("GEMINI_FALLBACK_MODEL", "").strip()
    if fallback_model and fallback_model != model_name:
        print(f"[reader] Пробуем запасную модель {fallback_model}")
        try:
            return client.models.generate_content(model=fallback_model, contents=contents)
        except genai_errors.APIError as e:
            if e.code not in OVERLOAD_CODES:
                raise
            print(f"[reader] Запасная модель {fallback_model} тоже перегружена: {e}")

    raise GeminiOverloadedError()


def read_prescription(image_bytes: bytes) -> list:
    """
    Главная функция: отправляет фото рецепта в Gemini и возвращает список лекарств.

    Аргументы:
        image_bytes: байты изображения (jpeg, png или heic)

    Возвращает:
        Список словарей с полями: name, form, dose, frequency, duration, sure
        [] если на фото нет лекарств.

    Если Gemini два раза подряд ответил не JSON, бросает UnreadableResponseError.
    Если Gemini перегружен (503/429) и запасная модель тоже, бросает GeminiOverloadedError.
    Если файл не открывается как изображение, бросает InvalidImageError.
    """
    # Проверяем размер фото
    if len(image_bytes) > MAX_PHOTO_BYTES:
        raise ValueError(
            f"Фото слишком большое: {len(image_bytes) // 1024} КБ. "
            f"Максимум: {MAX_PHOTO_BYTES // 1024 // 1024} МБ"
        )

    # Получаем настройки из .env
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    if not api_key:
        raise MissingApiKeyError(
            "GEMINI_API_KEY не задан. "
            "Скопируйте backend/.env.example в backend/.env и вставьте ключ."
        )

    # Конвертируем фото в JPEG (обработка в памяти, файл не пишется на диск)
    jpeg_bytes = _convert_to_jpeg(image_bytes)

    # Загружаем инструкцию для модели
    prompt = _load_prompt()

    # Инициализируем клиент Gemini
    client = genai.Client(api_key=api_key)

    # Спрашиваем Gemini. Если ответ не JSON, повторяем запрос (всего MAX_ATTEMPTS раз).
    # Другие ошибки (ключ, плохой запрос) не повторяем: они сразу уходят наверх.
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Формируем запрос: картинка + текст инструкции
        # (при перегрузке Gemini _ask_gemini сама повторяет и пробует запасную модель)
        response = _ask_gemini(
            client,
            model_name,
            [
                types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
                prompt,
            ],
        )

        # Получаем текст ответа
        answer = response.text if response.text else ""

        # Разбираем JSON из ответа; если это не JSON, получим UnreadableResponseError
        try:
            return _validate_json(answer, strict=True)
        except UnreadableResponseError:
            print(f"[reader] Ответ не JSON (попытка {attempt} из {MAX_ATTEMPTS})")

    # Обе попытки закончились не-JSON ответом
    raise UnreadableResponseError()


# ──────────────────────────────────────────────────
# Запуск из консоли для проверки:
# python -m ai.reader test_photos/recept1.jpg
# ──────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python -m ai.reader <путь_к_фото>")
        print("Пример:        python -m ai.reader test_photos/recept1.jpg")
        sys.exit(1)

    photo_path = Path(sys.argv[1])

    # Проверяем что файл существует
    if not photo_path.exists():
        print(f"Файл не найден: {photo_path}")
        print("Создайте папку test_photos/ и положите туда фото рецепта.")
        sys.exit(1)

    # Проверяем расширение файла
    ext = photo_path.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        print(f"Формат не поддерживается: {ext}")
        print(f"Допустимые форматы: {', '.join(ALLOWED_EXTENSIONS)}")
        sys.exit(1)

    print(f"Читаем рецепт: {photo_path}")
    print("Отправляем в Gemini...")

    # Читаем фото в байты (в памяти, никуда не пишем)
    image_bytes = photo_path.read_bytes()

    try:
        drugs = read_prescription(image_bytes)
    except EnvironmentError as e:
        print(f"\nОшибка настроек: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"\nОшибка фото: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nОшибка запроса к Gemini: {e}")
        print("Проверьте: ключ правильный? Доступен ли интернет?")
        sys.exit(1)

    # Выводим результат
    if not drugs:
        print("\nЛекарства не найдены (или рецепт не читается).")
    else:
        print(f"\nНайдено лекарств: {len(drugs)}\n")
        for i, drug in enumerate(drugs, 1):
            sure_label = "✓ уверенно" if drug["sure"] else "⚠ неуверенно"
            print(f"{i}. {drug['name']} [{sure_label}]")
            if drug["form"]:
                print(f"   Форма: {drug['form']}")
            if drug["dose"]:
                print(f"   Доза: {drug['dose']}")
            if drug["frequency"]:
                print(f"   Как часто: {drug['frequency']}")
            if drug["duration"]:
                print(f"   Курс: {drug['duration']}")
            print()

    print("--- JSON-ответ ---")
    print(json.dumps(drugs, ensure_ascii=False, indent=2))

