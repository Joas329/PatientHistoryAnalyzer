"""
CTCAE v5 reference vocabulary + numeric grading.

Grades are derived ONLY from the numeric criteria published in CTCAE v5.
Criteria that CTCAE states clinically (Anemia G4 "life-threatening",
Hyperglycemia at every grade) are never inferred from a number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace
from datetime import datetime
from typing import Iterable, TYPE_CHECKING

import yaml

from .events import Event, ReferenceRange, GRADED, NORMAL, MISSING, NO_TERM, NOT_GRADEABLE

if TYPE_CHECKING:
    from reference_ranges import LabRanges

# ---------------------------------------------------------------------------
# Units. Canonical: hemoglobin g/dL, counts 10^9/L, glucose mg/dL, ALT/AST U/L
# ---------------------------------------------------------------------------
_HGB_TO_GDL = {"g/dL": 1.0, "g/L": 0.1, "mmol/L": 1.6129}
_COUNT_TO_1E9L = {"10^9/L": 1.0, "10^3/uL": 1.0, "/mm3": 1e-3, "/uL": 1e-3}
_GLU_TO_MGDL = {"mg/dL": 1.0, "mmol/L": 18.0158}
_PLAUSIBLE = {"hemoglobin": (1.0, 30.0), "count": (0.0, 1000.0),
              "glucose": (5.0, 1500.0), "enzyme": (0.0, 20000.0)}


class UnitError(ValueError):
    """Value cannot be trusted after unit conversion."""


def _convert(value: float, unit: str, table: dict[str, float], kind: str) -> float:
    if unit not in table:
        raise UnitError(f"unknown {kind} unit {unit!r}; expected one of {sorted(table)}")
    out = value * table[unit]
    lo, hi = _PLAUSIBLE[kind]
    if not lo <= out <= hi:
        raise UnitError(f"{kind} {value} {unit} -> {out:g} is implausible; check the unit")
    return out

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
# Marker map
# ---------------------------------------------------------------------------
_MARKER_MAP: dict[str, dict] = {
    "hemoglobina":             {"term": "Anemia", "kind": "hgb", "unit": "g/dL"},
    "leucocitos_totales":      {"term": "White blood cell decreased", "kind": "count", "unit": "10^3/uL", "lln": "wbc_lln"},
    "neutrofilos_totales_anc": {"term": "Neutrophil count decreased", "kind": "count", "unit": "10^3/uL", "lln": "neutrophils_lln"},
    "linfocitos_abs":          {"term": "Lymphocyte count decreased", "kind": "count", "unit": "10^3/uL", "lln": "lymphocytes_lln"},
    "recuento_plaquetas":      {"term": "Platelet count decreased", "kind": "count", "unit": "10^3/uL", "lln": "platelets_lln"},
    "glucosa":                 {"term": "Hypoglycemia", "kind": "glucose", "unit": "mg/dL"},
    "transaminasa_piruvica":   {"term": "Alanine aminotransferase increased", "kind": "enzyme", "unit": "U/L", "uln": "alt_uln"},
    "transaminasa_oxalacetica":{"term": "Aspartate aminotransferase increased", "kind": "enzyme", "unit": "U/L", "uln": "ast_uln"},
}
_NOT_GRADEABLE = {
    "eosinofilos_abs": ("Eosinophilia", "G1 requires >ULN AND >baseline; no baseline available"),
}
_NO_TERM = {
    "hematocrito", "hematies", "volumen_corpuscular_medio",
    "hemoglobina_corpuscular_media", "concentracion_hemoglobina_corpuscular",
    "rdw_pct", "rdw_sd", "basofilos_abs", "monocitos_abs", "bastones_abs",
    "neutrofilos_segmentados_abs", "volumen_plaquetario_medio",
}
_EXAM_LEVEL = ("glucosa", "transaminasa_piruvica", "transaminasa_oxalacetica")
_PCT = "_pct"


class CTCAE:
    """CTCAE v5 vocabulary, with numeric grading that emits Event DTOs."""

    def __init__(self, path: str, ranges: "LabRanges"):
        if ranges is None:
            raise ValueError(
                "CTCAE requires lab reference ranges; pass "
                "ranges=as_reference_ranges(). There is no default -- grading "
                "against guessed ranges is unsafe."
            )
        with open(path) as f:
            doc = yaml.safe_load(f)
        self.version: str = doc["meta"]["source"]
        self.ranges = ranges
        self._by_term: dict[str, dict] = {t["term"].lower(): t for t in doc["terms"]}

    # -- vocabulary ---------------------------------------------------------
    def lookup(self, term: str) -> dict:
        hit = self._by_term.get(term.lower())
        if hit is None:
            raise KeyError(f"{term!r} is not a CTCAE v5 term")
        return hit

    def criteria(self, term: str, grade: int) -> str | None:
        return self.lookup(term)["grades"][grade]

    def _event(self, **kw) -> Event:
        return Event(ctcae_version=self.version, **kw)

    # -- grading ------------------------------------------------------------
    def grade_marker(self, name: str, value: float | None, *,
                     unit: str | None = None, baseline_normal: bool | None = None,
                     observed_at: datetime | None = None) -> Event:
        base = dict(type=name, value=value, unit=unit, normal_range=None, term=None,
                    grade=None, observed_at=observed_at)

        if value is None:
            return self._event(**{**base, "status": MISSING})
        if name.endswith(_PCT):
            return self._event(**{**base, "unit": "%", "status": NOT_GRADEABLE,
                                  "reason": "CTCAE grades absolute counts, not percentages"})
        if name in _NO_TERM:
            return self._event(**{**base, "status": NO_TERM,
                                  "reason": "no CTCAE v5 term for this marker"})
        if name in _NOT_GRADEABLE:
            term, why = _NOT_GRADEABLE[name]
            return self._event(**{**base, "term": term, "status": NOT_GRADEABLE, "reason": why})

        rule = _MARKER_MAP.get(name)
        if rule is None:
            raise KeyError(f"{name!r} has no CTCAE mapping; add it to _MARKER_MAP or _NO_TERM")

        unit = unit or rule["unit"]
        term, kind = rule["term"], rule["kind"]
        self.lookup(term)  # vocabulary and map must agree

        if kind == "hgb":
            x = _convert(value, unit, _HGB_TO_GDL, "hemoglobin")
            lln = self.ranges.hemoglobin_lln
            rng = ReferenceRange(lln, None, "g/dL", self.ranges.source)
            grade, cu = _grade_decreasing(term, x, lln), "g/dL"

        elif kind == "count":
            x = _convert(value, unit, _COUNT_TO_1E9L, "count")
            lln = getattr(self.ranges, rule["lln"])
            rng = ReferenceRange(lln, None, "10^9/L", self.ranges.source)
            grade, cu = _grade_decreasing(term, x, lln), "10^9/L"

        elif kind == "glucose":
            x = _convert(value, unit, _GLU_TO_MGDL, "glucose")
            lln, uln = self.ranges.glucose_lln, self.ranges.glucose_uln
            rng, cu = ReferenceRange(lln, uln, "mg/dL", self.ranges.source), "mg/dL"
            if x > uln:
                # Hyperglycemia has NO numeric criteria at any grade.
                return self._event(**{**base, "unit": unit, "term": "Hyperglycemia",
                                      "normal_range": rng, "canonical_value": x, "canonical_unit": cu,
                                      "status": NOT_GRADEABLE,
                                      "reason": "Hyperglycemia is graded by intervention, not by value"})
            grade = _grade_decreasing(term, x, lln)

        elif kind == "enzyme":
            x = _convert(value, unit, {"U/L": 1.0, "UI/L": 1.0}, "enzyme")
            uln = getattr(self.ranges, rule["uln"])
            rng, cu = ReferenceRange(None, uln, "U/L", self.ranges.source), "U/L"
            if baseline_normal is None:
                return self._event(**{**base, "unit": unit, "term": term, "normal_range": rng,
                                      "canonical_value": x, "canonical_unit": cu,
                                      "status": NOT_GRADEABLE,
                                      "reason": "CTCAE grades ALT/AST vs ULN or vs baseline; "
                                                "set exam.baseline_normal"})
            if not baseline_normal:
                return self._event(**{**base, "unit": unit, "term": term, "normal_range": rng,
                                      "canonical_value": x, "canonical_unit": cu,
                                      "status": NOT_GRADEABLE,
                                      "reason": "abnormal baseline: grade is a multiple of the "
                                                "patient's own baseline, which is not stored here"})
            grade = _grade_uln_multiple(term, x, uln)

        else:
            raise AssertionError(f"unhandled kind {kind!r}")

        status = GRADED if grade > 0 else NORMAL
        reason = None
        if grade and term in _CLINICAL_CEILING and grade == max(g for g, _, _ in _DECREASING[term]):
            reason = _CLINICAL_CEILING[term]
        return self._event(**{**base, "unit": unit, "term": term, "normal_range": rng,
                              "canonical_value": x, "canonical_unit": cu,
                              "grade": grade, "status": status, "reason": reason})

    def grade_exam(self, exam, exam_index: int | None = None) -> list[Event]:
        """Grade one exam and record the events on it. Idempotent."""
        hemograma = getattr(exam, "hemograma", None)
        if hemograma is None:
            raise AttributeError(
                f"{type(exam).__name__} has no .hemograma; check that MedicalExam "
                "assigns its fields (a hand-written __init__ overrides @dataclass)"
            )
        exam.clear_events()  # derived data: never append to stale events
        when = getattr(exam, "fecha_toma_muestra", None)
        baseline = getattr(exam, "baseline_normal", None)

        names = [f.name for f in fields(hemograma)]
        for n in names:
            ev = self.grade_marker(n, getattr(hemograma, n), observed_at=when)
            exam.add_event(replace(ev, exam_index=exam_index))
        for n in _EXAM_LEVEL:
            if not hasattr(exam, n):
                continue
            ev = self.grade_marker(n, getattr(exam, n),
                                   baseline_normal=baseline, observed_at=when)
            exam.add_event(replace(ev, exam_index=exam_index))
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
            lines += ["", "Requires review:"] + [f"  {e}" for e in review]
        return "\n".join(lines)