# app/pages/trend_plot.py
from .theme import COLORS
from matplotlib.figure import Figure
from PySide6.QtCore import QSize, QObject, QEvent
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QScrollArea, QFrame, QStyle, QApplication

import matplotlib.dates as mdates

HEMO_MARKERS = {
    "hemoglobina": ("Hemoglobina", "g/dL"),
    "hemoglobina_corpuscular_media": ("HCM", "pg"),
    "hematocrito": ("Hematocrito", "%"),
    "hematies": ("Hematíes", "10^6/µL"),
    "volumen_corpuscular_medio": ("VCM", "fL"),
    "concentracion_hemoglobina_corpuscular": ("CHCM", "g/dL"),
    "rdw_pct": ("RDW %", "%"),
    "rdw_sd": ("RDW SD", "fL"),
    "leucocitos_totales": ("Leucocitos", "10^3/µL"),
    "eosinofilos_pct": ("Eosinófilos %", "%"),
    "eosinofilos_abs": ("Eosinófilos", "10^3/µL"),
    "basofilos_pct": ("Basófilos %", "%"),
    "basofilos_abs": ("Basófilos", "10^3/µL"),
    "linfocitos_pct": ("Linfocitos %", "%"),
    "linfocitos_abs": ("Linfocitos", "10^3/µL"),
    "monocitos_pct": ("Monocitos %", "%"),
    "monocitos_abs": ("Monocitos", "10^3/µL"),
    "neutrofilos_segmentados_pct": ("Neutrófilos seg %", "%"),
    "neutrofilos_segmentados_abs": ("Neutrófilos seg", "10^3/µL"),
    "neutrofilos_totales_anc": ("ANC", "10^3/µL"),
    "bastones_pct": ("Bastones %", "%"),
    "bastones_abs": ("Bastones", "10^3/µL"),
    "recuento_plaquetas": ("Plaquetas", "10^3/µL"),
    "volumen_plaquetario_medio": ("VPM", "fL"),
}

CHEM_MARKERS = {
    "glucosa": ("Glucosa", "mg/dL"),
    "urea_serica": ("Urea", "mg/dL"),
    "nitrogeno_ureico_bun": ("BUN", "mg/dL"),
    "creatinina_serica": ("Creatinina", "mg/dL"),
    "transaminasa_piruvica": ("ALT", "U/L"),
    "transaminasa_oxalacetica": ("AST", "U/L"),
    "bilirrubina_total": ("Bilirrubina total", "mg/dL"),
    "bilirrubina_indirecta": ("Bilirrubina indirecta", "mg/dL"),
    "bilirrubina_directa": ("Bilirrubina directa", "mg/dL"),
    "fosfatasa_alcalina": ("Fosfatasa alcalina", "U/L"),
    "proteinas_totales": ("Proteínas totales", "g/dL"),
    "albumina": ("Albúmina", "g/dL"),
    "calcio_serico": ("Calcio", "mg/dL"),
    "fosforo_serico": ("Fósforo", "mg/dL"),
    "sodio": ("Sodio", "mEq/L"),
    "potasio": ("Potasio", "mEq/L"),
    "cloro": ("Cloro", "mEq/L"),
    "bicarbonato_serico": ("Bicarbonato", "mEq/L"),
}

HEMO_ATTRS = set(HEMO_MARKERS)
MARKERS = {**HEMO_MARKERS, **CHEM_MARKERS}

_SERIES_COLOR = "#4fd6be"
_DEFAULT_ROWS = 3
_ROW_MIN_HEIGHT = 260


def _value(exam, attr):
    obj = exam.hemograma if attr in HEMO_ATTRS else exam
    return getattr(obj, attr, None)


class _WheelForwarder(QObject):
    def __init__(self, target):
        super().__init__(target)
        self._target = target

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            QApplication.sendEvent(self._target, event)
            return True   # swallow it on the canvas; the viewport already handled it
        return False


class MarkerPlot(QFrame):
    def __init__(self, attr, label, unit, exams, on_remove, wheel_target):
        super().__init__()
        self.setObjectName("Card")
        self.setMinimumHeight(_ROW_MIN_HEIGHT)
        self.attr = attr
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
        # let wheel events over the plot scroll the stack instead of being eaten
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

        xs, ys = [], []
        for e in self._exams:
            v = _value(e, self.attr)
            if v is not None:
                xs.append(e.fecha_toma_muestra)
                ys.append(v)

        if ys:
            ax.plot(xs, ys, marker="o", markersize=5, linewidth=1.8, color=_SERIES_COLOR)
        else:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes, color=dim, fontsize=9)

        ax.set_ylabel(unit, color=dim, fontsize=8)
        ax.tick_params(colors=dim, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(grid_col)
        ax.grid(True, color=grid_col, alpha=0.35, linewidth=0.6)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        self.fig.autofmt_xdate(rotation=30, ha="right")
        self.fig.subplots_adjust(left=0.13, right=0.97, top=0.94, bottom=0.26)
        self.canvas.draw_idle()

class TrendPlotWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._exams = []
        self._available = []
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
        return {r.attr for r in self._rows}

    def _refresh_combo(self):
        """Rebuild the picker from available markers that aren't already plotted."""
        shown = self._shown_attrs()
        remaining = [a for a in self._available if a not in shown]

        self.add_combo.blockSignals(True)
        self.add_combo.clear()
        for attr in remaining:
            self.add_combo.addItem(MARKERS[attr][0], attr)
        self.add_combo.blockSignals(False)

        # nothing left to add -> disable the control pair
        can_add = bool(remaining)
        self.add_combo.setEnabled(can_add)
        self.add_button.setEnabled(can_add)

    def _add_row(self, attr):
        if attr is None or attr in self._shown_attrs():
            return
        label, unit = MARKERS[attr]
        row = MarkerPlot(attr, label, unit, self._exams, on_remove=self._remove_row, wheel_target=self.scroll.viewport())
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
        exams = [e for e in patient.medical_records if e.fecha_toma_muestra is not None]
        exams.sort(key=lambda e: e.fecha_toma_muestra)
        self._exams = exams

        self._available = [
            attr for attr in MARKERS
            if any(_value(e, attr) is not None for e in exams)
        ]

        self._clear_rows()
        for attr in self._available[:_DEFAULT_ROWS]:
            self._add_row(attr)