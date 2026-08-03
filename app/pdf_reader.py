import fitz
import re

from .Patient import MedicalExam, Hemograma, Patient
from .dates import parse_toma_datetime, coerce_date, check_edad, NACIMIENTO_RE

NUM_RE = re.compile(r"\d+(?:\.\d+)?")

# (label as it appears in the PDF, attribute name)
FIELD_MAP = [
    ("Hemoglobina Corpuscular Media", "hemoglobina_corpuscular_media"),
    ("Hemoglobina (Método: Fotometria)", "hemoglobina"),
    ("Hematocrito", "hematocrito"),
    ("Hematíes", "hematies"),
    ("Volumen Corpuscular Medio", "volumen_corpuscular_medio"),
    ("Concentración de la Hemoglobina Corpuscular", "concentracion_hemoglobina_corpuscular"),
    ("Indice de Anisocitosis (RDW) (%)", "rdw_pct"),
    ("Indice de Anisocitosis (RDW) (SD)", "rdw_sd"),
    ("Leucocitos Totales", "leucocitos_totales"),
    ("Eosinófilos (%)", "eosinofilos_pct"),
    ("Eosinófilos (10^3/UL)", "eosinofilos_abs"),
    ("Basófilos (%)", "basofilos_pct"),
    ("Basófilos (10^3/UL)", "basofilos_abs"),
    ("Linfocitos (%)", "linfocitos_pct"),
    ("Linfocitos (10^3/UL)", "linfocitos_abs"),
    ("Monocitos (%)", "monocitos_pct"),
    ("Monocitos (10^3/UL)", "monocitos_abs"),
    ("Neutrófilos Segmentados (%)", "neutrofilos_segmentados_pct"),
    ("Neutrófilos Segmentados (10^3/UL)", "neutrofilos_segmentados_abs"),
    ("Neutrófilos Totales (ANC)", "neutrofilos_totales_anc"),
    ("Bastones (%)", "bastones_pct"),
    ("Bastones (10^3/UL)", "bastones_abs"),
    ("Recuento de Plaquetas", "recuento_plaquetas"),
    ("Volumen Plaquetario Medio", "volumen_plaquetario_medio"),
]

CHEM_FIELDS = [
    ("Glucosa (sérica)", "glucosa"),
    ("Urea sérica", "urea_serica"),
    ("Nitrógeno Ureico BUN", "nitrogeno_ureico_bun"),
    ("CREATININA sérica", "creatinina_serica"),
    ("Transaminasa Pirúvica (ALT)", "transaminasa_piruvica"),
    ("Transaminasa Oxalacética (AST)", "transaminasa_oxalacetica"),
    ("BILIRRUBINA TOTAL", "bilirrubina_total"),
    ("BILIRRUBINA INDIRECTA", "bilirrubina_indirecta"),
    ("BILIRRUBINA DIRECTA", "bilirrubina_directa"),
    ("Fosfatasa Alcalina", "fosfatasa_alcalina"),
    ("Proteínas Totales", "proteinas_totales"),
    ("Albumina sérica", "albumina"),
    ("Calcio sérico", "calcio_serico"),
    ("FOSFORO, sérico", "fosforo_serico"),
    ("SODIO", "sodio"),
    ("POTASIO", "potasio"),
    ("CLORO", "cloro"),
    ("BICARBONATO SERICO", "bicarbonato_serico"),
]

# labels that also appear as bare section headers (header line has no value)
_ALSO_HEADERS = {"SODIO", "POTASIO", "CLORO", "BICARBONATO SERICO"}


def header_text(page) -> str:
    """Header text from the PDF's own text layer (no OCR / no Tesseract)."""
    text = page.get_text("text")
    return "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())


def first_number(words: list[str]) -> float | None:
    for w in words:
        if w == "*":
            continue
        if NUM_RE.fullmatch(w):
            return float(w)
    return None


def iter_lines(page) -> list[list[str]]:
    data = page.get_text("dict")
    lines = []
    for block in data["blocks"]:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            words = []
            for span in line["spans"]:
                words.extend(span["text"].split())
            if words:
                lines.append(words)
    return lines


def parse_chemistry(lines: list[list[str]], exam) -> None:
    n = len(lines)
    seen = set()
    for i, words in enumerate(lines):
        text = " ".join(words)
        for label, attr in CHEM_FIELDS:
            if label not in text or attr in seen:
                continue
            after = text.split(label, 1)[1]
            value = first_number(after.split())

            # bare section header: label is the whole line, no trailing text -> skip to the real row.
            # a wrapped data-row label ("... (Método: OMNI C-") has trailing text, so fall through and look ahead
            if value is None and label in _ALSO_HEADERS and not after.strip():
                break
            # label may wrap; use next line only if it isn't another analyte row
            if value is None and i + 1 < n:
                nxt = lines[i + 1]
                if not any(l in " ".join(nxt) for l, _ in CHEM_FIELDS):
                    value = first_number(nxt)

            if value is None and i + 2 < n:
                nxt = lines[i + 2]
                if not any(l in " ".join(nxt) for l, _ in CHEM_FIELDS):
                    value = first_number(nxt)
            if value is None:
                break
            setattr(exam, attr, value)
            seen.add(attr)
            break


def parse_hemograma(page) -> Hemograma:
    hemograma = Hemograma()
    pending_attr = None  # attribute waiting for its value on a following line

    for words in iter_lines(page):
        text = " ".join(words)

        # Does this line start a new field?
        matched_label = None
        matched_attr = None
        for label, attr in FIELD_MAP:
            if text.startswith(label):
                matched_label = label
                matched_attr = attr
                break

        if matched_attr is not None:
            # Try to find the value on the same line, after the label.
            rest = text[len(matched_label):].split()
            value = first_number(rest)
            if value is not None:
                setattr(hemograma, matched_attr, value)
                pending_attr = None
            else:
                # Value must be on a following line.
                pending_attr = matched_attr
            continue

        # No label on this line: if we're waiting for a value, grab it here.
        if pending_attr is not None:
            value = first_number(words)
            if value is not None:
                setattr(hemograma, pending_attr, value)
                pending_attr = None

    return hemograma


def read_pdf(file_path: str) -> MedicalExam:
    doc = fitz.open(file_path)
    try:
        exam = MedicalExam()

        page1 = doc[0]
        exam.hemograma = parse_hemograma(page1)
        exam.fecha_toma_muestra = parse_toma_datetime(
            header_text(page1), source=file_path
        )

        chem_lines: list[list[str]] = []
        for pno in range(1, doc.page_count):
            chem_lines.extend(iter_lines(doc[pno]))
        parse_chemistry(chem_lines, exam)

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

    # Labels and values sit on separate lines in the text layer
    # (e.g. "Paciente:\nMK-2870-011 .. 260100001"), so allow a newline between
    # the label and the value. The patient code is the trailing run of digits.
    if m := re.search(r"Paciente\s*[:;.]?\s+.*?(\d+)\s*$", text, re.MULTILINE):
        patient.patient_code = m.group(1)
    if m := re.search(r"Sexo\s*[:;.]?\s+(\w+)", text, re.IGNORECASE):
        patient.sexo = m.group(1)
    if m := re.search(r"Edad\s*[:;.]?\s+(\d+)", text, re.IGNORECASE):
        patient.edad = int(m.group(1))
    if m := NACIMIENTO_RE.search(text):
        patient.fecha_nacimiento = coerce_date(m.group(1))

    # Free sanity check: raises EdadMismatchError only on a real conflict
    # (swap-reconciled inversion, or a gap wider than the birthday-boundary slack).
    toma = parse_toma_datetime(text, source=file_path)
    if patient.fecha_nacimiento and patient.edad is not None:
        check_edad(patient.fecha_nacimiento, toma, patient.edad, file_path)

    return patient

if __name__ == "__main__":
    file_path = "./data/202616390945_MK2870011.pdf"
    medical_exam = read_patient_info(file_path)
    print(medical_exam)