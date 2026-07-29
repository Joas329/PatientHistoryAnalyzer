from PySide6.QtWidgets import QMainWindow, QStackedWidget

from .pages.central_page import CentralPage
from .pages.enroll_patient_page import EnrollPatientPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Patient History Analyzer")
        self.resize(1000, 700)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.central_page = CentralPage()
        self.enroll_patient_page = EnrollPatientPage()
        self.enroll_patient_page.back_requested.connect(self.show_home_page)

        self.stack.addWidget(self.central_page)
        self.stack.addWidget(self.enroll_patient_page)

        self.central_page.directory_selected.connect(self.analyze_directory)
        self.central_page.exit_button.clicked.connect(self.close)

        self.stack.setCurrentWidget(self.central_page)

    def analyze_directory(self, directory):
        self.stack.setCurrentWidget(self.enroll_patient_page)
        self.enroll_patient_page.load_from_directory(directory)

    def show_home_page(self):
        self.stack.setCurrentWidget(self.central_page)