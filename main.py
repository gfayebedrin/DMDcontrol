import sys
from PySide6.QtWidgets import QApplication
from stim1p.ui.dmd_stim_widget import StimDMDWidget

app = QApplication(sys.argv)
ui = StimDMDWidget()
ui.showMaximized()
sys.exit(app.exec())


# To run the DMD control software, click on the ▶️ (Run Python File) button in the top right corner of this window.