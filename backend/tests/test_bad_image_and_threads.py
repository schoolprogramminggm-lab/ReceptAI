"""
tests/test_bad_image_and_threads.py:
1. Битое изображение или «не картинка» -> ответ 400 «Это не фото рецепта…» (kk/ru),
   а не «не настроен GEMINI_API_KEY».
2. Медленный вызов Gemini не блокирует сервер: пока один запрос ждёт, другие работают.

Gemini замокан, в сеть мы не ходим.

Запуск:  cd backend  ->  python -m pytest tests/test_bad_image_and_threads.py
"""

import asyncio
import io
import threading
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from ai import reader
from ai.reader import INVALID_IMAGE_MESSAGE, InvalidImageError, read_prescription
from main import app

client = TestClient(app)


def make_jpeg():
    """Настоящее маленькое JPEG-изображение."""
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), color=(120, 30, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def no_gemini(monkeypatch):
    """Ключ задан, а Gemini подменён: если до него дойдёт запрос, тест упадёт."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = AssertionError("Gemini не должен вызываться")
    monkeypatch.setattr(reader.genai, "Client", lambda api_key: fake_client)


# ---------- битое изображение ----------

def test_not_an_image_raises_invalid_image_error(monkeypatch):
    no_gemini(monkeypatch)
    with pytest.raises(InvalidImageError) as e:
        read_prescription(b"this is definitely not an image")
    assert str(e.value) == "Это не фото рецепта, выберите другое изображение"


def test_truncated_image_raises_invalid_image_error(monkeypatch):
    # Настоящая картинка, у которой отрезана половина файла
    no_gemini(monkeypatch)
    jpeg = make_jpeg()
    with pytest.raises(InvalidImageError):
        read_prescription(jpeg[: len(jpeg) // 2])


@pytest.mark.parametrize("lang, expected", [
    ("ru", "Это не фото рецепта, выберите другое изображение"),
    ("kk", INVALID_IMAGE_MESSAGE["kk"]),
])
def test_api_broken_photo_returns_400(monkeypatch, lang, expected):
    # Целиком через API, read_prescription не подменяем: именно так ловилась старая ошибка
    no_gemini(monkeypatch)
    response = client.post(
        "/api/read",
        files={"photo": ("recept.jpg", io.BytesIO(b"not an image at all"), "image/jpeg")},
        data={"lang": lang},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == expected
    assert "GEMINI_API_KEY" not in response.json()["detail"]


def test_api_missing_key_is_still_500(monkeypatch):
    # Настоящая проблема с ключом по-прежнему даёт 500 и понятное сообщение
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = client.post(
        "/api/read",
        files={"photo": ("recept.jpg", io.BytesIO(make_jpeg()), "image/jpeg")},
        data={"lang": "ru"},
    )
    assert response.status_code == 500
    assert "GEMINI_API_KEY" in response.json()["detail"]


@patch("main.read_prescription", side_effect=OSError("disk read failed"))
def test_api_other_oserror_is_not_reported_as_missing_key(mock_read):
    # Любая другая OSError — это общая ошибка 502, а не «не настроен ключ»
    response = client.post(
        "/api/read",
        files={"photo": ("recept.jpg", io.BytesIO(make_jpeg()), "image/jpeg")},
        data={"lang": "ru"},
    )
    assert response.status_code == 502
    assert "GEMINI_API_KEY" not in response.json()["detail"]
    assert "disk read failed" not in response.json()["detail"]


# ---------- сервер не блокируется ----------

def test_slow_gemini_does_not_block_server():
    # Первый запрос «зависает» в Gemini, пока мы не разрешим ему завершиться.
    # Если обработчик блокирует сервер, health-запрос не получит ответ,
    # пока первый не закончится. Тогда проверка внутри теста упадёт.
    started = threading.Event()
    release = threading.Event()

    def slow_read(image_bytes):
        started.set()
        release.wait(timeout=5)  # «ждём ответ Gemini»
        return []

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            slow_request = asyncio.create_task(
                http.post(
                    "/api/read",
                    files={"photo": ("recept.jpg", make_jpeg(), "image/jpeg")},
                    data={"lang": "ru"},
                )
            )

            # ждём, пока медленный запрос дойдёт до «Gemini»
            for _ in range(200):
                if started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert started.is_set()

            # Пока он ждёт, сервер отвечает на другие запросы
            health = await asyncio.wait_for(http.get("/api/health"), timeout=2)
            assert health.status_code == 200
            assert not slow_request.done(), "сервер был заблокирован медленным запросом"

            # Отпускаем «Gemini»: медленный запрос тоже успешно завершается
            release.set()
            slow_response = await slow_request
            assert slow_response.status_code == 200

    with patch("main.read_prescription", slow_read):
        asyncio.run(scenario())
