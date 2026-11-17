"""
Тестирование эндпоинтов бэкенда FastAPI:
- GET /api/health
- POST /api/read (с моком Gemini reader и проверкой структуры ответа)
- Проверка разделения полей (form, dose, frequency, duration)
- Карточки лекарств: цена, аналоги, «как написал врач», disclaimer на kk и ru
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
    # «натрия хлорид» есть в справочнике, поэтому название приходит оттуда (с большой буквы)
    assert drug["name"].lower() == "натрия хлорид"
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


@patch("main.read_prescription")
def test_read_prescription_adds_match_and_score(mock_read):
    # AI прочитал три названия: с опечаткой, сомнительное и бессмыслицу.
    # Сервер должен проверить их по справочнику и добавить match, score, note.
    mock_read.return_value = [
        {"name": "Амоксицилин", "form": "капсулы", "dose": None,
         "frequency": None, "duration": None, "sure": True},
        {"name": "Азотроп", "form": "капли", "dose": None,
         "frequency": None, "duration": None, "sure": False},
        {"name": "Кшфгх", "form": None, "dose": None,
         "frequency": None, "duration": None, "sure": False},
    ]

    dummy_image = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"0" * 50)
    response = client.post(
        "/api/read",
        files={"photo": ("recept.jpg", dummy_image, "image/jpeg")},
        data={"lang": "ru"},
    )
    assert response.status_code == 200
    found, unsure, nonsense = response.json()["drugs"]

    # Уверенно найдено: название из справочника, предупреждения нет
    assert found["match"] == "Амоксициллин"
    assert found["score"] >= 85
    assert found["note"] is None

    # Ниже порога: match пустой, но есть подсказка «возможно это …»
    assert unsure["match"] is None
    assert "Не уверен, возможно это «Атропин»" in unsure["note"]

    # Бессмыслица: не найдено
    assert nonsense["match"] is None
    assert nonsense["score"] < 85


@patch("main.read_prescription")
def test_read_prescription_two_drug_cards(mock_read):
    # Рецепт с двумя лекарствами. Gemini замокан, в сеть мы не ходим.
    # Дозу, схему и курс пишем «неаккуратно»: сервер должен вернуть их без изменений.
    mock_read.return_value = [
        {"name": "Азитромицин", "form": "капс.", "dose": "по 1  капс.",
         "frequency": "1 р/д  утром", "duration": "3 дн.", "sure": True},
        {"name": "Амоксиклав", "form": "таб.", "dose": "625 мг",
         "frequency": "2 раза в день", "duration": "7 дней", "sure": True},
    ]

    dummy_image = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"0" * 50)
    response = client.post(
        "/api/read",
        files={"photo": ("recept.jpg", dummy_image, "image/jpeg")},
        data={"lang": "ru"},
    )
    assert response.status_code == 200
    data = response.json()

    # Две карточки
    cards = data["drugs"]
    assert len(cards) == 2

    for card in cards:
        # название из справочника, «для чего» и цена
        assert card["match"] is not None
        assert card["name"] == card["match"]
        assert card["indication"]
        assert isinstance(card["price_kzt"], int) and card["price_kzt"] > 0
        assert card["note"] is None
        assert card["status"] == "found"

        # аналоги: от 1 до 3, у каждого название и цена, по возрастанию цены
        assert 1 <= len(card["analogs"]) <= 3
        for analog in card["analogs"]:
            assert analog["name"] != card["name"]
            assert isinstance(analog["price_kzt"], int)
        prices = [a["price_kzt"] for a in card["analogs"]]
        assert prices == sorted(prices)

    # «Как написал врач»: ровно как прочитал AI
    assert cards[0]["dose"] == "по 1  капс."
    assert cards[0]["frequency"] == "1 р/д  утром"
    assert cards[0]["duration"] == "3 дн."
    assert cards[1]["dose"] == "625 мг"
    assert cards[1]["frequency"] == "2 раза в день"
    assert cards[1]["duration"] == "7 дней"

    # Предупреждение на двух языках
    assert "Замену согласуйте с врачом или фармацевтом" in data["disclaimer"]["ru"]
    assert data["disclaimer"]["kk"]


@patch("main.read_prescription")
def test_unsure_card_has_no_price_and_analogs(mock_read):
    # Название не уверенно найдено в справочнике: цену и аналоги не показываем,
    # а даём подсказку в поле note
    mock_read.return_value = [
        {"name": "Азотроп", "form": "капли", "dose": "1 капля",
         "frequency": "2 раза в день", "duration": "7 дней", "sure": False},
    ]

    dummy_image = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"0" * 50)
    response = client.post(
        "/api/read",
        files={"photo": ("recept.jpg", dummy_image, "image/jpeg")},
        data={"lang": "ru"},
    )
    card = response.json()["drugs"][0]
    assert card["name"] == "Азотроп"            # остаётся как прочитал AI
    assert card["match"] is None
    assert card["price_kzt"] is None
    assert card["analogs"] == []
    assert card["status"] == "unsure"
    assert "Не уверен, возможно это" in card["note"]
    assert card["dose"] == "1 капля"
