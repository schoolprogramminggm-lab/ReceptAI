"""
drugs/status.py — статусы карточек лекарств и всего рецепта.

У каждой карточки лекарства РОВНО ОДИН статус из трёх.
У всего рецепта тоже ровно один итоговый статус из трёх.
Строки ниже — единственное место, где они записаны; в README они продублированы для людей.
"""

# ── Статус одной карточки ─────────────────────────────────────────────
FOUND = "found"                      # найдено в справочнике, AI тоже прочитал уверенно
UNSURE = "unsure"                    # «Не уверен, возможно это …»
NOT_IN_DIRECTORY = "not_in_directory"  # нет в справочнике — уточните у врача

DRUG_STATUSES = (FOUND, UNSURE, NOT_IN_DIRECTORY)

# ── Итоговый статус рецепта ───────────────────────────────────────────
ALL_FOUND = "all_found"        # все карточки со статусом found
PARTLY_FOUND = "partly_found"  # часть карточек found, часть нет
NONE_FOUND = "none_found"      # ни одной found (в том числе когда лекарств нет совсем)

RECIPE_STATUSES = (ALL_FOUND, PARTLY_FOUND, NONE_FOUND)


def recipe_status(cards):
    """Считает итоговый статус рецепта по статусам карточек."""
    found = sum(1 for card in cards if card["status"] == FOUND)
    if found == 0:
        return NONE_FOUND
    if found == len(cards):
        return ALL_FOUND
    return PARTLY_FOUND
