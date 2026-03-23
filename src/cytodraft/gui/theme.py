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
"""
