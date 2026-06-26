import re
from datetime import datetime, timedelta, timezone

LATIN_TO_CYRILLIC = str.maketrans(
    "ABEKMHOPCTYX",
    "АВЕКМНОРСТУХ",
)


# Russian plate patterns: А123ВС77, В456КХ199, etc.
RU_PLATE_PATTERN = re.compile(
    r"^[АВЕКМНОРСТУХ]\d{3}[АВЕКМНОРСТУХ]{2}\d{2,3}$"
)


def normalize_plate(raw: str) -> str:
    plate = raw.upper().strip().replace(" ", "").replace("-", "")
    plate = plate.translate(LATIN_TO_CYRILLIC)
    return plate


def is_valid_ru_plate(plate: str) -> bool:
    return bool(RU_PLATE_PATTERN.match(plate))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
