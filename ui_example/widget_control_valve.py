"""Control valve widget"""

import cv2
import numpy as np
import screeninfo
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QTime, QTimer

from .ui_widget_control_valve import Ui_WidgetControlValve
from loader.mainwindow import MainWindow

COLOR_RGB = {
    "Blue": [1, 0, 0],
    "Green": [0, 1, 0],
    "Red": [0, 0, 1],
    "Black": [0, 0, 0],
    "White": [1, 1, 1],
}


def display_monochrome_image(screen_id: int, color_rgb: list):
    """Display monochrome image on the monitor"""
    # get the size of the screen
    screen = screeninfo.get_monitors()[screen_id]
    width, height = screen.width, screen.height

    image = np.ones((height, width, 3), dtype=np.float32)
    image[:, :] = color_rgb  # red at bottom-right

    window_name = "projector"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.moveWindow(window_name, screen.x - 1, screen.y - 1)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.imshow(window_name, image)


class WidgetControlValve(QWidget):
    """Widget for camera parameters"""

    number_of_iteration = 0
    duree = QTime(0, 0, 0)

    def __init__(self, acquisition, worker, parent: MainWindow = None):
        super().__init__(parent)
        self.ui = Ui_WidgetControlValve()
        self.ui.setupUi(self)
        self.acquisition = acquisition
        self.worker = worker
        self.main_window = parent
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)

        # create QAction
        self.setObjectName("Control valve")
        # self.setWindowIcon(QIcon.fromTheme(QIcon.ThemeIcon.))

        for monitor in screeninfo.get_monitors():
            if not monitor.is_primary:
                self.ui.combo_box_screen_number.addItem(str(monitor.name))

        self._connect()
        self._close_valve()
        self._wait_display()
        self.ui.progress_bar.setValue(0)

    def _connect(self):
        self.ui.push_button_open_valve.clicked.connect(self._open_valve)
        self.ui.push_button_close_valve.clicked.connect(self._close_valve)
        self.ui.push_button_update_image.clicked.connect(self._update_screen)
        self.ui.push_button_start_sequence.clicked.connect(self._start_sequence)
        self.ui.push_button_stop_sequence.clicked.connect(self._stop_sequence)
        self.ui.push_button_abort_sequence.clicked.connect(self._abort_sequence)

        self.ui.spin_box_number_iteration.valueChanged.connect(self._update_time)

    def _open_valve(self):
        """Open the valve"""
        self.ui.push_button_open_valve.setVisible(False)
        self.ui.push_button_close_valve.setVisible(True)
        opening_time = self.ui.spin_box_opening_time.value()
        if "arduino" in self.acquisition.devices:
            self.acquisition.devices["arduino"].open_valve(opening_time / 1000)
        QTimer.singleShot(opening_time, self._ui_close_valve)

    def _ui_close_valve(self):
        self.ui.push_button_open_valve.setVisible(True)
        self.ui.push_button_close_valve.setVisible(False)

    def _close_valve(self):
        """Close the valve"""
        if "arduino" in self.acquisition.devices:
            self.acquisition.devices["arduino"].close_valve()
        self._ui_close_valve()

    def _update_screen(self):
        """Update the screen"""
        screen_id = self.ui.combo_box_screen_number.currentIndex()
        color = self.ui.combo_box_color.currentText()
        time_minute = self.ui.time_edit_video_time.time().minute()
        time_second = self.ui.time_edit_video_time.time().second()
        display_time = int(time_minute * 60 + time_second) * 1000
        if color == "None":
            self._stop_display()
        else:
            color_rgb = COLOR_RGB[color]
            display_monochrome_image(screen_id, color_rgb)
        if display_time > 0:
            QTimer.singleShot(display_time, self._wait_display)

    def _wait_display(self):
        """Stop the display"""
        screen_id = self.ui.combo_box_screen_number.currentIndex()
        color = self.ui.combo_box_color_while_waiting.currentText()
        if color == "None":
            self._stop_display()
        else:
            color_rgb = COLOR_RGB[color]
            display_monochrome_image(screen_id, color_rgb)

    def _stop_display(self):
        """Stop the display"""
        cv2.destroyAllWindows()

    def _deliver_food(self):
        """Deliver food"""
        self._open_valve()
        self._update_screen()

    def _update_time(self):
        nombre_iteration = (
            self.ui.spin_box_number_iteration.value()
            - WidgetControlValve.number_of_iteration
        )
        # En millisecondes
        temps_inter_ouverture = self.ui.time_edit_between_opening.time()

        if WidgetControlValve.number_of_iteration == 0:
            temps_init = self.ui.time_edit_init_time.time()
        else:
            temps_init = temps_inter_ouverture
        seconds = nombre_iteration * temps_inter_ouverture.second()
        minutes = nombre_iteration * temps_inter_ouverture.minute()
        WidgetControlValve.duree = temps_init.addSecs(60 * minutes + seconds)
        self.ui.label_total_time_value.setText(
            WidgetControlValve.duree.toString("hh:mm:ss")
        )

    def _update_end_time(self):
        now = QTime.currentTime()
        duree = WidgetControlValve.duree
        end = now.addSecs(60 * (60 * duree.hour() + duree.minute()) + duree.second())
        self.ui.label_end_time_value.setText(end.toString("hh:mm:ss"))

    def _start_sequence(self):
        """Start the sequence"""
        self.ui.push_button_start_sequence.setVisible(False)
        self.ui.push_button_stop_sequence.setVisible(True)
        self.ui.push_button_abort_sequence.setVisible(True)
        self._update_time()
        self._update_end_time()

        if self.ui.checkbox_record_sequence.isChecked():
            self.worker.start_record()
        self._wait_display()
        if not self.timer.remainingTime() == -1:
            self.timer.start()
        else:
            self.ui.progress_bar.setValue(0)
            init_time = self.ui.time_edit_init_time.time()
            self.timer.timeout.connect(self._run_sequence)
            self.timer.start(1000 * (init_time.second() + 60 * init_time.minute()))

    def _run_sequence(self):
        """Run the sequence"""
        self.timer.stop()
        nombre_iteration = self.ui.spin_box_number_iteration.value()
        percent = WidgetControlValve.number_of_iteration / nombre_iteration
        print(int(percent * 100), self.timer.isSingleShot())
        self.ui.progress_bar.setValue(int(percent * 100))
        if WidgetControlValve.number_of_iteration < nombre_iteration:
            self._deliver_food()
            WidgetControlValve.number_of_iteration += 1
            waiting_time = self.ui.time_edit_between_opening.time()
            self.timer.start(
                1000 * (waiting_time.second() + 60 * waiting_time.minute())
            )
        else:
            self._abort_sequence()

    def _stop_sequence(self):
        """Stop the sequence"""
        # remaining_time = self.timer.remainingTime()
        self.timer.stop()
        self.ui.push_button_start_sequence.setVisible(True)
        self.ui.push_button_stop_sequence.setVisible(False)
        self.ui.push_button_abort_sequence.setVisible(True)

    def _abort_sequence(self):
        """Abort the sequence"""
        self.timer.stop()
        WidgetControlValve.number_of_iteration = 0
        self.ui.progress_bar.setValue(100)
        self.ui.push_button_start_sequence.setVisible(True)
        self.ui.push_button_stop_sequence.setVisible(False)
        self.ui.push_button_abort_sequence.setVisible(False)
