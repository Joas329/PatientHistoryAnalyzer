# app/theme.py
from __future__ import annotations

# -- palette ---------------------------------------------------------------
BG = "#0d1117" # app background, deepest
SURFACE = "#1a212b" # panels
SURFACE_2 = "#222c38" # cards on panels
SURFACE_3 = "#2c3846" # hover
BORDER = "#3d4b5c" # hairlines
BORDER_HI = "#4e6075" # focused

TEXT = "#e6edf3" # primary
TEXT_DIM = "#9aa7b4" # secondary
TEXT_MUTE = "#6b7785" # captions, disabled

ACCENT = "#2dd4bf" # teal: interactive only
ACCENT_DK = "#1a9d8f"

# Grade ramp: 0 calm slate, then amber -> deep red. Distinguishable in
# grayscale and for deuteranopia (no green/red pairing).
GRADE = {
    0: "#3d4b5a", # slate — normal
    1: "#c9a227", # amber
    2: "#e08b2e", # orange
    3: "#d95c34", # burnt orange
    4: "#c03434", # red — life-threatening
}
GRADE_TEXT = {0: "#c3cdd8", 1: "#1a1200", 2: "#1a1200", 3: "#ffffff", 4: "#ffffff"}
REVIEW_BG = "#2a3441" # neutral: "needs review" is NOT severity

COLORS = {
    "bg": BG, "surface": SURFACE, "surface_2": SURFACE_2, "surface_3": SURFACE_3,
    "border": BORDER, "border_hi": BORDER_HI,
    "text": TEXT, "text_dim": TEXT_DIM, "text_mute": TEXT_MUTE,
    "accent": ACCENT, "grade": GRADE, "grade_text": GRADE_TEXT, "review_bg": REVIEW_BG,
}

# -- stylesheet (applied once at the app root) -----------------------------
STYLESHEET = f"""
* {{
    font-family: "Inter", "Segoe UI", "Helvetica Neue", sans-serif;
    color: {TEXT};
}}

/* Base background for everything. Panels/cards override by object name
   (a more specific selector), so they keep their surface colour on top. */
QWidget {{ background-color: {BG}; }}

QLabel {{ background: transparent; border: none; }}

/* Panels ------------------------------------------------------------- */
QFrame#Panel {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#Card {{
    background-color: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

/* Content wrappers inside panels must be transparent, else they repaint
   the panel surface with the base colour and the frame appears to vanish. */
QWidget#Clear {{ background: transparent; }}

/* Toolbar ------------------------------------------------------------ */
QFrame#Toolbar {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

/* Buttons ------------------------------------------------------------ */
QPushButton {{
    background-color: {SURFACE_2};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover  {{ background-color: {SURFACE_3}; border-color: {BORDER_HI}; }}
QPushButton:pressed {{ background-color: {BG}; }}

QPushButton#Primary {{
    background-color: {ACCENT_DK};
    border-color: {ACCENT};
    color: #04211d;
    font-weight: 600;
}}
QPushButton#Primary:hover  {{ background-color: {ACCENT}; }}
QPushButton#Primary:pressed {{ background-color: {ACCENT_DK}; }}

/* Text roles --------------------------------------------------------- */
QLabel#Title {{ font-size: 15px; font-weight: 700; letter-spacing: 0.3px; }}
QLabel#PanelHdr {{ font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
                   color: {TEXT_MUTE}; }}
QLabel#Key {{ color: {TEXT_MUTE}; font-size: 12px; }}
QLabel#Value {{ color: {TEXT}; font-size: 14px; font-weight: 600; }}
QLabel#Status {{ color: {TEXT_DIM}; font-size: 12px; }}

/* Scroll ------------------------------------------------------------- */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER_HI}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {TEXT_MUTE}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""