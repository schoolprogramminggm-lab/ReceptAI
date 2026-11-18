"""
tests/test_directory_prompt.py — справочник в промпте, read_as, выбор формы (#21).
Gemini замокан, в сеть не ходим.

Запуск:  cd backend  ->  python -m pytest tests/test_directory_prompt.py
"""

import io
from unittest.mock import MagicMock

from PIL import Image

from ai import reader
from ai.reader import _parse_answer, read_prescription
from drugs.search import all_drugs, choose_form, directory_for_prompt, find_drug
from drugs.status import FOUND, UNSURE
from main import make_card


def make_png():
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_directory_list_goes_into_prompt(monkeypatch):
    # Фейковый Gemini запоминает, что ему отправили
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = MagicMock(text='{"drugs": [], "advice": []}')
    monkeypatch.setattr(reader.genai, "Client", lambda api_key: fake_client)

    read_prescription(make_png())

    # contents = [картинка, текст промпта]
    sent_prompt = fake_client.models.generate_content.call_args.kwargs["contents"][1]
    assert reader.DRUG_LIST_MARK not in sent_prompt  # метка заменена списком
    # каждая строка справочника (название, МНН, форма) есть в промпте
    for d in all_drugs():
        assert f"{d['trade_name']} | {d['inn']} | {d['form']}" in sent_prompt
    # обе формы Амоксиклава видны модели
    assert "Амоксиклав | амоксициллин + клавулановая кислота | таблетки 625 мг" in sent_prompt
    assert "порошок для суспензии 228.5 мг/5 мл" in sent_prompt


def test_directory_list_has_one_line_per_drug():
    assert len(directory_for_prompt().splitlines()) == len(all_drugs())


def test_read_as_is_saved():
    answer = ('{"drugs": [{"name": "Амоксиклав", "read_as": "Жлавол", '
              '"form": "суспензия 228.5 мг/5 мл", "sure": false}], "advice": []}')
    drug = _parse_answer(answer)["drugs"][0]
    assert drug["name"] == "Амоксиклав"
    assert drug["read_as"] == "Жлавол"


def test_read_as_defaults_to_name():
    # модель не прислала read_as (или прислала пустым): считаем, что прочитано то же
    answer = '{"drugs": [{"name": "Атропин", "sure": true}, {"name": "Икс", "read_as": " "}]}'
    drugs = _parse_answer(answer)["drugs"]
    assert drugs[0]["read_as"] == "Атропин"
    assert drugs[1]["read_as"] == "Икс"


def test_card_returns_read_as():
    card = make_card({"name": "Фурацилин", "read_as": "Фуроцилин", "sure": True}, "ru")
    assert card["status"] == FOUND
    assert card["name"] == "Фурацилин"
    assert card["read_as"] == "Фуроцилин"  # приложение покажет «в рецепте написано: …»


def test_weak_replacement_is_unsure():
    # AI подставил «Амоксиклав», хотя написано «Жлавол», и сам поставил sure=true:
    # сервер не верит такой замене
    card = make_card({"name": "Амоксиклав", "read_as": "Жлавол", "sure": True}, "ru")
    assert card["status"] == UNSURE
    assert "Амоксиклав" in card["note"]
    assert card["price_kzt"] is None


def test_long_read_as_with_the_name_inside_is_not_weak():
    # AI записал в read_as целую фразу, но название внутри неё есть: это не слабая замена
    card = make_card(
        {"name": "Натрия хлорид", "read_as": "раствором натрия хлорида 0,9%", "sure": True}, "ru")
    assert card["status"] == FOUND


def test_choose_form_between_two_candidates():
    # у Амоксиклава две строки: таблетки и суспензия
    drug, _ = find_drug("Амоксиклав")
    suspension = choose_form(drug, "суспензия 228.5 мг/5 мл")
    tablets = choose_form(drug, "таблетки 625 мг")
    assert "суспензии" in suspension["form"]
    assert tablets["form"] == "таблетки 625 мг"


def test_card_picks_suspension_form():
    card = make_card(
        {"name": "Амоксиклав", "read_as": "Амоксиклав", "form": "суспензия 228.5 мг/5 мл",
         "sure": True}, "ru")
    assert card["status"] == FOUND
    assert "суспензии" in card["form"]
