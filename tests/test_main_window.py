from pathlib import Path

import numpy as np
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea, QSplitter

from cytodraft.gui.main_window import MainWindow
from cytodraft.models.gate import RangeGate
from cytodraft.models.sample import ChannelInfo, SampleData


def get_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def make_sample(name: str, event_count: int = 4) -> SampleData:
    channels = [
        ChannelInfo(index=0, number=1, pnn="FSC-A", pns="", pnr=1024.0),
        ChannelInfo(index=1, number=2, pnn="SSC-A", pns="", pnr=1024.0),
    ]
    events = np.arange(event_count * 2, dtype=float).reshape(event_count, 2)
    return SampleData(
        file_path=Path(name),
        version="3.1",
        event_count=event_count,
        channels=channels,
        events=events,
        metadata={},
        scatter_indices=[0, 1],
        fluoro_indices=[],
        time_index=None,
    )


def test_load_sample_replaces_previous_entry_in_sample_list() -> None:
    get_app()
    window = MainWindow()

    samples = [
        make_sample("first.fcs"),
        make_sample("second.fcs"),
    ]

    def fake_load_sample(_: str) -> SampleData:
        return samples.pop(0)

    window.sample_service.load_sample = fake_load_sample

    window.load_sample("first.fcs")
    window.load_sample("second.fcs")

    assert window.current_sample is not None
    assert window.current_sample.file_name == "second.fcs"
    assert window.sample_panel.sample_list.count() == 1
    assert window.sample_panel.sample_list.item(0).text() == "second.fcs"


def test_remove_selected_sample_clears_loaded_state() -> None:
    get_app()
    window = MainWindow()
    sample = make_sample("demo.fcs")

    window.current_sample = sample
    window.gates = [
        RangeGate(
            name="Gate 1",
            parent_name="All events",
            channel_index=0,
            channel_label="FSC-A",
            x_min=0.0,
            x_max=1.0,
            event_count=2,
            percentage_parent=50.0,
            percentage_total=50.0,
            full_mask=np.array([True, False, True, False]),
        )
    ]
    window.active_gate = window.gates[0]
    window.sample_panel.add_sample(sample.file_name)
    window.sample_panel.add_gate(window.gates[0].label)

    window.remove_selected_sample()

    assert window.current_sample is None
    assert window.gates == []
    assert window.active_gate is None
    assert window.sample_panel.sample_list.count() == 0
    assert window.sample_panel.gate_list.count() == 1
    assert window.sample_panel.gate_list.item(0).text() == "All events"
    assert window.inspector_panel.file_label.text() == "—"


def test_rename_active_gate_updates_model_and_list() -> None:
    get_app()
    window = MainWindow()
    gate = RangeGate(
        name="Gate 1",
        parent_name="All events",
        channel_index=0,
        channel_label="FSC-A",
        x_min=0.0,
        x_max=1.0,
        event_count=2,
        percentage_parent=50.0,
        percentage_total=50.0,
        full_mask=np.array([True, False, True, False]),
    )

    window.gates = [gate]
    window.active_gate = gate
    window.sample_panel.reset_gates()
    window.sample_panel.add_gate(gate.label)
    window.on_gate_selection_changed(1)

    window.on_rename_active_gate("Lymphocytes")

    assert gate.name == "Lymphocytes"
    assert window.sample_panel.gate_list.item(1).text().startswith("Lymphocytes |")
    assert window.inspector_panel.active_gate_label.text() == "Lymphocytes"
    assert window.inspector_panel.gate_name_edit.text() == "Lymphocytes"


def test_recolor_active_gate_updates_model_and_list(monkeypatch) -> None:
    get_app()
    window = MainWindow()
    gate = RangeGate(
        name="Gate 1",
        parent_name="All events",
        channel_index=0,
        channel_label="FSC-A",
        x_min=0.0,
        x_max=1.0,
        event_count=2,
        percentage_parent=50.0,
        percentage_total=50.0,
        full_mask=np.array([True, False, True, False]),
    )

    window.gates = [gate]
    window.active_gate = gate
    window.sample_panel.reset_gates()
    window.sample_panel.add_gate(gate.label)
    window.on_gate_selection_changed(1)

    monkeypatch.setattr(
        "cytodraft.gui.main_window.QColorDialog.getColor",
        lambda *args, **kwargs: QColor("#0088cc"),
    )

    window.on_recolor_active_gate()

    assert gate.color_hex == "#0088cc"
    assert window.sample_panel.gate_list.item(1).foreground().color().name() == "#0088cc"
    assert "#0088cc" in window.inspector_panel.gate_color_button.styleSheet()


def test_prompt_for_gate_details_returns_name_and_color(monkeypatch) -> None:
    get_app()
    window = MainWindow()

    monkeypatch.setattr(
        "cytodraft.gui.main_window.QInputDialog.getText",
        lambda *args, **kwargs: ("My Gate", True),
    )
    monkeypatch.setattr(
        "cytodraft.gui.main_window.QColorDialog.getColor",
        lambda *args, **kwargs: QColor("#44aa55"),
    )

    details = window.prompt_for_gate_details(
        initial_name="Gate 1",
        initial_color="#d43c3c",
        title="Apply gate",
    )

    assert details == ("My Gate", "#44aa55")


def test_delete_gate_from_context_removes_gate(monkeypatch) -> None:
    get_app()
    window = MainWindow()
    sample = make_sample("demo.fcs")
    gate = RangeGate(
        name="Gate 1",
        parent_name="All events",
        channel_index=0,
        channel_label="FSC-A",
        x_min=0.0,
        x_max=1.0,
        event_count=2,
        percentage_parent=50.0,
        percentage_total=50.0,
        full_mask=np.array([True, False, True, False]),
    )

    window.current_sample = sample
    window.gates = [gate]
    window.active_gate = gate
    window.sample_panel.reset_gates()
    window.sample_panel.add_gate(gate.label)
    window.on_gate_selection_changed(1)

    monkeypatch.setattr(
        "cytodraft.gui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    window.on_delete_gate_from_context(0)

    assert window.gates == []
    assert window.active_gate is None
    assert window.sample_panel.gate_list.count() == 1
    assert window.sample_panel.gate_list.item(0).text() == "All events"


def test_current_population_color_uses_active_gate_color() -> None:
    get_app()
    window = MainWindow()
    gate = RangeGate(
        name="Gate 1",
        parent_name="All events",
        channel_index=0,
        channel_label="FSC-A",
        x_min=0.0,
        x_max=1.0,
        event_count=2,
        percentage_parent=50.0,
        percentage_total=50.0,
        full_mask=np.array([True, False, True, False]),
        color_hex="#aa33cc",
    )

    window.active_gate = gate

    assert window.current_population_color() == "#aa33cc"


def test_main_window_uses_scrollable_side_panels() -> None:
    get_app()
    window = MainWindow()

    splitter = window.centralWidget()

    assert isinstance(splitter, QSplitter)
    assert isinstance(splitter.widget(0), QScrollArea)
    assert isinstance(splitter.widget(2), QScrollArea)
    assert window.sample_panel.minimumWidth() == 0
    assert window.inspector_panel.minimumWidth() == 0
