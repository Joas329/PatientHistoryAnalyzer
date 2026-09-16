from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import fitz

from .Patient import LabResult, MedicalExam, Patient
from .dates import NACIMIENTO_RE, check_edad, coerce_date, parse_toma_datetime

NUM_RE = re.compile(r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)")
UNISEX = {"M/F", "F/M", "BOTH", "AMBOS", "ALL", ""}
QUALITATIVE_VALUES = {
    "NEGATIVO", "POSITIVO", "REACTIVO", "NO REACTIVO", "AMARILLO", "YELLOW",
    "TRANSPARENTE", "TRANSPARENT", "TRAZAS", "ESCASO", "MODERADO", "MUCHOS",
    "ABUNDANTE", "REGULAR", "FEW", "MODERATE", "MANY",
}


@dataclass(frozen=True)
class ReferenceRange:
    category: str
    test_name: str
    canonical_name: str
    age_min: float | None = None
    age_max: float | None = None
    time_value: float | None = None
    time_unit: str | None = None
    lower: float | None = None
    upper: float | None = None
    sex: str | None = None
    unit: str | None = None
    method: str | None = None
    sample_type: str | None = None
    condition: str | None = None
    reference_text: str | None = None
    notes: str | None = None


@dataclass
class AnalyteDefinition:
    canonical_name: str
    aliases: set[str] = field(default_factory=set)
    references: list[ReferenceRange] = field(default_factory=list)


@dataclass(frozen=True)
class AliasHit:
    alias: str
    start: int
    end: int
    canonical_names: tuple[str, ...]


@dataclass
class ReferenceCatalog:
    registry: dict[str, AnalyteDefinition]
    alias_to_names: dict[str, tuple[str, ...]]
    alias_pattern: re.Pattern[str]

    def find(self, normalized_line: str) -> AliasHit | None:
        match = self.alias_pattern.search(normalized_line)
        if not match:
            return None
        alias = match.group(0)
        names = self.alias_to_names.get(alias)
        if not names:
            return None
        return AliasHit(alias=alias, start=match.start(), end=match.end(), canonical_names=names)


def _to_float(value: str | None) -> float | None:
    if value is None or not str(value).strip():
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.upper().replace("µ", "U").replace("Μ", "U")
    return re.sub(r"\s+", " ", text).strip()


def normalize_sex(value: str | None) -> str | None:
    if not value:
        return None
    value = normalize(value)
    if value in {"M", "MALE", "MASCULINO", "HOMBRE"}:
        return "M"
    if value in {"F", "FEMALE", "FEMENINO", "MUJER"}:
        return "F"
    return value


def header_text(page) -> str:
    text = page.get_text("text")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def iter_lines(page) -> list[str]:
    data = page.get_text("dict")
    lines = []
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            text = " ".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if text:
                lines.append(text)
    return lines


def _default_reference_csv() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parent / "resources" / "reference_ranges.csv",
        here.parent / "data" / "reference_ranges.csv",
        here.parent.parent / "resources" / "reference_ranges.csv",
        here.parent.parent / "data" / "reference_ranges.csv",
        Path.cwd() / "resources" / "reference_ranges.csv",
        Path.cwd() / "data" / "reference_ranges.csv",
        Path.cwd() / "reference_ranges.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("Could not find reference_ranges.csv. Pass reference_csv=... explicitly.")


@lru_cache(maxsize=8)
def load_reference_ranges(csv_path: str) -> tuple[ReferenceRange, ...]:
    ranges = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            ranges.append(ReferenceRange(
                category=(row.get("category") or "").strip(),
                test_name=(row.get("test_name") or "").strip(),
                canonical_name=(row.get("canonical_name") or "").strip(),
                age_min=_to_float(row.get("age_min")),
                age_max=_to_float(row.get("age_max")),
                time_value=_to_float(row.get("time_value")),
                time_unit=(row.get("time_unit") or "").strip() or None,
                lower=_to_float(row.get("lower")),
                upper=_to_float(row.get("upper")),
                sex=(row.get("sex") or "").strip() or None,
                unit=(row.get("unit") or "").strip() or None,
                method=(row.get("method") or "").strip() or None,
                sample_type=(row.get("sample_type") or "").strip() or None,
                condition=(row.get("condition") or "").strip() or None,
                reference_text=(row.get("reference_text") or "").strip() or None,
                notes=(row.get("notes") or "").strip() or None,
            ))
    return tuple(ranges)


def _split_test_name(test_name: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s+/\s+", test_name) if part.strip()]


def _aliases_for_reference(ref: ReferenceRange) -> set[str]:
    aliases: set[str] = set()

    def add(text: str | None) -> None:
        if not text:
            return
        value = normalize(text)
        if len(value) >= 2:
            aliases.add(value)

    add(ref.test_name)
    add(ref.canonical_name.replace("_", " "))

    for part in _split_test_name(ref.test_name):
        add(part)
        add(re.sub(r"\s*\((?:METHOD|METODO|MÉTODO)[^)]*\)\s*$", "", part, flags=re.IGNORECASE))
        add(re.sub(r"\s+(?:SERICA|SÉRICA|SERICO|SÉRICO)$", "", part, flags=re.IGNORECASE))
        for abbr in re.findall(r"\(([A-Za-z][A-Za-z0-9]{1,7})\)", part):
            add(abbr)

    return aliases


def _compile_alias_pattern(aliases: list[str]) -> re.Pattern[str]:
    # Longest aliases first means "TRANSAMINASA PIRUVICA (ALT)" wins over "ALT"
    # at the same location. The negative lookarounds prevent matches inside words.
    alternatives = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    return re.compile(rf"(?<![A-Z0-9])(?:{alternatives})(?![A-Z0-9])")


@lru_cache(maxsize=8)
def load_catalog(csv_path: str) -> ReferenceCatalog:
    references = load_reference_ranges(csv_path)
    registry: dict[str, AnalyteDefinition] = {}
    alias_map: dict[str, set[str]] = {}

    for ref in references:
        if not ref.canonical_name:
            continue
        entry = registry.setdefault(ref.canonical_name, AnalyteDefinition(ref.canonical_name))
        entry.references.append(ref)
        aliases = _aliases_for_reference(ref)
        entry.aliases.update(aliases)
        for alias in aliases:
            alias_map.setdefault(alias, set()).add(ref.canonical_name)

    alias_to_names = {alias: tuple(sorted(names)) for alias, names in alias_map.items()}
    pattern = _compile_alias_pattern(list(alias_to_names))
    return ReferenceCatalog(registry=registry, alias_to_names=alias_to_names, alias_pattern=pattern)


def _unit_score(line_norm: str, definition: AnalyteDefinition) -> int:
    score = 0
    for ref in definition.references:
        if ref.unit and normalize(ref.unit) in line_norm:
            score = max(score, 4)
    return score


def _category_score(page_context: str, definition: AnalyteDefinition) -> int:
    score = 0
    for ref in definition.references:
        if ref.category and normalize(ref.category) in page_context:
            score = max(score, 2)
    return score


def resolve_canonical(hit: AliasHit, line_norm: str, page_context: str, catalog: ReferenceCatalog) -> str | None:
    if len(hit.canonical_names) == 1:
        return hit.canonical_names[0]

    scored = []
    for name in hit.canonical_names:
        definition = catalog.registry[name]
        score = _unit_score(line_norm, definition) + _category_score(page_context, definition)
        scored.append((score, name))

    scored.sort(reverse=True)
    if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1]

    # Ambiguous aliases such as GLUCOSA can refer to serum or urine. It is safer
    # to skip an unresolved row than silently attach it to the wrong analyte.
    return None


def _extract_value(line_norm: str, end: int) -> float | str | None:
    remainder = line_norm[end:].strip(" :-;|")
    number = NUM_RE.search(remainder)
    if number:
        return float(number.group())

    for phrase in sorted(QUALITATIVE_VALUES, key=len, reverse=True):
        if remainder.startswith(phrase):
            return phrase
    return None


def _age_matches(ref: ReferenceRange, age: int | None) -> bool:
    if age is None:
        return True
    if ref.age_min is not None and age < ref.age_min:
        return False
    if ref.age_max is not None and age > ref.age_max:
        return False
    return True


def _sex_matches(ref_sex: str | None, patient_sex: str | None) -> bool:
    ref = normalize(ref_sex or "")
    patient = normalize_sex(patient_sex)
    if ref in UNISEX:
        return True
    return patient is not None and normalize_sex(ref) == patient


def _condition_matches(ref: ReferenceRange, condition: str | None) -> bool:
    if not condition:
        return not ref.condition
    if not ref.condition:
        return True
    a, b = normalize(condition), normalize(ref.condition)
    return a in b or b in a


def select_reference(references: list[ReferenceRange], age: int | None, sex: str | None, context: dict | None = None) -> tuple[ReferenceRange | None, str | None]:
    context = context or {}
    condition = context.get("condition")
    time_value = context.get("time_value")
    time_unit = normalize(context.get("time_unit", "")) if context.get("time_unit") else None

    candidates = [ref for ref in references if _age_matches(ref, age)]
    if not candidates:
        return None, "NO_REFERENCE"

    sex_candidates = [ref for ref in candidates if _sex_matches(ref.sex, sex)] if sex else [ref for ref in candidates if normalize(ref.sex or "") in UNISEX]
    if sex_candidates:
        candidates = sex_candidates

    if time_value is not None:
        timed = [ref for ref in candidates if ref.time_value == float(time_value) and (not time_unit or normalize(ref.time_unit or "") == time_unit)]
        if timed:
            candidates = timed
    else:
        untimed = [ref for ref in candidates if ref.time_value is None]
        if untimed:
            candidates = untimed

    if condition:
        conditioned = [ref for ref in candidates if _condition_matches(ref, str(condition))]
        if conditioned:
            candidates = conditioned
    else:
        unconditional = [ref for ref in candidates if not ref.condition]
        if unconditional:
            candidates = unconditional

    if not candidates:
        return None, "NO_REFERENCE"

    def specificity(ref: ReferenceRange) -> tuple[int, int, int]:
        return (
            int(ref.age_min is not None) + int(ref.age_max is not None),
            int(normalize(ref.sex or "") not in UNISEX),
            int(bool(ref.condition)),
        )

    best_score = max(specificity(ref) for ref in candidates)
    best = [ref for ref in candidates if specificity(ref) == best_score]
    if len(best) == 1:
        return best[0], None

    signatures = {(ref.lower, ref.upper, ref.reference_text, ref.condition, ref.time_value) for ref in best}
    if len(signatures) == 1:
        return best[0], None
    return None, "AMBIGUOUS_REFERENCE"


def classify_value(value: float | str, ref: ReferenceRange | None, missing_status: str | None = None) -> str:
    if ref is None:
        return missing_status or "NO_REFERENCE"

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = float(value)
        if ref.lower is not None and value < ref.lower:
            return "LOW"
        if ref.upper is not None and value > ref.upper:
            return "HIGH"
        if ref.lower is not None or ref.upper is not None:
            return "NORMAL"

        text = normalize(ref.reference_text or "")
        gray = re.search(r"ZONA GRIS\s*:?\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", text)
        neg = re.search(r"NEGATIVO\s*:?\s*<\s*=?\s*(\d+(?:\.\d+)?)", text)
        pos = re.search(r"POSITIVO\s*:?\s*>\s*=?\s*(\d+(?:\.\d+)?)", text)
        if gray and float(gray.group(1)) <= value <= float(gray.group(2)):
            return "GRAY_ZONE"
        if neg and value < float(neg.group(1)):
            return "NORMAL"
        if pos and value >= float(pos.group(1)):
            return "POSITIVE"
        return "REFERENCE_TEXT" if ref.reference_text else "NO_REFERENCE"

    value_norm = normalize(str(value))
    reference_norm = normalize(ref.reference_text or "")
    return "NORMAL" if value_norm and reference_norm and value_norm in reference_norm else "REFERENCE_TEXT"


def _lookahead_value(normalized_lines: list[str], index: int, catalog: ReferenceCatalog, page_context: str, max_lines: int = 2) -> float | str | None:
    for offset in range(1, max_lines + 1):
        j = index + offset
        if j >= len(normalized_lines):
            break
        next_line = normalized_lines[j]
        hit = catalog.find(next_line)
        if hit and resolve_canonical(hit, next_line, page_context, catalog) is not None:
            break
        value = _extract_value(next_line, 0)
        if value is not None:
            return value
    return None


def parse_results(doc: fitz.Document, catalog: ReferenceCatalog, age: int | None, sex: str | None, reference_context: dict[str, dict] | None = None) -> dict[str, LabResult]:
    results: dict[str, LabResult] = {}
    reference_context = reference_context or {}

    for page in doc:
        raw_lines = iter_lines(page)
        normalized_lines = [normalize(line) for line in raw_lines]
        page_context = " ".join(normalized_lines[:40])

        for i, line_norm in enumerate(normalized_lines):
            hit = catalog.find(line_norm)
            source_norm = line_norm

            if hit is None and i + 1 < len(normalized_lines):
                joined = f"{line_norm} {normalized_lines[i + 1]}"
                hit = catalog.find(joined)
                if hit:
                    source_norm = joined

            if hit is None:
                continue

            canonical_name = resolve_canonical(hit, source_norm, page_context, catalog)
            if canonical_name is None or canonical_name in results:
                continue

            value = _extract_value(source_norm, hit.end)
            if value is None:
                value = _lookahead_value(normalized_lines, i, catalog, page_context)
            if value is None:
                continue

            definition = catalog.registry[canonical_name]
            ref, ref_status = select_reference(definition.references, age, sex, reference_context.get(canonical_name))
            fallback = definition.references[0] if definition.references else None
            status = classify_value(value, ref, ref_status)

            results[canonical_name] = LabResult(
                canonical_name=canonical_name,
                test_name=ref.test_name if ref else (fallback.test_name if fallback else canonical_name),
                value=value,
                category=ref.category if ref else (fallback.category if fallback else None),
                unit=ref.unit if ref else (fallback.unit if fallback else None),
                reference_low=ref.lower if ref else None,
                reference_high=ref.upper if ref else None,
                reference_text=ref.reference_text if ref else None,
                reference_condition=ref.condition if ref else None,
                reference_notes=ref.notes if ref else None,
                status=status,
                method=ref.method if ref else (fallback.method if fallback else None),
                sample_type=ref.sample_type if ref else (fallback.sample_type if fallback else None),
            )

    return results


def read_pdf(file_path: str, reference_csv: str | None = None, patient: Patient | None = None, reference_context: dict[str, dict] | None = None) -> MedicalExam:
    csv_path = Path(reference_csv) if reference_csv else _default_reference_csv()
    catalog = load_catalog(str(csv_path.resolve()))
    patient = patient or read_patient_info(file_path)

    doc = fitz.open(file_path)
    try:
        exam = MedicalExam()
        exam.fecha_toma_muestra = parse_toma_datetime(header_text(doc[0]), source=file_path)
        for result in parse_results(doc, catalog, patient.edad, patient.sexo, reference_context).values():
            exam.add_result(result)
        return exam
    finally:
        doc.close()


def read_patient_info(file_path: str) -> Patient:
    patient = Patient()
    doc = fitz.open(file_path)
    try:
        text = header_text(doc[0])
    finally:
        doc.close()

    if match := re.search(r"Paciente\s*[:;.]?\s+.*?(\d+)\s*$", text, re.MULTILINE):
        patient.patient_code = match.group(1)
    if match := re.search(r"Sexo\s*[:;.]?\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)", text, re.IGNORECASE):
        patient.sexo = match.group(1)
    if match := re.search(r"Edad\s*[:;.]?\s+(\d+)", text, re.IGNORECASE):
        patient.edad = int(match.group(1))
    if match := NACIMIENTO_RE.search(text):
        patient.fecha_nacimiento = coerce_date(match.group(1))

    toma = parse_toma_datetime(text, source=file_path)
    if patient.fecha_nacimiento and patient.edad is not None:
        check_edad(patient.fecha_nacimiento, toma, patient.edad, file_path)
    return patient