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
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

# Загружаем переменные из backend/.env
load_dotenv()

# Максимальный размер фото — 8 МБ
MAX_PHOTO_BYTES = 8 * 1024 * 1024

# Допустимые форматы входного файла
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic"}


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
    # Открываем изображение из байтов (не из файла!)
    img = Image.open(io.BytesIO(image_bytes))

    # Переводим в RGB — JPEG не поддерживает прозрачность (RGBA)
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    # Сохраняем обратно в байты как JPEG
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=85)
    return output.getvalue()


def _validate_json(text: str) -> list:
    """
    Проверяет, что ответ Gemini — это правильный JSON-массив.
    Возвращает список лекарств или [] если что-то пошло не так.
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
        return []

    # Проверяем что это список
    if not isinstance(data, list):
        print(f"[reader] Ответ не является списком: {type(data)}")
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


def read_prescription(image_bytes: bytes) -> list:
    """
    Главная функция: отправляет фото рецепта в Gemini и возвращает список лекарств.

    Аргументы:
        image_bytes: байты изображения (jpeg, png или heic)

    Возвращает:
        Список словарей с полями: name, form, dose, frequency, duration, sure
        Или [] если не удалось прочитать.
    """
    # Проверяем размер фото
    if len(image_bytes) > MAX_PHOTO_BYTES:
        raise ValueError(
            f"Фото слишком большое: {len(image_bytes) // 1024} КБ. "
            f"Максимум: {MAX_PHOTO_BYTES // 1024 // 1024} МБ"
        )

    # Получаем настройки из .env
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY не задан. "
            "Скопируйте backend/.env.example в backend/.env и вставьте ключ."
        )

    # Конвертируем фото в JPEG (обработка в памяти, файл не пишется на диск)
    jpeg_bytes = _convert_to_jpeg(image_bytes)

    # Загружаем инструкцию для модели
    prompt = _load_prompt()

    # Инициализируем клиент Gemini
    client = genai.Client(api_key=api_key)

    # Формируем запрос: картинка + текст инструкции
    response = client.models.generate_content(
        model=model_name,
        contents=[
            types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
            prompt,
        ],
    )

    # Получаем текст ответа
    answer = response.text if response.text else ""

    # Разбираем JSON из ответа
    drugs = _validate_json(answer)

    return drugs


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
