"""
Thème visuel sombre Fusion 360 et feuilles de style Qt (QSS).
Définit une esthétique industrielle sobre et moderne avec des accents bleu métallisé.
"""

from __future__ import annotations


FUSION_DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1e1f22;
    color: #e0e2e8;
    font-family: "Segoe UI", "Inter", "Helvetica Neue", sans-serif;
    font-size: 12px;
}

/* Barre de menu principale */
QMenuBar {
    background-color: #18191c;
    color: #cccccc;
    border-bottom: 1px solid #2b2d32;
    padding: 2px 4px;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
    border-radius: 3px;
}
QMenuBar::item:selected {
    background-color: #2b2d32;
    color: #ffffff;
}

QMenu {
    background-color: #222428;
    color: #e0e2e8;
    border: 1px solid #36393f;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px;
    border-radius: 3px;
}
QMenu::item:selected {
    background-color: #007acc;
    color: #ffffff;
}

/* Barre d'onglets du ruban (Ribbon) */
QTabWidget::pane {
    border-top: 1px solid #2f3238;
    background-color: #232529;
}
QTabBar::tab {
    background-color: #1e1f22;
    color: #9da3af;
    padding: 8px 18px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    font-weight: bold;
    font-size: 11px;
}
QTabBar::tab:hover {
    background-color: #282a2f;
    color: #e0e2e8;
}
QTabBar::tab:selected {
    background-color: #232529;
    color: #00a2ff;
    border-bottom: 2px solid #00a2ff;
}

/* Boutons d'action dans le ruban */
QToolButton, QPushButton {
    background-color: #2b2e35;
    color: #d8dbe2;
    border: 1px solid #3c4049;
    border-radius: 4px;
    padding: 5px 10px;
    font-weight: 500;
}
QToolButton:hover, QPushButton:hover {
    background-color: #383c45;
    border-color: #007acc;
    color: #ffffff;
}
QToolButton:pressed, QPushButton:pressed {
    background-color: #007acc;
    color: #ffffff;
}

/* Arbre de navigation gauche (Browser) */
QTreeWidget {
    background-color: #18191c;
    border: 1px solid #2b2d32;
    border-radius: 4px;
    color: #d1d5db;
    padding: 4px;
}
QTreeWidget::item {
    padding: 4px;
    border-radius: 3px;
}
QTreeWidget::item:hover {
    background-color: #26282d;
}
QTreeWidget::item:selected {
    background-color: #094771;
    color: #ffffff;
}

/* Panneaux dockables */
QDockWidget {
    color: #d1d5db;
    font-weight: bold;
}
QDockWidget::title {
    background-color: #222429;
    padding: 6px;
    border-bottom: 1px solid #2b2d32;
}

/* Contrôles de formulaires et paramètres */
QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox {
    background-color: #141517;
    border: 1px solid #36393f;
    border-radius: 3px;
    color: #f0f2f5;
    padding: 4px 8px;
    min-height: 20px;
}
QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus, QComboBox:focus {
    border: 1px solid #00a2ff;
}

QSlider::groove:horizontal {
    height: 4px;
    background: #36393f;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #00a2ff;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #ffffff;
    border: 1px solid #00a2ff;
    width: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}

/* Barre de défilement moderne */
QScrollBar:vertical, QScrollBar:horizontal {
    background: #18191c;
    width: 8px;
    height: 8px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #3a3d45;
    border-radius: 4px;
}
QScrollBar::handle:hover {
    background: #50545f;
}
QScrollBar::add-line, QScrollBar::sub-line {
    background: none;
}
"""
