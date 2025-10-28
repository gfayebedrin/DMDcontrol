"""Pattern sequence import/export helpers for :class:`StimDMDWidget`.

The pattern table in the widget doubles as both a UI editor and an interface to
persist experiments.  This module documents how the pieces fit together:
reading/writing table contents, serialising pattern metadata and exporting
analysis information alongside the raw sequence.  Adding commentary here keeps
the high-level responsibilities close to the implementation.
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox, QTableWidgetItem

from ...logic import saving
from ...logic.calibration import DMDCalibration
from ...logic.geometry import axis_micrometre_to_global
from ...logic.sequence import PatternSequence


class PatternSequenceIOMixin:
    """Mixin bundling pattern table handling and persistence helpers.

    The mixin is responsible for translating the mutable table widget state into
    :class:`~stim1p.logic.sequence.PatternSequence` objects and vice versa.  It
    also encapsulates how files are located so UI code can focus on wiring
    signals.
    """

    _calibration: DMDCalibration | None

    def _read_table_ms(self):
        """Extract timing/duration/sequence columns from the pattern table."""

        timings, durations, sequence = [], [], []
        rows = self.ui.tableWidget.rowCount()
        for r in range(rows):
            t_item = self.ui.tableWidget.item(r, 0)
            d_item = self.ui.tableWidget.item(r, 1)
            s_item = self.ui.tableWidget.item(r, 2)
            try:
                if t_item and s_item:
                    t_text = (t_item.text() or "").strip()
                    s_text = (s_item.text() or "").strip()
                    if not t_text or not s_text:
                        continue
                    d_text = (d_item.text() if d_item else "") or ""
                    d_text = d_text.strip()
                    t = int(t_text)
                    d = int(d_text) if d_text else 0
                    s = int(s_text)
                    timings.append(t)
                    durations.append(d)
                    sequence.append(s)
            except Exception:
                continue
        return timings, durations, sequence

    def _write_table_ms(self, model: PatternSequence):
        """Populate the pattern table with values from ``model``."""

        t_ms = model.timings_milliseconds
        d_ms = model.durations_milliseconds
        seq = model.sequence
        self._updating_table = True
        self.table_manager.ensure_desc_column()
        self.ui.tableWidget.setRowCount(len(seq))
        for r, (t, d, s) in enumerate(zip(t_ms, d_ms, seq)):
            self.ui.tableWidget.setItem(r, 0, QTableWidgetItem(str(int(t))))
            self.ui.tableWidget.setItem(r, 1, QTableWidgetItem(str(int(d))))
            self.ui.tableWidget.setItem(r, 2, QTableWidgetItem(str(int(s))))
            self.table_manager.set_sequence_row_description(r, int(s))
        self._updating_table = False

    def _collect_model(self) -> PatternSequence | None:
        """Return the current :class:`PatternSequence` or surface validation errors."""

        try:
            return self.model
        except RuntimeError as exc:
            QMessageBox.warning(self, "Calibration required", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Pattern export failed", str(exc))
        return None

    def _prompt_save_path(self, title: str, initial_path: str) -> str:
        """Prompt the user for a file path and normalise the extension."""

        initial = initial_path.strip()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            title,
            initial if initial else "",
            "HDF5 files (*.h5 *.hdf5);;All files (*)",
        )
        if not file_path:
            return ""
        return self._ensure_h5_extension(file_path)

    @staticmethod
    def _ensure_h5_extension(path: str) -> str:
        """Append ``.h5`` to ``path`` if no HDF5-compatible suffix is present."""

        trimmed = path.strip()
        if not trimmed:
            return ""
        candidate = Path(trimmed)
        if candidate.suffix.lower() in {".h5", ".hdf5"}:
            return str(candidate)
        return str(candidate.with_suffix(".h5"))

    def _write_pattern_sequence(
        self,
        file_path: str,
        model: PatternSequence,
        *,
        silent: bool = False,
    ) -> str | None:
        """Serialise ``model`` to disk and optionally announce the destination."""

        target = self._ensure_h5_extension(file_path)
        if not target:
            return None
        try:
            saving.save_pattern_sequence(target, model)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", str(exc))
            return None
        if not silent:
            print(f"Saved PatternSequence to {target}")
        return target

    def _write_analysis_metadata(
        self,
        file_path: str,
        model: PatternSequence,
    ) -> None:
        """Append coordinate metadata to the exported pattern sequence file."""

        if self._calibration is None:
            raise RuntimeError("A calibration must be available to export analysis metadata.")
        calibration = self._calibration
        with h5py.File(file_path, "a") as handle:
            if "analysis" in handle:
                del handle["analysis"]
            analysis_grp = handle.create_group("analysis")
            analysis_grp.attrs["version"] = 1
            analysis_grp.attrs["generator"] = "StimDMDWidget"

            axis_grp = analysis_grp.create_group("axis")
            axis_grp.attrs["defined"] = bool(self._axis_defined)
            axis_grp.attrs["coordinate_system"] = "camera_pixels"
            axis_grp.attrs["camera_shape"] = np.asarray(calibration.camera_shape, dtype=np.int64)
            if self._axis_defined:
                axis_grp.create_dataset(
                    "origin_camera",
                    data=np.asarray(self._axis_origin_camera, dtype=np.float64),
                )
                axis_grp.create_dataset(
                    "angle_rad",
                    data=np.array(self._axis_angle_rad, dtype=np.float64),
                )
                try:
                    origin_um = self._axis_origin_micrometre()
                    axis_grp.create_dataset(
                        "origin_micrometre",
                        data=np.asarray(origin_um, dtype=np.float64),
                    )
                except Exception:  # noqa: BLE001
                    pass

            patterns_grp = analysis_grp.create_group("patterns_camera")
            patterns_grp.attrs["coordinate_system"] = "camera_pixels"

            descriptions = model.descriptions or []
            shape_types = model.shape_types or []

            axis_def = self._axis_definition()

            for pattern_index, pattern in enumerate(model.patterns):
                pattern_grp = patterns_grp.create_group(f"pattern_{pattern_index}")
                if pattern_index < len(descriptions) and descriptions[pattern_index]:
                    pattern_grp.attrs["description"] = descriptions[pattern_index]
                for poly_index, polygon in enumerate(pattern):
                    points = np.asarray(polygon, dtype=np.float64)
                    if points.ndim != 2 or points.shape[1] != 2:
                        continue
                    if self._axis_defined:
                        global_um = axis_micrometre_to_global(
                            points,
                            axis_def,
                            calibration,
                        )
                    else:
                        global_um = points
                    camera_points = calibration.micrometre_to_camera(global_um.T).T
                    dataset = pattern_grp.create_dataset(
                        f"polygon_{poly_index}", data=camera_points
                    )
                    if (
                        pattern_index < len(shape_types)
                        and poly_index < len(shape_types[pattern_index])
                    ):
                        dataset.attrs["shape_type"] = str(
                            shape_types[pattern_index][poly_index]
                        )

    def _load_patterns_file(self):
        """Load a pattern sequence from disk and populate the editor."""

        initial = self.ui.lineEdit_file_path.text().strip()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select pattern sequence",
            initial if initial else "",
            "HDF5 files (*.h5 *.hdf5);;All files (*)",
        )
        if not file_path:
            return
        if self._calibration is None:
            QMessageBox.warning(
                self,
                "Calibration required",
                "Load or compute a DMD calibration before loading patterns.",
            )
            return
        try:
            self.model = saving.load_pattern_sequence(file_path)
        except RuntimeError as exc:
            QMessageBox.warning(self, "Calibration required", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Load failed", str(exc))
            return
        self.ui.lineEdit_file_path.setText(file_path)
        print(f"Loaded PatternSequence from {file_path}")

    def _save_file(self) -> None:
        """Save the current pattern sequence, prompting for a path if necessary."""

        model = self._collect_model()
        if model is None:
            return
        current_path = self.ui.lineEdit_file_path.text().strip()
        if not current_path:
            target_path = self._prompt_save_path("Save pattern sequence", "")
            if not target_path:
                return
        else:
            target_path = self._ensure_h5_extension(current_path)
        saved_path = self._write_pattern_sequence(target_path, model)
        if saved_path:
            self.ui.lineEdit_file_path.setText(saved_path)

    def _save_file_as(self) -> None:
        """Always prompt for a location before saving the current sequence."""

        model = self._collect_model()
        if model is None:
            return
        current_path = self.ui.lineEdit_file_path.text().strip()
        target_path = self._prompt_save_path("Save pattern sequence as", current_path)
        if not target_path:
            return
        saved_path = self._write_pattern_sequence(target_path, model)
        if saved_path:
            self.ui.lineEdit_file_path.setText(saved_path)

    def _export_patterns_for_analysis(self) -> None:
        """Persist the sequence and supplement it with analysis metadata."""

        model = self._collect_model()
        if model is None:
            return
        current_path = self.ui.lineEdit_file_path.text().strip()
        target_path = self._prompt_save_path("Export pattern sequence", current_path)
        if not target_path:
            return
        saved_path = self._write_pattern_sequence(target_path, model, silent=True)
        if not saved_path:
            return
        try:
            self._write_analysis_metadata(saved_path, model)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "Export incomplete",
                "Pattern sequence saved, but analysis metadata could not be written.\n"
                f"Reason: {exc}",
            )
            return
        print(f"Exported PatternSequence with analysis metadata to {saved_path}")

    def _new_model(self):
        """Reset the editor to an empty :class:`PatternSequence`."""

        self.model = PatternSequence(
            patterns=[], sequence=[], timings=[], durations=[], descriptions=[]
        )
        self.ui.lineEdit_file_path.clear()
        print("Loaded empty PatternSequence")

    def _add_row_table(self):
        """Insert a new empty row at the bottom of the pattern table."""

        self.ui.tableWidget.insertRow(self.ui.tableWidget.rowCount())

    def _remove_row_table(self):
        """Delete any selected rows from the pattern table."""

        rows = sorted(
            {i.row() for i in self.ui.tableWidget.selectedIndexes()}, reverse=True
        )
        for r in rows:
            self.ui.tableWidget.removeRow(r)

    def _cycle_patterns(self) -> None:
        """Expand the table so each pattern is repeated according to user input."""

        pattern_count = self.ui.treeWidget.topLevelItemCount()
        if pattern_count <= 0:
            QMessageBox.information(
                self,
                "No patterns",
                "Create at least one pattern before cycling them.",
            )
            return

        table = self.ui.tableWidget
        last_time = 0
        if table.rowCount() > 0:
            last_item = table.item(table.rowCount() - 1, 0)
            if last_item is not None:
                try:
                    last_time = int(last_item.text())
                except Exception:
                    last_time = 0

        default_repeat_gap = 100
        default_cycle_gap = 250
        default_duration = 100
        default_first_time = last_time + default_repeat_gap if table.rowCount() > 0 else 0

        dialog = self._cycle_dialog_factory(
            default_first_time=default_first_time,
            default_cycle_count=1,
            default_repeat_count=1,
            default_repeat_gap=default_repeat_gap,
            default_cycle_gap=default_cycle_gap,
            default_duration=default_duration,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        params = dialog.values()
        cycle_count = max(1, int(params["cycle_count"]))
        repeat_count = max(1, int(params["repeat_count"]))
        first_time = int(params["first_time_ms"])
        repeat_gap = int(params["repeat_gap_ms"])
        cycle_gap = int(params["cycle_gap_ms"])
        duration = int(params["duration_ms"])

        if cycle_count <= 0 or repeat_count <= 0:
            return

        entries: list[tuple[int, int]] = []
        current_time = first_time

        for cycle_index in range(cycle_count):
            for pattern_idx in range(pattern_count):
                for repeat_index in range(repeat_count):
                    # Each ``entries`` tuple stores the pattern index and the
                    # start time for a single presentation.  We build the full
                    # list first to keep the table mutation isolated below.
                    entries.append((pattern_idx, current_time))
                    is_last_entry = (
                        cycle_index == cycle_count - 1
                        and pattern_idx == pattern_count - 1
                        and repeat_index == repeat_count - 1
                    )
                    if is_last_entry:
                        continue
                    current_time += repeat_gap
                    end_of_cycle = (
                        repeat_index == repeat_count - 1
                        and pattern_idx == pattern_count - 1
                    )
                    if end_of_cycle:
                        current_time += cycle_gap

        if not entries:
            return

        self.table_manager.ensure_desc_column()
        signals_were_blocked = self.ui.tableWidget.blockSignals(True)
        try:
            for pattern_idx, start_time in entries:
                row = table.rowCount()
                table.insertRow(row)
                table.setItem(row, 0, QTableWidgetItem(str(start_time)))
                table.setItem(row, 1, QTableWidgetItem(str(duration)))
                table.setItem(row, 2, QTableWidgetItem(str(pattern_idx)))
                self.table_manager.set_sequence_row_description(row, pattern_idx)
        finally:
            self.ui.tableWidget.blockSignals(signals_were_blocked)
        self.table_manager.refresh_sequence_descriptions()

    def _cycle_dialog_factory(self, **defaults):
        from ..dmd_dialogs import CyclePatternsDialog

        return CyclePatternsDialog(self, **defaults)
