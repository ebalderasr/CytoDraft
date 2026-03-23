from __future__ import annotations


APP_STYLESHEET = """
QWidget {
    background: #eef2f7;
    color: #18212f;
    font-family: "Segoe UI", "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 13px;
}

QMainWindow, QSplitter {
    background: #eef2f7;
}

QWidget#plotAreaCard {
    background: transparent;
}

QWidget#plotSurface {
    background: #fbfcfe;
    border: 1px solid #d7e0ea;
    border-radius: 16px;
}

QSplitter::handle {
    background: transparent;
}

QSplitter::handle:horizontal {
    width: 10px;
}

QSplitter::handle:vertical {
    height: 10px;
}

QGroupBox {
    background: #fbfcfe;
    border: 1px solid #d7e0ea;
    border-radius: 14px;
    font-weight: 700;
    margin-top: 14px;
    padding: 16px 14px 12px 14px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
    color: #526072;
    background: #eef2f7;
    border-radius: 8px;
}

QTabWidget::pane {
    border: 1px solid #d7e0ea;
    border-radius: 14px;
    background: #fbfcfe;
    top: -1px;
}

QTabBar::tab {
    background: #e4ebf3;
    color: #516071;
    border: 1px solid #d7e0ea;
    padding: 8px 15px;
    border-top-left-radius: 11px;
    border-top-right-radius: 11px;
    margin-right: 6px;
}

QTabBar::tab:selected {
    background: #fbfcfe;
    color: #102033;
    border-bottom-color: #fbfcfe;
}

QLabel {
    background: transparent;
}

QLabel#inspectorSectionLabel {
    color: #536274;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

QLabel#inspectorCaption {
    color: #7b8794;
    font-size: 11px;
    font-weight: 600;
}

QLabel#inspectorFileValue {
    color: #132033;
    font-size: 15px;
    font-weight: 700;
    background: #f4f7fb;
    border: 1px solid #e1e8f0;
    border-radius: 10px;
    padding: 10px 12px;
}

QLabel#inspectorMetricValue {
    color: #132033;
    font-size: 14px;
    font-weight: 700;
    background: #f4f7fb;
    border: 1px solid #e1e8f0;
    border-radius: 10px;
    padding: 8px 10px;
}

QLabel#inspectorActiveValue {
    color: #17305f;
    font-size: 13px;
    font-weight: 700;
    background: #eaf1ff;
    border: 1px solid #c9dafc;
    border-radius: 10px;
    padding: 9px 11px;
}

QLineEdit,
QComboBox,
QSpinBox,
QListWidget {
    background: #ffffff;
    border: 1px solid #ccd7e2;
    border-radius: 10px;
    padding: 7px 10px;
    selection-background-color: #d8e8ff;
    selection-color: #102033;
}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QListWidget:focus {
    border: 1px solid #2a6df4;
}

QListWidget {
    padding: 6px;
    outline: 0;
}

QListWidget::item {
    border-radius: 9px;
    padding: 8px 10px;
    margin: 2px 0;
}

QListWidget::item:selected {
    background: #dce9ff;
    color: #102033;
}

QTableWidget {
    background: #ffffff;
    border: 1px solid #ccd7e2;
    border-radius: 12px;
    gridline-color: #e5edf5;
    alternate-background-color: #f8fbff;
    selection-background-color: #dce9ff;
    selection-color: #102033;
}

QHeaderView::section {
    background: #f4f7fb;
    color: #4b5b6d;
    border: none;
    border-right: 1px solid #e3eaf2;
    border-bottom: 1px solid #e3eaf2;
    padding: 8px 10px;
    font-weight: 700;
}

QPushButton {
    background: #e8edf3;
    color: #17202c;
    border: 1px solid #d4dde7;
    border-radius: 10px;
    padding: 10px 12px;
    min-height: 18px;
    font-weight: 600;
}

QPushButton:hover {
    background: #dbe2ea;
}

QPushButton:pressed {
    background: #cfd8e3;
}

QPushButton:checked {
    background: #dbeafe;
    color: #1d4ed8;
    border: 1px solid #93c5fd;
}

QPushButton[variant="primary"] {
    background: #2563eb;
    color: #ffffff;
    border: 1px solid #1d4ed8;
}

QPushButton[variant="primary"]:hover {
    background: #1d4ed8;
}

QPushButton[variant="danger"] {
    background: #fff1f2;
    color: #b42318;
    border: 1px solid #fecdd3;
}

QPushButton[variant="danger"]:hover {
    background: #ffe4e6;
}

QPushButton[variant="subtle"] {
    background: #ffffff;
}

QPushButton[variant="chip"] {
    background: #e8edf3;
    color: #536274;
    border: 1px solid #ccd7e2;
    border-radius: 12px;
    padding: 3px 10px;
    min-height: 0;
    font-size: 11px;
    font-weight: 600;
}

QPushButton[variant="chip"]:hover {
    background: #dde4ed;
    color: #2d3e52;
}

QPushButton[variant="chip"]:checked {
    background: #dbeafe;
    color: #1d4ed8;
    border-color: #93c5fd;
}

QPushButton[variant="chip"]:checked:hover {
    background: #c7dcfc;
}

QToolButton {
    background: #ffffff;
    color: #17202c;
    border: 1px solid #d4dde7;
    border-radius: 9px;
    padding: 4px 8px;
    font-weight: 700;
}

QToolButton:hover {
    background: #edf3f9;
}

QToolButton:pressed {
    background: #dfe7f0;
}

QToolButton[variant="primary"] {
    background: #2b6ef3;
    color: #ffffff;
    border: 1px solid #1f5fe0;
}

QToolButton[variant="primary"]:hover {
    background: #1f5fe0;
}

QToolButton[variant="danger"] {
    background: #fff2f3;
    color: #b42318;
    border: 1px solid #f5c2c7;
}

QToolButton[variant="danger"]:hover {
    background: #ffe7ea;
}

QToolButton[variant="subtle"] {
    background: #ffffff;
}

QCheckBox {
    spacing: 8px;
}

QStatusBar {
    background: #fbfcfe;
    border-top: 1px solid #d7e0ea;
}

QToolBar {
    background: #fbfcfe;
    border-bottom: 1px solid #d7e0ea;
    padding: 6px 10px;
    spacing: 6px;
}

QToolBar::separator {
    background: #d7e0ea;
    width: 1px;
    margin: 4px 6px;
}

QToolBar QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 7px 13px;
    font-weight: 600;
    color: #233043;
}

QToolBar QToolButton:hover {
    background: #e7eef6;
    border-color: #d7e0ea;
}

QToolBar QToolButton:pressed {
    background: #dbe4ed;
}

QToolBar QToolButton:checked {
    background: #dbe8ff;
    color: #1c4fd2;
    border-color: #a7c4fb;
}

QMenu {
    background: #ffffff;
    border: 1px solid #d4dde7;
    border-radius: 10px;
    padding: 6px;
}

QMenu::item {
    padding: 8px 18px;
    border-radius: 8px;
}

QMenu::item:selected {
    background: #dce9ff;
}

QMenu::separator {
    height: 1px;
    background: #e8edf3;
    margin: 4px 6px;
}

/* ── Menu bar ────────────────────────────────────────────────── */

QMenuBar {
    background: #eef2f7;
    border-bottom: 1px solid #d7e0ea;
    padding: 2px 4px;
    spacing: 2px;
}

QMenuBar::item {
    background: transparent;
    padding: 5px 10px;
    border-radius: 7px;
    color: #233043;
}

QMenuBar::item:selected {
    background: #dce9ff;
    color: #1d4ed8;
}

QMenuBar::item:pressed {
    background: #c8daff;
}

/* ── Scrollbars ──────────────────────────────────────────────── */

QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 3px 2px 3px 0;
}

QScrollBar::handle:vertical {
    background: #c8d5e2;
    border-radius: 4px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #a9bfcf;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
    height: 0;
}

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0 3px 2px 3px;
}

QScrollBar::handle:horizontal {
    background: #c8d5e2;
    border-radius: 4px;
    min-width: 20px;
}

QScrollBar::handle:horizontal:hover {
    background: #a9bfcf;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
    width: 0;
}

/* ── List item hover ─────────────────────────────────────────── */

QListWidget::item:hover:!selected {
    background: #eef3fa;
}

/* Disable alternating rows on lists (hover/selection give feedback instead) */
QListWidget {
    alternate-background-color: #ffffff;
}

/* ── ComboBox drop-down button ───────────────────────────────── */

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    border-left: 1px solid #dce5ee;
    border-top-right-radius: 9px;
    border-bottom-right-radius: 9px;
    width: 22px;
    background: #f4f7fb;
}

QComboBox::drop-down:hover {
    background: #eaeff5;
}

QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #d4dde7;
    selection-background-color: #dce9ff;
    selection-color: #102033;
    padding: 4px;
    outline: 0;
}

/* ── SpinBox buttons ─────────────────────────────────────────── */

QSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #ccd7e2;
    border-bottom: 1px solid #ccd7e2;
    border-top-right-radius: 9px;
    background: #f4f7fb;
}

QSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    border-left: 1px solid #ccd7e2;
    border-bottom-right-radius: 9px;
    background: #f4f7fb;
}

QSpinBox::up-button:hover,
QSpinBox::down-button:hover {
    background: #eaeff5;
}

/* ── Checkbox indicators ─────────────────────────────────────── */

QCheckBox::indicator,
QListWidget::indicator {
    width: 16px;
    height: 16px;
    border: 1.5px solid #b5c4d1;
    border-radius: 5px;
    background: #ffffff;
}

QCheckBox::indicator:hover,
QListWidget::indicator:hover {
    border-color: #2a6df4;
    background: #f0f6ff;
}

QCheckBox::indicator:checked,
QListWidget::indicator:checked {
    background: #2563eb;
    border-color: #1d4ed8;
}

QCheckBox::indicator:checked:hover,
QListWidget::indicator:checked:hover {
    background: #1d4ed8;
}

/* ── Disabled states ─────────────────────────────────────────── */

QPushButton:disabled {
    background: #f0f4f8;
    color: #9aaabb;
    border-color: #dce5ee;
}

QToolButton:disabled {
    color: #a0b0bf;
    background: transparent;
    border-color: transparent;
}

QComboBox:disabled,
QSpinBox:disabled,
QLineEdit:disabled {
    background: #f5f8fb;
    color: #9aaabb;
    border-color: #dce5ee;
}

QListWidget:disabled {
    background: #f5f8fb;
    color: #9aaabb;
}

/* ── Tooltip ─────────────────────────────────────────────────── */

QToolTip {
    background: #1b2738;
    color: #e2eaf3;
    border: 1px solid #2e3f54;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
}

/* ── Panel info labels ───────────────────────────────────────── */

QLabel#panelInfoLabel {
    color: #8697a8;
    font-size: 11px;
    padding: 1px 2px;
}

/* ── Dialog buttons minimum size ─────────────────────────────── */

QDialogButtonBox QPushButton {
    min-width: 80px;
}
"""
