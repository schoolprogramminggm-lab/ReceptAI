"""
tests/test_search.py — проверка нечёткого поиска по справочнику (drugs/search.py).

Запуск:  cd backend  ->  python -m pytest tests/test_search.py
"""

from drugs.search import (
    check_name,
    find_closest,
    find_drug,
    get_threshold,
)


def test_exact_name():
    # Точное название находится со 100% (регистр не важен)
    drug, score = find_drug("парацетамол")
    assert drug["trade_name"] == "Парацетамол"
    assert score == 100


def test_typo_in_name():
    # Опечатка: «Амоксицилин» (одна «л») вместо «Амоксициллин»
    drug, score = find_drug("Амоксицилин")
    assert drug is not None
    assert drug["trade_name"] == "Амоксициллин"
    assert score >= 85


def test_issue_example_atropen():
    # Пример из issue #8: «Атропен» -> «Атропин» (Атропин есть в drugs.csv)
    drug, score = find_drug("Атропен")
    assert drug["trade_name"] == "Атропин"
    assert score >= 85


def test_nonsense_not_found():
    # Бессмыслица не должна превращаться в лекарство
    drug, score = find_drug("Кшфгх")
    assert drug is None
    assert score < 85


def test_search_by_inn():
    # В справочнике нет торгового названия «Колекальциферол», это только МНН.
    # Его должно найти по колонке inn: Витамин D3 или Аквадетрим.
    drug, score = find_drug("Колекальциферол")
    assert drug is not None
    assert drug["inn"] == "колекальциферол"
    assert score == 100


def test_inn_with_typo():
    # МНН с опечаткой тоже находится: «ацетилцистеен» -> ацетилцистеин
    drug, score = find_drug("ацетилцистеен")
    assert drug is not None
    assert drug["inn"] == "ацетилцистеин"


def test_empty_name():
    # Пустое название и None — не падаем, возвращаем «не найдено»
    assert find_drug("") == (None, 0)
    assert find_drug("   ") == (None, 0)
    assert find_drug(None) == (None, 0)


def test_below_threshold_gives_unsure_message():
    # «Азотроп» похож на «Атропин», но меньше 85%: нужен ответ «Не уверен, возможно это …»
    drug, score = find_drug("Азотроп")
    assert drug is None  # уверенно не нашли

    result = check_name("Азотроп")
    assert result["match"] is None
    assert result["score"] < 85
    assert "Не уверен, возможно это «Атропин»" in result["note"]
    assert "врача или фармацевта" in result["note"]


def test_unsure_message_in_kazakh():
    result = check_name("Азотроп", lang="kk")
    assert "Атропин" in result["note"]
    assert "Сенімді емеспін" in result["note"]


def test_check_name_found():
    # Уверенное совпадение: match заполнен, предупреждения нет
    result = check_name("Амоксицилин")
    assert result["match"] == "Амоксициллин"
    assert result["score"] >= 85
    assert result["note"] is None


def test_check_name_nonsense():
    # Бессмыслица: match пустой, подсказки «возможно это» нет
    result = check_name("Кшфгх")
    assert result["match"] is None
    assert "возможно это" not in result["note"]


def test_threshold_from_env(monkeypatch):
    # Порог берётся из переменной DRUG_MATCH_THRESHOLD
    monkeypatch.setenv("DRUG_MATCH_THRESHOLD", "99")
    assert get_threshold() == 99

    # С порогом 99 опечатка «Амоксицилин» (95.7%) уже не считается найденной
    drug, score = find_drug("Амоксицилин")
    assert drug is None

    # Если в .env мусор — используется 85 по умолчанию
    monkeypatch.setenv("DRUG_MATCH_THRESHOLD", "abc")
    assert get_threshold() == 85

    # Если переменной нет совсем — тоже 85
    monkeypatch.delenv("DRUG_MATCH_THRESHOLD")
    assert get_threshold() == 85


def test_find_closest_ignores_threshold():
    # find_closest возвращает ближайшее лекарство, даже если похожесть низкая
    drug, score = find_closest("Кшфгх")
    assert drug is not None
    assert score < 85
