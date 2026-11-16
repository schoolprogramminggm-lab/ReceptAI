"""
tests/test_reader_overload.py — перегрузка Gemini (503/429): повторы, запасная модель, понятные сообщения.
Gemini замокан, паузы (time.sleep) подменены, в сеть мы не ходим и ничего не ждём.

Запуск:  cd backend  ->  python -m pytest tests/test_reader_overload.py
"""

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors
from PIL import Image

from ai import reader
from ai.reader import GeminiOverloadedError, OVERLOADED_MESSAGE, read_prescription
from main import app

client = TestClient(app)

GOOD_JSON = '[{"name": "Атропин", "form": "капли", "dose": "1 капля", "sure": true}]'
MAIN_MODEL = "main-model"
FALLBACK_MODEL = "fallback-model"


def make_png():
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def error(code):
    """Ошибка Gemini с нужным кодом (503 — перегрузка, 429 — лимит, 400 — плохой запрос)."""
    body = {"error": {"code": code, "message": "high demand", "status": "UNAVAILABLE"}}
    if code >= 500:
        return genai_errors.ServerError(code, body)
    return genai_errors.ClientError(code, body)


def fake_gemini(monkeypatch, steps, fallback=FALLBACK_MODEL):
    """
    Подменяет Gemini. steps — что вернёт каждый следующий вызов:
    ошибка (бросается) или текст ответа.
    Возвращает (fake_client, sleeps): sleeps — список «пауз», которые сделал бы сервер.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", MAIN_MODEL)
    if fallback:
        monkeypatch.setenv("GEMINI_FALLBACK_MODEL", fallback)
    else:
        monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)

    answers = [s if isinstance(s, Exception) else MagicMock(text=s) for s in steps]
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = answers
    monkeypatch.setattr(reader.genai, "Client", lambda api_key: fake_client)

    sleeps = []
    monkeypatch.setattr(reader.time, "sleep", lambda seconds: sleeps.append(seconds))
    return fake_client, sleeps


def models_used(fake_client):
    """Какие модели были запрошены, по порядку."""
    return [call.kwargs["model"] for call in fake_client.models.generate_content.call_args_list]


def test_503_503_then_success(monkeypatch):
    # Два раза 503, на третьей попытке успех: паузы 2 и 4 секунды, запасная модель не нужна
    fake_client, sleeps = fake_gemini(monkeypatch, [error(503), error(503), GOOD_JSON])

    drugs = read_prescription(make_png())

    assert drugs[0]["name"] == "Атропин"
    assert models_used(fake_client) == [MAIN_MODEL] * 3
    assert sleeps == [2, 4]


def test_429_is_retried_like_503(monkeypatch):
    # 429 (лимит запросов) обрабатывается так же, как 503
    fake_client, sleeps = fake_gemini(monkeypatch, [error(429), GOOD_JSON])
    assert len(read_prescription(make_png())) == 1
    assert models_used(fake_client) == [MAIN_MODEL] * 2
    assert sleeps == [2]


def test_503_all_the_time_uses_fallback_model(monkeypatch):
    # Основная модель 3 раза подряд 503: один раз пробуем запасную, и она отвечает
    fake_client, sleeps = fake_gemini(
        monkeypatch, [error(503), error(503), error(503), GOOD_JSON]
    )

    drugs = read_prescription(make_png())

    assert drugs[0]["name"] == "Атропин"
    assert models_used(fake_client) == [MAIN_MODEL] * 3 + [FALLBACK_MODEL]
    assert sleeps == [2, 4]  # после третьей попытки пауза не нужна


def test_everything_failed_gives_overloaded_error(monkeypatch):
    # И основная, и запасная модель перегружены: понятная ошибка, ровно 4 запроса
    fake_client, sleeps = fake_gemini(monkeypatch, [error(503)] * 4)

    with pytest.raises(GeminiOverloadedError) as e:
        read_prescription(make_png())

    assert str(e.value) == "Сервис распознавания перегружен, попробуйте через минуту"
    assert models_used(fake_client) == [MAIN_MODEL] * 3 + [FALLBACK_MODEL]


def test_no_fallback_model_configured(monkeypatch):
    # Запасная модель не задана в .env: после трёх попыток сразу ошибка
    fake_client, sleeps = fake_gemini(monkeypatch, [error(503)] * 3, fallback="")

    with pytest.raises(GeminiOverloadedError):
        read_prescription(make_png())

    assert models_used(fake_client) == [MAIN_MODEL] * 3


def test_other_errors_are_not_retried(monkeypatch):
    # Ошибка 400 — это не перегрузка: повторять бессмысленно, ошибка уходит наверх сразу
    fake_client, sleeps = fake_gemini(monkeypatch, [error(400)])

    with pytest.raises(genai_errors.ClientError):
        read_prescription(make_png())

    assert models_used(fake_client) == [MAIN_MODEL]
    assert sleeps == []


@pytest.mark.parametrize("lang, expected", [
    ("ru", "Сервис распознавания перегружен, попробуйте через минуту"),
    ("kk", OVERLOADED_MESSAGE["kk"]),
])
@patch("main.read_prescription", side_effect=GeminiOverloadedError())
def test_api_overloaded_returns_503(mock_read, lang, expected):
    # API отвечает кодом 503 и понятным текстом на языке пользователя
    response = client.post(
        "/api/read",
        files={"photo": ("recept.png", io.BytesIO(make_png()), "image/png")},
        data={"lang": lang},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == expected


@pytest.mark.parametrize("lang", ["ru", "kk"])
@patch("main.read_prescription")
def test_api_never_shows_raw_error_text(mock_read, lang):
    # Неизвестная ошибка: пользователь не видит ни текста ошибки, ни технических деталей
    mock_read.side_effect = RuntimeError("secret internals: key=AIza123 host=10.0.0.5")

    response = client.post(
        "/api/read",
        files={"photo": ("recept.png", io.BytesIO(make_png()), "image/png")},
        data={"lang": lang},
    )
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "secret" not in detail and "AIza123" not in detail and "10.0.0.5" not in detail
    assert "RuntimeError" not in detail
    assert detail  # понятный текст есть


@patch("main.read_prescription")
def test_api_raw_gemini_json_is_hidden(mock_read):
    # Ровно ситуация из живого теста: сырая ошибка Gemini 503 не попадает в ответ
    mock_read.side_effect = error(500)
    response = client.post(
        "/api/read",
        files={"photo": ("recept.png", io.BytesIO(make_png()), "image/png")},
        data={"lang": "ru"},
    )
    assert response.status_code == 502
    assert "UNAVAILABLE" not in response.json()["detail"]
    assert "high demand" not in response.json()["detail"]
