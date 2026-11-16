"""
tests/test_reader_timeout.py — таймаут вызова Gemini (GEMINI_TIMEOUT_SEC) и переход на запасную модель.

«Зависание» замокано: зависший вызов бросает httpx.ReadTimeout и «тратит» на это ровно
столько секунд, сколько ему разрешили (по поддельным часам). Поэтому тесты проверяют
и время, но сами выполняются мгновенно.
В конце один настоящий тест: реальная библиотека Gemini против локального сервера, который молчит.

Запуск:  cd backend  ->  python -m pytest tests/test_reader_timeout.py
"""

import io
import socket
import threading
import time
from unittest.mock import MagicMock

import httpx
import pytest
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image

from ai import reader
from ai.reader import (
    TOTAL_TIMEOUT_SEC,
    GeminiOverloadedError,
    UnreadableResponseError,
    get_call_timeout,
    read_prescription,
)

GOOD_JSON = '[{"name": "Атропин", "form": "капли", "dose": "1 капля", "sure": true}]'
GARBAGE = "Извините, я не смог прочитать этот рецепт."
MAIN_MODEL = "main-model"
FALLBACK_MODEL = "flash-lite-model"


class Hang:
    """Вызов, который зависает: тратит весь выданный ему таймаут и падает с ReadTimeout."""


class Slow:
    """Вызов, который отвечает текстом, но не сразу (тратит `seconds` секунд)."""

    def __init__(self, text, seconds):
        self.text = text
        self.seconds = seconds


def make_png():
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def error(code):
    body = {"error": {"code": code, "message": "x", "status": "UNAVAILABLE"}}
    if code >= 500:
        return genai_errors.ServerError(code, body)
    return genai_errors.ClientError(code, body)


class Setup:
    """Поддельные часы и журнал вызовов Gemini, чтобы смотреть, что и когда было вызвано."""

    def __init__(self):
        self.clock = 0.0   # «текущее время» в секундах
        self.calls = []    # [(модель, таймаут в секундах)], по порядку
        self.sleeps = []   # паузы между повторами


def fake_gemini(monkeypatch, steps, fallback=FALLBACK_MODEL, timeout_env=None):
    """
    steps — что делает каждый следующий вызов Gemini:
      Hang()         зависание (таймаут)
      Slow(text, s)  ответ текстом через s секунд
      исключение     бросается сразу (например, 503)
      строка         ответ текстом без задержки
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", MAIN_MODEL)
    if fallback:
        monkeypatch.setenv("GEMINI_FALLBACK_MODEL", fallback)
    else:
        monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)
    if timeout_env is None:
        monkeypatch.delenv("GEMINI_TIMEOUT_SEC", raising=False)
    else:
        monkeypatch.setenv("GEMINI_TIMEOUT_SEC", timeout_env)

    state = Setup()
    queue = list(steps)

    def generate_content(model, contents, config):
        # какой таймаут запросила программа (в библиотеке он в миллисекундах)
        timeout = config.http_options.timeout / 1000
        state.calls.append((model, timeout))
        step = queue.pop(0)
        if isinstance(step, Hang):
            state.clock += timeout
            raise httpx.ReadTimeout("timed out")
        if isinstance(step, Slow):
            state.clock += step.seconds
            return MagicMock(text=step.text)
        if isinstance(step, Exception):
            raise step
        return MagicMock(text=step)

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = generate_content
    monkeypatch.setattr(reader.genai, "Client", lambda api_key: fake_client)

    # поддельные часы: пауза двигает время вперёд, но ничего не ждёт
    monkeypatch.setattr(reader, "_now", lambda: state.clock)

    def fake_sleep(seconds):
        state.sleeps.append(seconds)
        state.clock += seconds

    monkeypatch.setattr(reader.time, "sleep", fake_sleep)
    return state


def models(state):
    return [model for model, _ in state.calls]


# ---------- основной сценарий ----------

def test_hang_goes_straight_to_fallback_model(monkeypatch):
    # Основная модель молчит: без повторов и пауз сразу запасная, и она отвечает
    state = fake_gemini(monkeypatch, [Hang(), GOOD_JSON])

    drugs = read_prescription(make_png())

    assert drugs[0]["name"] == "Атропин"
    assert models(state) == [MAIN_MODEL, FALLBACK_MODEL]
    assert state.sleeps == []   # повторов основной модели не было
    assert state.clock == 25    # потратили один таймаут


def test_default_timeout_is_25_seconds(monkeypatch):
    state = fake_gemini(monkeypatch, [GOOD_JSON])
    read_prescription(make_png())
    assert state.calls == [(MAIN_MODEL, 25)]


def test_both_models_hang_gives_overloaded_error(monkeypatch):
    # Зависли обе модели: понятная ошибка, и всё уложилось в 55 секунд
    state = fake_gemini(monkeypatch, [Hang(), Hang()])

    with pytest.raises(GeminiOverloadedError) as e:
        read_prescription(make_png())

    assert str(e.value) == "Сервис распознавания перегружен, попробуйте через минуту"
    assert models(state) == [MAIN_MODEL, FALLBACK_MODEL]
    assert state.clock <= TOTAL_TIMEOUT_SEC


def test_hang_without_fallback_model(monkeypatch):
    # Запасной модели в .env нет: после зависания сразу ошибка
    state = fake_gemini(monkeypatch, [Hang()], fallback="")
    with pytest.raises(GeminiOverloadedError):
        read_prescription(make_png())
    assert models(state) == [MAIN_MODEL]


def test_504_is_treated_like_a_timeout(monkeypatch):
    # Gemini сам прервал долгий запрос (504): тоже сразу запасная модель, без повторов
    state = fake_gemini(monkeypatch, [error(504), GOOD_JSON])
    assert len(read_prescription(make_png())) == 1
    assert models(state) == [MAIN_MODEL, FALLBACK_MODEL]
    assert state.sleeps == []


# ---------- настройка GEMINI_TIMEOUT_SEC ----------

def test_timeout_from_env(monkeypatch):
    state = fake_gemini(monkeypatch, [Hang(), GOOD_JSON], timeout_env="10")
    read_prescription(make_png())
    # каждый вызов получил таймаут 10 секунд
    assert state.calls == [(MAIN_MODEL, 10), (FALLBACK_MODEL, 10)]


@pytest.mark.parametrize("value", ["abc", "", "0", "-5"])
def test_bad_timeout_value_falls_back_to_default(monkeypatch, value):
    monkeypatch.setenv("GEMINI_TIMEOUT_SEC", value)
    assert get_call_timeout() == 25


# ---------- общее время не больше 55 секунд ----------

def test_total_time_is_capped_at_55_seconds(monkeypatch):
    # Худший случай: 503, 503 (паузы 2 и 4 с), потом зависание 25 с, потом зависает запасная.
    # Запасной достаётся только то, что осталось от 55 секунд: 55 - 2 - 4 - 25 = 24 с.
    state = fake_gemini(monkeypatch, [error(503), error(503), Hang(), Hang()])

    with pytest.raises(GeminiOverloadedError):
        read_prescription(make_png())

    assert state.sleeps == [2, 4]
    assert state.calls == [
        (MAIN_MODEL, 25), (MAIN_MODEL, 25), (MAIN_MODEL, 25), (FALLBACK_MODEL, 24)
    ]
    assert state.clock == TOTAL_TIMEOUT_SEC  # ровно 55, не больше


def test_huge_timeout_in_env_cannot_exceed_total_budget(monkeypatch):
    # В .env поставили 100 секунд: первый вызов всё равно получает не больше 55,
    # времени на запасную модель не остаётся, и вызывать её не нужно
    state = fake_gemini(monkeypatch, [Hang(), GOOD_JSON], timeout_env="100")

    with pytest.raises(GeminiOverloadedError):
        read_prescription(make_png())

    assert state.calls == [(MAIN_MODEL, 55)]
    assert state.clock == TOTAL_TIMEOUT_SEC


def test_no_second_json_attempt_when_time_is_up(monkeypatch):
    # Первый ответ не JSON и пришёл за 54.5 с: на повторный запрос времени нет
    state = fake_gemini(monkeypatch, [Slow(GARBAGE, 54.5), GOOD_JSON])

    with pytest.raises(UnreadableResponseError):
        read_prescription(make_png())

    assert len(state.calls) == 1


def test_json_retry_still_works_when_there_is_time(monkeypatch):
    # А если время есть, повтор из-за не-JSON ответа работает как раньше
    state = fake_gemini(monkeypatch, [Slow(GARBAGE, 5), GOOD_JSON])
    assert len(read_prescription(make_png())) == 1
    assert len(state.calls) == 2


# ---------- настоящая библиотека против «молчащего» сервера ----------

def test_real_sdk_times_out_against_silent_server(monkeypatch):
    # Локальный сервер принимает соединение и ничего не отвечает: «зависший Gemini».
    # Проверяем, что настоящая библиотека действительно обрывает запрос по нашему таймауту.
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(5)
    port = server.getsockname()[1]
    connections = []

    def accept_forever():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return  # сервер закрыт
            connections.append(conn)

    threading.Thread(target=accept_forever, daemon=True).start()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_TIMEOUT_SEC", "1")
    monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)
    # reader.genai и genai — один и тот же модуль, поэтому настоящий Client запоминаем ДО подмены
    real_client = genai.Client
    monkeypatch.setattr(
        reader.genai,
        "Client",
        lambda api_key: real_client(
            api_key=api_key,
            http_options=types.HttpOptions(base_url=f"http://127.0.0.1:{port}"),
        ),
    )

    try:
        started = time.monotonic()
        with pytest.raises(GeminiOverloadedError):
            read_prescription(make_png())
        elapsed = time.monotonic() - started
    finally:
        server.close()
        for conn in connections:
            conn.close()

    # оборвали примерно через 1 секунду (а не висели 25 или 60)
    assert 0.8 <= elapsed < 5
