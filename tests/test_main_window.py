from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QScrollArea, QSplitter, QTabWidget

from cytodraft.gui.main_window import MainWindow
from cytodraft.core.statistics import StatisticResult
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


def test_load_sample_appends_multiple_entries_to_sample_list() -> None:
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
    assert window.sample_panel.group_list.count() == 3
    assert window.sample_panel.group_list.item(1).text() == "Compensation"
    assert window.sample_panel.group_list.item(2).text() == "Ungrouped"
    assert window.sample_panel.sample_list.count() == 2
    assert window.sample_panel.sample_list.item(0).text() == "first.fcs"
    assert window.sample_panel.sample_list.item(1).text() == "second.fcs"


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
    window.workspace.add_sample(sample)
    window._refresh_group_list()
    window.sample_panel.add_sample("demo.fcs", 0)
    window.sample_panel.add_gate(window.gates[0].label)

    window.remove_selected_sample()

    assert window.current_sample is None
    assert window.gates == []
    assert window.active_gate is None
    assert window.sample_panel.sample_list.count() == 0
    assert window.sample_panel.gate_list.count() == 1
    assert window.sample_panel.gate_list.item(0).text() == "All events"
    assert window.inspector_panel.file_label.text() == "—"


def test_assign_sample_group_updates_workspace_and_list() -> None:
    get_app()
    window = MainWindow()
    sample = make_sample("demo.fcs")

    window.workspace.add_sample(sample)
    window._sync_from_workspace()
    window._refresh_sample_list(select_active=True)

    window.on_assign_sample_group(0, "Controls")

    assert window.workspace.samples[0].group_name == "Controls"
    assert any(
        window.sample_panel.group_list.item(row).text() == "Controls"
        for row in range(window.sample_panel.group_list.count())
    )
    assert window.sample_panel.sample_list.item(0).text() == "demo.fcs"


def test_load_sample_can_target_compensation_group() -> None:
    get_app()
    window = MainWindow()
    sample = make_sample("comp.fcs")
    window.sample_service.load_sample = lambda _: sample

    window.load_sample("comp.fcs", group_name="Compensation")

    assert window.workspace.samples[0].group_name == "Compensation"
    assert window.selected_group_name == "Compensation"
    assert "Compensation" in window.workspace.groups


def test_assign_sample_group_accepts_compensation() -> None:
    get_app()
    window = MainWindow()
    sample = make_sample("demo.fcs")

    window.workspace.add_sample(sample)
    window._sync_from_workspace()
    window._refresh_group_list()
    window._refresh_sample_list(select_active=True)

    window.on_assign_sample_group(0, "Compensation")

    assert window.workspace.samples[0].group_name == "Compensation"


def test_group_selection_filters_visible_samples() -> None:
    get_app()
    window = MainWindow()
    window.workspace.add_sample(make_sample("a.fcs"), group_name="Controls")
    window.workspace.add_sample(make_sample("b.fcs"), group_name="Specimen 1")
    window._refresh_group_list()
    window._refresh_sample_list(select_active=True)

    window.on_group_selection_changed("Controls")

    assert window.sample_panel.sample_list.count() == 1
    assert window.sample_panel.sample_list.item(0).text() == "a.fcs"


def test_group_annotations_update_details_panel() -> None:
    get_app()
    window = MainWindow()
    group = window.workspace.ensure_group("Controls")
    group.notes = "Tube A, unstained baseline"
    window._refresh_group_list()

    window.on_group_selection_changed("Controls")

    assert window.sample_panel.group_notes_label.text() == "Notes: Tube A, unstained baseline"


def test_workspace_starts_with_default_compensation_group() -> None:
    get_app()
    window = MainWindow()

    assert any(
        window.sample_panel.group_list.item(row).text() == "Compensation"
        for row in range(window.sample_panel.group_list.count())
    ) or "Compensation" in window.workspace.groups
    assert window.workspace.groups["Compensation"].notes == "Reserved for single-stain compensation controls."


def test_compensation_sample_display_name_includes_metadata_summary() -> None:
    get_app()
    window = MainWindow()
    sample_state = window.workspace.add_sample(make_sample("fitc.fcs"), group_name="Compensation")
    sample_state.compensation.control_type = "single_stain"
    sample_state.compensation.fluorochrome = "FITC"
    sample_state.compensation.target_channel = "FSC-A"
    window._refresh_group_list()
    window.on_group_selection_changed("Compensation")

    assert "FITC" in window.sample_panel.sample_list.item(0).text()
    assert "FSC-A" in window.sample_panel.sample_list.item(0).text()


def test_sample_details_show_compensation_metadata() -> None:
    get_app()
    window = MainWindow()
    sample_state = window.workspace.add_sample(make_sample("pe.fcs"), group_name="Compensation")
    sample_state.compensation.control_type = "single_stain"
    sample_state.compensation.fluorochrome = "PE"
    sample_state.compensation.target_channel = "SSC-A"
    sample_state.compensation.notes = "Bright control"
    window._refresh_group_list()
    window.on_group_selection_changed("Compensation")
    window.on_sample_selection_changed(0)

    assert "PE" in window.sample_panel.sample_details_label.text()
    assert "SSC-A" in window.sample_panel.sample_details_label.text()
    assert "Bright control" in window.sample_panel.sample_details_label.text()


def test_compensation_setup_table_shows_compensation_samples() -> None:
    get_app()
    window = MainWindow()
    sample_state = window.workspace.add_sample(make_sample("fitc_control.fcs"), group_name="Compensation")
    sample_state.compensation.fluorochrome = "FITC"
    sample_state.compensation.target_channel = "FSC-A"
    sample_state.compensation_positive.sample_index = 0
    sample_state.compensation_positive.population_name = "Positive gate"
    sample_state.compensation_negative.sample_index = 0
    sample_state.compensation_negative.population_name = "Negative gate"
    window._refresh_compensation_setup()

    assert window.inspector_panel.compensation_table.rowCount() == 1
    assert window.inspector_panel.compensation_table.item(0, 0).text() == "fitc_control.fcs"
    assert window.inspector_panel.compensation_table.item(0, 2).text() == "FITC"
    assert "Positive gate" in window.inspector_panel.compensation_table.item(0, 4).text()


def test_apply_active_gate_to_group_copies_gate_to_matching_group() -> None:
    get_app()
    window = MainWindow()
    source = make_sample("source.fcs")
    target = make_sample("target.fcs")
    other = make_sample("other.fcs")

    source_state = window.workspace.add_sample(source, group_name="Controls")
    source_gate = RangeGate(
        name="Live",
        parent_name="All events",
        channel_index=0,
        channel_label="FSC-A",
        x_min=2.0,
        x_max=5.0,
        event_count=2,
        percentage_parent=50.0,
        percentage_total=50.0,
        full_mask=np.array([False, True, True, False]),
    )
    source_state.gates.append(source_gate)
    source_state.active_gate_name = "Live"
    window.workspace.add_sample(target, group_name="Controls")
    window.workspace.add_sample(other, group_name="Specimen 1")

    window.on_apply_active_gate_to_group(0)

    assert len(window.workspace.samples[1].gates) == 1
    assert window.workspace.samples[1].gates[0].name == "Live"
    assert window.workspace.samples[1].gates[0].full_mask.tolist() == [False, True, True, False]
    assert window.workspace.samples[2].gates == []


def test_apply_all_gates_to_all_samples_preserves_hierarchy() -> None:
    get_app()
    window = MainWindow()
    source = make_sample("source.fcs")
    target = make_sample("target.fcs")

    source_state = window.workspace.add_sample(source, group_name="Specimen 1")
    parent_gate = RangeGate(
        name="Parent",
        parent_name="All events",
        channel_index=0,
        channel_label="FSC-A",
        x_min=2.0,
        x_max=5.0,
        event_count=2,
        percentage_parent=50.0,
        percentage_total=50.0,
        full_mask=np.array([False, True, True, False]),
    )
    child_gate = RangeGate(
        name="Child",
        parent_name="Parent",
        channel_index=1,
        channel_label="SSC-A",
        x_min=3.0,
        x_max=6.0,
        event_count=2,
        percentage_parent=100.0,
        percentage_total=50.0,
        full_mask=np.array([False, True, True, False]),
    )
    source_state.gates.extend([parent_gate, child_gate])
    window.workspace.add_sample(target, group_name="Specimen 2")

    window.on_apply_all_gates_to_all_samples(0)

    cloned_parent, cloned_child = window.workspace.samples[1].gates
    assert cloned_parent.name == "Parent"
    assert cloned_child.parent_name == "Parent"
    assert cloned_parent.full_mask.tolist() == [False, True, True, False]
    assert cloned_child.full_mask.tolist() == [False, True, True, False]


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
    assert window.sample_panel.gate_list.item(1).text().startswith("Lymphocytes <- All events |")
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


def test_main_window_uses_compact_inspector_layout() -> None:
    get_app()
    window = MainWindow()

    splitter = window.centralWidget()

    assert isinstance(splitter, QSplitter)
    assert splitter.widget(0) is window.sample_panel
    assert splitter.widget(2) is window.inspector_panel
    assert window.sample_panel.minimumWidth() == 0
    assert window.inspector_panel.minimumWidth() == 0
    assert isinstance(window.inspector_panel.controls_tabs, QTabWidget)
    assert window.inspector_panel.controls_tabs.count() == 4
    assert window.inspector_panel.controls_tabs.tabText(0) == "Gate"
    assert window.inspector_panel.controls_tabs.tabText(1) == "Ajustes de grafica"
    assert window.inspector_panel.controls_tabs.tabText(2) == "Statistics"
    assert window.inspector_panel.controls_tabs.tabText(3) == "Compensation"
    gate_tab = window.inspector_panel.controls_tabs.widget(0)
    assert isinstance(gate_tab, QScrollArea)
    gate_layout = gate_tab.widget().layout()
    assert gate_layout.itemAt(0).widget().title() == "Visualizacion"
    assert gate_layout.itemAt(1).widget().title() == "Gate actions"
    assert gate_layout.itemAt(2).widget().title() == "Scatter gate type"
    assert gate_layout.itemAt(3).widget().title() == "Histogram gate type"


def test_gate_tab_locks_invalid_gate_types_by_plot_mode() -> None:
    get_app()
    window = MainWindow()
    panel = window.inspector_panel

    panel.set_plot_mode("scatter")
    assert panel.rectangle_gate_button.isEnabled()
    assert panel.polygon_gate_button.isEnabled()
    assert panel.circle_gate_button.isEnabled()
    assert not panel.histogram_range_button.isEnabled()
    assert panel.current_scatter_gate_type() == "rectangle"

    panel.set_plot_mode("histogram")
    assert not panel.rectangle_gate_button.isEnabled()
    assert not panel.polygon_gate_button.isEnabled()
    assert not panel.circle_gate_button.isEnabled()
    assert panel.histogram_range_button.isEnabled()
    assert panel.histogram_range_button.isChecked()


def test_plot_mode_combo_switches_panel_to_histogram() -> None:
    get_app()
    window = MainWindow()
    panel = window.inspector_panel

    panel.plot_mode_combo.setCurrentIndex(1)

    assert panel.current_plot_mode() == "histogram"
    assert not panel.rectangle_gate_button.isEnabled()
    assert panel.histogram_range_button.isEnabled()


def test_view_controls_emit_redraw_without_qt_signature_errors(monkeypatch) -> None:
    get_app()
    window = MainWindow()
    panel = window.inspector_panel
    redraw_calls: list[bool] = []

    monkeypatch.setattr(window, "redraw_current_plot", lambda: redraw_calls.append(True))

    panel.x_scale_combo.setCurrentIndex(1)
    panel.x_min_edit.setText("10")
    panel.x_min_edit.editingFinished.emit()
    panel.apply_view_button.click()

    assert len(redraw_calls) == 3


def test_create_gate_button_text_stays_generic() -> None:
    get_app()
    window = MainWindow()
    panel = window.inspector_panel

    panel.set_plot_mode("scatter")
    assert panel.create_gate_button.text() == "Create gate"

    panel.circle_gate_button.setChecked(True)
    assert panel.create_gate_button.text() == "Create gate"

    panel.polygon_gate_button.setChecked(True)
    assert panel.create_gate_button.text() == "Create gate"

    panel.set_plot_mode("histogram")
    assert panel.create_gate_button.text() == "Create gate"


def test_create_gate_button_click_creates_scatter_roi() -> None:
    get_app()
    window = MainWindow()
    sample = make_sample("demo.fcs")

    window.current_sample = sample
    window._update_inspector(sample)
    window._configure_axis_selectors(sample)
    window.redraw_current_plot(show_status=False)

    window.inspector_panel.create_gate_button.click()

    assert window.plot_panel._rect_roi is not None
    assert window.statusBar().currentMessage() == "Gate ROI created. Adjust it and then click Apply gate."


def test_statistics_tab_calculates_population_metrics() -> None:
    get_app()
    window = MainWindow()
    sample = make_sample("demo.fcs")
    gate = RangeGate(
        name="Gate 1",
        parent_name="All events",
        channel_index=0,
        channel_label="FSC-A",
        x_min=0.0,
        x_max=3.0,
        event_count=2,
        percentage_parent=50.0,
        percentage_total=50.0,
        full_mask=np.array([True, True, False, False]),
    )

    window.current_sample = sample
    window.gates = [gate]
    window.active_gate = gate
    window._update_inspector(sample)
    window._configure_axis_selectors(sample)
    window._refresh_statistics_population_options()
    window.inspector_panel.set_statistics_populations([("All events", None), ("Gate 1", 0)], selected_gate_index=0)
    window.inspector_panel.set_statistics_channels(["FSC-A", "SSC-A"], selected_channel_index=0)

    for row in range(window.inspector_panel.statistics_metric_list.count()):
        item = window.inspector_panel.statistics_metric_list.item(row)
        item.setCheckState(Qt.Unchecked)
    window.inspector_panel.statistics_metric_list.item(0).setCheckState(Qt.Checked)
    window.inspector_panel.statistics_metric_list.item(3).setCheckState(Qt.Checked)

    window.on_calculate_statistics()

    assert window.inspector_panel.statistics_table.rowCount() == 2
    assert window.inspector_panel.statistics_table.item(0, 0).text() == "Event count"
    assert window.inspector_panel.statistics_table.item(0, 1).text() == "2"
    assert window.inspector_panel.statistics_table.item(1, 0).text() == "Mean"
    assert window.inspector_panel.statistics_table.item(1, 1).text() == "1.0000"


def test_population_context_labels_show_origin_and_direct_children() -> None:
    get_app()
    window = MainWindow()
    sample = make_sample("demo.fcs")
    parent_gate = RangeGate(
        name="Gate 1",
        parent_name="All events",
        channel_index=0,
        channel_label="FSC-A",
        x_min=0.0,
        x_max=3.0,
        event_count=2,
        percentage_parent=50.0,
        percentage_total=50.0,
        full_mask=np.array([True, True, False, False]),
    )
    child_gate = RangeGate(
        name="Gate 2",
        parent_name="Gate 1",
        channel_index=0,
        channel_label="FSC-A",
        x_min=0.0,
        x_max=1.0,
        event_count=1,
        percentage_parent=50.0,
        percentage_total=25.0,
        full_mask=np.array([True, False, False, False]),
    )

    window.current_sample = sample
    window.gates = [parent_gate, child_gate]
    window.sample_panel.reset_gates()
    for gate in window.gates:
        window.sample_panel.add_gate(window._gate_list_label(gate), select=False)

    window.on_gate_selection_changed(1)
    assert window.sample_panel.population_origin_label.text() == "Origin: All events"
    assert window.sample_panel.population_children_label.text() == "Subpopulations: Gate 2"

    window.on_gate_selection_changed(2)
    assert window.sample_panel.population_origin_label.text() == "Origin: Gate 1"
    assert window.sample_panel.population_children_label.text() == "Subpopulations: —"


def test_scatter_can_overlay_direct_subpopulations() -> None:
    get_app()
    window = MainWindow()
    sample = make_sample("demo.fcs")
    parent_gate = RangeGate(
        name="Gate 1",
        parent_name="All events",
        channel_index=0,
        channel_label="FSC-A",
        x_min=0.0,
        x_max=5.0,
        event_count=3,
        percentage_parent=75.0,
        percentage_total=75.0,
        full_mask=np.array([True, True, True, False]),
        color_hex="#ff0000",
    )
    child_gate = RangeGate(
        name="Gate 2",
        parent_name="Gate 1",
        channel_index=0,
        channel_label="FSC-A",
        x_min=0.0,
        x_max=3.0,
        event_count=2,
        percentage_parent=66.67,
        percentage_total=50.0,
        full_mask=np.array([True, True, False, False]),
        color_hex="#00aa55",
    )

    window.current_sample = sample
    window.gates = [parent_gate, child_gate]
    window.active_gate = parent_gate
    window._update_inspector(sample)
    window._configure_axis_selectors(sample)
    window.inspector_panel.show_subpopulations_checkbox.setChecked(True)

    window.redraw_current_plot(show_status=False)

    assert len(window.plot_panel._subpopulation_scatter_items) == 1


def test_export_statistics_uses_csv_export(monkeypatch) -> None:
    get_app()
    window = MainWindow()
    sample = make_sample("demo.fcs")

    window.current_sample = sample
    window._latest_statistics_population_name = "All events"
    window._latest_statistics_channel_name = "FSC-A"
    window._latest_statistics = [StatisticResult(key="mean", label="Mean", value=3.5)]

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: ("stats_export.csv", "CSV files (*.csv)"),
    )

    calls: list[str] = []

    monkeypatch.setattr(
        "cytodraft.gui.main_window.export_population_statistics_to_csv",
        lambda **kwargs: calls.append(kwargs["population_name"]) or Path("stats_export.csv"),
    )

    window.on_export_statistics()

    assert calls == ["All events"]


def test_export_active_gate_uses_fcs_export_for_fcs_extension(monkeypatch) -> None:
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
    window.active_gate = gate

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: ("gate_export.fcs", "FCS files (*.fcs)"),
    )

    calls: list[str] = []

    monkeypatch.setattr(
        "cytodraft.gui.main_window.export_masked_events_to_fcs",
        lambda *args, **kwargs: calls.append("fcs") or Path("gate_export.fcs"),
    )
    monkeypatch.setattr(
        "cytodraft.gui.main_window.export_masked_events_to_csv",
        lambda *args, **kwargs: calls.append("csv") or Path("gate_export.csv"),
    )

    window.on_export_active_gate()

    assert calls == ["fcs"]
