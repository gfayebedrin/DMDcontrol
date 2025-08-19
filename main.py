import sys
from PySide6.QtWidgets import QApplication
from stim1p.ui.dmd_stim_widget import StimDMDWidget

app = QApplication(sys.argv)
ui = StimDMDWidget()
ui.showMaximized()
sys.exit(app.exec())