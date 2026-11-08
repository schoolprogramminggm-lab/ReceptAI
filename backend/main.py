"""
main.py — FastAPI бэкенд ReceptAI

Запуск сервера:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import sys
from typing import Optional
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from ai.reader import read_prescription

# Загружаем переменные окружения (.env)
load_dotenv()

app = FastAPI(
    title="ReceptAI API",
    description="API для распознавания рецептов врача и поиска аналогов лекарств",
    version="0.2.0",
)

# Разрешаем CORS, чтобы мобильное приложение Expo могло слать запросы
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Лимит размера файла: 8 МБ
MAX_PHOTO_SIZE = 8 * 1024 * 1024


@app.get("/api/health")
def health_check():
    """
    Проверка работоспособности сервера.
    Используется мобильным приложением для быстрой проверки связи.
    """
    return {
        "status": "ok",
        "app": "ReceptAI",
        "message": "Сервер работает нормально / Сервер қалыпты жұмыс істеп тұр",
    }


@app.post("/api/read")
async def read_prescription_endpoint(
    photo: UploadFile = File(...),
    lang: Optional[str] = Form("ru"),
):
    """
    Приём фотографии рецепта на распознавание через Gemini AI.

    Входные параметры:
        photo: файл изображения (jpg, png, heic)
        lang: язык ответа ('kk' или 'ru')
    """
    # 1. Считываем файл напрямую в память
    image_bytes = await photo.read()

    # 2. Проверяем размер
    if len(image_bytes) > MAX_PHOTO_SIZE:
        raise HTTPException(
            status_code=400,
            detail=(
                "Фото тым үлкен (8 МБ аспауы керек)"
                if lang == "kk"
                else "Фотография слишком большая (максимум 8 МБ)"
            ),
        )

    # 3. Базовая валидация расширения/MIME типа
    filename = (photo.filename or "").lower()
    allowed_exts = (".jpg", ".jpeg", ".png", ".heic")
    if filename and not filename.endswith(allowed_exts):
        raise HTTPException(
            status_code=400,
            detail=(
                "Қолдау көрсетілмейтін пішім (тек JPG, PNG, HEIC)"
                if lang == "kk"
                else "Неподдерживаемый формат (только JPG, PNG, HEIC)"
            ),
        )

    # 4. Отправляем в Gemini AI на чтение рукописного текста
    try:
        drugs = read_prescription(image_bytes)
    except EnvironmentError as e:
        # Не настроен API-ключ на сервере
        raise HTTPException(
            status_code=500,
            detail=(
                "Серверде Gemini API кілті бапталмаған"
                if lang == "kk"
                else "На сервере не настроен GEMINI_API_KEY"
            ),
        )
    except Exception as e:
        # Ошибка сети / квоты / региона
        error_msg = str(e)
        detail_msg = (
            f"Рецептті тану кезінде қате орын алды: {error_msg}"
            if lang == "kk"
            else f"Ошибка распознавания рецепта нейросетью: {error_msg}"
        )
        raise HTTPException(status_code=502, detail=detail_msg)

    # 5. Возвращаем распознанные лекарства
    message = (
        f"Рецепт сәтті танылды! {len(drugs)} дәрі табылды."
        if lang == "kk"
        else f"Рецепт успешно распознан! Найдено лекарств: {len(drugs)}."
    )

    if not drugs:
        message = (
            "Суреттен рецепт немесе дәрі анықталмады. Басқа анық суретті байқап көріңіз."
            if lang == "kk"
            else "На фото не найдено лекарств или почерк не удалось разобрать. Попробуйте более четкое фото."
        )

    disclaimer = (
        "Бұл дәрігер кеңесін алмастырмайды. Дәрі-дәрмекті қабылдамас бұрын маманмен кеңесіңіз."
        if lang == "kk"
        else "Это не замена консультации врача. Обязательно уточните у врача или фармацевта."
    )

    return {
        "success": True,
        "message": message,
        "received_size_kb": round(len(image_bytes) / 1024, 1),
        "lang": lang,
        "drugs": drugs,
        "disclaimer": disclaimer,
    }
