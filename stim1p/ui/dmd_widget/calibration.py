"""Calibration workflow helpers used by :class:`StimDMDWidget`."""

from __future__ import annotations

import os
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from ...logic import saving
from ...logic.calibration import DMDCalibration, compute_calibration_from_square
from ..capture_tools import AxisCapture
from ..dmd_dialogs import CalibrationDialog, CalibrationPreparationDialog

class CalibrationWorkflowMixin:
    """Mixin collecting the calibration related routines."""

    _last_calibration_file_path: str
    _current_image: np.ndarray | None
    _preferences: object

    def remember_calibration_file(self, path: str) -> None:
        """Store the path to the most recently used calibration file."""

        self._last_calibration_file_path = path
        self._preferences.set_last_calibration_file_path(path)

    def last_calibration_file_path(self) -> str:
        """Return the last calibration file recorded for this session."""

        return self._last_calibration_file_path

    def _ensure_calibration_available(self) -> None:
        stored_path = self.last_calibration_file_path()
        if stored_path:
            success, _ = self._load_calibration_from_path(stored_path)
            if success:
                return
        self._calibrate_dmd()

    def _calibrate_dmd(self) -> None:
        action = self._prompt_calibration_action()
        if action is None:
            return
        if action == "load":
            self._load_calibration_from_dialog()
        elif action == "define":
            self._define_new_calibration()

    def _prompt_calibration_action(self) -> str | None:
        prompt = QMessageBox(self)
        prompt.setWindowTitle("Calibrate DMD")
        prompt.setIcon(QMessageBox.Icon.Question)
        prompt.setText("Choose how to obtain a DMD calibration.")
        load_button = prompt.addButton(
            "Load calibration file", QMessageBox.ButtonRole.ActionRole
        )
        define_button = prompt.addButton(
            "Define new calibration", QMessageBox.ButtonRole.ActionRole
        )
        prompt.addButton(QMessageBox.StandardButton.Cancel)
        if self._calibration is None:
            prompt.setDefaultButton(define_button)
        else:
            prompt.setDefaultButton(load_button)
        prompt.exec()
        clicked = prompt.clickedButton()
        if clicked is None:
            return None
        standard = prompt.standardButton(clicked)
        if standard == QMessageBox.StandardButton.Cancel:
            return None
        if clicked is load_button:
            return "load"
        if clicked is define_button:
            return "define"
        return None

    def _load_calibration_from_dialog(self) -> None:
        last_path = self.last_calibration_file_path()
        initial = ""
        if last_path:
            candidate = Path(str(last_path)).expanduser()
            if candidate.exists():
                initial = str(candidate)
            else:
                parent = candidate.parent
                if parent.exists():
                    initial = str(parent)
        file_filter = "Calibration files (*.h5 *.hdf5);;All files (*)"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select calibration file",
            initial,
            file_filter,
        )
        if not file_path:
            return
        success, error = self._load_calibration_from_path(file_path)
        if not success:
            QMessageBox.warning(
                self,
                "Calibration load error",
                f"Unable to load calibration file:\n{error}",
            )

    def _prompt_calibration_preparation(self) -> tuple[str, int] | None:
        mirror_counts = self._preferences.mirror_counts()
        default_mirror = int(
            max(1, round(0.5 * (float(mirror_counts[0]) + float(mirror_counts[1]))))
        )
        try:
            dmd_shape = self._stim.dmd_shape()
        except Exception:  # noqa: BLE001
            dmd_shape = None

        dialog = CalibrationPreparationDialog(
            self,
            default_square_size=default_mirror,
            can_send=self._stim.is_dmd_connected,
            max_square_size=min(dmd_shape) if dmd_shape is not None else None,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        action = dialog.chosen_action()
        size = dialog.square_size()
        if action is None:
            return None
        return action, size

    def _send_calibration_frame(self, square_size: int) -> bool:
        if not self._stim.is_dmd_connected:
            QMessageBox.information(
                self,
                "DMD disconnected",
                "Connect to the DMD before sending a calibration frame.",
            )
            return False
        try:
            self._stim.display_calibration_frame(square_size)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "Calibration frame error",
                str(exc),
            )
            return False
        return True

    def _define_new_calibration(self) -> None:
        """Guide the user through loading a calibration image and storing it."""

        preparation = self._prompt_calibration_preparation()
        if preparation is None:
            return
        action, square_size = preparation
        if action == "send":
            self._send_calibration_frame(square_size)

        initial_dir = self.ui.lineEdit_image_folder_path.text().strip()
        stored_image_path = self._preferences.last_calibration_image_path()
        if stored_image_path:
            stored_dir = os.path.dirname(stored_image_path)
            if stored_dir:
                initial_dir = stored_dir
        file_filter = (
            "Image files (*.png *.jpg *.jpeg *.tif *.tiff *.gif);;All files (*)"
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select calibration image",
            initial_dir if initial_dir else "",
            file_filter,
        )
        if not file_path:
            return
        try:
            with Image.open(file_path) as pil_image:
                calibration_image = np.array(pil_image)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Calibration image error",
                f"Unable to load calibration image:\n{exc}",
            )
            return
        self._preferences.set_last_calibration_image_path(file_path)
        selected_dir = os.path.dirname(file_path)
        if selected_dir:
            self.ui.lineEdit_image_folder_path.setText(selected_dir)

        previous_image = self._current_image
        previous_view = self._capture_view_state()
        selected_items = self.ui.treeWidget.selectedItems()
        selected_item = selected_items[0] if selected_items else None
        self.roi_manager.clear_visible_only()

        self._set_image(
            calibration_image,
            fit_to_view=True,
            apply_axis=False,
            auto_contrast=True,
        )

        diagonal_points = self._prompt_calibration_diagonal()
        if diagonal_points is None:
            QMessageBox.information(
                self,
                "Calibration cancelled",
                "No calibration diagonal was drawn. Calibration has been cancelled.",
            )
            self._restore_after_calibration(previous_image, previous_view, selected_item)
            return

        invert_defaults = self._preferences.axes_inverted()
        default_invert_x = bool(invert_defaults[0])
        default_invert_y = bool(invert_defaults[1])
        default_mirrors = self._preferences.mirror_counts()
        if action == "send":
            default_mirrors = (int(square_size), int(square_size))
        dialog = CalibrationDialog(
            self,
            default_mirrors=default_mirrors,
            default_pixel_size=self._preferences.pixel_size(),
            default_invert_x=default_invert_x,
            default_invert_y=default_invert_y,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._restore_after_calibration(previous_image, previous_view, selected_item)
            return

        square_mirrors, pixel_size, invert_x, invert_y = dialog.values()
        self._preferences.set_mirror_counts(square_mirrors, square_mirrors)
        self._preferences.set_pixel_size(pixel_size)
        self._preferences.set_axes_inverted(invert_x, invert_y)
        camera_shape = (
            int(calibration_image.shape[1]),
            int(calibration_image.shape[0]),
        )
        if self.dmd is not None and hasattr(self.dmd, "shape"):
            try:
                dmd_shape = tuple(int(v) for v in self.dmd.shape)
            except Exception:
                dmd_shape = (1024, 768)
        else:
            dmd_shape = (1024, 768)

        try:
            calibration = compute_calibration_from_square(
                diagonal_points,
                square_mirrors,
                pixel_size,
                camera_shape=camera_shape,
                dmd_shape=dmd_shape,
                invert_x=invert_x,
                invert_y=invert_y,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Calibration failed", str(exc))
            self._restore_after_calibration(previous_image, previous_view, selected_item)
            return

        self.calibration = calibration
        print(
            "Updated DMD calibration: pixels/mirror=(%.3f, %.3f), µm/mirror=(%.3f, %.3f), rotation=%.2f°"
            % (
                calibration.camera_pixels_per_mirror[0],
                calibration.camera_pixels_per_mirror[1],
                calibration.micrometers_per_mirror[0],
                calibration.micrometers_per_mirror[1],
                np.degrees(calibration.camera_rotation_rad),
            )
        )
        self._prompt_save_calibration(calibration)
        self._restore_after_calibration(previous_image, previous_view, selected_item)

    def _prompt_save_calibration(self, calibration: DMDCalibration) -> None:
        response = QMessageBox.question(
            self,
            "Save calibration",
            "Do you want to save this calibration to a file?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        last_path = self.last_calibration_file_path()
        initial = ""
        if last_path:
            candidate = Path(str(last_path)).expanduser()
            if candidate.exists():
                initial = str(candidate)
            else:
                parent = candidate.parent
                if parent.exists():
                    initial = str(parent / candidate.name)
        file_filter = "Calibration files (*.h5 *.hdf5);;All files (*)"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save calibration",
            initial,
            file_filter,
        )
        if not file_path:
            return
        root, ext = os.path.splitext(file_path)
        if not ext:
            file_path = f"{file_path}.h5"
        self._save_calibration_to_path(calibration, file_path)

    def _save_calibration_to_path(self, calibration: DMDCalibration, file_path: str) -> bool:
        path = Path(str(file_path)).expanduser()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            saving.save_calibration(str(path), calibration)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Save failed",
                f"Unable to save calibration file:\n{exc}",
            )
            return False
        self.remember_calibration_file(str(path))
        print(f"Saved DMD calibration to {path}")
        return True

    def _load_calibration_from_path(self, path_str: str) -> tuple[bool, str | None]:
        """Load calibration from disk and activate it."""

        path = Path(str(path_str)).expanduser()
        try:
            calibration = saving.load_calibration(str(path))
        except Exception as exc:
            message = f"{path}: {exc}"
            print(f"Failed to load stored calibration from {message}")
            return False, message
        self.calibration = calibration
        self.remember_calibration_file(str(path))
        try:
            pixel_size = calibration.camera_pixel_size_um
        except AttributeError:
            pixel_size = None
        if pixel_size is not None:
            self._preferences.set_pixel_size(float(pixel_size))
        print(f"Active DMD calibration: {path}")
        return True, None

    def _prompt_calibration_diagonal(self) -> np.ndarray | None:
        """Capture the diagonal of the illuminated calibration square."""

        prompt = QMessageBox(self)
        prompt.setWindowTitle("Select calibration diagonal")
        prompt.setIcon(QMessageBox.Icon.Information)
        prompt.setText("Draw the diagonal of the illuminated calibration square.")
        prompt.setInformativeText(
            "Left-click and drag to draw the line. Right-click or press Esc to cancel."
        )
        prompt.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok
        )
        if prompt.exec() != QMessageBox.StandardButton.Ok:
            return None

        capture = AxisCapture(self._get_view_box(), self)
        segment = capture.exec()
        if segment is None:
            return None
        start, end = segment
        start_xy = np.array([start.x(), start.y()], dtype=float)
        end_xy = np.array([end.x(), end.y()], dtype=float)
        if not np.all(np.isfinite(start_xy)) or not np.all(np.isfinite(end_xy)):
            return None
        if np.linalg.norm(end_xy - start_xy) < 1e-9:
            return None
        return np.vstack((start_xy, end_xy))

    def _capture_view_state(
        self,
    ) -> tuple[tuple[float, float], tuple[float, float]] | None:
        view = self._get_view_box()
        try:
            x_range, y_range = view.viewRange()
        except Exception:
            return None
        return (tuple(x_range), tuple(y_range))

    def _restore_after_calibration(
        self,
        previous_image: np.ndarray | None,
        previous_view_range: tuple[tuple[float, float], tuple[float, float]] | None,
        selected_item,
    ) -> None:
        if previous_image is not None:
            self._set_image(previous_image, auto_contrast=True)
            if previous_view_range is not None:
                x_range, y_range = previous_view_range
                self._get_view_box().setRange(
                    xRange=x_range,
                    yRange=y_range,
                    padding=0.0,
                )
        else:
            self._image_item.clear()
            self._current_levels = None
            self._current_image = None

        if selected_item is not None:
            self.roi_manager.show_for_item(selected_item)
        else:
            self.roi_manager.clear_visible_only()
