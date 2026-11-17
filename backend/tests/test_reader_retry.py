"""
tests/test_reader_retry.py — один повтор запроса, если Gemini ответил не JSON.
Gemini замокан, в сеть мы не ходим.

Запуск:  cd backend  ->  python -m pytest tests/test_reader_retry.py
"""

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from ai import reader
from ai.reader import UNREADABLE_MESSAGE, UnreadableResponseError, read_prescription
from main import app

client = TestClient(app)

# Правильный ответ Gemini: одно лекарство
GOOD_JSON = '[{"name": "Атропин", "form": "капли", "dose": "1 капля", "sure": true}]'
# Мусор вместо JSON
GARBAGE = "Извините, я не смог прочитать этот рецепт."


def make_png():
    """Маленькая настоящая картинка (reader конвертирует её в JPEG)."""
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def fake_gemini(monkeypatch, answers):
    """
    Подменяет Gemini: каждый вызов generate_content возвращает следующий текст из answers.
    Возвращает fake_client, у которого можно посчитать число вызовов.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = [MagicMock(text=a) for a in answers]
    monkeypatch.setattr(reader.genai, "Client", lambda api_key: fake_client)
    return fake_client


def test_garbage_then_json_succeeds(monkeypatch):
    # Первый ответ мусор, второй JSON: повтор сработал, результат получен
    fake_client = fake_gemini(monkeypatch, [GARBAGE, GOOD_JSON])

    drugs = read_prescription(make_png())["drugs"]

    assert len(drugs) == 1
    assert drugs[0]["name"] == "Атропин"
    assert fake_client.models.generate_content.call_count == 2


def test_two_garbage_answers_raise_error(monkeypatch):
    # Оба ответа мусор: ошибка «Не удалось прочитать, переснимите рецепт»
    fake_client = fake_gemini(monkeypatch, [GARBAGE, GARBAGE])

    with pytest.raises(UnreadableResponseError) as error:
        read_prescription(make_png())

    assert str(error.value) == "Не удалось прочитать, переснимите рецепт"
    # Повтор ровно один: всего 2 запроса, третьего нет
    assert fake_client.models.generate_content.call_count == 2


def test_good_json_first_time_no_retry(monkeypatch):
    # Если JSON пришёл сразу, второй запрос не нужен
    fake_client = fake_gemini(monkeypatch, [GOOD_JSON])
    read_prescription(make_png())
    assert fake_client.models.generate_content.call_count == 1


def test_empty_array_is_not_an_error(monkeypatch):
    # «[]» — это правильный JSON («лекарств на фото нет»), повтор не нужен
    fake_client = fake_gemini(monkeypatch, ["[]"])
    assert read_prescription(make_png())["drugs"] == []
    assert fake_client.models.generate_content.call_count == 1


def test_empty_text_is_retried(monkeypatch):
    # Пустой ответ (None) тоже не JSON: повторяем
    fake_client = fake_gemini(monkeypatch, [None, GOOD_JSON])
    assert len(read_prescription(make_png())["drugs"]) == 1
    assert fake_client.models.generate_content.call_count == 2


@pytest.mark.parametrize("lang, expected", [
    ("ru", "Не удалось прочитать, переснимите рецепт"),
    ("kk", UNREADABLE_MESSAGE["kk"]),
])
@patch("main.read_prescription", side_effect=UnreadableResponseError())
def test_api_returns_message_in_user_language(mock_read, lang, expected):
    # API отвечает понятной ошибкой на языке пользователя
    photo = io.BytesIO(make_png())
    response = client.post(
        "/api/read",
        files={"photo": ("recept.png", photo, "image/png")},
        data={"lang": lang},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == expected
