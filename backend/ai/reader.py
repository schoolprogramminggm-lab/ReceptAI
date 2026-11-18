"""
ai/reader.py — чтение рецепта по фото через Gemini API.

Использование из консоли (для проверки):
    cd backend
    venv\\Scripts\\activate
    python -m ai.reader test_photos/recept1.jpg

Использование из кода:
    from ai.reader import read_prescription
    result = read_prescription(image_bytes)
"""

import io
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image

from drugs.search import directory_for_prompt

# Метка в prompt.txt, вместо которой подставляется список лекарств из справочника
DRUG_LIST_MARK = "{{DRUG_LIST}}"

# Модель Gemini по умолчанию, если GEMINI_MODEL не задан в .env
DEFAULT_MODEL = "gemini-3.8-flash"

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

# Сколько секунд ждём ответ на ОДИН вызов Gemini, если в .env нет GEMINI_TIMEOUT_SEC
DEFAULT_CALL_TIMEOUT_SEC = 25

# Весь запрос к Gemini (все попытки, паузы и запасная модель) должен уложиться в это время.
# У приложения таймаут 60 секунд, поэтому оставляем запас
TOTAL_TIMEOUT_SEC = 55

# Если до конца общего времени осталось меньше этого, новый вызов уже не начинаем
MIN_CALL_TIMEOUT_SEC = 1

# 504 = Gemini сам прервал слишком долгий запрос. Считаем это таким же «зависанием», как таймаут
SERVER_TIMEOUT_CODES = (504,)

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
    """Читает инструкцию для Gemini из prompt.txt и вставляет в неё справочник лекарств."""
    # Путь к prompt.txt находится в той же папке, что и этот файл
    prompt_path = Path(__file__).parent / "prompt.txt"
    text = prompt_path.read_text(encoding="utf-8")
    # В prompt.txt есть фигурные скобки JSON, поэтому format() не подходит:
    # просто заменяем метку на список лекарств из drugs.csv
    return text.replace(DRUG_LIST_MARK, directory_for_prompt())


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


def _norm(text) -> str:
    """Строка для сравнения: без регистра, лишних пробелов и точки в конце."""
    return " ".join(str(text).lower().split()).rstrip(".")


def _parse_answer(text: str, strict: bool = False) -> dict:
    """
    Разбирает ответ Gemini и возвращает {"drugs": [...], "advice": [...]}.

    Ответ должен быть JSON-объектом {"drugs": [...], "advice": [...]}.
    Если модель по старой привычке прислала просто массив лекарств, считаем,
    что советов нет. Мусор превращается в пустой результат.

    strict=True: если ответ не JSON, бросаем UnreadableResponseError
    (так read_prescription узнаёт, что нужен повтор). Пустые drugs — это
    нормальный ответ «лекарств на фото нет», а не ошибка.
    """
    empty = {"drugs": [], "advice": []}

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
        return empty

    # Достаём список лекарств и список советов
    if isinstance(data, dict):
        items = data.get("drugs")
        advice_items = data.get("advice")
    elif isinstance(data, list):
        items, advice_items = data, []  # старый формат: только лекарства
    else:
        items = None

    if not isinstance(items, list):
        print(f"[reader] В ответе нет списка лекарств: {type(data)}")
        if strict:
            raise UnreadableResponseError()
        return empty

    # Проверяем каждое лекарство — должны быть обязательные поля
    drugs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # Поле name обязательно
        if "name" not in item:
            continue
        # Добавляем все нужные поля, если их нет — None
        # read_as — что AI прочитал буквально. Если модель его не прислала
        # (или прислала пустым), считаем, что прочитано то же, что в name
        read_as = item.get("read_as")
        if not isinstance(read_as, str) or not read_as.strip():
            read_as = item.get("name")
        drug = {
            "name": item.get("name"),
            "read_as": read_as,
            "form": item.get("form"),
            "dose": item.get("dose"),
            "frequency": item.get("frequency"),
            "duration": item.get("duration"),
            # sure по умолчанию False — лучше перестраховаться
            "sure": bool(item.get("sure", False)),
        }
        drugs.append(drug)

    # Советы: только непустые строки, без повторов
    drug_names = {_norm(d["name"]) for d in drugs if d["name"]}
    advice = []
    if isinstance(advice_items, list):
        for tip in advice_items:
            if not isinstance(tip, str) or not tip.strip():
                continue
            # один и тот же текст не должен быть и лекарством, и советом
            if _norm(tip) in drug_names or _norm(tip) in {_norm(a) for a in advice}:
                continue
            advice.append(tip.strip())

    return {"drugs": drugs, "advice": advice}


def _validate_json(text: str, strict: bool = False) -> list:
    """Только список лекарств из ответа Gemini (советы см. _parse_answer)."""
    return _parse_answer(text, strict)["drugs"]


def _now():
    """Текущее время в секундах (для подсчёта оставшегося времени). Вынесено для тестов."""
    return time.monotonic()


def get_call_timeout():
    """Сколько секунд ждать один вызов Gemini: GEMINI_TIMEOUT_SEC из .env, по умолчанию 25."""
    try:
        seconds = float(os.getenv("GEMINI_TIMEOUT_SEC", ""))
    except ValueError:
        return DEFAULT_CALL_TIMEOUT_SEC
    # ноль и отрицательные числа не имеют смысла
    return seconds if seconds > 0 else DEFAULT_CALL_TIMEOUT_SEC


def _generate(client, model_name, contents, deadline):
    """
    Один вызов Gemini с таймаутом.

    Таймаут = GEMINI_TIMEOUT_SEC, но не больше, чем осталось до deadline (общего срока),
    поэтому весь запрос в сумме не длиннее TOTAL_TIMEOUT_SEC.
    Если Gemini не ответил вовремя, библиотека бросает httpx.TimeoutException.
    """
    left = deadline - _now()
    if left < MIN_CALL_TIMEOUT_SEC:
        # общее время вышло, новый вызов не начинаем
        print(f"[reader] Общее время {TOTAL_TIMEOUT_SEC} с вышло, модель {model_name} не вызываем")
        raise GeminiOverloadedError()

    timeout = min(get_call_timeout(), left)
    # В настройках библиотеки таймаут задаётся в миллисекундах
    config = types.GenerateContentConfig(
        http_options=types.HttpOptions(timeout=int(timeout * 1000))
    )
    return client.models.generate_content(model=model_name, contents=contents, config=config)


def _ask_gemini(client, model_name, contents, deadline=None):
    """
    Один вопрос к Gemini с защитой от перегрузки и зависания.

    1. Основную модель пробуем до OVERLOAD_ATTEMPTS раз (паузы 2 и 4 секунды),
       если Gemini отвечает 503 или 429.
    2. Если Gemini не ответил за GEMINI_TIMEOUT_SEC (или ответил 504), повторять
       основную модель нет смысла: сразу переходим к запасной.
    3. Запасную модель из GEMINI_FALLBACK_MODEL пробуем один раз.
    4. Если и она не ответила, бросаем GeminiOverloadedError.
    Любая другая ошибка (неверный ключ, плохой запрос) сразу уходит наверх, без повторов.
    Подробности ошибок пишем только в лог сервера (print), пользователь их не видит.

    deadline — момент, к которому всё должно закончиться (по умолчанию через TOTAL_TIMEOUT_SEC).
    """
    if deadline is None:
        deadline = _now() + TOTAL_TIMEOUT_SEC

    for attempt in range(1, OVERLOAD_ATTEMPTS + 1):
        try:
            return _generate(client, model_name, contents, deadline)
        except httpx.TimeoutException:
            print(f"[reader] Gemini не ответил вовремя, модель {model_name}")
            break  # повторять зависшую модель бессмысленно: сразу запасная
        except genai_errors.APIError as e:
            if e.code in SERVER_TIMEOUT_CODES:
                print(f"[reader] Gemini прервал долгий запрос ({e.code}), модель {model_name}")
                break
            if e.code not in OVERLOAD_CODES:
                raise
            print(f"[reader] Gemini перегружен, модель {model_name}, "
                  f"попытка {attempt} из {OVERLOAD_ATTEMPTS}: {e}")
            # после последней попытки пауза не нужна; паузу не делаем длиннее, чем осталось времени
            if attempt < OVERLOAD_ATTEMPTS:
                time.sleep(min(OVERLOAD_PAUSES[attempt - 1], max(0, deadline - _now())))

    # Основная модель не отвечает: пробуем запасную (если она задана и отличается)
    fallback_model = os.getenv("GEMINI_FALLBACK_MODEL", "").strip()
    if fallback_model and fallback_model != model_name:
        print(f"[reader] Пробуем запасную модель {fallback_model}")
        try:
            return _generate(client, fallback_model, contents, deadline)
        except httpx.TimeoutException:
            print(f"[reader] Запасная модель {fallback_model} тоже не ответила вовремя")
        except genai_errors.APIError as e:
            if e.code not in OVERLOAD_CODES + SERVER_TIMEOUT_CODES:
                raise
            print(f"[reader] Запасная модель {fallback_model} тоже перегружена: {e}")

    raise GeminiOverloadedError()


def read_prescription(image_bytes: bytes) -> dict:
    """
    Главная функция: отправляет фото рецепта в Gemini и возвращает лекарства и советы врача.

    Аргументы:
        image_bytes: байты изображения (jpeg, png или heic)

    Возвращает словарь:
        {"drugs":  [словари с полями name, read_as, form, dose, frequency, duration, sure],
         "advice": ["пить тёплую воду", ...]}   # общие советы врача, это НЕ лекарства
        drugs == [] если на фото нет лекарств.

    Если Gemini два раза подряд ответил не JSON, бросает UnreadableResponseError.
    Если Gemini перегружен (503/429) или не отвечает (таймаут) и запасная модель тоже,
    бросает GeminiOverloadedError. Весь запрос длится не дольше TOTAL_TIMEOUT_SEC секунд.
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
    model_name = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)

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

    # Общий срок на все обращения к Gemini: уложиться в TOTAL_TIMEOUT_SEC секунд
    deadline = _now() + TOTAL_TIMEOUT_SEC

    # Спрашиваем Gemini. Если ответ не JSON, повторяем запрос (всего MAX_ATTEMPTS раз).
    # Другие ошибки (ключ, плохой запрос) не повторяем: они сразу уходят наверх.
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Повторять из-за не-JSON ответа, когда время почти вышло, уже поздно
        if attempt > 1 and deadline - _now() < MIN_CALL_TIMEOUT_SEC:
            print("[reader] Время вышло, повторный запрос из-за не-JSON ответа не делаем")
            break

        # Формируем запрос: картинка + текст инструкции
        # (при перегрузке Gemini _ask_gemini сама повторяет и пробует запасную модель)
        response = _ask_gemini(
            client,
            model_name,
            [
                types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
                prompt,
            ],
            deadline,
        )

        # Получаем текст ответа
        answer = response.text if response.text else ""

        # Разбираем JSON из ответа; если это не JSON, получим UnreadableResponseError
        try:
            return _parse_answer(answer, strict=True)
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
        result = read_prescription(image_bytes)
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
    drugs = result["drugs"]
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

    if result["advice"]:
        print("Советы врача (не лекарства):")
        for tip in result["advice"]:
            print(f"  - {tip}")
        print()

    print("--- JSON-ответ ---")
    print(json.dumps(result, ensure_ascii=False, indent=2))

