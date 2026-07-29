from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog

class CentralPage(QWidget):
    directory_selected = Signal(str)

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        logo = QLabel("Patient History Analyzer")
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("""
            QLabel {
                font-size: 32px;
                font-weight: bold;
            }
        """)

        self.analyze_button = QPushButton("Analizar Paciente")
        self.exit_button = QPushButton("Exit")

        button_style = """
            QPushButton {
                font-size: 18px;
                padding: 12px;
                min-width: 280px;
            }
        """
        self.analyze_button.setStyleSheet(button_style)
        self.exit_button.setStyleSheet(button_style)
        self.analyze_button.clicked.connect(self._choose_directory)

        layout.addWidget(logo)
        layout.addWidget(self.analyze_button)
        layout.addWidget(self.exit_button)

    def _choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Seleccionar directorio", "")
        if directory:
            self.directory_selected.emit(directory)