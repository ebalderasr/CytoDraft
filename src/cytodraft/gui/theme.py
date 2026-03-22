from __future__ import annotations


APP_STYLESHEET = """
QWidget {
    background: #f3f6fb;
    color: #1f2937;
    font-family: "Segoe UI", "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 13px;
}

QMainWindow, QSplitter {
    background: #f3f6fb;
}

QGroupBox {
    background: #ffffff;
    border: 1px solid #d9e2ec;
    border-radius: 12px;
    font-weight: 700;
    margin-top: 12px;
    padding: 14px 14px 12px 14px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #4b5563;
}

QTabWidget::pane {
    border: 1px solid #d9e2ec;
    border-radius: 12px;
    background: #ffffff;
    top: -1px;
}

QTabBar::tab {
    background: #e7edf5;
    color: #475569;
    border: 1px solid #d9e2ec;
    padding: 8px 14px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    margin-right: 6px;
}

QTabBar::tab:selected {
    background: #ffffff;
    color: #0f172a;
    border-bottom-color: #ffffff;
}

QLabel {
    background: transparent;
}

QLineEdit,
QComboBox,
QSpinBox,
QListWidget {
    background: #ffffff;
    border: 1px solid #cfd8e3;
    border-radius: 10px;
    padding: 7px 10px;
    selection-background-color: #dbeafe;
    selection-color: #0f172a;
}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QListWidget:focus {
    border: 1px solid #2563eb;
}

QListWidget {
    padding: 6px;
    outline: 0;
}

QListWidget::item {
    border-radius: 8px;
    padding: 8px 10px;
    margin: 2px 0;
}

QListWidget::item:selected {
    background: #e0ecff;
    color: #0f172a;
}

QPushButton {
    background: #e5e7eb;
    color: #111827;
    border: 1px solid #d1d5db;
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

QCheckBox {
    spacing: 8px;
}

QStatusBar {
    background: #ffffff;
    border-top: 1px solid #d9e2ec;
}

QToolBar {
    background: #ffffff;
    border-bottom: 1px solid #d9e2ec;
    padding: 4px 8px;
    spacing: 4px;
}

QToolBar::separator {
    background: #d9e2ec;
    width: 1px;
    margin: 4px 6px;
}

QToolBar QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 6px 12px;
    font-weight: 600;
    color: #1f2937;
}

QToolBar QToolButton:hover {
    background: #e7edf5;
    border-color: #d9e2ec;
}

QToolBar QToolButton:pressed {
    background: #d9e2ec;
}

QToolBar QToolButton:checked {
    background: #dbeafe;
    color: #1d4ed8;
    border-color: #93c5fd;
}

QMenu {
    background: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 10px;
    padding: 6px;
}

QMenu::item {
    padding: 8px 18px;
    border-radius: 8px;
}

QMenu::item:selected {
    background: #e0ecff;
}
"""
