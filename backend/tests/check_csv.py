"""Проверка структуры prescriptions.csv."""
import csv

with open("tests/prescriptions.csv", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

print(f"Строк: {len(rows)} (ожидаем 30)")
print(f"Колонки: {list(rows[0].keys())}")

print("\n--- Первые 3 заполненных примера ---")
for row in rows[:3]:
    names = row["expected_names"].split(";") if row["expected_names"] else []
    doses = row["expected_doses"].split(";") if row["expected_doses"] else []
    print(f"  #{row['id']} {row['file']}: {names}")
    print(f"      дозы: {doses}")

empty = sum(1 for r in rows if not r["expected_names"])
print(f"\nПустых строк (заполнить после написания фото): {empty}")
assert len(rows) == 30, f"Должно быть 30 строк, а не {len(rows)}"
print("OK — структура корректна")
