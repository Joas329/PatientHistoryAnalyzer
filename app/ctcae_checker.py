"""
CTCAE v5 reference vocabulary + numeric grading.

This version uses the reference interval already attached to each LabResult by
pdf_reader.py. It no longer depends on the removed reference_ranges.py module.

Grades are derived ONLY from numeric criteria already represented here.
Criteria that CTCAE states clinically are not inferred from a laboratory value.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime
from typing import Iterable

import yaml

from .events import Event, ReferenceRange, GRADED, NORMAL, MISSING, NOT_GRADEABLE


# ---------------------------------------------------------------------------
# Units. Canonical: hemoglobin g/dL, counts 10^9/L, glucose mg/dL, ALT/AST U/L
# ---------------------------------------------------------------------------
_HGB_TO_GDL = {"g/dL": 1.0, "g/L": 0.1, "mmol/L": 1.6129}
_COUNT_TO_1E9L = {"10^9/L": 1.0, "10^3/uL": 1.0, "/mm3": 1e-3, "/uL": 1e-3}
_GLU_TO_MGDL = {"mg/dL": 1.0, "mmol/L": 18.0158}
_ENZYME_TO_UL = {"U/L": 1.0, "UI/L": 1.0}

_PLAUSIBLE = {
    "hemoglobin": (1.0, 30.0),
    "count": (0.0, 1000.0),
    "glucose": (5.0, 1500.0),
    "enzyme": (0.0, 20000.0),
}


class UnitError(ValueError):
    """Value cannot be trusted after unit conversion."""


def _convert(value: float, unit: str, table: dict[str, float], kind: str) -> float:
    if unit not in table:
        raise UnitError(f"unknown {kind} unit {unit!r}; expected one of {sorted(table)}")
    out = float(value) * table[unit]
    lo, hi = _PLAUSIBLE[kind]
    if not lo <= out <= hi:
        raise UnitError(f"{kind} {value} {unit} -> {out:g} is implausible; check the unit")
    return out

def _convert_reference(value: float | None, unit: str, table: dict[str, float]) -> float | None:
    if value is None:
        return None
    if unit not in table:
        raise UnitError(f"unknown reference unit {unit!r}; expected one of {sorted(table)}")
    return float(value) * table[unit]

# ---------------------------------------------------------------------------
# Numeric bands. CTCAE writes "<1500 - 1000/mm3" meaning 1000 <= x < 1500.
# Bands are [lower_inclusive, upper_exclusive); None upper => use the LLN.
# ---------------------------------------------------------------------------
_DECREASING = {
    "Anemia": [(3, -math.inf, 8.0), (2, 8.0, 10.0), (1, 10.0, None)],
    "Neutrophil count decreased": [(4, -math.inf, 0.5), (3, 0.5, 1.0), (2, 1.0, 1.5), (1, 1.5, None)],
    "Platelet count decreased": [(4, -math.inf, 25.0), (3, 25.0, 50.0), (2, 50.0, 75.0), (1, 75.0, None)],
    "White blood cell decreased": [(4, -math.inf, 1.0), (3, 1.0, 2.0), (2, 2.0, 3.0), (1, 3.0, None)],
    "Lymphocyte count decreased": [(4, -math.inf, 0.2), (3, 0.2, 0.5), (2, 0.5, 0.8), (1, 0.8, None)],
    "Hypoglycemia": [(4, -math.inf, 30.0), (3, 30.0, 40.0), (2, 40.0, 55.0), (1, 55.0, None)],
}
# above these the criteria are clinical, not numeric
_CLINICAL_CEILING = {
    "Anemia": "G3 assumes transfusion indicated; G4 requires life-threatening consequences",
    "Hypoglycemia": "G4 also covers seizures / life-threatening consequences",
}
# ULN-multiple bands: (grade, lower_exclusive, upper_inclusive) in x ULN
_ULN_MULTIPLE = {
    "Alanine aminotransferase increased": [(4, 20.0, math.inf), (3, 5.0, 20.0), (2, 3.0, 5.0), (1, 1.0, 3.0)],
    "Aspartate aminotransferase increased": [(4, 20.0, math.inf), (3, 5.0, 20.0), (2, 3.0, 5.0), (1, 1.0, 3.0)],
}


def _grade_decreasing(term: str, x: float, lln: float) -> int:
    for grade, lo, hi in _DECREASING[term]:
        if lo <= x < (lln if hi is None else hi):
            return grade
    return 0


def _grade_uln_multiple(term: str, x: float, uln: float) -> int:
    ratio = x / uln
    for grade, lo, hi in _ULN_MULTIPLE[term]:
        if lo < ratio <= hi:
            return grade
    return 0


# ---------------------------------------------------------------------------
# These names come directly from reference_ranges.csv.
# ---------------------------------------------------------------------------
_MARKER_MAP: dict[str, dict] = {
    "hemoglobin": {"term": "Anemia", "kind": "hgb", "default_unit": "g/dL"},
    "wbc": {"term": "White blood cell decreased", "kind": "count", "default_unit": "10^3/uL"},
    "anc": {"term": "Neutrophil count decreased", "kind": "count", "default_unit": "10^3/uL"},
    "lymphocytes_absolute": {"term": "Lymphocyte count decreased", "kind": "count", "default_unit": "10^3/uL"},
    "platelets": {"term": "Platelet count decreased", "kind": "count", "default_unit": "10^3/uL"},
    "glucose": {"term": "Hypoglycemia", "kind": "glucose", "default_unit": "mg/dL"},
    "alt": {"term": "Alanine aminotransferase increased", "kind": "enzyme", "default_unit": "U/L"},
    "ast": {"term": "Aspartate aminotransferase increased", "kind": "enzyme", "default_unit": "U/L"},
}

_NOT_GRADEABLE = {
    "eosinophils_absolute": ("Eosinophilia", "G1 requires >ULN AND >baseline; no baseline is available"),
}


class CTCAE:
    # CTCAE v5 numeric grader operating directly on MedicalExam.results

    def __init__(self, path: str):
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        self.version: str = doc["meta"]["source"]
        self._by_term: dict[str, dict] = {t["term"].lower(): t for t in doc["terms"]}

    def lookup(self, term: str) -> dict:
        hit = self._by_term.get(term.lower())
        if hit is None:
            raise KeyError(f"{term!r} is not a CTCAE v5 term")
        return hit

    def criteria(self, term: str, grade: int) -> str | None:
        return self.lookup(term)["grades"][grade]

    def _event(self, **kw) -> Event:
        return Event(ctcae_version=self.version, **kw)

    def _not_gradeable(self, result, term: str | None, reason: str, observed_at: datetime | None) -> Event:
        return self._event(type=result.canonical_name, value=float(result.value) if result.is_numeric else result.value, unit=result.unit, normal_range=None, term=term, grade=None, observed_at=observed_at, status=NOT_GRADEABLE, reason=reason)

    def grade_result(self, result, *, baseline_normal: bool | None = None, observed_at: datetime | None = None) -> Event | None:
        """Grade one LabResult. Returns None when the analyte has no implemented CTCAE rule."""
        name = result.canonical_name

        if name in _NOT_GRADEABLE:
            term, why = _NOT_GRADEABLE[name]
            return self._not_gradeable(result, term, why, observed_at)

        rule = _MARKER_MAP.get(name)
        if rule is None:
            return None

        if not result.is_numeric:
            return self._event(type=name, value=None, unit=result.unit, normal_range=None, term=rule["term"], grade=None, observed_at=observed_at, status=MISSING, reason="CTCAE numeric grading requires a numeric laboratory result")

        value = float(result.value)
        unit = result.unit or rule["default_unit"]
        term = rule["term"]
        kind = rule["kind"]
        self.lookup(term)

        source = "reference_ranges.csv"
        if result.method:
            source = f"{source} · {result.method}"

        if kind == "hgb":
            x = _convert(value, unit, _HGB_TO_GDL, "hemoglobin")
            lln = _convert_reference(result.reference_low, unit, _HGB_TO_GDL)
            if lln is None:
                return self._not_gradeable(result, term, "No laboratory LLN was selected for this result", observed_at)
            rng = ReferenceRange(lln, None, "g/dL", source)
            grade = _grade_decreasing(term, x, lln)
            canonical_unit = "g/dL"

        elif kind == "count":
            x = _convert(value, unit, _COUNT_TO_1E9L, "count")
            lln = _convert_reference(result.reference_low, unit, _COUNT_TO_1E9L)
            if lln is None:
                return self._not_gradeable(result, term, "No laboratory LLN was selected for this result", observed_at)
            rng = ReferenceRange(lln, None, "10^9/L", source)
            grade = _grade_decreasing(term, x, lln)
            canonical_unit = "10^9/L"

        elif kind == "glucose":
            x = _convert(value, unit, _GLU_TO_MGDL, "glucose")
            lln = _convert_reference(result.reference_low, unit, _GLU_TO_MGDL)
            uln = _convert_reference(result.reference_high, unit, _GLU_TO_MGDL)
            if lln is None or uln is None:
                return self._not_gradeable(result, term, "No complete laboratory glucose reference interval was selected", observed_at)
            rng = ReferenceRange(lln, uln, "mg/dL", source)
            canonical_unit = "mg/dL"

            if x > uln:
                return self._event( type=name, value=value, unit=unit, normal_range=rng, term="Hyperglycemia", grade=None, observed_at=observed_at, canonical_value=x, canonical_unit=canonical_unit, status=NOT_GRADEABLE, reason="Hyperglycemia is graded by intervention, not by value")

            grade = _grade_decreasing(term, x, lln)

        elif kind == "enzyme":
            x = _convert(value, unit, _ENZYME_TO_UL, "enzyme")
            uln = _convert_reference(result.reference_high, unit, _ENZYME_TO_UL)
            if uln is None:
                return self._not_gradeable(result, term, "No laboratory ULN was selected for this result", observed_at)

            rng = ReferenceRange(None, uln, "U/L", source)
            canonical_unit = "U/L"

            if baseline_normal is None:
                return self._event( type=name, value=value, unit=unit, normal_range=rng, term=term, grade=None, observed_at=observed_at, canonical_value=x, canonical_unit=canonical_unit, status=NOT_GRADEABLE, reason="ALT/AST grading requires baseline status. Set exam.baseline_normal=True when baseline is known to be normal.")

            if not baseline_normal:
                return self._event( type=name, value=value, unit=unit, normal_range=rng, term=term, grade=None, observed_at=observed_at, canonical_value=x, canonical_unit=canonical_unit, status=NOT_GRADEABLE, reason="Abnormal baseline requires grading against the patient's own baseline; that baseline value is not currently stored.")

            grade = _grade_uln_multiple(term, x, uln)

        else:
            raise AssertionError(f"unhandled CTCAE kind {kind!r}")

        status = GRADED if grade > 0 else NORMAL
        reason = None
        if grade and term in _CLINICAL_CEILING and grade == max(g for g, _, _ in _DECREASING[term]):
            reason = _CLINICAL_CEILING[term]

        return self._event(type=name, value=value, unit=unit, normal_range=rng,term=term, grade=grade, observed_at=observed_at, canonical_value=x, canonical_unit=canonical_unit, status=status, reason=reason)

    def grade_exam(self, exam, exam_index: int | None = None) -> list[Event]:
        # Grade one exam from exam.results.
        exam.clear_events()
        when = getattr(exam, "fecha_toma_muestra", None)
        baseline_normal = getattr(exam, "baseline_normal", None)

        for canonical_name in (*_MARKER_MAP.keys(), *_NOT_GRADEABLE.keys()):
            result = exam.results.get(canonical_name)
            if result is None:
                continue

            event = self.grade_result(result, baseline_normal=baseline_normal, observed_at=when)
            if event is not None:
                exam.add_event(replace(event, exam_index=exam_index))

        return exam.events

    def grade_patient(self, patient) -> list[Event]:
        """Grade every exam, recording events on each. Returns the flat list."""
        out: list[Event] = []
        for i, exam in enumerate(patient.medical_records):
            out.extend(self.grade_exam(exam, exam_index=i))
        return out

    @staticmethod
    def report(events: Iterable[Event]) -> str:
        evs = list(events)
        graded = [e for e in evs if e.status in (GRADED, NORMAL)]
        worst = max((e.grade for e in graded if e.grade is not None), default=0)
        lines = [f"Worst CTCAE grade: {worst}", ""]
        lines += [f"  {e}" for e in sorted(graded, key=lambda e: -(e.grade or 0))]
        review = [e for e in evs if e.needs_review]
        if review:
            lines += ["", "Requires review:"]
            lines += [f"  {e}" for e in review]
        return "\n".join(lines)