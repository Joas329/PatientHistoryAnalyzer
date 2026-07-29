"""Immutable DTOs for flagged clinical events.

An Event is an audit record, not a verdict. It always carries the raw value
and the range it was judged against, so a grade can be re-derived if the
reference ranges or the CTCAE version change. Grades are a lossy projection;
raw values are not recoverable from them.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime

# Event.status values
GRADED = "graded" # a CTCAE grade >= 1 was derived
NORMAL = "normal" # in range; grade 0
MISSING = "missing" # no value supplied
NO_TERM = "no_ctcae_term" # CTCAE v5 does not grade this marker
NOT_GRADEABLE = "not_gradeable" # term exists, criteria not evaluable from one number

_FLAGGED_STATUSES = frozenset({GRADED})

@dataclass(frozen=True, slots=True)
class ReferenceRange:
    """The range a value was judged against. `source` matters for audit."""
    lln: float | None
    uln: float | None
    unit: str
    source: str = "ctcae_default"  # "lab" once you wire in the issuing lab

    def __str__(self) -> str:
        lo = "-inf" if self.lln is None else f"{self.lln:g}"
        hi = "+inf" if self.uln is None else f"{self.uln:g}"
        return f"[{lo}, {hi}] {self.unit} ({self.source})"

    def contains(self, x: float) -> bool:
        if self.lln is not None and x < self.lln:
            return False
        if self.uln is not None and x > self.uln:
            return False
        return True


@dataclass(frozen=True, slots=True)
class Event:
    """One marker, evaluated once, against one CTCAE version."""

    type: str                              # canonical field, e.g. 'hemoglobina'
    value: float | None                    # exactly as reported
    unit: str | None                       # exactly as reported
    normal_range: ReferenceRange | None
    term: str | None                       # CTCAE term (English; it is a key)
    grade: int | None                      # 0..4, None when not derivable
    status: str
    ctcae_version: str
    canonical_value: float | None = None   # after unit conversion
    canonical_unit: str | None = None
    reason: str | None = None
    observed_at: datetime | None = None
    exam_index: int | None = None

    @property
    def is_flagged(self) -> bool:
        """True only for a real CTCAE grade >= 1. Not for missing/ungradeable."""
        return self.status in _FLAGGED_STATUSES and (self.grade or 0) >= 1

    @property
    def needs_review(self) -> bool:
        """Something a human must look at, but not an abnormality per se."""
        return self.status == NOT_GRADEABLE

    def __str__(self) -> str:
        if self.status in (GRADED, NORMAL):
            return f"[G{self.grade}] {self.term}: {self.value} {self.unit}"
        tail = f" ({self.reason})" if self.reason else ""
        return f"[--] {self.type}: {self.status}{tail}"