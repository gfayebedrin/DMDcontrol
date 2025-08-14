"""Widget for DMD stimulation"""

import os
import sys
import glob
import numpy as np
from PIL import Image
import h5py

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import (
    QTreeWidgetItem,
    QApplication,
    QWidget,
    QFileDialog,
    QTableWidgetItem,
    QTreeWidget,
    QPlainTextEdit,
)
from PySide6.QtGui import QTextCharFormat, QTextCursor, QFont
import pyqtgraph as pg

import re

from qt.DMD_stim_ui import Ui_widget_dmd_stim

# Strip common ANSI escape sequences: CSI (e.g. \x1b[31m), OSC (e.g. hyperlinks), and ST/BEL terminators
ANSI_RE = re.compile(
    r"""
    (?:\x1b\[[0-9;?]*[ -/]*[@-~])      # CSI ... cmd
  | (?:\x1b\][^\x07\x1b]*(?:\x07|\x1b\\))  # OSC ... BEL or ST
  | (?:\x1b[@-Z\\-_])                  # 2-byte escapes
    """,
    re.VERBOSE,
)


class Polygon:
    """Pattern class for DMD stimulation"""

    def __init__(self, points, item: QTreeWidgetItem):
        self.roi = pg.PolyLineROI(points, closed=True)
        self.item = item
        self.roi.sigClicked.connect(lambda: self.item.setSelected(True))

    def change_ref(self, center, angle):
        """Change the referenciel of the roi"""
        self.roi.setPos(center)
        self.roi.setAngle(angle)

    def get_points(self):
        """Return handles points of the roi"""
        points = []
        for _, position in self.roi.getSceneHandlePositions():
            points.append([position.x(), position.y()])
        return np.asarray(points)


class QtTee(QObject):
    """A stream that forwards writes to the original stream and also emits a signal for the UI."""

    textWritten = Signal(str, bool)  # (text, is_err)

    def __init__(self, orig_stream, is_err=False):
        super().__init__()
        self._orig = orig_stream
        self._is_err = is_err
        # mirror common attributes for compatibility
        self.encoding = getattr(orig_stream, "encoding", "utf-8")

    def write(self, text: str):
        # pass-through to original stream
        self._orig.write(text)
        self._orig.flush()
        # also emit to UI
        if text:
            self.textWritten.emit(text, self._is_err)

    def flush(self):
        self._orig.flush()

    # optional niceties
    def isatty(self):
        return getattr(self._orig, "isatty", lambda: False)()

    def writable(self):
        return True

    def fileno(self):
        return getattr(self._orig, "fileno", lambda: -1)()


class StimDMDWidget(QWidget):
    """DMD Stimulation Widget"""

    def __init__(self, name="Stimulation DMD Widget", dmd=None, parent=None):
        super().__init__(parent=parent)
        self.ui = Ui_widget_dmd_stim()
        self.ui.setupUi(self)
        self.setObjectName(name)
        self.rois = []
        self.last_roi = None
        self.crosshair = pg.CrosshairROI([0, 0], [20, 20])
        self.dmd = dmd
        self.polygons = {}
        # self.setWindowIcon(QIcon.fromTheme(QIcon.name("accessories-calculator")))
        self.image_item = pg.ImageView(parent=self, view=pg.PlotItem())
        self.ui.stackedWidget_image.addWidget(self.image_item)
        self.ui.treeWidget.setEditTriggers(
            QTreeWidget.DoubleClicked  # Double-clic pour éditer
            | QTreeWidget.EditKeyPressed  # Appui sur F2 ou Entrée pour éditer
        )
        self._connect()

        # --- Console setup + tee redirection -------------------------------
        # make the console nice for logs
        self.ui.plainTextEdit_console_output.setReadOnly(True)
        self.ui.plainTextEdit_console_output.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.NoWrap
        )
        font = QFont("Courier New")
        font.setStyleHint(QFont.Monospace)
        self.ui.plainTextEdit_console_output.setFont(font)

        # keep originals
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr

        # create tees (they forward to originals AND emit to the UI)
        self._tee_out = QtTee(self._orig_stdout, is_err=False)
        self._tee_err = QtTee(self._orig_stderr, is_err=True)

        # connect signals so UI updates happen in the GUI thread
        self._tee_out.textWritten.connect(self._append_console_text)
        self._tee_err.textWritten.connect(self._append_console_text)

        # replace sys streams with tees (console still works via forward)
        sys.stdout = self._tee_out
        sys.stderr = self._tee_err
        # -------------------------------------------------------------------

    def _connect(self):
        """Connect signals and slots"""
        self.ui.pushButton_load_image.clicked.connect(self._load_image)
        self.ui.pushButton_change_folder.clicked.connect(self._change_folder)
        self.ui.pushButton_refresh_image.clicked.connect(self._refresh_image)
        self.ui.pushButton_show_grid.clicked.connect(self._show_grid)
        self.ui.pushButton_define_axis.clicked.connect(self._define_axis)
        self.ui.pushButton_add_pattern.clicked.connect(self._add_pattern)
        self.ui.pushButton_add_roi.clicked.connect(self._add_roi)

        self.ui.pushButton_add_row.clicked.connect(self._add_row_table)
        self.ui.pushButton_remove_row.clicked.connect(self._remove_row_table)

        self.ui.pushButton_remove_pattern.clicked.connect(self._remove_pattern_or_roi)
        self.ui.pushButton_load_patterns.clicked.connect(self._load_patterns_file)
        self.ui.pushButton_save_patterns.clicked.connect(self._save_file)
        self.ui.treeWidget.itemClicked.connect(self._process_item)

        # --- Console append helper --------------------------------------------

    def _append_console_text(self, text: str, is_err: bool):
        console = self.ui.plainTextEdit_console_output

        # 1) remove ANSI escapes
        cleaned = ANSI_RE.sub("", text)

        # 2) normalize CR-only progress lines (e.g. "xxx\ryyy")
        #    keep only the last carriage-return segment
        if "\r" in cleaned and "\n" not in cleaned:
            cleaned = cleaned.split("\r")[-1]

        if is_err:
            cursor = console.textCursor()
            cursor.movePosition(QTextCursor.End)
            fmt = QTextCharFormat()
            fmt.setForeground(Qt.red)
            cursor.mergeCharFormat(fmt)
            cursor.insertText(cleaned)
            cursor.mergeCharFormat(QTextCharFormat())  # reset
            console.setTextCursor(cursor)
        else:
            if cleaned.endswith("\n"):
                console.appendPlainText(cleaned[:-1])
            else:
                console.appendPlainText(cleaned)

    # ----------------------------------------------------------------------

    def closeEvent(self, event):
        # restore original streams
        sys.stdout = self._orig_stdout
        sys.stderr = self._orig_stderr
        super().closeEvent(event)

    def update_ui(self, data):
        """Update the UI with new data"""
        if self.dmd is not None:
            self._set_image(data)

    def set_up(self):
        """Set up the widget"""

    def _set_image(self, image):
        self.image_item.setImage(image.T)

    def _load_image(self, path: str = ""):
        try:
            path = QFileDialog.getOpenFileName(self, "Select file", "", "")[0]
            image = np.array(Image.open(path))
            self._set_image(image)
        except AttributeError:
            pass

    def _change_folder(self):
        try:
            filename = self.ui.lineEdit_folder_path.text()
            if filename == "":
                filename = "C:\\"
            path = QFileDialog.getExistingDirectory(
                None, "Select a folder:", filename, QFileDialog.ShowDirsOnly
            )
            self.ui.lineEdit_folder_path.setText(path)
        except AttributeError:
            pass

    def _refresh_image(self):
        folder_path = self.ui.lineEdit_folder_path.text()
        if not os.path.exists(folder_path):
            print(f"Le dossier '{folder_path}' n'existe pas.")
            return
        images = (
            glob.glob(os.path.join(folder_path, "*.[jJ][pP][gG]"))
            + glob.glob(os.path.join(folder_path, "*.[pP][nN][gG]"))
            + glob.glob(os.path.join(folder_path, "*.[jJ][pP][eE][gG]"))
            + glob.glob(os.path.join(folder_path, "*.[gG][iI][fF]"))
            + glob.glob(os.path.join(folder_path, "*.[tT][iI][fF]"))
            + glob.glob(os.path.join(folder_path, "*.[tT][iI][iI][fF]"))
        )
        if not images:
            return
        # Trie les images par date de modification (la plus récente en premier)
        last_image = max(images, key=os.path.getmtime)
        image = np.array(Image.open(last_image))
        self._set_image(image)

    def _show_grid(self):
        show = self.ui.pushButton_show_grid.isChecked()
        self.image_item.getView().showGrid(show, show)

    def _define_axis(self):
        """Define the axis of the widget"""
        if self.ui.pushButton_define_axis.isChecked():
            self.image_item.addItem(self.crosshair)
        else:
            self.image_item.removeItem(self.crosshair)
            for polygon in self.polygons.values():
                polygon.change_ref(self.crosshair.pos(), self.crosshair.angle())

    def _load_patterns_file(self):
        file_path = QFileDialog.getOpenFileName(self, "Select file", "", "")[0]
        with h5py.File(file_path, "r") as file:
            self._load_patterns(file)
            self._load_timing(file)
        self.ui.lineEdit_file_path.setText(file_path)

    def _load_patterns(self, file: h5py.File):
        index = 0
        if "patterns" not in file.keys():
            print("No Patterns in file")
            return
        self.ui.treeWidget.clear()
        patterns_group = file["patterns"]
        for name, pattern in patterns_group.items():
            if not isinstance(pattern, h5py.Group):
                continue
            root = QTreeWidgetItem(None, [name])
            root.setFlags(root.flags() | Qt.ItemIsEditable)
            self.ui.treeWidget.insertTopLevelItem(index, root)
            for p_name, polygon in pattern.items():
                if not isinstance(polygon, h5py.Dataset):
                    continue
                node = QTreeWidgetItem(None, [p_name])
                node.setFlags(node.flags() | Qt.ItemIsEditable)
                root.addChild(node)
                polygon = Polygon(polygon[()].astype("float64"), node)
                polygon.change_ref(self.crosshair.pos(), self.crosshair.angle())
                self.polygons[node] = polygon
            index += 1
        self._clear_rois()

    def _load_timing(self, file: h5py.File):
        try:
            sequence = file["sequence"][()]
            self.ui.tableWidget.setRowCount(len(sequence))
            for row, sequence in enumerate(file["sequence"]):
                item_timing = QTableWidgetItem(str(file["timings_ms"][row]))
                item_duration = QTableWidgetItem(str(file["durations_ms"][row]))
                item_pattern = QTableWidgetItem(str(sequence))
                self.ui.tableWidget.setItem(row, 0, item_timing)
                self.ui.tableWidget.setItem(row, 1, item_duration)
                self.ui.tableWidget.setItem(row, 2, item_pattern)
        except KeyError as e:
            print(e)

    def _save_file(self):
        file_path = self.ui.lineEdit_file_path.text()
        with h5py.File(file_path, "w") as file:
            self._get_pattern_from_tree(file)
            self._get_timing_from_table(file)

    def _get_pattern_from_tree(self, file: h5py.File):
        patterns_group = file.create_group("patterns")
        for index in range(self.ui.treeWidget.topLevelItemCount()):
            pattern_item = self.ui.treeWidget.topLevelItem(index)
            pattern_group = patterns_group.create_group(pattern_item.text(0))
            for polygon_index in range(pattern_item.childCount()):
                polygon_item = pattern_item.child(polygon_index)
                polygon = self.polygons[polygon_item]
                pattern_group.create_dataset(
                    name=polygon_item.text(0), data=polygon.get_points()
                )

    def _get_timing_from_table(self, file: h5py.File):
        timings = []
        durations = []
        sequence = []
        for row in range(self.ui.tableWidget.rowCount()):
            timings.append(int(self.ui.tableWidget.item(row, 0).text()))
            durations.append(int(self.ui.tableWidget.item(row, 1).text()))
            sequence.append(int(self.ui.tableWidget.item(row, 2).text()))
        file.create_dataset("timings_ms", data=np.asarray(timings))
        file.create_dataset("durations_ms", data=np.asarray(durations))
        file.create_dataset("sequence", data=np.asarray(sequence))

    def _process_item(self, item: QTreeWidgetItem, column):
        self._clear_rois()
        if item in self.polygons:
            polygon = self.polygons[item]
            roi = polygon.roi
            self.rois.append(roi)
            self.image_item.addItem(roi)
        else:
            for i in range(item.childCount()):
                polygon = self.polygons[item.child(i)]
                roi = polygon.roi
                self.rois.append(roi)
                self.image_item.addItem(roi)

    def _add_roi(self):
        """Add ROI to the widget"""
        if not self.ui.treeWidget.selectedItems():
            return
        selected_item = self.ui.treeWidget.selectedItems()[0]
        if selected_item.parent() is not None:
            root = selected_item.parent()
        else:
            root = selected_item
        a = 10
        positions = np.asarray([[a, a], [-a, a], [-a, -a], [a, -a]])
        node = QTreeWidgetItem(None, ["new roi"])
        node.setFlags(node.flags() | Qt.ItemIsEditable)
        root.addChild(node)
        polygon = Polygon(positions.astype("float64"), node)
        polygon.change_ref(self.crosshair.pos(), self.crosshair.angle())
        self.polygons[node] = polygon

    def _add_pattern(self):
        """Add pattern"""
        index = self.ui.treeWidget.topLevelItemCount()
        root = QTreeWidgetItem(None, ["new pattern"])
        root.setFlags(root.flags() | Qt.ItemIsEditable)
        self.ui.treeWidget.insertTopLevelItem(index, root)

    def _remove_pattern_or_roi(self):
        """Remove ROI from the widget"""
        if not self.ui.treeWidget.selectedItems():
            return
        selected_items = self.ui.treeWidget.selectedItems()
        for item in selected_items:
            parent = item.parent()
            if parent:
                parent.removeChild(item)
                items_to_remove = [item]
            else:
                index = self.ui.treeWidget.indexOfTopLevelItem(item)
                items_to_remove = item.takeChildren()
                self.ui.treeWidget.takeTopLevelItem(index)
            for item in items_to_remove:
                try:
                    polygon = self.polygons.pop(item)
                    self.rois.remove(polygon.roi)
                    self.image_item.removeItem(polygon.roi)
                except ValueError:
                    pass
            del item

    def _add_row_table(self):
        self.ui.tableWidget.insertRow(self.ui.tableWidget.rowCount())

    def _remove_row_table(self):
        rows_to_remove = []
        for index in self.ui.tableWidget.selectedIndexes():
            row = index.row()
            if row not in rows_to_remove:
                rows_to_remove.append(row)
        rows_to_remove.sort(reverse=True)
        for index in rows_to_remove:
            self.ui.tableWidget.removeRow(row)

    def _clear_rois(self):
        """Clear the ROIs from the widget"""
        for roi in self.rois:
            self.image_item.removeItem(roi)
        self.rois = []


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ui = StimDMDWidget()
    ui.show()
    sys.exit(app.exec())
