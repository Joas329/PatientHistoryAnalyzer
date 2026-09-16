from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .events import Event, GRADED, NORMAL


@dataclass
class LabResult:
    """One laboratory analyte parsed from a PDF.

    The CSV-driven reader is the source of truth for analyte identity,
    reference interval, units, method, sample type, and category.
    """

    canonical_name: str
    test_name: str
    value: float | str
    category: str | None = None
    unit: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    reference_text: str | None = None
    reference_condition: str | None = None
    reference_notes: str | None = None
    status: str | None = None
    method: str | None = None
    sample_type: str | None = None

    @property
    def is_numeric(self) -> bool:
        return isinstance(self.value, (int, float)) and not isinstance(self.value, bool)

    @property
    def is_out_of_range(self) -> bool:
        return self.status in {"LOW", "HIGH", "POSITIVE", "GRAY_ZONE"}

    @property
    def direction(self) -> str | None:
        if self.status == "LOW":
            return "low"
        if self.status in {"HIGH", "POSITIVE"}:
            return "high"
        return None

    @property
    def display_name(self) -> str:
        return self.test_name or self.canonical_name.replace("_", " ").title()

    @property
    def reference_range(self) -> tuple[float | None, float | None]:
        return self.reference_low, self.reference_high

    def __str__(self) -> str:
        unit = f" {self.unit}" if self.unit else ""
        status = f" [{self.status}]" if self.status else ""

        if self.reference_low is not None or self.reference_high is not None:
            low = "-∞" if self.reference_low is None else f"{self.reference_low:g}"
            high = "∞" if self.reference_high is None else f"{self.reference_high:g}"
            reference = f" ref=[{low}, {high}]"
        elif self.reference_text:
            reference = f" ref={self.reference_text}"
        else:
            reference = ""

        return f"{self.canonical_name}: {self.value}{unit}{reference}{status}"


@dataclass
class MedicalExam:
    """One blood/urine draw and all analytes found in its PDF."""

    fecha_toma_muestra: datetime | None = None
    results: dict[str, LabResult] = field(default_factory=dict)

    # Clinical context used by CTCAE. This is not a laboratory reference range.
    baseline_normal: bool | None = None

    # CTCAE events are derived from results.
    events: list[Event] = field(default_factory=list, repr=False)

    def add_result(self, result: LabResult) -> None:
        self.results[result.canonical_name] = result

    def get_result(self, canonical_name: str) -> LabResult | None:
        return self.results.get(canonical_name)

    def get_value(self, canonical_name: str, default: Any = None) -> Any:
        result = self.results.get(canonical_name)
        return result.value if result is not None else default

    @property
    def range_flags(self) -> list[LabResult]:
        return [result for result in self.results.values() if result.is_out_of_range]

    def add_event(self, event: Event) -> None:
        self.events.append(event)

    def clear_events(self) -> None:
        self.events.clear()

    @property
    def flagged(self) -> list[Event]:
        return sorted((event for event in self.events if event.is_flagged), key=lambda event: -(event.grade or 0))

    @property
    def needs_review(self) -> list[Event]:
        return [event for event in self.events if event.needs_review]

    @property
    def worst_grade(self) -> int:
        return max((event.grade for event in self.events if event.status in (GRADED, NORMAL) and event.grade is not None), default=0)

    def __str__(self) -> str:
        lines = [f"MedicalExam: {len(self.results)} laboratory results"]

        if self.fecha_toma_muestra is not None:
            lines[0] += f" @ {self.fecha_toma_muestra}"

        lines.extend(f"  {result}" for result in self.results.values())

        if self.events:
            lines.append(f"CTCAE worst grade: {self.worst_grade}")
            lines.extend(f"  {event}" for event in self.flagged)

        return "\n".join(lines)


@dataclass
class Patient:
    patient_code: str | None = None
    sexo: str | None = None
    fecha_nacimiento: str | None = None
    edad: int | None = None
    fecha_toma_muestra: str | None = None
    medical_records: list[MedicalExam] = field(default_factory=list)

    def add_medical_exam(self, exam: MedicalExam) -> None:
        self.medical_records.append(exam)

    @property
    def all_events(self) -> list[Event]:
        return [event for exam in self.medical_records for event in exam.events]

    @property
    def flagged(self) -> list[Event]:
        return [event for event in self.all_events if event.is_flagged]

    @property
    def worst_grade(self) -> int:
        return max((exam.worst_grade for exam in self.medical_records), default=0)