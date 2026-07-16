import re
from enum import StrEnum


class VatMode(StrEnum):
    EXCLUSIVE = "exclusive"  # таблиця без ПДВ, ПДВ додається нижче
    INCLUSIVE = "inclusive"  # таблиця вже з ПДВ
    NONE = "none"            # документ без ПДВ
    UNKNOWN = "unknown"      # не вдалося визначити


def detect_vat_mode(text: str) -> VatMode:
    normalized = re.sub(r"\s+", " ", text).lower()

    inclusive_markers = (
        "ціна з пдв",
        "сума з пдв",
        "цена с ндс",
        "сумма с ндс",
    )

    exclusive_markers = (
        "ціна без пдв",
        "сума без пдв",
        "цена без ндс",
        "сумма без ндс",
    )

    no_vat_markers = (
        "не є платником пдв",
        "без пдв згідно",
        "пдв не передбачено",
        "не оподатковується пдв",
    )

    if any(marker in normalized for marker in inclusive_markers):
        return VatMode.INCLUSIVE

    if any(marker in normalized for marker in exclusive_markers):
        return VatMode.EXCLUSIVE

    if any(marker in normalized for marker in no_vat_markers):
        return VatMode.NONE

    return VatMode.UNKNOWN