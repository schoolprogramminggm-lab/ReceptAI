"""
drugs/search.py — нечёткий поиск лекарства по справочнику data/drugs.csv.

Зачем это нужно:
    AI может неверно прочитать почерк врача, например «Атропен» вместо «Атропин».
    Мы не верим AI на слово, а сравниваем название со справочником
    и берём самое похожее настоящее название.

Главная функция:
    find_drug("Амоксицилин")  ->  ({"trade_name": "Амоксициллин", ...}, 95.7)
"""

import csv
import os
from pathlib import Path

from dotenv import load_dotenv
from rapidfuzz import fuzz, process

# Читаем backend/.env, чтобы получить DRUG_MATCH_THRESHOLD
load_dotenv()

# Путь к справочнику: backend/data/drugs.csv
CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "drugs.csv"

# Порог по умолчанию: похожесть от 85% и выше считаем «лекарство найдено»
DEFAULT_THRESHOLD = 85

# Если похожесть ниже этого числа, название совсем не похоже ни на что
# в справочнике (бессмыслица), и подсказку «возможно это …» мы не показываем
SUGGEST_MIN_SCORE = 65

# Справочник загружаем из файла один раз и храним здесь
_drugs = []         # список лекарств (каждое лекарство — словарь)
_search_names = []  # строки для поиска: торговые названия и МНН (маленькими буквами)
_search_owner = []  # _search_owner[i] — лекарство, которому принадлежит строка _search_names[i]


def get_threshold():
    """Читает порог из .env (DRUG_MATCH_THRESHOLD). Если там пусто или ошибка — 85."""
    text = os.getenv("DRUG_MATCH_THRESHOLD", "")
    try:
        return float(text)
    except ValueError:
        return DEFAULT_THRESHOLD


def load_drugs():
    """Читает drugs.csv и заполняет списки для поиска (один раз за запуск программы)."""
    if _drugs:  # уже загружено — повторно файл не читаем
        return

    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            trade_name = row["trade_name"].strip()
            inn = row["inn"].strip()
            if not trade_name:
                continue  # пустую строку пропускаем

            _drugs.append(row)

            # Ищем и по торговому названию, и по МНН (действующему веществу).
            # Оба названия указывают на одно и то же лекарство.
            _search_names.append(trade_name.lower())
            _search_owner.append(row)
            if inn:
                _search_names.append(inn.lower())
                _search_owner.append(row)


def all_drugs():
    """Весь справочник списком (нужен для поиска аналогов в analogs.py)."""
    load_drugs()
    return _drugs


def find_closest(name):
    """
    Находит в справочнике самое похожее лекарство БЕЗ учёта порога.
    Возвращает (лекарство, похожесть от 0 до 100).
    Если искать нечего (пустое название), вернёт (None, 0).
    """
    if not name or not name.strip():
        return None, 0

    load_drugs()

    # Сравниваем маленькими буквами, чтобы «АТРОПИН» и «атропин» были одинаковыми
    query = name.strip().lower()

    # extractOne перебирает все строки справочника и возвращает лучшую:
    # (найденная строка, похожесть, номер строки в списке)
    best = process.extractOne(query, _search_names, scorer=fuzz.ratio)
    if best is None:
        return None, 0

    _, score, index = best
    return _search_owner[index], round(score, 1)


def find_drug(name):
    """
    Ищет лекарство в справочнике по названию (торговому или МНН).

    Возвращает пару (лекарство, похожесть):
      - похожесть >= порога  -> (лекарство из справочника, похожесть)
      - похожесть <  порога  -> (None, похожесть): лекарство не найдено
    """
    drug, score = find_closest(name)
    if score >= get_threshold():
        return drug, score
    return None, score


def unsure_message(drug, lang="ru"):
    """Текст «Не уверен, возможно это …» для названия, которое ниже порога."""
    drug_name = drug["trade_name"]
    if lang == "kk":
        return (f"Сенімді емеспін, мүмкін бұл «{drug_name}». "
                "Дәрігерден немесе фармацевттен нақтылаңыз.")
    return (f"Не уверен, возможно это «{drug_name}». "
            "Уточните у врача или фармацевта.")


def check_name(name, lang="ru"):
    """
    Проверяет одно название, прочитанное AI, и готовит поля для ответа API.

    Возвращает словарь:
      match — название из справочника или None, если не найдено
      score — похожесть (0-100)
      note  — пояснение для человека или None, если всё в порядке
    """
    drug, score = find_drug(name)

    # 1. Нашли уверенно: показываем название из справочника без предупреждений
    if drug is not None:
        return {"match": drug["trade_name"], "score": score, "note": None}

    # 2. Не нашли: смотрим, есть ли хотя бы похожий вариант для подсказки
    closest, score = find_closest(name)
    if closest is not None and score >= SUGGEST_MIN_SCORE:
        return {"match": None, "score": score, "note": unsure_message(closest, lang)}

    # 3. Совсем ничего похожего (бессмыслица или пустое название)
    if lang == "kk":
        note = "Анықтамалықтан табылмады. Дәрігерден немесе фармацевттен нақтылаңыз."
    else:
        note = "В справочнике не найдено. Уточните у врача или фармацевта."
    return {"match": None, "score": score, "note": note}
