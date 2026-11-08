"""
Тестирование эндпоинтов бэкенда FastAPI:
- GET /api/health
- POST /api/read (с валидным файлом и проверкой ответа)
"""

import io
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "ReceptAI"


def test_read_prescription_stub():
    # Создаём фейковое изображение в памяти
    dummy_image = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"0" * 50)

    response = client.post(
        "/api/read",
        files={"photo": ("test_recept.jpg", dummy_image, "image/jpeg")},
        data={"lang": "ru"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "received_size_kb" in data
    assert len(data["drugs"]) > 0
    assert "disclaimer" in data


def test_read_prescription_unsupported_ext():
    dummy_file = io.BytesIO(b"random text")
    response = client.post(
        "/api/read",
        files={"photo": ("document.pdf", dummy_file, "application/pdf")},
        data={"lang": "ru"},
    )
    assert response.status_code == 400
