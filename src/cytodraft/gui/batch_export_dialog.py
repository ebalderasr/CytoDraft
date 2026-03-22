from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from cytodraft.core.statistics import STATISTIC_DEFINITIONS
from cytodraft.models.workspace import COMPENSATION_GROUP_NAME, WorkspaceState

_DEFAULT_CHECKED_METRICS = {"event_count", "percent_parent", "mean", "median"}


class _CheckList(QGroupBox):
    """A labeled group box with a checkable list and select/deselect-all buttons."""

    def __init__(
        self,
        title: str,
        items: list[str],
        checked: set[str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(title, parent)
        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        for label in items:
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            state = Qt.Checked if (checked is None or label in checked) else Qt.Unchecked
            item.setCheckState(state)
            self._list.addItem(item)

        select_btn = QPushButton("Select all")
        select_btn.setProperty("variant", "subtle")
        select_btn.clicked.connect(lambda: self._set_all(Qt.Checked))

        deselect_btn = QPushButton("Deselect all")
        deselect_btn.setProperty("variant", "subtle")
        deselect_btn.clicked.connect(lambda: self._set_all(Qt.Unchecked))

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.addWidget(select_btn)
        btn_row.addWidget(deselect_btn)
        btn_row.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(btn_row)
        layout.addWidget(self._list)
        self.setLayout(layout)

    def _set_all(self, state: Qt.CheckState) -> None:
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(state)

    def checked_items(self) -> list[str]:
        result = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.Checked:
                result.append(item.text())
        return result


class BatchExportDialog(QDialog):
    """Select groups, populations, channels, and metrics for a batch statistics export."""

    def __init__(self, workspace: WorkspaceState, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Statistics — Batch")
        self.resize(720, 560)

        # ── Collect available data from workspace ──────────────────────
        group_names = sorted(
            name for name in workspace.groups if name != COMPENSATION_GROUP_NAME
        )

        gate_names_ordered: list[str] = []
        seen_gates: set[str] = set()
        channel_names_ordered: list[str] = []
        seen_channels: set[str] = set()

        for _, ws in workspace.samples_in_group(None):
            if ws.group_name == COMPENSATION_GROUP_NAME:
                continue
            for gate in ws.gates:
                if gate.name not in seen_gates:
                    gate_names_ordered.append(gate.name)
                    seen_gates.add(gate.name)
            for ch in ws.sample.channels:
                name = ch.display_name
                if name not in seen_channels:
                    channel_names_ordered.append(name)
                    seen_channels.add(name)

        population_items = ["All events"] + gate_names_ordered
        metric_labels = [label for _, label in STATISTIC_DEFINITIONS]
        default_metric_labels = {
            label for key, label in STATISTIC_DEFINITIONS if key in _DEFAULT_CHECKED_METRICS
        }
        self._metric_label_to_key = {label: key for key, label in STATISTIC_DEFINITIONS}

        # ── Build 4-panel layout ───────────────────────────────────────
        self._groups_panel = _CheckList("Groups", group_names)
        self._populations_panel = _CheckList("Populations", population_items)
        self._channels_panel = _CheckList("Channels", channel_names_ordered)
        self._metrics_panel = _CheckList("Metrics", metric_labels, checked=default_metric_labels)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.addWidget(self._groups_panel)
        top_row.addWidget(self._populations_panel)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        bottom_row.addWidget(self._channels_panel)
        bottom_row.addWidget(self._metrics_panel)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._export_btn = button_box.addButton(
            "Export CSV...", QDialogButtonBox.ButtonRole.AcceptRole
        )
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addLayout(top_row, stretch=1)
        layout.addLayout(bottom_row, stretch=1)
        layout.addWidget(button_box)
        self.setLayout(layout)

    # ── Public API ─────────────────────────────────────────────────────

    def selected_groups(self) -> list[str]:
        return self._groups_panel.checked_items()

    def selected_populations(self) -> list[str]:
        return self._populations_panel.checked_items()

    def selected_channels(self) -> list[str]:
        return self._channels_panel.checked_items()

    def selected_metric_keys(self) -> list[str]:
        return [
            self._metric_label_to_key[label]
            for label in self._metrics_panel.checked_items()
            if label in self._metric_label_to_key
        ]
