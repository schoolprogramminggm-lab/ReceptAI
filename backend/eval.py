"""
eval.py — проверка точности: прогоняет тестовые рецепты через AI и справочник.

Запуск (из папки backend):
    venv\\Scripts\\python.exe eval.py
    venv\\Scripts\\python.exe eval.py --model gemini-3.5-flash-lite

Что делает:
    1. Читает tests/prescriptions.csv (правильные ответы).
    2. Для каждой строки берёт фото из test_photos/ (имя файла — колонка file).
       Строки без фото пропускает и пишет, сколько пропущено.
    3. Каждое фото проходит тот же путь, что и в приложении: Gemini -> справочник.
    4. Сравнивает названия лекарств с expected_names, считает точность и время.
    5. Печатает итог в консоль и пишет таблицу в docs/accuracy.md.

Нужен GEMINI_API_KEY в backend/.env. Запросы идут в Gemini, поэтому это платит лимит ключа.
"""

import argparse
import csv
import os
import time
from datetime import date
from pathlib import Path

from ai.reader import DEFAULT_MODEL, read_prescription
from main import make_card
from drugs.status import FOUND, NOT_IN_DIRECTORY, UNSURE

# Папки и файлы проекта
BACKEND_DIR = Path(__file__).resolve().parent
CSV_PATH = BACKEND_DIR / "tests" / "prescriptions.csv"
PHOTOS_DIR = BACKEND_DIR / "test_photos"
REPORT_PATH = BACKEND_DIR.parent / "docs" / "accuracy.md"


def norm(text):
    """Название для сравнения: маленькие буквы, без лишних пробелов."""
    return " ".join(str(text).lower().split())


def split_names(text):
    """'Амоксициллин;Ибупрофен' -> ['амоксициллин', 'ибупрофен'] (пустое -> [])."""
    return [norm(n) for n in (text or "").split(";") if n.strip()]


def load_rows(csv_path):
    """Читает prescriptions.csv, возвращает список строк-словарей."""
    with open(csv_path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def score_names(expected, found):
    """
    Сравнивает ожидаемые названия с найденными.
    Возвращает (сколько ожидаемых найдено верно, список лишних найденных названий).
    Лишние — это названия, которых нет в рецепте (выдуманные или прочитанные неверно).
    """
    correct = sum(1 for name in expected if name in found)
    extra = [name for name in found if name not in expected]
    return correct, extra


def evaluate_photo(row, photo_path):
    """Прогоняет одно фото и возвращает результат для таблицы."""
    expected = split_names(row["expected_names"])
    started = time.perf_counter()
    error = None
    cards = []
    try:
        result = read_prescription(photo_path.read_bytes())
        # make_card — то же, что делает сервер: проверка по справочнику, статус карточки
        cards = [make_card(drug, "ru") for drug in result["drugs"]]
    except Exception as e:
        # Ошибку Gemini (перегрузка, таймаут) не прячем: строка считается как 0 верных
        error = f"{type(e).__name__}: {e}"
    seconds = time.perf_counter() - started

    found = [norm(card["name"]) for card in cards if card["name"]]
    correct, extra = score_names(expected, found)
    return {
        "id": row["id"],
        "file": row["file"],
        "expected": expected,
        "found": [card["name"] for card in cards],
        "correct": correct,
        "extra": extra,
        "statuses": [card["status"] for card in cards],
        "seconds": seconds,
        "error": error,
    }


def run(csv_path=CSV_PATH, photos_dir=PHOTOS_DIR, evaluate=evaluate_photo):
    """
    Идёт по строкам CSV. Возвращает (результаты, сколько пропущено без фото,
    сколько пропущено без правильного ответа).
    """
    results = []
    no_photo = 0
    no_answer = 0
    for row in load_rows(csv_path):
        photo_path = Path(photos_dir) / row["file"]
        if not photo_path.exists():
            no_photo += 1
            continue
        if not split_names(row["expected_names"]):
            # фото есть, но правильные названия ещё не заполнены: считать не с чем
            no_answer += 1
            continue
        print(f"[{row['id']}] {row['file']} ...", flush=True)
        results.append(evaluate(row, photo_path))
    return results, no_photo, no_answer


def summarize(results):
    """Общие числа: верно / ожидалось, процент, лишние, статусы, среднее время."""
    expected_total = sum(len(r["expected"]) for r in results)
    correct_total = sum(r["correct"] for r in results)
    statuses = [s for r in results for s in r["statuses"]]
    seconds = [r["seconds"] for r in results]
    return {
        "expected_total": expected_total,
        "correct_total": correct_total,
        "percent": round(100 * correct_total / expected_total, 1) if expected_total else 0.0,
        "extra_total": sum(len(r["extra"]) for r in results),
        "found": statuses.count(FOUND),
        "unsure": statuses.count(UNSURE),
        "not_in_directory": statuses.count(NOT_IN_DIRECTORY),
        "avg_seconds": round(sum(seconds) / len(seconds), 1) if seconds else 0.0,
    }


def make_markdown(results, total, no_photo, no_answer, model):
    """Текст docs/accuracy.md: заголовок, таблица по рецептам, общий итог."""
    lines = [
        "# Точность распознавания",
        "",
        f"- Дата: {date.today().isoformat()}",
        f"- Модель Gemini: `{model}`",
        f"- Рецептов проверено: {len(results)} (пропущено без фото: {no_photo}, "
        f"без правильного ответа в CSV: {no_answer})",
        "",
        "| № | Файл | Ожидалось | Найдено | Верно | Лишние | Статусы | Время, с |",
        "|---|------|-----------|---------|-------|--------|---------|----------|",
    ]
    for r in results:
        found = ", ".join(r["found"]) or "—"
        if r["error"]:
            found = f"ОШИБКА: {r['error']}".replace("|", "/")
        lines.append(
            f"| {r['id']} | {r['file']} | {'; '.join(r['expected'])} | {found} | "
            f"{r['correct']}/{len(r['expected'])} | {', '.join(r['extra']) or '—'} | "
            f"{', '.join(r['statuses']) or '—'} | {r['seconds']:.1f} |"
        )
    lines += [
        "",
        f"**Итого: {total['correct_total']} из {total['expected_total']} лекарств "
        f"названы правильно — {total['percent']}%.**",
        "",
        f"- Статусы карточек: found — {total['found']}, unsure — {total['unsure']}, "
        f"not_in_directory — {total['not_in_directory']}",
        f"- Лишние названия (нет в рецепте): {total['extra_total']}",
        f"- Среднее время ответа: {total['avg_seconds']} с",
        "",
        "Правильно = название в карточке совпало с expected_names (регистр не важен), "
        "независимо от статуса. Статус показывает, насколько приложение было уверено.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Точность распознавания на тестовых рецептах")
    parser.add_argument("--model", help="модель Gemini (по умолчанию GEMINI_MODEL из .env)")
    args = parser.parse_args()

    if args.model:
        # reader.py берёт модель из переменной окружения при каждом вызове
        os.environ["GEMINI_MODEL"] = args.model
    # Запасную модель выключаем: иначе при перегрузке ответит другая модель,
    # и сравнение двух моделей будет нечестным
    os.environ["GEMINI_FALLBACK_MODEL"] = ""
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)

    results, no_photo, no_answer = run()
    if no_photo:
        print(f"Пропущено строк без фото: {no_photo}")
    if no_answer:
        print(f"Пропущено строк без правильного ответа (expected_names пуст): {no_answer}")
    if not results:
        print(f"Нет ни одного рецепта для проверки. Положите фото в {PHOTOS_DIR} "
              "(recept01.jpg … recept30.jpg) и заполните expected_names в tests/prescriptions.csv.")
        return

    total = summarize(results)
    text = make_markdown(results, total, no_photo, no_answer, model)

    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(text, encoding="utf-8")

    print()
    print(text)
    print(f"Сохранено: {REPORT_PATH}")


if __name__ == "__main__":
    main()
