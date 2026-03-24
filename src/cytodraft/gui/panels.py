from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QDoubleValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cytodraft.core.statistics import STATISTIC_DEFINITIONS

ITEM_ROLE_ID = Qt.UserRole
ITEM_ROLE_TYPE = Qt.UserRole + 1
ITEM_ROLE_GROUP = Qt.UserRole + 2


def _make_manager_button(
    text: str,
    *,
    tooltip: str,
    variant: str,
    fixed_width: int | None = None,
) -> QToolButton:
    button = QToolButton()
    button.setText(text)
    button.setToolTip(tooltip)
    button.setProperty("variant", variant)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    button.setFixedHeight(30)
    if fixed_width is not None:
        button.setFixedWidth(fixed_width)
    else:
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return button


class SamplePanel(QWidget):
    """Unified left panel: all samples listed with their gates as children."""

    # Sample signals
    sample_selection_changed = Signal(int)
    edit_sample_requested = Signal(int)
    add_sample_keyword_requested = Signal(int)
    edit_compensation_sample_requested = Signal(int)
    assign_sample_group_requested = Signal(int, str)
    assign_custom_sample_group_requested = Signal(int)
    apply_active_gate_to_group_requested = Signal(int)
    apply_all_gates_to_group_requested = Signal(int)
    apply_active_gate_to_all_requested = Signal(int)
    apply_all_gates_to_all_requested = Signal(int)
    # Group signals (accessed via sample context)
    select_group_samples_requested = Signal(str)   # group_name
    rename_group_requested = Signal(str)
    recolor_group_requested = Signal(str)
    annotate_group_requested = Signal(str)
    delete_group_requested = Signal(str)
    # Gate signals
    gate_selection_changed = Signal(int)
    rename_gate_context_requested = Signal(int)
    recolor_gate_context_requested = Signal(int)
    delete_gate_context_requested = Signal(int)
    export_gate_context_requested = Signal(int)
    # Batch sample signals (multi-select)
    delete_samples_batch_requested = Signal(object)             # list[int] workspace_indices
    assign_samples_group_batch_requested = Signal(object, str)  # (list[int], group_name)
    apply_active_gate_to_selected_requested = Signal(object)    # list[int] workspace_indices
    apply_all_gates_to_selected_requested = Signal(object)      # list[int] workspace_indices
    # Batch gate signals (multi-select)
    delete_gates_batch_requested = Signal(object)               # list[int] gate_indices
    apply_gates_to_group_batch_requested = Signal(int, object)  # (source_ws_index, list[int])
    apply_gates_to_all_batch_requested = Signal(int, object)    # (source_ws_index, list[int])

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._available_groups: list[tuple[str, str]] = []  # (name, color_hex)
        self._active_workspace_index: int | None = None
        self._ws_index_to_item: dict[int, QTreeWidgetItem] = {}

        self.sample_tree = QTreeWidget()
        self.sample_tree.setHeaderHidden(True)
        self.sample_tree.setColumnCount(1)
        self.sample_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sample_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.sample_tree.setIndentation(16)
        self.sample_tree.setAnimated(True)

        self.add_sample_button = _make_manager_button(
            "+",
            tooltip="Add samples to workspace",
            variant="primary",
            fixed_width=36,
        )
        self.remove_sample_button = _make_manager_button(
            "−",
            tooltip="Remove selected sample(s)",
            variant="danger",
            fixed_width=36,
        )
        self.remove_sample_button.setEnabled(False)
        self.more_options_button = _make_manager_button(
            "⋯  Options",
            tooltip="Show all actions for the selected item",
            variant="subtle",
        )
        self.more_options_button.setEnabled(False)

        toolbar_row = QHBoxLayout()
        toolbar_row.setContentsMargins(0, 0, 0, 0)
        toolbar_row.setSpacing(6)
        toolbar_row.addWidget(self.add_sample_button)
        toolbar_row.addWidget(self.remove_sample_button)
        toolbar_row.addWidget(self.more_options_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(2, 4, 2, 2)
        layout.setSpacing(4)
        layout.addLayout(toolbar_row)
        layout.addWidget(self.sample_tree)
        self.setLayout(layout)

        self.sample_tree.currentItemChanged.connect(self._on_tree_selection_changed)
        self.sample_tree.itemSelectionChanged.connect(self._on_selection_set_changed)
        self.sample_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self.more_options_button.clicked.connect(self._on_more_options_clicked)

    # ── Public API ──────────────────────────────────────────────────────

    def set_available_groups(self, groups: list[tuple[str, str]]) -> None:
        """Update the list of groups used to populate the right-click assign submenu."""
        self._available_groups = list(groups)

    def reset(self) -> None:
        self.sample_tree.clear()
        self._ws_index_to_item.clear()
        self._active_workspace_index = None
        self.remove_sample_button.setEnabled(False)
        self.more_options_button.setEnabled(False)

    def reset_samples(self) -> None:
        self.reset()

    def add_sample(
        self,
        name: str,
        workspace_index: int,
        group_color: str = "#5a6b7a",
        group_name: str = "",
    ) -> None:
        item = QTreeWidgetItem(self.sample_tree)
        item.setText(0, name)
        item.setData(0, ITEM_ROLE_ID, workspace_index)
        item.setData(0, ITEM_ROLE_TYPE, "sample")
        item.setData(0, ITEM_ROLE_GROUP, group_name)
        item.setForeground(0, QColor(group_color))
        if group_name:
            item.setToolTip(0, f"Group: {group_name}")
        self._ws_index_to_item[workspace_index] = item
        self._add_all_events_child(item)

    def update_sample(
        self,
        workspace_index: int,
        label: str,
        group_color: str,
        group_name: str = "",
    ) -> None:
        item = self._ws_index_to_item.get(workspace_index)
        if item is not None:
            item.setText(0, label)
            item.setForeground(0, QColor(group_color))
            if group_name:
                item.setData(0, ITEM_ROLE_GROUP, group_name)
                item.setToolTip(0, f"Group: {group_name}")

    def set_gates_for_sample(
        self,
        workspace_index: int,
        gates: list[tuple[str, str]],
    ) -> None:
        """Replace gate children for a sample. gates = list of (label, color_hex)."""
        item = self._ws_index_to_item.get(workspace_index)
        if item is None:
            return
        was_expanded = item.isExpanded()
        while item.childCount() > 0:
            item.removeChild(item.child(0))
        self._add_all_events_child(item)
        for gate_row, (label, color_hex) in enumerate(gates, start=1):
            child = QTreeWidgetItem(item)
            child.setText(0, label)
            child.setData(0, ITEM_ROLE_ID, gate_row)
            child.setData(0, ITEM_ROLE_TYPE, "gate")
            child.setForeground(0, QColor(color_hex))
        if was_expanded or gates:
            item.setExpanded(True)

    def update_gate_in_sample(
        self,
        workspace_index: int,
        gate_row: int,
        label: str,
        color_hex: str,
    ) -> None:
        item = self._ws_index_to_item.get(workspace_index)
        if item is None:
            return
        for i in range(item.childCount()):
            child = item.child(i)
            if child.data(0, ITEM_ROLE_ID) == gate_row:
                child.setText(0, label)
                child.setForeground(0, QColor(color_hex))
                break

    def select_sample(self, workspace_index: int) -> None:
        item = self._ws_index_to_item.get(workspace_index)
        if item is not None:
            self.sample_tree.setCurrentItem(item)
            item.setExpanded(True)

    def select_gate_row(self, workspace_index: int, gate_row: int) -> None:
        item = self._ws_index_to_item.get(workspace_index)
        if item is None:
            return
        for i in range(item.childCount()):
            child = item.child(i)
            if child.data(0, ITEM_ROLE_ID) == gate_row:
                self.sample_tree.setCurrentItem(child)
                return
        self.sample_tree.setCurrentItem(item)

    def highlight_group_samples(self, group_name: str) -> None:
        """Visually select all sample items belonging to group_name."""
        self.sample_tree.clearSelection()
        root = self.sample_tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.data(0, ITEM_ROLE_TYPE) == "sample" and item.data(0, ITEM_ROLE_GROUP) == group_name:
                item.setSelected(True)

    def current_sample_workspace_index(self) -> int | None:
        item = self.sample_tree.currentItem()
        if item is None:
            return None
        if item.data(0, ITEM_ROLE_TYPE) == "sample":
            val = item.data(0, ITEM_ROLE_ID)
            return int(val) if val is not None else None
        if item.data(0, ITEM_ROLE_TYPE) == "gate":
            parent = item.parent()
            if parent is not None:
                val = parent.data(0, ITEM_ROLE_ID)
                return int(val) if val is not None else None
        return None

    def selected_sample_workspace_indices(self) -> list[int]:
        """Return workspace indices of all selected sample items."""
        result = []
        for item in self.sample_tree.selectedItems():
            if item.data(0, ITEM_ROLE_TYPE) == "sample":
                val = item.data(0, ITEM_ROLE_ID)
                if val is not None:
                    result.append(int(val))
        return result

    def selected_gate_indices(self) -> list[int]:
        """Return 0-based gate indices for all selected real gate items."""
        result = []
        for item in self.sample_tree.selectedItems():
            if item.data(0, ITEM_ROLE_TYPE) == "gate":
                gate_row = int(item.data(0, ITEM_ROLE_ID) or 0)
                if gate_row > 0:
                    result.append(gate_row - 1)
        return result

    def selected_item_type(self) -> str | None:
        """Return "sample", "gate", "mixed", or None if nothing selected."""
        selected = self.sample_tree.selectedItems()
        if not selected:
            return None
        types = {item.data(0, ITEM_ROLE_TYPE) for item in selected}
        if len(types) == 1:
            return next(iter(types))
        return "mixed"

    # ── Backward-compatibility stubs ────────────────────────────────────

    def reset_gates(self) -> None:
        pass

    def add_gate(self, label: str, *, select: bool = True) -> None:
        pass

    def update_gate(self, gate_index: int, label: str, color_hex: str) -> None:
        pass

    def gate_item(self, gate_index: int) -> None:
        return None

    def set_population_context(self, origin_name: str, child_names: list[str]) -> None:
        pass

    def set_sample_details(self, details: str) -> None:
        pass

    # ── Private helpers ──────────────────────────────────────────────────

    def _add_all_events_child(self, parent_item: QTreeWidgetItem) -> None:
        child = QTreeWidgetItem(parent_item)
        child.setText(0, "All events")
        child.setData(0, ITEM_ROLE_ID, 0)
        child.setData(0, ITEM_ROLE_TYPE, "gate")

    def _on_tree_selection_changed(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            self.remove_sample_button.setEnabled(False)
            self.more_options_button.setEnabled(False)
            return

        # Multi-select: update buttons only, do NOT emit sample/gate signals.
        # Emitting would trigger a full refresh that calls setCurrentItem with
        # ClearAndSelect, which would destroy the multi-selection visually.
        if len(self.sample_tree.selectedItems()) > 1:
            self.remove_sample_button.setEnabled(True)
            self.more_options_button.setEnabled(True)
            return

        item_type = current.data(0, ITEM_ROLE_TYPE)
        self.remove_sample_button.setEnabled(True)
        self.more_options_button.setEnabled(True)

        if item_type == "sample":
            workspace_index = int(current.data(0, ITEM_ROLE_ID))
            if workspace_index != self._active_workspace_index:
                self._active_workspace_index = workspace_index
                self.sample_selection_changed.emit(workspace_index)
            # gate_selection_changed will be triggered by _refresh_gate_panel after sample loads

        elif item_type == "gate":
            parent = current.parent()
            if parent is None:
                return
            parent_ws_index = int(parent.data(0, ITEM_ROLE_ID))
            gate_row = int(current.data(0, ITEM_ROLE_ID) or 0)
            if parent_ws_index != self._active_workspace_index:
                # Different sample – switch sample first; gate resets to 0
                self._active_workspace_index = parent_ws_index
                self.sample_selection_changed.emit(parent_ws_index)
            else:
                # Same sample – just switch gate
                self.gate_selection_changed.emit(gate_row)

    def _on_selection_set_changed(self) -> None:
        """Keeps button states correct when selection changes without currentItemChanged firing
        (e.g. Ctrl+click to deselect an item, or going from multi back to single selection)."""
        selected = self.sample_tree.selectedItems()
        has_any = bool(selected)
        self.remove_sample_button.setEnabled(has_any)
        self.more_options_button.setEnabled(has_any)

    def _on_more_options_clicked(self) -> None:
        selected = self.sample_tree.selectedItems()
        if not selected:
            return
        global_pos = self.more_options_button.mapToGlobal(
            self.more_options_button.rect().bottomLeft()
        )
        if len(selected) > 1:
            self._dispatch_multi_context_menu(global_pos, selected)
            return
        item = selected[0]
        item_type = item.data(0, ITEM_ROLE_TYPE)
        if item_type == "sample":
            self._show_sample_context_menu(global_pos, item)
        elif item_type == "gate":
            self._show_gate_context_menu(global_pos, item)

    def _on_tree_context_menu(self, pos) -> None:
        item = self.sample_tree.itemAt(pos)
        if item is None:
            return
        global_pos = self.sample_tree.mapToGlobal(pos)
        selected = self.sample_tree.selectedItems()
        # If right-clicked item is not in current selection, treat as single-select
        if item not in selected or len(selected) == 1:
            self.sample_tree.setCurrentItem(item)
            item_type = item.data(0, ITEM_ROLE_TYPE)
            if item_type == "sample":
                self._show_sample_context_menu(global_pos, item)
            elif item_type == "gate":
                self._show_gate_context_menu(global_pos, item)
        else:
            self._dispatch_multi_context_menu(global_pos, selected)

    def _dispatch_multi_context_menu(self, global_pos, items: list[QTreeWidgetItem]) -> None:
        types = {it.data(0, ITEM_ROLE_TYPE) for it in items}
        if types == {"sample"}:
            self._show_multi_sample_context_menu(global_pos, items)
        elif types == {"gate"}:
            self._show_multi_gate_context_menu(global_pos, items)

    def _show_sample_context_menu(self, global_pos, item: QTreeWidgetItem) -> None:
        workspace_index = int(item.data(0, ITEM_ROLE_ID))
        item_group_name: str = item.data(0, ITEM_ROLE_GROUP) or ""

        menu = QMenu(self)

        # ── Assign to group ──────────────────────────────────
        assign_menu = menu.addMenu("Assign to group")
        group_actions: list[tuple[str, object]] = []
        for group_name, _ in self._available_groups:
            action = assign_menu.addAction(group_name)
            group_actions.append((group_name, action))
        if group_actions:
            assign_menu.addSeparator()
        custom_group_action = assign_menu.addAction("Other group...")

        # ── Sample actions ────────────────────────────────────
        menu.addSeparator()
        edit_action = menu.addAction("Edit sample...")
        edit_comp_action = menu.addAction("Edit compensation details")
        menu.addSeparator()
        delete_action = menu.addAction("Delete sample")

        # ── Gate propagation ──────────────────────────────────
        menu.addSeparator()
        apply_active_group_action = menu.addAction("Apply active gate to this group")
        apply_all_group_action = menu.addAction("Apply all gates to this group")
        apply_active_all_action = menu.addAction("Apply active gate to all samples")
        apply_all_all_action = menu.addAction("Apply all gates to all samples")

        # ── Group management ──────────────────────────────────
        if item_group_name:
            menu.addSeparator()
            select_group_action = menu.addAction(f"Select all in '{item_group_name}'")
            group_edit_menu = menu.addMenu(f"Edit group '{item_group_name}'")
            rename_group_action = group_edit_menu.addAction("Rename group...")
            recolor_group_action = group_edit_menu.addAction("Change group color...")
            notes_group_action = group_edit_menu.addAction("Edit notes...")
            group_edit_menu.addSeparator()
            delete_group_action = group_edit_menu.addAction("Delete group")
        else:
            select_group_action = None
            rename_group_action = None
            recolor_group_action = None
            notes_group_action = None
            delete_group_action = None

        chosen = menu.exec(global_pos)
        if chosen is None:
            return

        for group_name, action in group_actions:
            if chosen is action:
                self.assign_sample_group_requested.emit(workspace_index, group_name)
                return

        if chosen is custom_group_action:
            self.assign_custom_sample_group_requested.emit(workspace_index)
        elif chosen is edit_action:
            self.edit_sample_requested.emit(workspace_index)
        elif chosen is edit_comp_action:
            self.edit_compensation_sample_requested.emit(workspace_index)
        elif chosen is delete_action:
            self.remove_sample_button.click()
        elif chosen is apply_active_group_action:
            self.apply_active_gate_to_group_requested.emit(workspace_index)
        elif chosen is apply_all_group_action:
            self.apply_all_gates_to_group_requested.emit(workspace_index)
        elif chosen is apply_active_all_action:
            self.apply_active_gate_to_all_requested.emit(workspace_index)
        elif chosen is apply_all_all_action:
            self.apply_all_gates_to_all_requested.emit(workspace_index)
        elif select_group_action is not None and chosen is select_group_action:
            self.select_group_samples_requested.emit(item_group_name)
        elif rename_group_action is not None and chosen is rename_group_action:
            self.rename_group_requested.emit(item_group_name)
        elif recolor_group_action is not None and chosen is recolor_group_action:
            self.recolor_group_requested.emit(item_group_name)
        elif notes_group_action is not None and chosen is notes_group_action:
            self.annotate_group_requested.emit(item_group_name)
        elif delete_group_action is not None and chosen is delete_group_action:
            self.delete_group_requested.emit(item_group_name)

    def _show_gate_context_menu(self, global_pos, item: QTreeWidgetItem) -> None:
        gate_row = int(item.data(0, ITEM_ROLE_ID) or 0)
        if gate_row == 0:
            return
        gate_index = gate_row - 1

        # Get the parent sample's workspace_index for propagation actions
        parent = item.parent()
        parent_ws_index: int | None = None
        if parent is not None and parent.data(0, ITEM_ROLE_TYPE) == "sample":
            parent_ws_index = int(parent.data(0, ITEM_ROLE_ID))

        menu = QMenu(self)
        rename_action = menu.addAction("Rename gate")
        recolor_action = menu.addAction("Change color")
        menu.addSeparator()
        export_action = menu.addAction("Export gate events...")
        menu.addSeparator()
        apply_group_action = menu.addAction("Apply this gate to this group")
        apply_all_action = menu.addAction("Apply this gate to all samples")
        menu.addSeparator()
        delete_action = menu.addAction("Delete gate")

        chosen = menu.exec(global_pos)
        if chosen is None:
            return

        if chosen is rename_action:
            self.rename_gate_context_requested.emit(gate_index)
        elif chosen is recolor_action:
            self.recolor_gate_context_requested.emit(gate_index)
        elif chosen is export_action:
            self.export_gate_context_requested.emit(gate_index)
        elif chosen is delete_action:
            self.delete_gate_context_requested.emit(gate_index)
        elif chosen is apply_group_action and parent_ws_index is not None:
            self.apply_active_gate_to_group_requested.emit(parent_ws_index)
        elif chosen is apply_all_action and parent_ws_index is not None:
            self.apply_active_gate_to_all_requested.emit(parent_ws_index)

    def _show_multi_sample_context_menu(self, global_pos, items: list[QTreeWidgetItem]) -> None:
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        ws_indices = [int(item.data(0, ITEM_ROLE_ID)) for item in items]
        count = len(ws_indices)
        menu = QMenu(self)

        assign_menu = menu.addMenu(f"Assign {count} samples to group")
        group_actions: list[tuple[str, object]] = []
        for group_name, _ in self._available_groups:
            action = assign_menu.addAction(group_name)
            group_actions.append((group_name, action))
        if group_actions:
            assign_menu.addSeparator()
        custom_group_action = assign_menu.addAction("Other group...")

        menu.addSeparator()
        apply_active_action = menu.addAction(f"Apply active gate to {count} selected samples")
        apply_all_action = menu.addAction(f"Apply all gates to {count} selected samples")
        menu.addSeparator()
        delete_action = menu.addAction(f"Delete {count} selected samples")

        chosen = menu.exec(global_pos)
        if chosen is None:
            return

        for group_name, action in group_actions:
            if chosen is action:
                self.assign_samples_group_batch_requested.emit(ws_indices, group_name)
                return

        if chosen is custom_group_action:
            group_name, accepted = QInputDialog.getText(
                self, "Assign group", "Group name:"
            )
            if not accepted:
                return
            normalized = group_name.strip()
            if not normalized:
                QMessageBox.warning(self, "Assign group", "Group name cannot be empty.")
                return
            self.assign_samples_group_batch_requested.emit(ws_indices, normalized)
        elif chosen is apply_active_action:
            self.apply_active_gate_to_selected_requested.emit(ws_indices)
        elif chosen is apply_all_action:
            self.apply_all_gates_to_selected_requested.emit(ws_indices)
        elif chosen is delete_action:
            self.delete_samples_batch_requested.emit(ws_indices)

    def _show_multi_gate_context_menu(self, global_pos, items: list[QTreeWidgetItem]) -> None:
        gate_items = [item for item in items if int(item.data(0, ITEM_ROLE_ID) or 0) > 0]
        if not gate_items:
            return
        gate_indices = [int(item.data(0, ITEM_ROLE_ID)) - 1 for item in gate_items]
        count = len(gate_indices)

        # Propagation only makes sense when all gates belong to the same parent sample
        parent_ws_index: int | None = None
        parent_ids = set()
        for item in gate_items:
            parent = item.parent()
            if parent and parent.data(0, ITEM_ROLE_TYPE) == "sample":
                parent_ids.add(int(parent.data(0, ITEM_ROLE_ID)))
        if len(parent_ids) == 1:
            parent_ws_index = next(iter(parent_ids))

        menu = QMenu(self)
        apply_group_action = None
        apply_all_action = None
        if parent_ws_index is not None:
            apply_group_action = menu.addAction(f"Apply {count} gates to this group")
            apply_all_action = menu.addAction(f"Apply {count} gates to all samples")
            menu.addSeparator()
        delete_action = menu.addAction(f"Delete {count} selected gates")

        chosen = menu.exec(global_pos)
        if chosen is None:
            return

        if apply_group_action is not None and chosen is apply_group_action:
            self.apply_gates_to_group_batch_requested.emit(parent_ws_index, gate_indices)
        elif apply_all_action is not None and chosen is apply_all_action:
            self.apply_gates_to_all_batch_requested.emit(parent_ws_index, gate_indices)
        elif chosen is delete_action:
            self.delete_gates_batch_requested.emit(gate_indices)


class InspectorPanel(QWidget):
    """Right panel: metadata and plot controls."""

    axes_changed = Signal(int, int)
    plot_mode_changed = Signal(str)
    sampling_changed = Signal(bool, int)
    view_settings_changed = Signal()
    auto_range_requested = Signal()
    calculate_statistics_requested = Signal()
    export_statistics_requested = Signal()
    batch_export_statistics_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self.file_label = QLabel("—")
        self.events_label = QLabel("—")
        self.channels_label = QLabel("—")
        self.active_gate_label = QLabel("—")
        self.displayed_points_label = QLabel("—")
        self._sample_header_label = QLabel("Current sample")
        self._sample_header_label.setObjectName("inspectorSectionLabel")
        self._file_caption_label = QLabel("File")
        self._file_caption_label.setObjectName("inspectorCaption")
        self._events_caption_label = QLabel("Events")
        self._events_caption_label.setObjectName("inspectorCaption")
        self._channels_caption_label = QLabel("Channels")
        self._channels_caption_label.setObjectName("inspectorCaption")
        self._displayed_caption_label = QLabel("Displayed")
        self._displayed_caption_label.setObjectName("inspectorCaption")
        self._active_caption_label = QLabel("Active population")
        self._active_caption_label.setObjectName("inspectorCaption")

        for label in (
            self.file_label,
            self.events_label,
            self.channels_label,
            self.active_gate_label,
            self.displayed_points_label,
        ):
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.file_label.setObjectName("inspectorFileValue")
        self.file_label.setWordWrap(True)
        self.events_label.setObjectName("inspectorMetricValue")
        self.channels_label.setObjectName("inspectorMetricValue")
        self.displayed_points_label.setObjectName("inspectorMetricValue")
        self.active_gate_label.setObjectName("inspectorActiveValue")

        info_box = QGroupBox("Session")
        info_layout = QVBoxLayout()
        info_layout.setSpacing(10)
        info_layout.addWidget(self._sample_header_label)
        info_layout.addWidget(self._file_caption_label)
        info_layout.addWidget(self.file_label)

        metrics_grid = QGridLayout()
        metrics_grid.setContentsMargins(0, 0, 0, 0)
        metrics_grid.setHorizontalSpacing(8)
        metrics_grid.setVerticalSpacing(6)
        metrics_grid.addWidget(self._events_caption_label, 0, 0)
        metrics_grid.addWidget(self._channels_caption_label, 0, 1)
        metrics_grid.addWidget(self._displayed_caption_label, 0, 2)
        metrics_grid.addWidget(self.events_label, 1, 0)
        metrics_grid.addWidget(self.channels_label, 1, 1)
        metrics_grid.addWidget(self.displayed_points_label, 1, 2)
        info_layout.addLayout(metrics_grid)
        info_layout.addWidget(self._active_caption_label)
        info_layout.addWidget(self.active_gate_label)
        info_box.setLayout(info_layout)

        self.plot_mode_combo = QComboBox()
        self.plot_mode_combo.addItem("Scatter (2D)", "scatter")
        self.plot_mode_combo.addItem("Histogram (1D)", "histogram")

        self.x_axis_combo = QComboBox()
        self.y_axis_combo = QComboBox()
        self.x_axis_combo.setEnabled(False)
        self.y_axis_combo.setEnabled(False)

        self.x_scale_combo = QComboBox()
        self.x_scale_combo.addItem("Linear", "linear")
        self.x_scale_combo.addItem("Log10", "log10")
        self.x_scale_combo.addItem("Asinh", "asinh")

        self.y_scale_combo = QComboBox()
        self.y_scale_combo.addItem("Linear", "linear")
        self.y_scale_combo.addItem("Log10", "log10")
        self.y_scale_combo.addItem("Asinh", "asinh")

        self.limit_points_checkbox = QCheckBox("Limit displayed points")
        self.limit_points_checkbox.setChecked(True)
        self.show_subpopulations_checkbox = QCheckBox("Show direct subpopulations")
        self.show_subpopulations_checkbox.setChecked(False)

        self.max_points_spin = QSpinBox()
        self.max_points_spin.setRange(1000, 200000)
        self.max_points_spin.setSingleStep(1000)
        self.max_points_spin.setValue(30000)

        validator = QDoubleValidator(self)

        self.x_min_edit = QLineEdit()
        self.x_max_edit = QLineEdit()
        self.y_min_edit = QLineEdit()
        self.y_max_edit = QLineEdit()

        for edit in (self.x_min_edit, self.x_max_edit, self.y_min_edit, self.y_max_edit):
            edit.setValidator(validator)
            edit.setPlaceholderText("auto")

        self.apply_view_button = QPushButton("Apply view")
        self.apply_view_button.setProperty("variant", "subtle")
        self.auto_range_button = QPushButton("Reset zoom")
        self.auto_range_button.setProperty("variant", "subtle")

        for button in (
            self.apply_view_button,
            self.auto_range_button,
        ):
            button.setMinimumHeight(34)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        visualization_box = QGroupBox("Visualization")
        visualization_form = QFormLayout()
        visualization_form.setHorizontalSpacing(10)
        visualization_form.setVerticalSpacing(8)
        visualization_form.addRow("Plot mode:", self.plot_mode_combo)
        visualization_form.addRow("X axis:", self.x_axis_combo)
        visualization_form.addRow("Y axis:", self.y_axis_combo)
        visualization_form.addRow("", self.show_subpopulations_checkbox)
        visualization_box.setLayout(visualization_form)

        plot_adjustments_box = QGroupBox("Scales & Range")
        plot_adjustments_form = QFormLayout()
        plot_adjustments_form.setHorizontalSpacing(10)
        plot_adjustments_form.setVerticalSpacing(8)
        plot_adjustments_form.addRow("X scale:", self.x_scale_combo)
        plot_adjustments_form.addRow("Y scale:", self.y_scale_combo)
        plot_adjustments_box.setLayout(plot_adjustments_form)

        range_box = QGroupBox("Visible Range")
        range_layout = QFormLayout()
        range_layout.setContentsMargins(0, 0, 0, 0)
        range_layout.setHorizontalSpacing(10)
        range_layout.setVerticalSpacing(8)
        range_layout.addRow("X min:", self.x_min_edit)
        range_layout.addRow("X max:", self.x_max_edit)
        range_layout.addRow("Y min:", self.y_min_edit)
        range_layout.addRow("Y max:", self.y_max_edit)
        range_box.setLayout(range_layout)

        quick_actions_box = QGroupBox("Quick Actions")
        quick_actions_layout = QVBoxLayout()
        quick_actions_layout.setSpacing(8)
        quick_actions_layout.addWidget(self.apply_view_button)
        quick_actions_layout.addWidget(self.auto_range_button)
        quick_actions_layout.addWidget(self.limit_points_checkbox)
        sampling_row = QFormLayout()
        sampling_row.setContentsMargins(0, 0, 0, 0)
        sampling_row.setHorizontalSpacing(10)
        sampling_row.addRow("Max points:", self.max_points_spin)
        quick_actions_layout.addLayout(sampling_row)
        quick_actions_layout.addStretch(1)
        quick_actions_box.setLayout(quick_actions_layout)

        view_controls_box = QWidget()
        view_layout = QVBoxLayout()
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setSpacing(10)
        view_layout.addWidget(visualization_box)
        view_layout.addWidget(plot_adjustments_box)
        view_layout.addWidget(range_box)
        view_layout.addWidget(quick_actions_box)
        view_layout.addStretch(1)
        view_controls_box.setLayout(view_layout)

        view_scroll_area = QScrollArea()
        view_scroll_area.setWidgetResizable(True)
        view_scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        view_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view_scroll_area.setWidget(view_controls_box)

        self.statistics_population_combo = QComboBox()
        self.statistics_population_combo.setEnabled(False)
        self.statistics_channel_combo = QComboBox()
        self.statistics_channel_combo.setEnabled(False)
        self.statistics_metric_list = QListWidget()
        self.statistics_metric_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.statistics_metric_list.setMinimumHeight(120)

        for stat_key, stat_label in STATISTIC_DEFINITIONS:
            item = QListWidgetItem(stat_label)
            item.setData(Qt.UserRole, stat_key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if stat_key in {"event_count", "percent_parent", "mean", "median"} else Qt.Unchecked)
            self.statistics_metric_list.addItem(item)

        self.calculate_statistics_button = QPushButton("Calculate statistics")
        self.calculate_statistics_button.setProperty("variant", "primary")
        self.export_statistics_button = QPushButton("Export statistics")
        self.export_statistics_button.setProperty("variant", "subtle")
        self.export_statistics_button.setEnabled(False)
        self.batch_export_statistics_button = QPushButton("Batch export...")
        self.batch_export_statistics_button.setProperty("variant", "subtle")
        self.batch_export_statistics_button.setToolTip(
            "Export statistics for multiple groups, populations, and channels at once"
        )

        self.statistics_table = QTableWidget(0, 2)
        self.statistics_table.setHorizontalHeaderLabels(["Statistic", "Value"])
        self.statistics_table.verticalHeader().setVisible(False)
        self.statistics_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.statistics_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.statistics_table.setAlternatingRowColors(True)
        self.statistics_table.setMinimumHeight(100)
        self.statistics_table.horizontalHeader().setStretchLastSection(True)

        self.controls_tabs = QTabWidget()
        self.controls_tabs.addTab(view_scroll_area, "View")

        statistics_box = QWidget()
        statistics_layout = QVBoxLayout()
        statistics_layout.setContentsMargins(0, 0, 0, 0)
        statistics_layout.setSpacing(10)

        statistics_selection_box = QGroupBox("Statistics selection")
        statistics_selection_form = QFormLayout()
        statistics_selection_form.setVerticalSpacing(10)
        statistics_selection_form.addRow("Population:", self.statistics_population_combo)
        statistics_selection_form.addRow("Channel:", self.statistics_channel_combo)
        statistics_selection_box.setLayout(statistics_selection_form)

        statistics_metrics_box = QGroupBox("Statistics")
        statistics_metrics_layout = QVBoxLayout()
        statistics_metrics_layout.setSpacing(10)
        statistics_metrics_layout.addWidget(self.statistics_metric_list)
        statistics_metrics_layout.addWidget(self.calculate_statistics_button)
        statistics_metrics_layout.addWidget(self.export_statistics_button)
        statistics_metrics_layout.addWidget(self.batch_export_statistics_button)
        statistics_metrics_box.setLayout(statistics_metrics_layout)

        statistics_results_box = QGroupBox("Results")
        statistics_results_layout = QVBoxLayout()
        statistics_results_layout.addWidget(self.statistics_table)
        statistics_results_box.setLayout(statistics_results_layout)

        statistics_layout.addWidget(statistics_selection_box)
        statistics_layout.addWidget(statistics_metrics_box)
        statistics_layout.addWidget(statistics_results_box)
        statistics_layout.addStretch(1)
        statistics_box.setLayout(statistics_layout)

        statistics_scroll_area = QScrollArea()
        statistics_scroll_area.setWidgetResizable(True)
        statistics_scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        statistics_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        statistics_scroll_area.setWidget(statistics_box)

        self.controls_tabs.addTab(statistics_scroll_area, "Statistics")


        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(info_box)
        layout.addWidget(self.controls_tabs, stretch=1)
        self.setLayout(layout)

        self.plot_mode_combo.currentIndexChanged.connect(self._emit_plot_mode_changed)
        self.x_axis_combo.currentIndexChanged.connect(self._emit_axes_changed)
        self.y_axis_combo.currentIndexChanged.connect(self._emit_axes_changed)
        self.x_scale_combo.currentIndexChanged.connect(self._emit_view_settings_changed)
        self.y_scale_combo.currentIndexChanged.connect(self._emit_view_settings_changed)
        self.limit_points_checkbox.toggled.connect(self._emit_sampling_changed)
        self.max_points_spin.valueChanged.connect(self._emit_sampling_changed)
        self.show_subpopulations_checkbox.toggled.connect(self._emit_view_settings_changed)

        self.x_min_edit.editingFinished.connect(self._emit_view_settings_changed)
        self.x_max_edit.editingFinished.connect(self._emit_view_settings_changed)
        self.y_min_edit.editingFinished.connect(self._emit_view_settings_changed)
        self.y_max_edit.editingFinished.connect(self._emit_view_settings_changed)

        self.apply_view_button.clicked.connect(self._emit_view_settings_changed)
        self.auto_range_button.clicked.connect(self._emit_auto_range_requested)

        self.calculate_statistics_button.clicked.connect(self.calculate_statistics_requested.emit)
        self.export_statistics_button.clicked.connect(self.export_statistics_requested.emit)
        self.batch_export_statistics_button.clicked.connect(self.batch_export_statistics_requested.emit)
        self.set_plot_mode("scatter")
        self.clear_statistics()

    def set_file_info(
        self,
        *,
        file_name: str = "—",
        events: str = "—",
        channels: str = "—",
        active_gate: str = "—",
    ) -> None:
        self.file_label.setText(file_name)
        self.events_label.setText(events)
        self.channels_label.setText(channels)
        self.active_gate_label.setText(active_gate)

    def set_active_gate(self, gate_name: str) -> None:
        self.active_gate_label.setText(gate_name)

    def set_channels(
        self,
        channel_names: list[str],
        *,
        x_index: int | None = None,
        y_index: int | None = None,
    ) -> None:
        with QSignalBlocker(self.x_axis_combo), QSignalBlocker(self.y_axis_combo):
            self.x_axis_combo.clear()
            self.y_axis_combo.clear()

            self.x_axis_combo.addItems(channel_names)
            self.y_axis_combo.addItems(channel_names)

            has_channels = len(channel_names) >= 1
            self.x_axis_combo.setEnabled(has_channels)
            self.y_axis_combo.setEnabled(len(channel_names) >= 2)

            if not has_channels:
                return

            if x_index is None:
                x_index = 0
            if y_index is None:
                y_index = 1 if len(channel_names) > 1 else 0

            self.x_axis_combo.setCurrentIndex(x_index)
            self.y_axis_combo.setCurrentIndex(y_index)

    def clear_channels(self) -> None:
        with QSignalBlocker(self.x_axis_combo), QSignalBlocker(self.y_axis_combo):
            self.x_axis_combo.clear()
            self.y_axis_combo.clear()
            self.x_axis_combo.setEnabled(False)
            self.y_axis_combo.setEnabled(False)
        with QSignalBlocker(self.statistics_channel_combo):
            self.statistics_channel_combo.clear()
            self.statistics_channel_combo.setEnabled(False)

    def set_statistics_populations(
        self,
        population_options: list[tuple[str, int | None]],
        *,
        selected_gate_index: int | None = None,
    ) -> None:
        with QSignalBlocker(self.statistics_population_combo):
            self.statistics_population_combo.clear()
            for label, gate_index in population_options:
                self.statistics_population_combo.addItem(label, gate_index)

            has_options = len(population_options) > 0
            self.statistics_population_combo.setEnabled(has_options)
            if not has_options:
                return

            selected_index = 0
            for combo_index in range(self.statistics_population_combo.count()):
                if self.statistics_population_combo.itemData(combo_index) == selected_gate_index:
                    selected_index = combo_index
                    break
            self.statistics_population_combo.setCurrentIndex(selected_index)

    def set_statistics_channels(
        self,
        channel_names: list[str],
        *,
        selected_channel_index: int | None = None,
    ) -> None:
        with QSignalBlocker(self.statistics_channel_combo):
            self.statistics_channel_combo.clear()
            self.statistics_channel_combo.addItems(channel_names)
            has_channels = len(channel_names) > 0
            self.statistics_channel_combo.setEnabled(has_channels)
            if not has_channels:
                return

            resolved_index = 0 if selected_channel_index is None else selected_channel_index
            self.statistics_channel_combo.setCurrentIndex(max(0, min(resolved_index, len(channel_names) - 1)))

    def current_statistics_population_index(self) -> int | None:
        data = self.statistics_population_combo.currentData()
        return int(data) if data is not None else None

    def current_statistics_channel_index(self) -> int:
        return self.statistics_channel_combo.currentIndex()

    def selected_statistics(self) -> list[str]:
        selected: list[str] = []
        for row in range(self.statistics_metric_list.count()):
            item = self.statistics_metric_list.item(row)
            if item.checkState() == Qt.Checked:
                selected.append(str(item.data(Qt.UserRole)))
        return selected

    def set_statistics_results(self, rows: list[tuple[str, str]]) -> None:
        self.statistics_table.setRowCount(len(rows))
        for row_index, (label, value) in enumerate(rows):
            self.statistics_table.setItem(row_index, 0, QTableWidgetItem(label))
            self.statistics_table.setItem(row_index, 1, QTableWidgetItem(value))
        self.export_statistics_button.setEnabled(len(rows) > 0)

    def clear_statistics(self) -> None:
        with QSignalBlocker(self.statistics_population_combo), QSignalBlocker(self.statistics_channel_combo):
            self.statistics_population_combo.clear()
            self.statistics_channel_combo.clear()
        self.statistics_population_combo.setEnabled(False)
        self.statistics_channel_combo.setEnabled(False)
        self.statistics_table.setRowCount(0)
        self.export_statistics_button.setEnabled(False)


    def current_axes(self) -> tuple[int, int]:
        return self.x_axis_combo.currentIndex(), self.y_axis_combo.currentIndex()

    def current_plot_mode(self) -> str:
        return self._plot_mode

    def set_plot_mode(self, mode: str) -> None:
        combo_index = self.plot_mode_combo.findData(mode)
        if combo_index >= 0 and self.plot_mode_combo.currentIndex() != combo_index:
            with QSignalBlocker(self.plot_mode_combo):
                self.plot_mode_combo.setCurrentIndex(combo_index)
        self._plot_mode = mode
        if mode == "histogram":
            self.y_axis_combo.setEnabled(False)
            self.y_scale_combo.setEnabled(False)
        else:
            self.y_axis_combo.setEnabled(self.y_axis_combo.count() >= 2)
            self.y_scale_combo.setEnabled(True)
    def current_scales(self) -> tuple[str, str]:
        x_mode = str(self.x_scale_combo.currentData())
        y_mode = str(self.y_scale_combo.currentData())
        return x_mode, y_mode

    def current_view_limits(self) -> tuple[float | None, float | None, float | None, float | None]:
        return (
            self._parse_optional_float(self.x_min_edit.text()),
            self._parse_optional_float(self.x_max_edit.text()),
            self._parse_optional_float(self.y_min_edit.text()),
            self._parse_optional_float(self.y_max_edit.text()),
        )

    def clear_view_limits(self) -> None:
        self.x_min_edit.clear()
        self.x_max_edit.clear()
        self.y_min_edit.clear()
        self.y_max_edit.clear()

    def sampling_settings(self) -> tuple[bool, int]:
        return self.limit_points_checkbox.isChecked(), self.max_points_spin.value()

    def show_subpopulations_enabled(self) -> bool:
        return self.show_subpopulations_checkbox.isChecked()

    def set_displayed_points(self, displayed: int | None, total: int | None) -> None:
        if displayed is None or total is None:
            self.displayed_points_label.setText("—")
            return
        self.displayed_points_label.setText(f"{displayed:,} / {total:,}")

    def _emit_axes_changed(self) -> None:
        x_index = self.x_axis_combo.currentIndex()
        y_index = self.y_axis_combo.currentIndex()

        if x_index < 0:
            return

        if self.current_plot_mode() == "histogram":
            self.axes_changed.emit(x_index, y_index)
            return

        if y_index < 0:
            return

        self.axes_changed.emit(x_index, y_index)

    def _emit_plot_mode_changed(self) -> None:
        mode = str(self.plot_mode_combo.currentData())
        self.set_plot_mode(mode)
        self.plot_mode_changed.emit(mode)

    def _emit_sampling_changed(self) -> None:
        self.sampling_changed.emit(
            self.limit_points_checkbox.isChecked(),
            self.max_points_spin.value(),
        )

    def _emit_view_settings_changed(self, *args: object) -> None:
        del args
        self.view_settings_changed.emit()

    def _emit_auto_range_requested(self, *args: object) -> None:
        del args
        self.auto_range_requested.emit()

    @staticmethod
    def _parse_optional_float(text: str) -> float | None:
        stripped = text.strip()
        if not stripped:
            return None
        return float(stripped)
