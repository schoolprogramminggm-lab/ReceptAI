"""
tests/test_analogs.py — проверка поиска аналогов (drugs/analogs.py).

Запуск:  cd backend  ->  python -m pytest tests/test_analogs.py
"""

from drugs import analogs
from drugs.analogs import find_analogs
from drugs.search import all_drugs


def _drug(name, inn, form, price):
    """Маленькая «строка справочника» для тестов."""
    return {"trade_name": name, "inn": inn, "form": form, "price_kzt": str(price)}


def test_small_example(monkeypatch):
    # Подменяем справочник маленьким списком, чтобы результат был понятен заранее
    fake = [
        _drug("А", "вещество1", "таблетки 500 мг", 300),
        _drug("Б", "вещество1", "таблетки 500 мг", 100),   # аналог, самый дешёвый
        _drug("В", "вещество1", "таблетки 500 мг", 200),   # аналог
        _drug("Г", "вещество1", "капсулы 250 мг", 50),     # другая форма — не аналог
        _drug("Д", "вещество2", "таблетки 500 мг", 10),    # другое вещество — не аналог
    ]
    monkeypatch.setattr(analogs, "all_drugs", lambda: fake)

    result = find_analogs(fake[0])
    # без самого лекарства «А», без «Г» (форма) и «Д» (вещество), по цене: Б (100), В (200)
    assert [d["trade_name"] for d in result] == ["Б", "В"]


def test_no_analogs(monkeypatch):
    fake = [_drug("А", "вещество1", "таблетки", 300), _drug("Б", "вещество2", "таблетки", 100)]
    monkeypatch.setattr(analogs, "all_drugs", lambda: fake)
    assert find_analogs(fake[0]) == []


def test_real_reference():
    # Проверяем все 130 лекарств настоящего справочника
    found_any = False
    for drug in all_drugs():
        result = find_analogs(drug)
        if result:
            found_any = True

        # 1. Сам препарат в списке аналогов не встречается
        assert drug["trade_name"] not in [d["trade_name"] for d in result]

        # 2. То же вещество и та же форма
        for d in result:
            assert d["inn"].strip().lower() == drug["inn"].strip().lower()
            assert d["form"].strip().lower() == drug["form"].strip().lower()

        # 3. Отсортировано по цене: от дешёвых к дорогим
        prices = [float(d["price_kzt"]) for d in result]
        assert prices == sorted(prices)

    # В справочнике есть лекарства с аналогами
    assert found_any
