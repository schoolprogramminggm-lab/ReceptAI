"""
Тестирование эндпоинтов бэкенда FastAPI:
- GET /api/health
- POST /api/read (с моком Gemini reader и проверкой структуры ответа)
- Проверка разделения полей (form, dose, frequency, duration)
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
    # Мокируем ответ от Gemini reader с детальным разделением полей
    mock_read.return_value = [
        {
            "name": "натрия хлорид",
            "form": "раствор 0.9%",
            "dose": "по 2 капли в оба глаза",
            "frequency": "форсаж: каждые 5 минут в течение 30 минут, 2 раза в день",
            "duration": "3 дня",
            "sure": True,
        },
        {
            "name": "неразборчиво",
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

    # Проверка разделения полей первого лекарства
    drug = data["drugs"][0]
    assert drug["name"] == "натрия хлорид"
    assert drug["form"] == "раствор 0.9%"
    assert drug["dose"] == "по 2 капли в оба глаза"
    assert "каждые 5 минут" in drug["frequency"]
    assert drug["duration"] == "3 дня"
    assert drug["sure"] is True

    # Проверка неуверенного распознавания
    unsure_drug = data["drugs"][1]
    assert unsure_drug["sure"] is False
    assert unsure_drug["dose"] is None
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
