import fitz
import re
import pytesseract
from PIL import Image

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

def extract_patient_code(words: list[str]) -> str | None:
    for w in words:
        print(w)
        if re.fullmatch(r"\d+", w):
            return w
    return None

def extract_int(words: list[str]) -> int | None:
    for w in words:
        if re.fullmatch(r"\d+", w):
            return int(w)
    return None

def extract_date(words: list[str]) -> str | None:
    text = " ".join(words)
    match = re.search(r"\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2}:\d{2})?", text)
    return match.group(0) if match else None

def extract_first_word(words: list[str]) -> str | None:
    return words[0] if words else None

def ocr_header_text(page) -> str:
    lines = iter_lines_ocr(page)
    return "\n".join(" ".join(words) for words in lines)

def first_number(words: list[str]) -> float | None:
    for w in words:
        if w == "*":
            continue
        if NUM_RE.fullmatch(w):
            return float(w)
    return None

PATIENT_INFO_FIELD_MAP = [
    ("Paciente", "patient_code", extract_patient_code),
    ("Sexo", "sexo", extract_first_word),
    ("Fe.Nac", "fecha_nacimiento", extract_date),
    ("Edad", "edad", extract_int),
    ("Fecha Toma", "fecha_toma_muestra", extract_date),
]

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

def iter_lines_ocr(page) -> list[list[str]]:
    pix = page.get_pixmap(dpi=300)

    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    # Crop top 300 pixels: left, top, right, bottom
    img = img.crop((0, 500, pix.width, 900))

    text = pytesseract.image_to_string(img, config="--psm 6")

    lines = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            lines.append(line.split())

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

            # bare section header: label is the whole line, no trailing text — skip to the real row.
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
            # print(f"{label}: {value}")
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
            ocr_header_text(page1), source=file_path
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
        text = ocr_header_text(doc[0])
    finally:
        doc.close()

    if m := re.search(r"Paciente\s*[:;.]?\s+.*?\s+(\d+)", text):
        patient.patient_code = m.group(1)
    if m := re.search(r"Sexo\s*[:;.]?\s+(\w+)", text, re.IGNORECASE):
        patient.sexo = m.group(1)
    if m := re.search(r"Edad\s*[:;.]?\s+(\d+)", text, re.IGNORECASE):
        patient.edad = int(m.group(1))
    if m := NACIMIENTO_RE.search(text):
        patient.fecha_nacimiento = coerce_date(m.group(1))

    # Free sanity check: does the birth date actually produce `edad`?
    toma = parse_toma_datetime(text, source=file_path)
    if patient.fecha_nacimiento and patient.edad is not None:
        if not check_edad(patient.fecha_nacimiento, patient.edad, toma):
            raise ValueError(
                f"{file_path}: Fe.Nac {patient.fecha_nacimiento:%d/%m/%Y} does not yield "
                f"edad {patient.edad} at {toma:%d/%m/%Y} — dd/mm vs mm/dd may be inverted"
            )
    return patient

if __name__ == "__main__":
    file_path = "./data/202616390945_MK2870011.pdf"
    medical_exam = read_patient_info(file_path)
    print(medical_exam)