"""
drugs/analogs.py — аналоги лекарства из справочника data/drugs.csv.

Аналог — это другое лекарство с ТЕМ ЖЕ действующим веществом (МНН, колонка inn)
и ТОЙ ЖЕ формой (колонка form, например «капсулы 500 мг»).
Часто аналог стоит дешевле, поэтому список отсортирован по цене: сначала самые дешёвые.

Главная функция:
    find_analogs(drug)  ->  [лекарство, лекарство, ...]
"""

from drugs.search import all_drugs


def _same(a, b):
    """Сравнивает две строки без учёта регистра и пробелов по краям."""
    return a.strip().lower() == b.strip().lower()


def _price(drug):
    """Цена лекарства числом. Если цены нет или она написана странно — считаем очень дорогой."""
    try:
        return float(drug["price_kzt"])
    except (ValueError, TypeError, KeyError):
        return float("inf")


def find_analogs(drug):
    """
    Ищет аналоги для лекарства `drug` (строка из справочника: словарь с ключами
    trade_name, inn, form, price_kzt).

    Возвращает список лекарств-аналогов, отсортированный по цене (от дешёвых к дорогим).
    Само лекарство в список не входит.
    """
    inn = drug.get("inn") or ""
    if not inn.strip():
        return []  # без действующего вещества сравнивать не с чем

    result = []
    for other in all_drugs():
        # пропускаем само лекарство
        if _same(other["trade_name"], drug["trade_name"]):
            continue
        # берём только то же вещество и ту же форму
        if _same(other["inn"], inn) and _same(other["form"], drug["form"]):
            result.append(other)

    # сортируем по цене: sorted с key=_price
    return sorted(result, key=_price)
