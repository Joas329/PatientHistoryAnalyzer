# app/dates.py
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

# edad may be computed against a slightly different instant than the draw
# (order vs. collection vs. validation), so tolerate a one-year boundary slip.
_EDAD_TOLERANCE = 1

TOMA_RE = re.compile(r"Fecha\s+Toma\s+de\s+Muestra\s*[:;.]?\s*" r"(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)", re.IGNORECASE)

NACIMIENTO_RE = re.compile(r"Fe\s*\.?\s*Nac\s*[:;.]?\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE)

class DateParseError(ValueError):
    """A date field was present but could not be parsed, or was absent."""

class EdadMismatchError(ValueError):
    """Report edad disagrees with Fe.Nac in a way a date swap can't explain."""

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

def parse_nacimiento_date(text: str, source: str = "<text>") -> datetime:
    """Extract 'Fe.Nac'. Raises: an undated patient can't be age-checked."""
    m = NACIMIENTO_RE.search(text)
    if not m:
        raise DateParseError(f"{source}: no 'Fe.Nac' found")
    when = coerce_date(m.group(1))
    if when is None:
        raise DateParseError(f"{source}: unparseable birth date {m.group(1)!r}")
    return when

def _age(birth: datetime, ref: datetime) -> int:
    # full years elapsed; drop one if the birthday hasn't landed yet this ref-year
    return ref.year - birth.year - ((ref.month, ref.day) < (birth.month, birth.day))

def _reconciles(birth, ref, stated_edad):
    return _age(birth, ref) == stated_edad

def check_edad(birth: datetime, ref: datetime, stated_edad: int, src: str) -> None:
    """Cross-check report edad against Fe.Nac. Raises only on a real conflict."""
    if ref < birth:
        raise EdadMismatchError(f"{src}: sample date {ref:%d/%m/%Y} precedes "
                                f"Fe.Nac {birth:%d/%m/%Y}")
    if _reconciles(birth, ref, stated_edad):
        return
    # A genuine dd/mm inversion is only worth naming if the swap actually reconciles.
    swapped = ref.replace(month=ref.day, day=ref.month) if ref.day <= 12 else None
    if swapped and _reconciles(birth, swapped, stated_edad):
        raise EdadMismatchError(f"{src}: sample date {ref:%d/%m/%Y} looks inverted; "
                                f"{swapped:%d/%m/%Y} yields edad {stated_edad}")
    if abs(_age(birth, ref) - stated_edad) <= _EDAD_TOLERANCE:
        return  # boundary noise; edad's reference instant != the sample date
    raise EdadMismatchError(f"{src}: Fe.Nac {birth:%d/%m/%Y} yields {_age(birth, ref)}, report states edad {stated_edad}")
