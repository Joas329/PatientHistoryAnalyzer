from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime

from .events import Event, GRADED, NORMAL


@dataclass
class Hemograma:
    hemoglobina: float | None = None
    hematocrito: float | None = None
    hematies: float | None = None
    volumen_corpuscular_medio: float | None = None
    hemoglobina_corpuscular_media: float | None = None
    concentracion_hemoglobina_corpuscular: float | None = None
    rdw_pct: float | None = None
    rdw_sd: float | None = None
    leucocitos_totales: float | None = None
    eosinofilos_pct: float | None = None
    basofilos_pct: float | None = None
    linfocitos_pct: float | None = None
    monocitos_pct: float | None = None
    neutrofilos_segmentados_pct: float | None = None
    bastones_pct: float | None = None
    eosinofilos_abs: float | None = None
    basofilos_abs: float | None = None
    linfocitos_abs: float | None = None
    monocitos_abs: float | None = None
    neutrofilos_segmentados_abs: float | None = None
    bastones_abs: float | None = None
    recuento_plaquetas: float | None = None
    volumen_plaquetario_medio: float | None = None
    neutrofilos_totales_anc: float | None = None

    def __str__(self) -> str:
        lines = ["Hemograma:"]
        for f in fields(self):
            lines.append(f"  {f.name} = {getattr(self, f.name)}")
        return "\n".join(lines)


@dataclass
class MedicalExam:
    """One draw. Holds raw values AND the events derived from them.

    Note: the single-field wrapper classes (TransaminasaPiruvica etc.) were
    dropped -- a dataclass wrapping one float adds an attribute hop and buys
    nothing. If you need units per analyte, put them on the exam.
    """

    hemograma: Hemograma = field(default_factory=Hemograma)
    glucosa: float | None = None
    transaminasa_piruvica: float | None = None      # TGP / ALT
    transaminasa_oxalacetica: float | None = None   # TGO / AST
    fecha_toma_muestra: datetime | None = None

    # Baseline status governs how CTCAE grades ALT/AST. None => not gradeable.
    baseline_normal: bool | None = None

    events: list[Event] = field(default_factory=list, repr=False)

    # Out-of-range markers vs the lab's own reference intervals. Distinct from
    # events: "abnormal" is a lab signal, not necessarily a CTCAE finding.
    range_flags: list = field(default_factory=list, repr=False)

    # -- event tracking ----------------------------------------------------
    def add_event(self, ev: Event) -> None:
        self.events.append(ev)

    def clear_events(self) -> None:
        """Events are derived data. Re-grading must not append to stale ones."""
        self.events.clear()

    @property
    def flagged(self) -> list[Event]:
        """Only real CTCAE grades >= 1, worst first."""
        return sorted((e for e in self.events if e.is_flagged),
                      key=lambda e: -(e.grade or 0))

    @property
    def needs_review(self) -> list[Event]:
        return [e for e in self.events if e.needs_review]

    @property
    def worst_grade(self) -> int:
        return max((e.grade for e in self.events
                    if e.status in (GRADED, NORMAL) and e.grade is not None),
                   default=0)

    def __str__(self) -> str:
        if not self.events:
            return "MedicalExam: (not graded)"
        lines = [f"MedicalExam  worst grade: {self.worst_grade}"]
        lines += [f"  {e}" for e in self.flagged] or ["  (nothing flagged)"]
        if self.needs_review:
            lines.append("  requires review:")
            lines += [f"    {e}" for e in self.needs_review]
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
        return [e for x in self.medical_records for e in x.events]

    @property
    def flagged(self) -> list[Event]:
        return [e for e in self.all_events if e.is_flagged]

    @property
    def worst_grade(self) -> int:
        return max((x.worst_grade for x in self.medical_records), default=0)