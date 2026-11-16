"""
main.py — FastAPI бэкенд ReceptAI

Запуск сервера:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import logging
import os
import sys
from typing import Optional
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from ai.reader import (
    OVERLOADED_MESSAGE,
    UNREADABLE_MESSAGE,
    GeminiOverloadedError,
    UnreadableResponseError,
    read_prescription,
)
from drugs.analogs import find_analogs
from drugs.search import check_name, find_drug

# Загружаем переменные окружения (.env)
load_dotenv()

# Журнал сервера: сюда пишем подробности ошибок, пользователю они не показываются
logger = logging.getLogger("uvicorn.error")

# Сколько аналогов показываем в карточке
MAX_ANALOGS = 3

# Предупреждение на двух языках. Приложение само выбирает нужный по языку пользователя.
DISCLAIMER = {
    "kk": "Бұл дәрігер кеңесін алмастырмайды. Алмастыруды дәрігермен немесе фармацевтпен келісіңіз.",
    "ru": "Это не замена консультации врача. Замену согласуйте с врачом или фармацевтом.",
}


def make_card(read, lang):
    """
    Делает карточку лекарства из того, что прочитал AI.

    read — словарь от AI: name, form, dose, frequency, duration, sure
    Если лекарство уверенно найдено в справочнике, берём из него название, форму,
    «для чего», цену и аналоги. Если нет, цену и аналоги не показываем:
    не угадываем лекарство, а даём подсказку unsure_message.
    """
    check = check_name(read.get("name"), lang)  # match, score, note

    # Строка справочника нужна только если лекарство найдено уверенно
    row = None
    if check["match"]:
        row, _ = find_drug(read.get("name"))

    analogs = []
    if row:
        for a in find_analogs(row)[:MAX_ANALOGS]:
            analogs.append({"name": a["trade_name"], "price_kzt": int(float(a["price_kzt"]))})

    return {
        # из справочника, если нашли, иначе как прочитал AI
        "name": row["trade_name"] if row else read.get("name"),
        "form": row["form"] if row else read.get("form"),
        "indication": row["indication"] if row else None,  # «для чего»
        # «как написал врач»: ровно как прочитал AI, ничего не меняем
        "dose": read.get("dose"),
        "frequency": read.get("frequency"),
        "duration": read.get("duration"),
        "sure": read.get("sure"),
        "price_kzt": int(float(row["price_kzt"])) if row else None,
        "analogs": analogs,
        "match": check["match"],
        "score": check["score"],
        "note": check["note"],             # оставлено как раньше
        "unsure_message": check["note"],   # «Не уверен, возможно это …» (None, если всё хорошо)
    }

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
    except UnreadableResponseError:
        # Gemini дважды ответил не JSON: просим переснять рецепт (kk/ru)
        raise HTTPException(
            status_code=422,
            detail=UNREADABLE_MESSAGE["kk"] if lang == "kk" else UNREADABLE_MESSAGE["ru"],
        )
    except GeminiOverloadedError:
        # Gemini перегружен, а повторы и запасная модель не помогли
        raise HTTPException(
            status_code=503,
            detail=OVERLOADED_MESSAGE["kk"] if lang == "kk" else OVERLOADED_MESSAGE["ru"],
        )
    except Exception:
        # Любая другая ошибка (сеть, квота, регион, неверный ключ).
        # Подробности пишем только в журнал сервера, пользователю даём общий текст:
        # в сыром тексте ошибки бывают технические детали, которые ему не нужны.
        logger.exception("Ошибка распознавания рецепта")
        raise HTTPException(
            status_code=502,
            detail=(
                "Рецептті тану мүмкін болмады, қайталап көріңіз"
                if lang == "kk"
                else "Не удалось распознать рецепт, попробуйте ещё раз"
            ),
        )

    # 5. Проверяем каждое название, прочитанное AI, по справочнику
    # и делаем из него карточку: цена, «для чего», аналоги, match/score
    drugs = [make_card(drug, lang) for drug in drugs]

    # 6. Возвращаем распознанные лекарства
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

    return {
        "success": True,
        "message": message,
        "received_size_kb": round(len(image_bytes) / 1024, 1),
        "lang": lang,
        "drugs": drugs,
        "disclaimer": DISCLAIMER,  # сразу на двух языках: {"kk": ..., "ru": ...}
    }
