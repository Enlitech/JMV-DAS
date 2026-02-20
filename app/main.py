import sys
from PySide6.QtWidgets import QApplication
import os

from ui.main_window import MainWindow

# Ensure project root is on sys.path so we can import `backend.*`
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
    
def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()