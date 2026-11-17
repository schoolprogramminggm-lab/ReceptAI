"""
Тесты issues #17, #18, #19 (Gemini везде замокан, в сеть мы не ходим):
- #17: лекарства из живого теста есть в справочнике, цены без источника не выдумываем
- #18: у каждой карточки ровно один статус, у рецепта один итоговый статус
- #19: советы врача лежат в advice и не попадают в карточки лекарств
"""

import csv
import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ai.reader import _parse_answer
from drugs.search import CSV_PATH
from drugs.status import (
    ALL_FOUND, DRUG_STATUSES, FOUND, NONE_FOUND, NOT_IN_DIRECTORY,
    PARTLY_FOUND, RECIPE_STATUSES, UNSURE,
)
from main import app

client = TestClient(app)


def drug(name, form=None, sure=True):
    """Лекарство в том виде, как его возвращает reader.py."""
    return {"name": name, "form": form, "dose": "по 1", "frequency": "2 раза в день",
            "duration": "5 дней", "sure": sure}


# Тестовые рецепты: что «прочитал» Gemini. Это не настоящие рецепты, а придуманные.
RECIPES = {
    # рецепт из живого теста 16.11: всё должно найтись
    "all_found": {
        "drugs": [
            drug("Фурацилин", "раствор 0.02%"),
            drug("Беродуал", "раствор для ингаляций"),
            drug("Реглан"),
            drug("Аквалор софт душ"),
        ],
        "advice": ["Пить много тёплой воды", "Полоскать горло после еды"],
        "expected": {"Фурацилин": FOUND, "Беродуал": FOUND, "Реглан": FOUND,
                     "Аквалор софт душ": FOUND},
        "recipe_status": ALL_FOUND,
    },
    # часть нашлась, часть нет
    "partly_found": {
        "drugs": [
            drug("Реглан"),
            drug("Азотроп", "капли", sure=False),      # похоже на «Атропин»
            drug("Qxzvwjkp"),                          # бессмыслица
            drug("Фурацилин", sure=False),             # в справочнике есть, но AI не уверен
        ],
        "advice": ["Не гулять 3 дня"],
        "expected": {"Реглан": FOUND, "Азотроп": UNSURE, "Qxzvwjkp": NOT_IN_DIRECTORY,
                     "Фурацилин": UNSURE},
        "recipe_status": PARTLY_FOUND,
    },
    # ничего не нашлось
    "none_found": {
        "drugs": [drug("Азотроп", "капли", sure=False), drug("Qxzvwjkp")],
        "advice": [],
        "expected": {"Азотроп": UNSURE, "Qxzvwjkp": NOT_IN_DIRECTORY},
        "recipe_status": NONE_FOUND,
    },
    # на фото только советы, лекарств нет
    "only_advice": {
        "drugs": [],
        "advice": ["Тёплое питьё", "Постельный режим"],
        "expected": {},
        "recipe_status": NONE_FOUND,
    },
}


def post_recipe(recipe, lang="ru"):
    """Отправляет фото-пустышку в API, а Gemini подменяем готовым ответом."""
    answer = {"drugs": recipe["drugs"], "advice": recipe["advice"]}
    with patch("main.read_prescription", return_value=answer):
        photo = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"0" * 50)
        response = client.post(
            "/api/read",
            files={"photo": ("recept.jpg", photo, "image/jpeg")},
            data={"lang": lang},
        )
    assert response.status_code == 200
    return response.json()


# ── #18: один статус ──────────────────────────────────────────────────

@pytest.mark.parametrize("key", RECIPES)
def test_every_card_has_exactly_one_status(key):
    data = post_recipe(RECIPES[key])
    assert len(data["drugs"]) == len(RECIPES[key]["drugs"])

    for card in data["drugs"]:
        # статус один и взят из фиксированного списка
        assert isinstance(card["status"], str)
        assert card["status"] in DRUG_STATUSES

        # статус совпадает с ожидаемым для этого лекарства
        assert card["status"] == RECIPES[key]["expected"][card["name"]]


@pytest.mark.parametrize("key", RECIPES)
def test_recipe_has_one_final_status(key):
    data = post_recipe(RECIPES[key])
    assert data["recipe_status"] in RECIPE_STATUSES
    assert data["recipe_status"] == RECIPES[key]["recipe_status"]


@pytest.mark.parametrize("key", RECIPES)
def test_no_contradictions_on_cards(key):
    # «Найдено» и «не уверен / нет в справочнике» одновременно быть не может
    for card in post_recipe(RECIPES[key])["drugs"]:
        if card["status"] == FOUND:
            assert card["match"] is not None
            assert card["note"] is None          # предупреждения нет
            assert card["sure"] is True           # AI тоже прочитал уверенно
            assert card["indication"]
        else:
            assert card["match"] is None
            assert card["note"]                    # есть объяснение для человека
            assert card["price_kzt"] is None       # цену и аналоги не выдумываем
            assert card["analogs"] == []

        if card["status"] == UNSURE:
            assert "возможно это" in card["note"]
        if card["status"] == NOT_IN_DIRECTORY:
            assert "не найдено" in card["note"]


def test_statuses_in_kazakh_are_the_same_codes():
    # Коды статусов одинаковые на любом языке, меняется только текст note
    ru = post_recipe(RECIPES["partly_found"], "ru")
    kk = post_recipe(RECIPES["partly_found"], "kk")
    assert [c["status"] for c in ru["drugs"]] == [c["status"] for c in kk["drugs"]]
    assert ru["recipe_status"] == kk["recipe_status"]


# ── #17: справочник ───────────────────────────────────────────────────

def test_furacilin_and_berodual_solution_are_found():
    data = post_recipe(RECIPES["all_found"])
    cards = {c["name"]: c for c in data["drugs"]}

    assert cards["Фурацилин"]["status"] == FOUND
    assert cards["Беродуал"]["status"] == FOUND
    # у Беродуала две формы (аэрозоль и раствор): взялась та, что написал врач
    assert "раствор для ингаляций" in cards["Беродуал"]["form"]


def test_amoxiclav_suspension_uses_suspension_row_not_tablets():
    # Из живого теста: в рецепте суспензия, а в справочнике были только таблетки 625 мг
    recipe = {"drugs": [drug("Амоксиклав", "суспензия 228.5 мг/5 мл")], "advice": []}
    card = post_recipe(recipe)["drugs"][0]
    assert card["status"] == FOUND
    assert "суспензии 228.5" in card["form"]

    # и таблетки по-прежнему находятся как таблетки
    recipe = {"drugs": [drug("Амоксиклав", "таблетки 625 мг")], "advice": []}
    assert "таблетки 625" in post_recipe(recipe)["drugs"][0]["form"]


def test_new_drugs_from_live_test_are_in_directory():
    for name in ["Фурацилин", "Аквалор софт душ", "Реглан", "Натрия хлорид"]:
        recipe = {"drugs": [drug(name)], "advice": []}
        assert post_recipe(recipe)["drugs"][0]["status"] == FOUND, name


def test_unchecked_price_stays_empty_with_source():
    # Правило справочника: либо цена + источник, либо пустая цена и «нужно проверить».
    # Мы не выдумываем цены: у новых лекарств цена пустая.
    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) >= 130 + 15  # было 130, добавили до 20
    for row in rows:
        assert row["price_source"].strip(), row["trade_name"]       # источник есть всегда
        if not row["price_kzt"].strip():
            assert row["price_source"] == "нужно проверить"

    # API при пустой цене отдаёт price_kzt = None, а не падает
    card = post_recipe(RECIPES["all_found"])["drugs"][0]
    assert card["name"] == "Фурацилин"
    assert card["price_kzt"] is None
    assert card["price_source"] == "нужно проверить"
    for analog in card["analogs"]:
        assert analog["price_kzt"] is None or isinstance(analog["price_kzt"], int)


# ── #19: советы отдельно от лекарств ──────────────────────────────────

@pytest.mark.parametrize("key", RECIPES)
def test_advice_is_separate_from_drugs(key):
    data = post_recipe(RECIPES[key])

    assert data["advice"] == RECIPES[key]["advice"]
    assert isinstance(data["advice"], list)

    # ни один совет не стал карточкой лекарства
    card_names = {c["name"].lower() for c in data["drugs"]}
    for tip in data["advice"]:
        assert tip.lower() not in card_names

    # а тексты карточек (название, доза, форма) не повторяют советы
    for card in data["drugs"]:
        for field in ("name", "form", "dose", "frequency", "duration", "note"):
            assert card[field] not in data["advice"]


def test_warm_water_is_not_a_card():
    # Из живого теста: «пить тёплую воду» не должна становиться лекарством
    data = post_recipe(RECIPES["all_found"])
    assert len(data["drugs"]) == 4
    assert all("воды" not in c["name"].lower() for c in data["drugs"])
    assert "Пить много тёплой воды" in data["advice"]


def test_reader_removes_advice_that_repeats_a_drug():
    # Если Gemini записал одно и то же и в drugs, и в advice, в advice это не остаётся
    text = ('{"drugs": [{"name": "Фурацилин", "sure": true}],'
            ' "advice": ["фурацилин", "Тёплая вода", "тёплая вода.", "  ", 5]}')
    result = _parse_answer(text)
    assert [d["name"] for d in result["drugs"]] == ["Фурацилин"]
    assert result["advice"] == ["Тёплая вода"]   # без повторов и мусора


def test_reader_understands_old_array_format_and_missing_advice():
    # Gemini прислал массив по-старому: лекарства есть, советов нет
    assert _parse_answer('[{"name": "Реглан", "sure": true}]')["advice"] == []
    # объект без advice
    assert _parse_answer('{"drugs": []}') == {"drugs": [], "advice": []}


def test_prompt_asks_for_separate_advice():
    from ai.reader import _load_prompt
    prompt = _load_prompt()
    assert '"advice"' in prompt
    assert "тёплая вода" in prompt
