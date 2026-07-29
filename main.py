# main.py
import sys
from PySide6.QtWidgets import QApplication
from app.main_window import MainWindow
from app.pages.theme import STYLESHEET


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
