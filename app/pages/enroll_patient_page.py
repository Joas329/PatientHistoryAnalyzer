# app/pages/enroll_patient_page.py

from pathlib import Path
import traceback

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .timeline import TimelineWidget
from .trend_plot import TrendPlotWidget
from ..ctcae_checker import CTCAE, UnitError
from ..pdf_reader import read_pdf, read_patient_info
from ..resources_path import resource
from .theme import COLORS

CTCAE_FILE_PATH = str(resource("resources", "ctcae_v5.yaml"))
REFERENCE_RANGES_FILE_PATH = str(resource("resources", "reference_ranges.csv"))

class _PdfFolderWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, files: list[Path]):
        super().__init__()
        self.files = files

    @Slot()
    def run(self):
        try:
            patient = read_patient_info(str(self.files[0]))
            total = len(self.files)

            for index, pdf_file in enumerate(self.files, start=1):
                self.progress.emit(index, total, pdf_file.name)
                exam = read_pdf(str(pdf_file), reference_csv=REFERENCE_RANGES_FILE_PATH, patient=patient)
                patient.add_medical_exam(exam)

            # Lab reference-range comparison was already performed by read_pdf().
            # CTCAE is a separate layer and now grades directly from exam.results.
            checker = CTCAE(CTCAE_FILE_PATH)
            checker.grade_patient(patient)

            self.finished.emit(patient)

        except Exception:
            self.failed.emit(traceback.format_exc())


class EnrollPatientPage(QWidget):
    back_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("Root")
        self.selected_directory = ""
        self._load_thread: QThread | None = None
        self._load_worker: _PdfFolderWorker | None = None

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

        for key, value in (("Age", self.age_value), ("Sex", self.gender_value), ("Exams", self.records_value)):
            row = QHBoxLayout()
            label = QLabel(key)
            label.setObjectName("Key")
            label.setFixedWidth(90)
            value.setObjectName("Value")
            row.addWidget(label)
            row.addWidget(value, 1)
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
        if self._load_thread is not None and self._load_thread.isRunning():
            self.message.setText("A folder is already being processed.")
            return

        directory = Path(directory)
        self.selected_directory = str(directory)
        files = sorted(directory.glob("*.pdf"))

        if not files:
            self.message.setText("No PDF files found in that folder.")
            return

        self.message.setText(f"Preparing {len(files)} PDF files…")
        self.summary_body.setText("Reading laboratory PDFs…")

        self._load_thread = QThread(self)
        self._load_worker = _PdfFolderWorker(files)
        self._load_worker.moveToThread(self._load_thread)

        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.progress.connect(self._on_load_progress)
        self._load_worker.finished.connect(self._on_patient_loaded)
        self._load_worker.failed.connect(self._on_load_failed)

        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_worker.failed.connect(self._load_thread.quit)
        self._load_worker.finished.connect(self._load_worker.deleteLater)
        self._load_worker.failed.connect(self._load_worker.deleteLater)
        self._load_thread.finished.connect(self._on_thread_finished)
        self._load_thread.finished.connect(self._load_thread.deleteLater)

        self._load_thread.start()

    @Slot(int, int, str)
    def _on_load_progress(self, current: int, total: int, filename: str):
        self.message.setText(f"Reading PDF {current}/{total}: {filename}")

    @Slot(object)
    def _on_patient_loaded(self, patient):
        self.patient_code_label.setText(str(patient.patient_code or "—"))
        self.age_value.setText(f"{patient.edad} años" if patient.edad is not None else "—")
        self.gender_value.setText(patient.sexo or "—")
        self.records_value.setText(str(len(patient.medical_records)))

        self.timeline.populate(patient)
        self.trend_plot.populate(patient)
        self._update_summary(patient)

        total_results = sum(len(exam.results) for exam in patient.medical_records)
        self.message.setText(f"Loaded {len(patient.medical_records)} exams · {total_results} lab results.")

    @Slot(str)
    def _on_load_failed(self, details: str):
        self.message.setText("Could not process this folder.")
        # Show the final exception line prominently while preserving the traceback in the detailed text for debugging.
        lines = [line for line in details.strip().splitlines() if line.strip()]
        short_message = lines[-1] if lines else "Unknown processing error"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("Processing error")
        box.setText(short_message)
        box.setDetailedText(details)
        box.exec()

    @Slot()
    def _on_thread_finished(self):
        self._load_worker = None
        self._load_thread = None

    def _update_summary(self, patient) -> None:
        worst = patient.worst_grade
        flagged = len(patient.flagged)
        n_range = sum(len(exam.range_flags) for exam in patient.medical_records)
        color = COLORS["grade"].get(worst, COLORS["grade"][0])

        self.summary_body.setText(
            f"<span style='font-size:30px; font-weight:700; color:{color};'>G{worst}</span>"
            f"<span style='color:{COLORS['text_mute']};;'>&nbsp;&nbsp;worst grade</span><br>"
            f"<span style='color:{COLORS['text_dim']};;'>{flagged} flagged events · "
            f"{n_range} out-of-range values across {len(patient.medical_records)} exams</span>"
        )