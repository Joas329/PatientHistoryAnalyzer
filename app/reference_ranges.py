# app/reference_ranges.py
"""Laboratory reference intervals ("Valor Referencial") transcribed from the
issuing lab's report.

Two distinct jobs, kept separate on purpose:

  1. out_of_range()  -- every marker, both directions. A lab-normalcy signal.
  2. CTCAE grading   -- only the markers with a CTCAE term, only in the
                        gradeable direction, using CTCAE's OWN absolute
                        thresholds (in ctcae_checker). The reference range
                        supplies the Grade 0/1 boundary (LLN/ULN); it does
                        NOT define the higher grades.

Out-of-range is NOT the same as a gradeable adverse event. A high platelet
count is out of range but has no CTCAE term; do not manufacture one.

UNITS: ranges are stored in the units the LAB REPORTS, which match the value
column on the report (platelets read ~250 against a 150-350 reference), so no
unit conversion is needed. sanity_check() catches a lab that ever disagrees.
"""

from __future__ import annotations

from dataclasses import dataclass

# canonical field -> (low, high) in the lab's reported units
LAB_REFERENCE: dict[str, tuple[float, float]] = {
    "hemoglobina": (12.0, 16.0),                       # g/dL
    "hematocrito": (36.0, 46.0),                       # %
    "hematies": (4.0, 4.9),                            # 10^6/uL
    "volumen_corpuscular_medio": (80.0, 100.0),        # fL
    "hemoglobina_corpuscular_media": (26.0, 34.0),     # pg
    "concentracion_hemoglobina_corpuscular": (31.0, 37.0),  # g/dL
    "rdw_pct": (11.0, 14.0),                           # %
    "rdw_sd": (36.4, 46.3),                            # fL
    "leucocitos_totales": (4.5, 11.0),                 # 10^3/uL
    "eosinofilos_pct": (0.0, 3.0),                     # %
    "basofilos_pct": (0.0, 1.0),                       # %
    "linfocitos_pct": (24.0, 44.0),                    # %
    "monocitos_pct": (3.0, 6.0),                       # %
    "neutrofilos_segmentados_pct": (35.0, 66.0),       # %
    "bastones_pct": (0.0, 5.0),                        # %
    "eosinofilos_abs": (0.0, 0.7),                     # 10^3/uL
    "basofilos_abs": (0.0, 0.2),                       # 10^3/uL
    "linfocitos_abs": (1.0, 4.8),                      # 10^3/uL
    "monocitos_abs": (0.0, 0.9),                       # 10^3/uL
    "neutrofilos_segmentados_abs": (1.8, 7.7),         # 10^3/uL
    "bastones_abs": (0.0, 0.5),                        # 10^3/uL
    "recuento_plaquetas": (150.0, 350.0),              # 10^3/uL  (value may be /uL!)
    "volumen_plaquetario_medio": (7.5, 11.5),          # fL
    "neutrofilos_totales_anc": (1.8, 8.2),             # 10^3/uL

    # -- biochemistry (report page 2) ----------------------------------------
    # Field names must match whatever pdf_reader assigns on the exam.
    "depuracion_creatinina": (50.0, 70.0),             # mL/min (Cockcroft-Gault)
    "glucosa": (82.0, 115.0),                          # mg/dL  (NOT 70-99)
    "urea_serica": (16.6, 48.5),                       # mg/dL
    "nitrogeno_ureico_bun": (8.0, 23.0),               # mg/dL
    "creatinina_serica": (0.5, 0.9),                   # mg/dL
    "transaminasa_piruvica": (0.0, 35.0),              # U/L  (ALT; ULN 35, NOT 40)
    "transaminasa_oxalacetica": (0.0, 35.0),           # U/L  (AST; ULN 35, NOT 40)
    "bilirrubina_total": (0.0, 1.2),                   # mg/dL (adults)

    # -- biochemistry page 3 -------------------------------------------------
    "bilirrubina_indirecta": (0.1, 1.0),               # mg/dL
    "bilirrubina_directa": (0.0, 0.3),                 # mg/dL
    "fosfatasa_alcalina": (35.0, 104.0),               # U/L
    "proteinas_totales": (6.4, 8.3),                   # g/dL (adults; prematuros 3.6-6.0)
    "albumina": (3.5, 5.2),                            # g/dL
    "calcio_serico": (8.8, 10.2),                      # mg/dL
    "fosforo_serico": (2.5, 4.5),                      # mg/dL
    "sodio": (133.0, 145.0),                           # mmol/L
    "potasio": (3.7, 5.4),                             # mmol/L
    "cloro": (96.0, 108.0),                            # mmol/L
    "bicarbonato_serico": (22.0, 28.0),                # mmol/L
}

# Rows on the report that LOOK like reference ranges but are not, and must
# never be parsed as intervals:
#   "Sexo: Masculino 1 / Femenino 0.85" -> Cockcroft-Gault sex coefficient
#   "Edad", "Peso", "Sexo"              -> formula inputs, not analytes
#   section headers, "COMENTARIO"       -> no value
_NOT_A_RANGE = frozenset({
    "sexo_coeficiente", "edad", "peso", "sexo", "comentario",
})




@dataclass(frozen=True, slots=True)
class RangeFlag:
    field: str
    value: float
    low: float
    high: float
    direction: str  # "low" | "high" | "normal"

    @property
    def out_of_range(self) -> bool:
        return self.direction != "normal"


def classify(field: str, value: float | None) -> RangeFlag | None:
    """Where does `value` sit relative to the lab range? None if no range/value.

    Values and reference ranges are printed in the same unit on the report
    (confirmed: platelets read ~250, matching the 150-350 reference), so no
    unit conversion is needed here. See sanity_check() to catch a lab whose
    value column ever disagrees with its own reference column.
    """
    if value is None or field not in LAB_REFERENCE:
        return None
    low, high = LAB_REFERENCE[field]
    if value < low:
        direction = "low"
    elif value > high:
        direction = "high"
    else:
        direction = "normal"
    return RangeFlag(field, value, low, high, direction)


def sanity_check(field: str, value: float | None) -> str | None:
    """Detect a value that is ~1000x off its own reference range: a unit
    mismatch, not a finding. Returns a message if suspicious, else None.

    A real result can sit well outside its range, but not by 50x. This catches
    the day a different lab prints a count in /uL (250000) against a /uL*10^3
    reference (150-350) -- loudly, instead of silently mis-grading.
    """
    if value is None or field not in LAB_REFERENCE:
        return None
    low, high = LAB_REFERENCE[field]
    if high > 0 and value > high * 50:
        return (f"{field}={value:g} is ~{round(value / high)}x its reference "
                f"upper bound {high:g}; likely a unit mismatch, not a real value")
    return None


# Which object each field lives on: the hemogram, or the exam (biochemistry).
_HEMOGRAM_FIELDS = frozenset({
    "hemoglobina", "hematocrito", "hematies", "volumen_corpuscular_medio",
    "hemoglobina_corpuscular_media", "concentracion_hemoglobina_corpuscular",
    "rdw_pct", "rdw_sd", "leucocitos_totales", "eosinofilos_pct", "basofilos_pct",
    "linfocitos_pct", "monocitos_pct", "neutrofilos_segmentados_pct", "bastones_pct",
    "eosinofilos_abs", "basofilos_abs", "linfocitos_abs", "monocitos_abs",
    "neutrofilos_segmentados_abs", "bastones_abs", "recuento_plaquetas",
    "volumen_plaquetario_medio", "neutrofilos_totales_anc",
})


def out_of_range(exam) -> list[RangeFlag]:
    """All out-of-range markers on an exam, both directions.

    Hemogram fields are read off exam.hemograma; biochemistry fields off the
    exam itself. Pass the MedicalExam, not the Hemograma.
    """
    hemograma = getattr(exam, "hemograma", None)
    if hemograma is None:
        raise TypeError(
            f"out_of_range expects a MedicalExam (with .hemograma), got "
            f"{type(exam).__name__}. Pass the exam, not exam.hemograma."
        )
    flags = []
    for field in LAB_REFERENCE:
        source = hemograma if field in _HEMOGRAM_FIELDS else exam
        value = getattr(source, field, None) if source is not None else None
        flag = classify(field, value)
        if flag is not None and flag.out_of_range:
            flags.append(flag)
    return flags


@dataclass(frozen=True)
class LabRanges:
    """The LLN/ULN the CTCAE grader reads, derived from the lab's report.

    No defaults: every value comes from the report. Constructing this without
    a field is a programming error, not a silent fallback to a guess.

    Hemoglobin reference ranges are biologically sex-specific, but this lab's
    report prints a single hemoglobin range, so we carry one value. If a report
    ever provides sex-specific ranges, reintroduce the split then.
    """
    source: str
    hemoglobin_lln: float            # g/dL (single range on this report)
    neutrophils_lln: float           # 10^3/uL == 10^9/L
    platelets_lln: float
    wbc_lln: float
    lymphocytes_lln: float
    eosinophils_uln: float
    glucose_lln: float               # mg/dL
    glucose_uln: float
    alt_uln: float                   # U/L
    ast_uln: float


def as_reference_ranges() -> LabRanges:
    """Build the CTCAE LLN/ULN container from this lab's transcribed table.

    Counts are 10^3/uL == 10^9/L, CTCAE's canonical count unit, so they
    transfer directly.
    """
    return LabRanges(
        source="lab_pdf_valor_referencial",
        hemoglobin_lln=LAB_REFERENCE["hemoglobina"][0],          # 12.0 g/dL
        neutrophils_lln=LAB_REFERENCE["neutrofilos_totales_anc"][0],  # 1.8
        platelets_lln=LAB_REFERENCE["recuento_plaquetas"][0],    # 150
        wbc_lln=LAB_REFERENCE["leucocitos_totales"][0],          # 4.5
        lymphocytes_lln=LAB_REFERENCE["linfocitos_abs"][0],      # 1.0
        eosinophils_uln=LAB_REFERENCE["eosinofilos_abs"][1],     # 0.7
        glucose_lln=LAB_REFERENCE["glucosa"][0],                 # 82
        glucose_uln=LAB_REFERENCE["glucosa"][1],                 # 115
        alt_uln=LAB_REFERENCE["transaminasa_piruvica"][1],       # 35
        ast_uln=LAB_REFERENCE["transaminasa_oxalacetica"][1],    # 35
    )