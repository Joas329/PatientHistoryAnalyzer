from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_SUPERSCRIPT = str.maketrans({"³": "3", "²": "2", "µ": "u", "μ": "u"})


def normalize(label: str) -> str:
    """Casefold, strip accents/punctuation, collapse whitespace.

    'Neutrófilos Segmentados (%)' -> 'neutrofilos segmentados'
    """
    s = label.translate(_SUPERSCRIPT)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9%\s]", " ", s)   # keep % : it distinguishes pct from abs
    s = re.sub(r"\s+", " ", s).strip()
    return s


class UnknownLabelError(KeyError):
    """A PDF label that is not in the lexicon. Never guess — add it."""


class AmbiguousNumberError(ValueError):
    """A numeric string with more than one plausible interpretation."""


# ---------------------------------------------------------------------------
# Lexicon: Spanish label -> canonical Hemograma field
# ---------------------------------------------------------------------------
# Curated by hand. Add aliases as you meet them; never fuzzy-match.

_ALIASES: dict[str, tuple[str, ...]] = {
    "hemoglobina": ("hemoglobina", "hb", "hgb", "hemoglobina hb"),
    "hematocrito": ("hematocrito", "hto", "hct"),
    "hematies": ("hematies", "eritrocitos", "globulos rojos", "recuento de hematies", "rbc"),
    "volumen_corpuscular_medio": ("volumen corpuscular medio", "vcm", "mcv"),
    "hemoglobina_corpuscular_media": ("hemoglobina corpuscular media", "hcm", "mch"),
    "concentracion_hemoglobina_corpuscular": (
        "concentracion de hemoglobina corpuscular media", "concentracion hemoglobina corpuscular",
        "chcm", "mchc",
    ),
    "rdw_pct": ("rdw", "rdw %", "rdw cv", "amplitud de distribucion eritrocitaria"),
    "rdw_sd": ("rdw sd",),
    "leucocitos_totales": (
        "leucocitos", "leucocitos totales", "globulos blancos",
        "recuento de leucocitos", "wbc", "cuenta de leucocitos",
    ),
    "eosinofilos_pct": ("eosinofilos %", "eosinofilos", "eos %"),
    "basofilos_pct": ("basofilos %", "basofilos", "baso %"),
    "linfocitos_pct": ("linfocitos %", "linfocitos", "linf %"),
    "monocitos_pct": ("monocitos %", "monocitos", "mono %"),
    "neutrofilos_segmentados_pct": (
        "segmentados", "segmentados %", "neutrofilos segmentados",
        "neutrofilos segmentados %", "neutrofilos %",
    ),
    # 'Abastonados' is the Peruvian term for band cells.
    "bastones_pct": ("abastonados", "abastonados %", "bastones", "bastones %", "cayados"),
    "eosinofilos_abs": ("eosinofilos absolutos", "eosinofilos abs", "recuento absoluto de eosinofilos"),
    "basofilos_abs": ("basofilos absolutos", "basofilos abs"),
    "linfocitos_abs": ("linfocitos absolutos", "linfocitos abs", "recuento absoluto de linfocitos"),
    "monocitos_abs": ("monocitos absolutos", "monocitos abs"),
    "neutrofilos_segmentados_abs": ("segmentados absolutos", "neutrofilos segmentados absolutos"),
    "bastones_abs": ("abastonados absolutos", "bastones absolutos"),
    "recuento_plaquetas": ("plaquetas", "recuento de plaquetas", "recuento plaquetario", "plt"),
    "volumen_plaquetario_medio": ("volumen plaquetario medio", "vpm", "mpv"),
    "neutrofilos_totales_anc": (
        "neutrofilos totales", "neutrofilos absolutos", "recuento absoluto de neutrofilos",
        "anc", "rat", "neutrofilos totales anc",
    ),
}

# invert, normalising every alias
_LOOKUP: dict[str, str] = {}
for _field, _names in _ALIASES.items():
    for _n in _names:
        key = normalize(_n)
        if key in _LOOKUP and _LOOKUP[key] != _field:
            raise RuntimeError(f"lexicon collision: {key!r} -> {_LOOKUP[key]} and {_field}")
        _LOOKUP[key] = _field


def _candidates(raw: str) -> list[str]:
    """Deterministic rewrites of a label, tried in order. No fuzzy matching.

    'Volumen Corpuscular Medio (VCM)' -> ['volumen corpuscular medio vcm',
                                          'volumen corpuscular medio', 'vcm']
    """
    parens = re.findall(r"\(([^)]*)\)", raw)
    stripped = re.sub(r"\([^)]*\)", " ", raw)
    cands = [normalize(raw), normalize(stripped)]
    cands += [normalize(p) for p in parens]
    out: list[str] = []
    for c in cands:                       # dedupe, drop empties and bare '%'
        if c and c != "%" and c not in out:
            out.append(c)
    return out


def resolve_label(raw: str) -> str:
    """Spanish PDF label -> canonical field name. Raises on anything unknown."""
    tried = _candidates(raw)
    for key in tried:
        field = _LOOKUP.get(key)
        if field is not None:
            return field
    raise UnknownLabelError(
        f"label {raw!r} (tried {tried}) is not in the lexicon; "
        "add it to _ALIASES rather than guessing"
    )


# ---------------------------------------------------------------------------
# Numbers: resolve decimal-separator ambiguity by plausibility, not by locale
# ---------------------------------------------------------------------------
# Plausible ranges in the unit the field is normally REPORTED in
# (counts -> /mm3, hemoglobina -> g/dL, percentages -> %).
_PLAUSIBLE_RAW: dict[str, tuple[float, float]] = {
    "hemoglobina": (1.0, 30.0),
    "hematocrito": (5.0, 70.0),
    "hematies": (0.5, 9.0),
    "volumen_corpuscular_medio": (40.0, 140.0),
    "hemoglobina_corpuscular_media": (10.0, 50.0),
    "concentracion_hemoglobina_corpuscular": (20.0, 40.0),
    "rdw_pct": (5.0, 40.0),
    "rdw_sd": (20.0, 100.0),
    "leucocitos_totales": (50.0, 500_000.0),
    "recuento_plaquetas": (1_000.0, 2_000_000.0),
    "volumen_plaquetario_medio": (5.0, 20.0),
    "neutrofilos_totales_anc": (0.0, 200_000.0),
}
for _f in ("eosinofilos", "basofilos", "linfocitos", "monocitos",
           "neutrofilos_segmentados", "bastones"):
    _PLAUSIBLE_RAW[f"{_f}_pct"] = (0.0, 100.0)
    _PLAUSIBLE_RAW[f"{_f}_abs"] = (0.0, 200_000.0)


def _interpretations(token: str) -> set[float]:
    """Every way a human could reasonably read this numeric string."""
    t = token.strip().replace(" ", "")
    out: set[float] = set()
    if not re.fullmatch(r"[\d.,]+", t):
        raise ValueError(f"{token!r} is not numeric")

    has_dot, has_comma = "." in t, "," in t
    if has_dot and has_comma:
        # the LAST separator is the decimal one
        dec = "." if t.rfind(".") > t.rfind(",") else ","
        grp = "," if dec == "." else "."
        out.add(float(t.replace(grp, "").replace(dec, ".")))
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        # (a) decimal separator
        if t.count(sep) == 1:
            out.add(float(t.replace(sep, ".")))
        # (b) thousands separator
        if re.fullmatch(rf"\d{{1,3}}(\{sep}\d{{3}})+", t):
            out.add(float(t.replace(sep, "")))
    else:
        out.add(float(t))
    return out


def parse_value(field: str, token: str) -> float:
    """Parse a Spanish-formatted number, disambiguated by clinical plausibility.

    '45.000' and '45,000' both -> 45000.0 for plaquetas, because 45.0 /mm3
    is not a survivable platelet count. Raises rather than guessing.
    """
    lo, hi = _PLAUSIBLE_RAW[field]
    cands = _interpretations(token)
    ok = {v for v in cands if lo <= v <= hi}
    if len(ok) == 1:
        return ok.pop()
    if not ok:
        raise ValueError(
            f"{field}={token!r} gives {sorted(cands)}, none plausible for range [{lo}, {hi}]"
        )
    raise AmbiguousNumberError(
        f"{field}={token!r} is ambiguous: {sorted(ok)} are all plausible; "
        "resolve the decimal separator upstream"
    )


# ---------------------------------------------------------------------------
# Output: CTCAE term -> Spanish, for display only. NEVER used as a key.
# ---------------------------------------------------------------------------
TERM_ES: dict[str, str] = {
    "Anemia": "Anemia",
    "White blood cell decreased": "Recuento de leucocitos disminuido",
    "Neutrophil count decreased": "Recuento de neutrófilos disminuido",
    "Lymphocyte count decreased": "Recuento de linfocitos disminuido",
    "Lymphocyte count increased": "Recuento de linfocitos aumentado",
    "Platelet count decreased": "Recuento de plaquetas disminuido",
    "Leukocytosis": "Leucocitosis",
    "Eosinophilia": "Eosinofilia",
    "Hemoglobin increased": "Hemoglobina aumentada",
}

STATUS_ES = {
    "graded": "graduado",
    "normal": "normal",
    "missing": "ausente",
    "no_ctcae_term": "sin término CTCAE",
    "not_gradeable": "no graduable",
}


def term_es(term: str) -> str:
    """Display-only. Unofficial: NCI publishes no Spanish clinician CTCAE."""
    return TERM_ES.get(term, term)


def parse_hemogram_lines(lines: list[tuple[str, str]]) -> dict[str, float]:
    """[(label, value_token), ...] -> {canonical_field: value}. Raises loudly."""
    out: dict[str, float] = {}
    for label, token in lines:
        field = resolve_label(label)
        out[field] = parse_value(field, token)
    return out