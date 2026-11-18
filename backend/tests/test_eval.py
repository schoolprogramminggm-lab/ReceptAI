"""
tests/test_eval.py — eval.py считает точность на двух искусственных рецептах.
Gemini не вызывается: read_prescription подменена.

Запуск:  cd backend  ->  python -m pytest tests/test_eval.py
"""

import eval as accuracy  # файл backend/eval.py


def fake_reader(answers):
    """Возвращает функцию-замену read_prescription: отдаёт ответы по очереди."""
    answers = iter(answers)
    return lambda image_bytes: {"drugs": next(answers), "advice": []}


def test_accuracy_on_two_prescriptions(tmp_path, monkeypatch):
    # CSV с тремя рецептами: два с фото, третий без фото
    csv_path = tmp_path / "prescriptions.csv"
    csv_path.write_text(
        "id,file,expected_names,expected_doses,notes\n"
        "1,a.jpg,Атропин,,\n"
        "2,b.jpg,Амоксициллин;Ибупрофен,,\n"
        "3,c.jpg,Метформин,,\n",
        encoding="utf-8",
    )
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.jpg").write_bytes(b"x")

    # Рецепт 1: Атропин найден. Рецепт 2: Амоксициллин верно, Ибупрофен прочитан как Жлавол
    monkeypatch.setattr(accuracy, "read_prescription", fake_reader([
        [{"name": "Атропин", "read_as": "Атропин", "sure": True}],
        [{"name": "Амоксициллин", "read_as": "Амоксициллин", "sure": True},
         {"name": "Жлавол", "read_as": "Жлавол", "sure": False}],
    ]))

    results, no_photo, no_answer = accuracy.run(csv_path, tmp_path)

    assert no_photo == 1  # рецепт 3 без фото пропущен
    assert no_answer == 0
    assert [r["correct"] for r in results] == [1, 1]
    assert results[0]["statuses"] == ["found"]
    assert results[1]["statuses"][0] == "found"
    assert results[1]["extra"] == ["жлавол"]  # лишнее название

    total = accuracy.summarize(results)
    assert total["expected_total"] == 3
    assert total["correct_total"] == 2
    assert total["percent"] == 66.7
    assert total["extra_total"] == 1

    # таблица содержит модель, процент и строки рецептов
    text = accuracy.make_markdown(results, total, no_photo, no_answer, "test-model")
    assert "test-model" in text
    assert "66.7%" in text
    assert "a.jpg" in text and "b.jpg" in text
    assert "c.jpg" not in text


def test_row_without_expected_names_is_skipped(tmp_path):
    csv_path = tmp_path / "prescriptions.csv"
    csv_path.write_text(
        "id,file,expected_names,expected_doses,notes\n4,d.jpg,,,заполнить\n", encoding="utf-8")
    (tmp_path / "d.jpg").write_bytes(b"x")

    results, no_photo, no_answer = accuracy.run(csv_path, tmp_path)

    assert results == [] and no_photo == 0 and no_answer == 1
