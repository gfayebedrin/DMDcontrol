"""Dialog helpers for the DMD stimulation widget."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class CalibrationDialog(QDialog):
    """Collect user inputs required to build a calibration."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        default_mirrors: tuple[int, int] = (100, 100),
        default_pixel_size: float = 1.0,
        default_invert_x: bool = False,
        default_invert_y: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle("Calibrate DMD")
        layout = QFormLayout(self)

        self._mirror_size = QSpinBox(self)
        self._mirror_size.setRange(1, 8192)
        default_avg = 0.5 * (float(default_mirrors[0]) + float(default_mirrors[1]))
        default_size = max(1, min(8192, int(round(default_avg))))
        self._mirror_size.setValue(default_size)
        layout.addRow("Square size (mirrors)", self._mirror_size)

        self._pixel_size = QDoubleSpinBox(self)
        self._pixel_size.setRange(1e-6, 10_000.0)
        self._pixel_size.setDecimals(6)
        clamped_size = max(
            self._pixel_size.minimum(),
            min(self._pixel_size.maximum(), float(default_pixel_size)),
        )
        self._pixel_size.setValue(clamped_size)
        layout.addRow("Camera pixel size (µm)", self._pixel_size)

        self._invert_x = QCheckBox(self)
        self._invert_x.setChecked(bool(default_invert_x))
        self._invert_x.setText("Flip DMD X axis (X→X−x)")
        layout.addRow(self._invert_x)

        self._invert_y = QCheckBox(self)
        self._invert_y.setChecked(bool(default_invert_y))
        self._invert_y.setText("Flip DMD Y axis (Y→Y−y)")
        layout.addRow(self._invert_y)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> tuple[int, float, bool, bool]:
        return (
            self._mirror_size.value(),
            self._pixel_size.value(),
            self._invert_x.isChecked(),
            self._invert_y.isChecked(),
        )


class CalibrationPreparationDialog(QDialog):
    """Ask the user whether to display a calibration frame before proceeding."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        default_square_size: int = 100,
        can_send: bool = False,
        max_square_size: int | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Prepare Calibration")
        self._chosen_action: str | None = "skip"

        layout = QFormLayout(self)

        message = QLabel(self)
        message.setText(
            "Send a bright square to the DMD before selecting\n"
            "the calibration image?"
        )
        message.setWordWrap(True)
        message.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addRow(message)

        self._square_size = QSpinBox(self)
        self._square_size.setRange(1, 8192)
        if max_square_size is not None:
            self._square_size.setMaximum(max(1, int(max_square_size)))
        self._square_size.setValue(max(1, int(default_square_size)))
        layout.addRow("Square size (mirrors)", self._square_size)

        button_box = QDialogButtonBox(parent=self)
        send_button = QPushButton("Send to DMD", self)
        send_button.setEnabled(can_send)
        if not can_send:
            send_button.setToolTip("Connect to the DMD to send a calibration frame.")
        skip_button = QPushButton("Continue without sending", self)
        skip_button.setDefault(True)
        cancel_button = button_box.addButton(
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.addButton(send_button, QDialogButtonBox.ButtonRole.AcceptRole)
        button_box.addButton(skip_button, QDialogButtonBox.ButtonRole.AcceptRole)
        layout.addRow(button_box)

        send_button.clicked.connect(self._on_send_clicked)
        skip_button.clicked.connect(self._on_skip_clicked)
        cancel_button.clicked.connect(self.reject)

    def _on_send_clicked(self) -> None:
        sender = self.sender()
        if sender is None or not sender.isEnabled():
            return
        self._chosen_action = "send"
        self.accept()

    def _on_skip_clicked(self) -> None:
        self._chosen_action = "skip"
        self.accept()

    def chosen_action(self) -> str | None:
        return self._chosen_action

    def square_size(self) -> int:
        return int(self._square_size.value())


class CyclePatternsDialog(QDialog):
    """Collect parameters required to generate cycle/repeat table entries."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        default_first_time: int = 0,
        default_cycle_count: int = 1,
        default_repeat_count: int = 1,
        default_repeat_gap: int = 100,
        default_cycle_gap: int = 250,
        default_duration: int = 100,
    ):
        super().__init__(parent)
        self.setWindowTitle("Cycle patterns")
        main_layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._cycle_count = QSpinBox(self)
        self._cycle_count.setRange(1, 1_000_000)
        self._cycle_count.setValue(max(1, int(default_cycle_count)))
        form.addRow("Number of cycles", self._cycle_count)

        self._repeat_count = QSpinBox(self)
        self._repeat_count.setRange(1, 1_000_000)
        self._repeat_count.setValue(max(1, int(default_repeat_count)))
        form.addRow("Repetitions per pattern", self._repeat_count)

        self._first_time = QSpinBox(self)
        self._first_time.setRange(0, 3_600_000)
        self._first_time.setSingleStep(10)
        self._first_time.setValue(max(0, int(default_first_time)))
        form.addRow("First pattern time (ms)", self._first_time)

        self._repeat_gap = QSpinBox(self)
        self._repeat_gap.setRange(0, 3_600_000)
        self._repeat_gap.setSingleStep(10)
        self._repeat_gap.setValue(max(0, int(default_repeat_gap)))
        form.addRow("Separation between repetitions (ms)", self._repeat_gap)

        self._cycle_gap = QSpinBox(self)
        self._cycle_gap.setRange(0, 3_600_000)
        self._cycle_gap.setSingleStep(10)
        self._cycle_gap.setValue(max(0, int(default_cycle_gap)))
        form.addRow("Additional gap between cycles (ms)", self._cycle_gap)

        self._duration = QSpinBox(self)
        self._duration.setRange(1, 3_600_000)
        self._duration.setSingleStep(10)
        self._duration.setValue(max(1, int(default_duration)))
        form.addRow("Duration for each entry (ms)", self._duration)

        main_layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    def values(self) -> dict[str, int | str]:
        return {
            "cycle_count": int(self._cycle_count.value()),
            "repeat_count": int(self._repeat_count.value()),
            "first_time_ms": int(self._first_time.value()),
            "repeat_gap_ms": int(self._repeat_gap.value()),
            "cycle_gap_ms": int(self._cycle_gap.value()),
            "duration_ms": int(self._duration.value()),
        }
