"""
Тестирование эндпоинтов бэкенда FastAPI:
- GET /api/health
- POST /api/read (с моком Gemini reader и проверкой структуры ответа)
"""

import io
from unittest.mock import patch
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


@patch("main.read_prescription")
def test_read_prescription_success(mock_read):
    # Мокируем ответ от Gemini reader
    mock_read.return_value = [
        {
            "name": "Атропин",
            "form": "капли глазные 1%",
            "dose": "1 капля",
            "frequency": "2 раза в день",
            "duration": "7 дней",
            "sure": True,
        },
        {
            "name": "Азотроп",
            "form": "таблетки",
            "dose": None,
            "frequency": None,
            "duration": None,
            "sure": False,
        },
    ]

    dummy_image = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"0" * 50)
    response = client.post(
        "/api/read",
        files={"photo": ("recept.jpg", dummy_image, "image/jpeg")},
        data={"lang": "ru"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["drugs"]) == 2
    assert data["drugs"][0]["name"] == "Атропин"
    assert data["drugs"][0]["sure"] is True
    assert data["drugs"][1]["sure"] is False
    assert data["drugs"][1]["dose"] is None
    assert "disclaimer" in data


@patch("main.read_prescription")
def test_read_prescription_empty_result(mock_read):
    # Модель не нашла лекарств (пустой список)
    mock_read.return_value = []

    dummy_image = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"0" * 50)
    response = client.post(
        "/api/read",
        files={"photo": ("empty.jpg", dummy_image, "image/jpeg")},
        data={"lang": "kk"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["drugs"] == []
    assert "рецепт немесе дәрі анықталмады" in data["message"]


def test_read_prescription_unsupported_ext():
    dummy_file = io.BytesIO(b"dummy pdf content")
    response = client.post(
        "/api/read",
        files={"photo": ("document.pdf", dummy_file, "application/pdf")},
        data={"lang": "ru"},
    )
    assert response.status_code == 400
