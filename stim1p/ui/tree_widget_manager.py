from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QTreeWidgetItem,
    QMessageBox,
    QInputDialog,
    QTableWidgetItem,
)
import pyqtgraph as pg
import numpy as np

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from dmd_stim_widget import StimDMDWidget
T = TypeVar("T")


def _assert_not_None(item: T | None) -> T:
    assert item is not None
    return item


class TreeWidgetManager:
    def __init__(
        self,
        widget: StimDMDWidget,
    ):
        self._next_pattern_id = 0
        self.widget = widget

    def new_pattern_id(self) -> int:
        pid = self._next_pattern_id
        self._next_pattern_id += 1
        return pid

    def attach_pattern_id(self, item: QTreeWidgetItem, pid: int) -> None:
        item.setData(0, Qt.ItemDataRole.UserRole, int(pid))

    def pattern_id(self, item: QTreeWidgetItem) -> int:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        return int(data) if data is not None else -1

    def pattern_id_order(self) -> list[int]:
        items = [
            _assert_not_None(self.widget.ui.treeWidget.topLevelItem(i))
            for i in range(self.widget.ui.treeWidget.topLevelItemCount())
        ]
        return [self.pattern_id(item) for item in items]

    def extract_description(self, text: str) -> str:
        s = text.strip()
        if s.startswith("#"):
            s = s[1:]
            while s and s[0].isdigit():
                s = s[1:]
            s = s.lstrip(" -:\t")
        return s

    def set_pattern_label(self, item: QTreeWidgetItem, index: int, desc: str) -> None:
        item.setText(0, f"#{index} {desc}".rstrip())

    def renumber_pattern_labels(self) -> None:
        for i in range(self.widget.ui.treeWidget.topLevelItemCount()):
            item = self.widget.ui.treeWidget.topLevelItem(i)
            assert item is not None
            desc = self.extract_description(item.text(0))
            self.set_pattern_label(item, i, desc)
        self.refresh_sequence_descriptions()

    def remap_sequence_by_ids(
        self,
        old_ids: list[int],
        new_ids: list[int],
        *,
        on_deleted: str = "drop",
        replace_with: int | None = None,
    ) -> None:
        id_to_new_idx = {pid: i for i, pid in enumerate(new_ids)}
        rows_to_drop = []
        for r in range(self.widget.ui.tableWidget.rowCount()):
            idx_item = self.widget.ui.tableWidget.item(r, 2)
            if not idx_item:
                continue
            try:
                old_idx = int(idx_item.text())
            except Exception:
                continue
            if not (0 <= old_idx < len(old_ids)):
                continue
            pid = old_ids[old_idx]
            if pid in id_to_new_idx:
                idx_item.setText(str(id_to_new_idx[pid]))
            else:
                if on_deleted == "drop":
                    rows_to_drop.append(r)
                elif on_deleted == "replace" and replace_with is not None:
                    idx_item.setText(str(replace_with))
        for r in sorted(rows_to_drop, reverse=True):
            self.widget.ui.tableWidget.removeRow(r)
        self.refresh_sequence_descriptions()

    def ensure_desc_column(self):
        tbl = self.widget.ui.tableWidget
        if tbl.columnCount() < 4:
            tbl.setColumnCount(4)
        if not tbl.horizontalHeaderItem(3):
            tbl.setHorizontalHeaderItem(3, QTableWidgetItem("Description"))

    def pattern_description_by_index(self, idx: int) -> str:
        if 0 <= idx < self.widget.ui.treeWidget.topLevelItemCount():
            item = self.widget.ui.treeWidget.topLevelItem(idx)
            assert item is not None
            return self.extract_description(item.text(0))
        return ""

    def set_sequence_row_description(self, row: int, pattern_idx: int) -> None:
        self.ensure_desc_column()
        desc = self.pattern_description_by_index(pattern_idx)
        it = self.widget.ui.tableWidget.item(row, 3)
        if it is None:
            it = QTableWidgetItem("")
            self.widget.ui.tableWidget.setItem(row, 3, it)
        it.setText(desc)
        it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

    def refresh_sequence_descriptions(self):
        self._updating_table = True
        rows = self.widget.ui.tableWidget.rowCount()
        for r in range(rows):
            idx_item = self.widget.ui.tableWidget.item(r, 2)
            if not idx_item:
                continue
            try:
                idx = int(idx_item.text())
            except Exception:
                continue
            self.set_sequence_row_description(r, idx)
        self._updating_table = False

    # Actions

    def add_roi(self):
        if not self.widget.ui.treeWidget.selectedItems():
            return
        selected = self.widget.ui.treeWidget.selectedItems()[0]
        root = selected.parent() or selected
        a = 10
        positions = np.asarray([[a, a], [-a, a], [-a, -a], [a, -a]], dtype=float)
        node = QTreeWidgetItem(["roi"])
        root.addChild(node)
        poly = self.widget.roi_manager.register_polygon(node, positions)
        poly.change_ref(self.widget.crosshair.pos(), self.widget.crosshair.angle())

    def add_pattern(self):
        index = self.widget.ui.treeWidget.topLevelItemCount()
        root = QTreeWidgetItem([""])
        self.attach_pattern_id(root, self.new_pattern_id())
        root.setFlags(root.flags() | Qt.ItemFlag.ItemIsEditable)
        self.widget.ui.treeWidget.insertTopLevelItem(index, root)
        self.set_pattern_label(root, index, "")
        self.renumber_pattern_labels()

    def _remove_pattern_and_update_sequence(
        self, pattern: QTreeWidgetItem, del_idx: int, old_ids: list[int]
    ) -> list[int]:
        self.widget.ui.treeWidget.takeTopLevelItem(del_idx)
        self.widget.roi_manager.remove_items(
            [pattern] + [pattern.child(i) for i in range(pattern.childCount())]
        )
        new_ids = self.pattern_id_order()
        self.remap_sequence_by_ids(old_ids, new_ids, on_deleted="drop")
        self.renumber_pattern_labels()
        return new_ids

    def remove_selected_patterns(self):

        items = self.widget.ui.treeWidget.selectedItems()
        if not items:
            return

        patterns = [it for it in items if it.parent() is None]
        leaves = [it for it in items if it.parent() is not None]

        # Remove leaves from their parents, and ROIs associated with the leaves
        for leaf in leaves:
            parent = leaf.parent()
            if parent is None:
                continue
            parent.removeChild(leaf)

        self.widget.roi_manager.remove_items(leaves)

        if not patterns:
            return

        # Handle pattern removal
        old_ids = self.pattern_id_order()

        for pattern in patterns:

            # Identify the pattern
            del_idx = self.widget.ui.treeWidget.indexOfTopLevelItem(pattern)
            if del_idx < 0:
                continue
            assert del_idx in range(len(old_ids))
            desc_cur = self.extract_description(pattern.text(0))
            use_count = 0

            # Count the number of uses in the table
            for r in range(self.widget.ui.tableWidget.rowCount()):
                it = self.widget.ui.tableWidget.item(r, 2)
                if it and it.text().isdigit() and int(it.text()) == del_idx:
                    use_count += 1

            if use_count == 0 or len(old_ids) == 1:
                old_ids = self._remove_pattern_and_update_sequence(
                    pattern, del_idx, old_ids
                )
                continue

            # Ask what to do with used pattern
            msg = QMessageBox(self.widget)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Pattern is used")
            msg.setText(
                f"Pattern #{del_idx} ({desc_cur or 'no description'}) is used {use_count} times in the sequence."
            )
            remove_btn = msg.addButton(
                "Remove rows", QMessageBox.ButtonRole.DestructiveRole
            )
            replace_btn = msg.addButton(
                "Replace uses…", QMessageBox.ButtonRole.ActionRole
            )
            cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)
            msg.exec()

            if msg.clickedButton() is cancel_btn:
                continue

            if msg.clickedButton() is remove_btn:
                old_ids = self._remove_pattern_and_update_sequence(
                    pattern, del_idx, old_ids
                )
                continue

            if msg.clickedButton() is replace_btn:

                remaining_old = [i for i in range(len(old_ids)) if i != del_idx]

                # Prompt the user to choose an index to replace with
                chosen_old_idx, ok = QInputDialog.getInt(
                    self.widget,
                    "Replace uses",
                    f"Replace all uses of #{del_idx} with old index:",
                    value=min(remaining_old),
                    minValue=min(remaining_old),
                    maxValue=max(remaining_old),
                )

                if not ok or chosen_old_idx not in remaining_old:
                    continue

                self.widget.ui.treeWidget.takeTopLevelItem(del_idx)
                self.widget.roi_manager.remove_items(
                    [pattern] + [pattern.child(i) for i in range(pattern.childCount())]
                )

                new_ids = self.pattern_id_order()

                target_pid = old_ids[chosen_old_idx]

                target_new_idx = new_ids.index(target_pid)
                self.remap_sequence_by_ids(
                    old_ids,
                    new_ids,
                    on_deleted="replace",
                    replace_with=target_new_idx,
                )
                self.renumber_pattern_labels()
                old_ids = new_ids
