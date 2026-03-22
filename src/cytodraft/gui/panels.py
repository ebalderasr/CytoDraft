from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SamplePanel(QWidget):
    """Left panel: loaded samples and gate tree placeholder."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.sample_list = QListWidget()
        self.sample_list.setAlternatingRowColors(True)

        self.gate_list = QListWidget()
        self.gate_list.setAlternatingRowColors(True)

        self.add_sample_button = QPushButton("Load sample")
        self.remove_sample_button = QPushButton("Remove selected")
        self.remove_sample_button.setEnabled(False)

        sample_box = QGroupBox("Samples")
        sample_layout = QVBoxLayout()
        sample_layout.addWidget(self.sample_list)
        sample_layout.addWidget(self.add_sample_button)
        sample_layout.addWidget(self.remove_sample_button)
        sample_box.setLayout(sample_layout)

        gate_box = QGroupBox("Gates")
        gate_layout = QVBoxLayout()
        gate_layout.addWidget(self.gate_list)
        gate_box.setLayout(gate_layout)

        layout = QVBoxLayout()
        layout.addWidget(sample_box, stretch=3)
        layout.addWidget(gate_box, stretch=2)
        self.setLayout(layout)

        self.sample_list.currentRowChanged.connect(self._on_sample_selection_changed)

    def add_sample(self, name: str) -> None:
        self.sample_list.addItem(name)

    def _on_sample_selection_changed(self, row: int) -> None:
        self.remove_sample_button.setEnabled(row >= 0)


class InspectorPanel(QWidget):
    """Right panel: basic metadata / future controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.file_label = QLabel("—")
        self.events_label = QLabel("—")
        self.channels_label = QLabel("—")
        self.active_gate_label = QLabel("—")

        for label in (
            self.file_label,
            self.events_label,
            self.channels_label,
            self.active_gate_label,
        ):
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        info_box = QGroupBox("Inspector")
        form = QFormLayout()
        form.addRow("File:", self.file_label)
        form.addRow("Events:", self.events_label)
        form.addRow("Channels:", self.channels_label)
        form.addRow("Active gate:", self.active_gate_label)
        info_box.setLayout(form)

        placeholder_box = QGroupBox("Plot controls")
        placeholder_layout = QVBoxLayout()
        placeholder_layout.addWidget(QLabel("Axis selectors, transforms, and gate tools will appear here."))
        placeholder_box.setLayout(placeholder_layout)

        layout = QVBoxLayout()
        layout.addWidget(info_box)
        layout.addWidget(placeholder_box)
        layout.addStretch(1)
        self.setLayout(layout)

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
