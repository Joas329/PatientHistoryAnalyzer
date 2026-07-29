# app/dates.py
"""Date parsing shared by the PDF reader and the UI.

Lives outside both so the parser never imports Qt and the UI never imports fitz.
"""

from __future__ import annotations

import re
from datetime import date, datetime

# Peruvian reports are dd/mm/yyyy. ISO first (unambiguous), then day-first.
# Longest variants before shorter ones: strptime is greedy per-format, not global.
_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
    "%d-%m-%Y %H:%M:%S", "%d-%m-%Y",
    "%d/%m/%y %H:%M:%S", "%d/%m/%y",
)

TOMA_RE = re.compile(
    r"Fecha\s+Toma\s+de\s+Muestra\s*[:;.]?\s*"
    r"(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)",
    re.IGNORECASE,
)

NACIMIENTO_RE = re.compile(
    r"Fe\s*\.?\s*Nac\s*[:;.]?\s*(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)

class DateParseError(ValueError):
    """A date field was present but could not be parsed, or was absent."""


def coerce_date(value) -> datetime | None:
    """Best-effort parse. Returns None rather than guessing wrong."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        s = value.strip()
        for fmt in _FORMATS:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


def parse_toma_datetime(text: str, source: str = "<text>") -> datetime:
    """Extract 'Fecha Toma de Muestra'. Raises: an undated draw is unusable."""
    m = TOMA_RE.search(text)
    if not m:
        raise DateParseError(f"{source}: no 'Fecha Toma de Muestra' found")
    when = coerce_date(m.group(1))
    if when is None:
        raise DateParseError(f"{source}: unparseable sample date {m.group(1)!r}")
    return when


def check_edad(fecha_nacimiento: datetime, edad: int, on: datetime) -> bool:
    """Cross-check dd/mm vs mm/dd: does the birth date actually yield `edad`?"""
    years = on.year - fecha_nacimiento.year - (
        (on.month, on.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
    )
    return years == edad