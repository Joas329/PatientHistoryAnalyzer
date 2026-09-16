# app/pages/timeline.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from ..dates import coerce_date
from .theme import COLORS

_G = COLORS["grade"]
_GT = COLORS["grade_text"]


def _bubble_css(bg: str, fg: str) -> str:
    return (f"background-color:{bg}; color:{fg}; border:none; border-radius:11px; font-size:12px; font-weight:700; padding:2px 9px;")

def _format_number(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"{value:g}"

def _format_lab_value(result) -> str:
    if result.is_numeric:
        text = _format_number(float(result.value))
    else:
        text = str(result.value)

    if result.unit:
        text += f" {result.unit}"

    return text

def _format_reference(result) -> str:
    low = result.reference_low
    high = result.reference_high

    if low is not None and high is not None:
        return f"{_format_number(low)}–{_format_number(high)}"

    if low is not None:
        return f"≥ {_format_number(low)}"

    if high is not None:
        return f"≤ {_format_number(high)}"

    if result.reference_text:
        return result.reference_text

    return "—"

def _range_arrow(result) -> str:
    if result.direction == "low":
        return "↓"
    if result.direction == "high":
        return "↑"
    if result.status == "GRAY_ZONE":
        return "◆"
    return "•"

class Bubble(QLabel):
    def __init__(self, text: str, grade: int = 0, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(22)
        self.setMinimumWidth(22)
        self.setStyleSheet(_bubble_css(_G.get(grade, _G[0]), _GT.get(grade, _GT[0])))


class ExamCard(QFrame):
    def __init__(self, exam, parent=None):
        super().__init__(parent)
        self.exam = exam
        self._expanded = False
        self.setObjectName("Card")

        flagged = exam.flagged
        worst = exam.worst_grade
        range_flags = exam.range_flags

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QWidget()
        body.setStyleSheet(f"border-left:3px solid {_G.get(worst, _G[0])}; border-top-left-radius:8px; border-bottom-left-radius:8px;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 11, 14, 11)
        bl.setSpacing(0)
        outer.addWidget(body)

        # header
        header = QWidget()
        header.setCursor(Qt.PointingHandCursor)
        header.setStyleSheet("border:none;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(10)

        when = coerce_date(exam.fecha_toma_muestra)

        self.chevron = QLabel("\u203a")
        self.chevron.setStyleSheet(f"color:{COLORS['text_mute']}; font-size:16px; border:none;")
        self.chevron.setFixedWidth(10)

        date_lbl = QLabel(when.strftime("%d %b %Y").lstrip("0") if when else "Fecha desconocida")
        date_lbl.setStyleSheet(f"color:{COLORS['text']}; font-size:14px; font-weight:600; border:none;")

        time_lbl = None
        if when:
            time_lbl = QLabel(when.strftime("%H:%M"))
            time_lbl.setStyleSheet(f"color:{COLORS['text_mute']}; font-size:12px; border:none;")

        hl.addWidget(self.chevron)
        hl.addWidget(date_lbl)
        if time_lbl is not None:
            hl.addWidget(time_lbl)
        hl.addStretch()

        if worst:
            cap = QLabel("peor grado")
            cap.setStyleSheet(f"color:{COLORS['text_mute']}; font-size:11px; border:none;")
            hl.addWidget(cap)
            hl.addWidget(Bubble(f"G{worst}", worst))
        n_lbl = QLabel(f"{len(flagged)} eventos")
        n_lbl.setStyleSheet(f"color:{COLORS['text_dim']}; font-size:12px; border:none;")
        hl.addWidget(n_lbl)

        if range_flags:
            oor = QLabel(f"{len(range_flags)} fuera de rango")
            oor.setStyleSheet(f"color:{COLORS['text_mute']}; font-size:11px; border:none;")
            hl.addWidget(oor)

        bl.addWidget(header)

        # Details
        self.details = QWidget()
        self.details.setStyleSheet("border:none;")
        dl = QVBoxLayout(self.details)
        dl.setContentsMargins(20, 12, 0, 2)
        dl.setSpacing(7)

        if not flagged and not range_flags:
            empty = QLabel("Sin hallazgos.")
            empty.setStyleSheet(f"color:{COLORS['text_mute']}; font-size:12px; border:none;")
            dl.addWidget(empty)

        if flagged:
            event_head = QLabel("CTCAE")
            event_head.setStyleSheet(f"color:{COLORS['text_mute']}; font-size:10px; font-weight:700; letter-spacing:1px; border:none; padding-top:2px;")
            dl.addWidget(event_head)

            for event in flagged:
                dl.addWidget(self._event_row(event))

        if range_flags:
            head = QLabel("FUERA DE RANGO (vs. referencia del laboratorio)")
            head.setStyleSheet(f"color:{COLORS['text_mute']}; font-size:10px; font-weight:700; letter-spacing:1px; border:none; padding-top:6px;")
            dl.addWidget(head)

            for result in range_flags:
                dl.addWidget(self._lab_result_row(result))

        self.details.setVisible(False)
        bl.addWidget(self.details)

        header.mousePressEvent = self._toggle

    def _lab_result_row(self, result) -> QLabel:
        arrow = _range_arrow(result)
        value_text = _format_lab_value(result)
        reference_text = _format_reference(result)

        row = QLabel(f"{arrow} {result.display_name}: {value_text}  (ref {reference_text})")
        row.setWordWrap(True)
        row.setStyleSheet(f"color:{COLORS['text_dim']}; font-size:12px; border:none;")

        tooltip = [
            f"Canonical name: {result.canonical_name}",
            f"Status: {result.status or '—'}",
        ]

        if result.category:
            tooltip.append(f"Category: {result.category}")

        if result.method:
            tooltip.append(f"Method: {result.method}")

        if result.sample_type:
            tooltip.append(f"Sample: {result.sample_type}")

        if result.reference_condition:
            tooltip.append(f"Reference condition: {result.reference_condition}")

        if result.reference_notes:
            tooltip.append(f"Reference notes: {result.reference_notes}")

        row.setToolTip("\n".join(tooltip))
        return row

    def _event_row(self, ev) -> QWidget:
        row = QWidget()
        row.setStyleSheet("border:none;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)

        grade = ev.grade or 0
        rl.addWidget(Bubble(f"G{grade}", grade))

        term = QLabel(ev.term or ev.type or "CTCAE event")
        term.setStyleSheet(f"color:{COLORS['text']}; font-size:13px; font-weight:500; border:none;")
        rl.addWidget(term)
        rl.addStretch()

        if isinstance(ev.value, (int, float)):
            value_text = f"{ev.value:g}"
        else:
            value_text = str(ev.value)

        if ev.unit:
            value_text += f" {ev.unit}"

        val = QLabel(value_text)
        val.setStyleSheet(f"color:{COLORS['text_dim']}; font-size:13px; font-weight:600; border:none;")
        rl.addWidget(val)

        rng = getattr(ev, "normal_range", None)
        if rng is not None:
            ref = QLabel(str(rng))
            ref.setStyleSheet(f"color:{COLORS['text_mute']}; font-size:11px; border:none;")
            rl.addWidget(ref)
        return row

    def _toggle(self, _event) -> None:
        self._expanded = not self._expanded
        self.details.setVisible(self._expanded)
        self.chevron.setText("\u2304" if self._expanded else "\u203a")

class TimelineWidget(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)

        self._body = QWidget()
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(0, 0, 8, 0)
        self._layout.setSpacing(8)
        self._layout.addStretch()
        self.setWidget(self._body)

    def clear(self) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def populate(self, patient) -> None:
        self.clear()
        exams = _sorted(patient.medical_records)
        if not exams:
            empty = QLabel("No hay exámenes cargados.")
            empty.setStyleSheet(f"color:{COLORS['text_mute']}; font-size:13px;")
            self._layout.insertWidget(0, empty)
            return
        for i, exam in enumerate(exams):
            card = ExamCard(exam)
            card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            self._layout.insertWidget(i, card)


def _sorted(exams: list) -> list:
    # Dated exams newest-first; undated exams last, original order preserved.
    dated = []
    undated = []

    for index, exam in enumerate(exams):
        date = coerce_date(exam.fecha_toma_muestra)

        if date:
            dated.append((date, index, exam))
        else:
            undated.append((date, index, exam))

    dated.sort(key=lambda item: item[1])
    dated.sort(key=lambda item: item[0], reverse=True)

    return [item[2] for item in dated] + [item[2] for item in undated]
