from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QTreeWidgetItem,
    QMessageBox,
    QInputDialog,
    QTableWidgetItem,
)

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from dmd_stim_widget import StimDMDWidget

T = TypeVar("T")


def _assert_not_None(item: T | None) -> T:
    assert item is not None
    return item


def extract_description(text: str) -> str:
    return text.strip().lstrip("#0123456789").lstrip(" -:\t")


class TreeManager:
    def __init__(self, widget: StimDMDWidget):
        self.widget = widget
        self._next_pattern_id = 0

    def new_pattern_id(self) -> int:
        """Generate a new pattern ID."""
        pid = self._next_pattern_id
        self._next_pattern_id += 1
        return pid

    def attach_pattern_id(self, item: QTreeWidgetItem, pid: int) -> None:
        """Attach a pattern ID to a tree widget item."""
        item.setData(0, Qt.ItemDataRole.UserRole, pid)

    def pattern_id(self, item: QTreeWidgetItem) -> int:
        """Get the pattern ID associated with a tree widget item."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        return int(data) if data is not None else -1

    def pattern_id_order(self) -> list[int]:
        """Get pattern IDs in order."""
        items = [
            _assert_not_None(self.widget.ui.treeWidget.topLevelItem(i))
            for i in range(self.widget.ui.treeWidget.topLevelItemCount())
        ]
        return [self.pattern_id(item) for item in items]

    def set_pattern_label(self, item: QTreeWidgetItem, index: int, desc: str) -> None:
        """Set the label for a pattern item."""
        item.setText(0, f"#{index} {desc}".rstrip())

    def renumber_pattern_labels(self) -> None:
        """Renumber all pattern labels to match their order in the tree."""
        for i in range(self.widget.ui.treeWidget.topLevelItemCount()):
            item = self.widget.ui.treeWidget.topLevelItem(i)
            assert item is not None
            desc = extract_description(item.text(0))
            self.set_pattern_label(item, i, desc)
        self.widget.table_manager.refresh_sequence_descriptions()

    def pattern_description_by_index(self, idx: int) -> str:
        """Get the description for a pattern by its index."""

        if 0 <= idx < self.widget.ui.treeWidget.topLevelItemCount():
            item = self.widget.ui.treeWidget.topLevelItem(idx)
            assert item is not None
            return extract_description(item.text(0))
        return ""

    # Change handlers

    def on_item_changed(self, item: QTreeWidgetItem, col: int):
        if item.parent() is None:
            idx = self.widget.ui.treeWidget.indexOfTopLevelItem(item)
            if idx >= 0:
                desc = extract_description(item.text(col))
                self.set_pattern_label(item, idx, desc)
                self.widget.table_manager.refresh_sequence_descriptions()

    # Actions

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
        self.widget.table_manager.remap_sequence_by_ids(old_ids, new_ids, on_deleted="drop")
        self.renumber_pattern_labels()
        return new_ids

    def remove_selected_patterns(self):
        """
        Remove the currently selected patterns from the tree and the sequence.
        This will also remove any associated ROIs.
        Patterns that are in use in the table will be either removed or replaced based on user choice.
        """

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
            desc_cur = extract_description(pattern.text(0))
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
                self.widget.table_manager.remap_sequence_by_ids(
                    old_ids,
                    new_ids,
                    on_deleted="replace",
                    replace_with=target_new_idx,
                )
                self.renumber_pattern_labels()
                old_ids = new_ids


class TableManager:
    def __init__(self, widget: StimDMDWidget):
        self.widget = widget
        self._updating_table = False

    def ensure_desc_column(self):
        """Ensure the description column exists in the table."""

        tbl = self.widget.ui.tableWidget
        if tbl.columnCount() < 4:
            tbl.setColumnCount(4)
        if not tbl.horizontalHeaderItem(3):
            tbl.setHorizontalHeaderItem(3, QTableWidgetItem("Description"))

    def remap_sequence_by_ids(
        self,
        old_ids: list[int],
        new_ids: list[int],
        *,
        on_deleted: str = "drop",
        replace_with: int | None = None,
    ) -> None:
        """Remap sequence IDs from old_ids to new_ids."""

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

    def set_sequence_row_description(self, row: int, pattern_idx: int) -> None:
        """Set the description for a sequence row based on the pattern index."""

        self.ensure_desc_column()
        desc = self.widget.tree_manager.pattern_description_by_index(pattern_idx)
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

    # Change handler

    def on_item_changed(self, item: QTableWidgetItem):
        if self._updating_table:
            return
        if item.column() == 2:
            try:
                idx = int(item.text())
            except Exception:
                return
            self.set_sequence_row_description(item.row(), idx)
