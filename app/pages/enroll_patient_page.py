# app/pages/enroll_patient_page.py

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .timeline import TimelineWidget
from .trend_plot import TrendPlotWidget
from ..dates import DateParseError
from ..eng_spa_bridge import UnknownLabelError, AmbiguousNumberError
from ..ctcae_checker import CTCAE, UnitError
from ..pdf_reader import read_pdf, read_patient_info
from ..reference_ranges import as_reference_ranges, out_of_range
from ..resources_path import resource
from .theme import COLORS

CTCAE_FILE_PATH = str(resource("resources", "ctcae_v5.yaml"))

class EnrollPatientPage(QWidget):
    back_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("Root")
        self.selected_directory = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        toolbar = QFrame()
        toolbar.setObjectName("Toolbar")
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(10, 8, 10, 8)
        tl.setSpacing(10)

        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.back_requested.emit)

        self.message = QLabel("Select a folder of lab PDFs to begin.")
        self.message.setObjectName("Status")

        tl.addWidget(self.back_button)
        tl.addSpacing(6)
        tl.addWidget(self.message, 1)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_left(), 5)
        body.addWidget(self._build_right(), 6)

        root.addWidget(toolbar)
        root.addLayout(body, 1)

    def _build_left(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(22, 20, 22, 20)
        pl.setSpacing(0)

        eyebrow = QLabel("PATIENT")
        eyebrow.setObjectName("PanelHdr")
        pl.addWidget(eyebrow)

        self.patient_code_label = QLabel("—")
        self.patient_code_label.setStyleSheet(f"font-size:24px; font-weight:700; color:{COLORS['text']};")
        pl.addSpacing(6)
        pl.addWidget(self.patient_code_label)
        pl.addSpacing(18)

        grid = QVBoxLayout()
        grid.setSpacing(10)
        self.age_value = QLabel("—")
        self.gender_value = QLabel("—")
        self.records_value = QLabel("—")
        for key, val in (("Age", self.age_value), ("Sex", self.gender_value), ("Exams", self.records_value)):
            row = QHBoxLayout()
            k = QLabel(key)
            k.setObjectName("Key")
            k.setFixedWidth(90)
            val.setObjectName("Value")
            row.addWidget(k)
            row.addWidget(val, 1)
            grid.addLayout(row)
        pl.addLayout(grid)
        pl.addSpacing(20)

        # severity summary
        self.summary = QFrame()
        self.summary.setObjectName("Card")
        sl = QVBoxLayout(self.summary)
        sl.setContentsMargins(16, 14, 16, 14)
        sl.setSpacing(8)
        sh = QLabel("SEVERITY SUMMARY")
        sh.setObjectName("PanelHdr")
        sl.addWidget(sh)
        self.summary_body = QLabel("Load a directory to see grading.")
        self.summary_body.setObjectName("Status")
        self.summary_body.setWordWrap(True)
        sl.addWidget(self.summary_body)
        pl.addWidget(self.summary)
        pl.addSpacing(20)

        records_hdr = QLabel("MEDICAL RECORDS")
        records_hdr.setObjectName("PanelHdr")
        pl.addWidget(records_hdr)
        pl.addSpacing(8)

        self.timeline = TimelineWidget()
        scroll = QScrollArea()
        scroll.setWidget(self.timeline)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        scroll.viewport().setStyleSheet("background: transparent;")
        pl.addWidget(scroll, 1)

        return panel

    def _build_right(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        pr = QVBoxLayout(panel)
        pr.setContentsMargins(20, 20, 16, 20)
        pr.setSpacing(14)

        hdr = QLabel("TRENDS")
        hdr.setObjectName("PanelHdr")
        pr.addWidget(hdr)

        self.trend_plot = TrendPlotWidget()
        pr.addWidget(self.trend_plot, 1)
        return panel

    def load_from_directory(self, directory: str):
        directory = Path(directory)
        self.selected_directory = str(directory)
        self.message.setText(f"Selected: {directory}")

        files = sorted(directory.glob("*.pdf"))
        if not files:
            self.message.setText("No PDF files found in that folder.")
            return

        try:
            patient = read_patient_info(str(files[0]))
            for pdf_file in files:
                patient.add_medical_exam(read_pdf(str(pdf_file)))

            # Grade against the LAB's reference ranges, not placeholder LLNs.
            c = CTCAE(CTCAE_FILE_PATH, ranges=as_reference_ranges())
            c.grade_patient(patient)

            for exam in patient.medical_records:
                exam.range_flags = out_of_range(exam)
        except (UnknownLabelError, AmbiguousNumberError, UnitError, DateParseError, KeyError, ValueError, FileNotFoundError) as e:
            self.message.setText("Could not process this folder.")
            QMessageBox.critical(self, "Processing error", str(e))
            return

        self.patient_code_label.setText(str(patient.patient_code or "—"))
        self.age_value.setText(f"{patient.edad} años" if patient.edad is not None else "—")
        self.gender_value.setText(patient.sexo or "—")
        self.records_value.setText(str(len(patient.medical_records)))

        self.timeline.populate(patient)
        self.trend_plot.populate(patient)
        self._update_summary(patient)
        self.message.setText(f"Loaded {len(patient.medical_records)} exams.")

    def _update_summary(self, patient) -> None:
        worst = patient.worst_grade
        flagged = len(patient.flagged)
        n_range = sum(len(getattr(e, "range_flags", [])) for e in patient.medical_records)
        color = COLORS["grade"].get(worst, COLORS["grade"][0])
        self.summary_body.setText(
            f"<span style='font-size:30px; font-weight:700; color:{color};'>G{worst}</span>"
            f"<span style='color:{COLORS['text_mute']};'>&nbsp;&nbsp;worst grade</span><br>"
            f"<span style='color:{COLORS['text_dim']};'>{flagged} flagged events · "
            f"{n_range} out-of-range values across "
            f"{len(patient.medical_records)} exams</span>"
        )