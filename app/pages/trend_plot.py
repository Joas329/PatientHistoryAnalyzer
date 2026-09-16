# app/pages/trend_plot.py

import math
import re

import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import QEvent, QObject, QSize
from PySide6.QtWidgets import QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStyle, QVBoxLayout, QWidget

from .theme import COLORS


_SERIES_COLOR = "#4fd6be"
_BAND_COLOR = "#3ddc84"
_BAD_POINT = "#f7768e"
_DEFAULT_ROWS = 3
_ROW_MIN_HEIGHT = 260


def _result(exam, canonical_name):
    return exam.results.get(canonical_name)


def _numeric_result(exam, canonical_name):
    result = _result(exam, canonical_name)
    if result is None or not result.is_numeric:
        return None
    return result


def _clean_label(test_name: str | None, canonical_name: str) -> str:
    if not test_name:
        return canonical_name.replace("_", " ").title()

    # Prefer the first (usually Spanish) name when the CSV contains
    # bilingual names separated by " / ".
    label = re.split(r"\s+/\s+", test_name, maxsplit=1)[0].strip()

    # Do not show method annotations in the plot picker/title.
    label = re.sub(r"\s*\((?:MÉTODO|METODO|METHOD)[^)]*\)\s*$", "", label, flags=re.IGNORECASE).strip()

    return label or canonical_name.replace("_", " ").title()


def _metadata_for(exams, canonical_name):
    for exam in exams:
        result = _result(exam, canonical_name)
        if result is not None:
            return {
                "label": _clean_label(result.test_name, canonical_name),
                "unit": result.unit or "",
                "category": result.category or "",
            }

    return {
        "label": canonical_name.replace("_", " ").title(),
        "unit": "",
        "category": "",
    }


def _is_bad(result) -> bool:
    return result is not None and result.is_out_of_range

def _outside_reference_fraction(result) -> float:
    """Return normalized distance outside the selected lab reference interval."""
    if result is None or not result.is_numeric:
        return 0.0

    value = float(result.value)
    low = result.reference_low
    high = result.reference_high

    if low is not None and value < low:
        return (float(low) - value) / max(abs(float(low)), 1e-12)

    if high is not None and value > high:
        return (value - float(high)) / max(abs(float(high)), 1e-12)

    return 0.0

def _trend_priority(exams, canonical_name):
    """Score an analyte so the worst three trends are shown by default."""
    results = []
    ctcae_grade = 0

    for exam in exams:
        result = _numeric_result(exam, canonical_name)
        if result is not None:
            results.append(result)

        for event in getattr(exam, "events", []):
            if getattr(event, "type", None) == canonical_name and getattr(event, "grade", None) is not None:
                ctcae_grade = max(ctcae_grade, int(event.grade))

    if not results:
        return (0, 0.0, 0, 0.0, 0.0)

    excursions = [_outside_reference_fraction(result) for result in results]
    abnormal_count = sum(1 for result in results if _is_bad(result))
    abnormal_fraction = abnormal_count / len(results)
    latest_excursion = excursions[-1] if excursions else 0.0

    return (
        ctcae_grade,
        max(excursions, default=0.0),
        abnormal_count,
        abnormal_fraction,
        latest_excursion,
    )


class _WheelForwarder(QObject):
    def __init__(self, target):
        super().__init__(target)
        self._target = target

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            QApplication.sendEvent(self._target, event)
            return True
        return False


class MarkerPlot(QFrame):
    def __init__(self, canonical_name, label, unit, exams, on_remove, wheel_target):
        super().__init__()
        self.setObjectName("Card")
        self.setMinimumHeight(_ROW_MIN_HEIGHT)

        self.canonical_name = canonical_name
        self.attr = canonical_name  # compatibility with the previous widget code
        self._exams = exams
        self._on_remove = on_remove

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(10)

        name = QLabel(label)
        name.setStyleSheet(f"font-size:14px; font-weight:700; color:{COLORS.get('text', '#e6e6e6')};")

        self.remove_button = QPushButton()
        self.remove_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.remove_button.setIconSize(QSize(16, 16))
        self.remove_button.setFixedSize(30, 30)
        self.remove_button.setFlat(True)
        self.remove_button.setToolTip("Remove this plot")
        self.remove_button.clicked.connect(lambda: self._on_remove(self))

        head.addWidget(name)
        head.addStretch(1)
        head.addWidget(self.remove_button)
        lay.addLayout(head)

        panel_bg = COLORS.get("panel", "#12161c")
        self.fig = Figure(figsize=(5, 2.4), facecolor=panel_bg)
        self.canvas = FigureCanvas(self.fig)

        self._wheel_forwarder = _WheelForwarder(wheel_target)
        self.canvas.installEventFilter(self._wheel_forwarder)
        lay.addWidget(self.canvas, 1)

        self._draw(unit)

    def _draw(self, unit):
        dim = COLORS.get("text_dim", "#9aa4b2")
        panel_bg = COLORS.get("panel", "#12161c")
        grid_col = COLORS.get("line", "#2a3340")

        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(panel_bg)

        xs = []
        ys = []
        results = []

        for exam in self._exams:
            result = _numeric_result(exam, self.canonical_name)
            if result is None:
                continue

            xs.append(exam.fecha_toma_muestra)
            ys.append(float(result.value))
            results.append(result)

        if ys:
            self._draw_reference_ranges(ax, xs, results)

            ax.plot(xs, ys, marker="o", markersize=5, linewidth=1.8, color=_SERIES_COLOR, zorder=3)

            bad = [(x, y) for x, y, result in zip(xs, ys, results) if _is_bad(result)]
            if bad:
                bx, by = zip(*bad)
                ax.plot(bx, by, "o", markersize=6, color=_BAD_POINT, zorder=4)

            self._set_y_limits(ax, ys, results)
        else:
            ax.text(0.5, 0.5, "No numeric data", ha="center", va="center", transform=ax.transAxes, color=dim, fontsize=9)

        ax.set_ylabel(unit, color=dim, fontsize=8)
        ax.tick_params(colors=dim, labelsize=8)

        for spine in ax.spines.values():
            spine.set_color(grid_col)

        ax.grid(True, color=grid_col, alpha=0.35, linewidth=0.6)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        self.fig.autofmt_xdate(rotation=30, ha="right")
        self.fig.subplots_adjust(left=0.13, right=0.97, top=0.94, bottom=0.26)
        self.canvas.draw_idle()

    def _draw_reference_ranges(self, ax, xs, results):
        lows = [result.reference_low for result in results]
        highs = [result.reference_high for result in results]

        numeric_pairs = [(lo, hi) for lo, hi in zip(lows, highs) if lo is not None and hi is not None]

        # If all numeric references are the same, show the old-style flat band.
        if numeric_pairs and len(numeric_pairs) == len(results) and len(set(numeric_pairs)) == 1:
            lo, hi = numeric_pairs[0]
            ax.axhspan(lo, hi, color=_BAND_COLOR, alpha=0.12, zorder=0)
            ax.axhline(lo, color=_BAND_COLOR, alpha=0.55, linewidth=0.8, linestyle="--", zorder=1)
            ax.axhline(hi, color=_BAND_COLOR, alpha=0.55, linewidth=0.8, linestyle="--", zorder=1)
            return

        # Reference intervals can change with age/sex/condition. Draw the
        # actual range selected for each exam instead of using one global range.
        low_values = [float(lo) if lo is not None else math.nan for lo in lows]
        high_values = [float(hi) if hi is not None else math.nan for hi in highs]

        if any(lo is not None for lo in lows):
            ax.plot(xs, low_values, color=_BAND_COLOR, alpha=0.55, linewidth=0.8, linestyle="--", zorder=1)

        if any(hi is not None for hi in highs):
            ax.plot(xs, high_values, color=_BAND_COLOR, alpha=0.55, linewidth=0.8, linestyle="--", zorder=1)

        if any(lo is not None and hi is not None for lo, hi in zip(lows, highs)):
            ax.fill_between(xs, low_values, high_values, color=_BAND_COLOR, alpha=0.10, zorder=0)

    def _set_y_limits(self, ax, ys, results):
        bounds = list(ys)

        for result in results:
            if result.reference_low is not None:
                bounds.append(float(result.reference_low))
            if result.reference_high is not None:
                bounds.append(float(result.reference_high))

        if not bounds:
            return

        ymin = min(bounds)
        ymax = max(bounds)
        pad = (ymax - ymin) * 0.10 or (abs(ymax) * 0.10 or 1.0)
        ax.set_ylim(ymin - pad, ymax + pad)


class TrendPlotWidget(QWidget):
    def __init__(self):
        super().__init__()

        self._exams = []
        self._available = []
        self._metadata = {}
        self._rows = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.add_button = QPushButton("Add plot")
        self.add_button.setObjectName("Primary")
        self.add_button.clicked.connect(self._add_selected)

        marker_label = QLabel("Marker")
        marker_label.setObjectName("Key")

        self.add_combo = QComboBox()

        controls.addWidget(self.add_button)
        controls.addWidget(marker_label)
        controls.addWidget(self.add_combo, 1)
        lay.addLayout(controls)

        self.container = QWidget()
        self.rows_layout = QVBoxLayout(self.container)
        self.rows_layout.setContentsMargins(0, 0, 6, 0)
        self.rows_layout.setSpacing(12)
        self.rows_layout.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.container)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("background: transparent;")
        self.scroll.viewport().setStyleSheet("background: transparent;")
        lay.addWidget(self.scroll, 1)

    def _shown_attrs(self):
        return {row.canonical_name for row in self._rows}

    def _refresh_combo(self):
        shown = self._shown_attrs()
        remaining = [name for name in self._available if name not in shown]

        self.add_combo.blockSignals(True)
        self.add_combo.clear()

        for canonical_name in remaining:
            meta = self._metadata[canonical_name]
            label = meta["label"]

            if meta["category"]:
                label = f"{meta['category']} · {label}"

            self.add_combo.addItem(label, canonical_name)

        self.add_combo.blockSignals(False)

        can_add = bool(remaining)
        self.add_combo.setEnabled(can_add)
        self.add_button.setEnabled(can_add)

    def _add_row(self, canonical_name):
        if canonical_name is None or canonical_name in self._shown_attrs():
            return

        meta = self._metadata[canonical_name]

        row = MarkerPlot(
            canonical_name,
            meta["label"],
            meta["unit"],
            self._exams,
            on_remove=self._remove_row,
            wheel_target=self.scroll.viewport(),
        )

        self._rows.append(row)
        self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
        self._refresh_combo()

        return row

    def _add_selected(self):
        self._add_row(self.add_combo.currentData())

    def _remove_row(self, row):
        self._rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self._refresh_combo()

    def _clear_rows(self):
        for row in self._rows:
            self.rows_layout.removeWidget(row)
            row.deleteLater()

        self._rows.clear()

    def populate(self, patient):
        exams = [exam for exam in patient.medical_records if exam.fecha_toma_muestra is not None]
        exams.sort(key=lambda exam: exam.fecha_toma_muestra)
        self._exams = exams

        # No hardcoded HEMO_MARKERS / CHEM_MARKERS. Any numeric analyte that the
        # CSV-driven PDF reader placed in exam.results becomes plotable.
        available = set()

        for exam in exams:
            for canonical_name, result in exam.results.items():
                if result.is_numeric:
                    available.add(canonical_name)

        self._metadata = {name: _metadata_for(exams, name) for name in available}

        # Stable, human-friendly ordering for the picker.
        self._available = sorted(
            available,
            key=lambda name: (
                self._metadata[name]["category"].casefold(),
                self._metadata[name]["label"].casefold(),
            ),
        )

        # Initial view: show the worst three trends seen so far.
        default_markers = sorted(
            available,
            key=lambda name: (
                _trend_priority(exams, name),
                self._metadata[name]["label"].casefold(),
            ),
            reverse=True,
        )[:_DEFAULT_ROWS]

        self._clear_rows()

        for canonical_name in default_markers:
            self._add_row(canonical_name)

        self._refresh_combo()