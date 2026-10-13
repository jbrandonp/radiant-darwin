"""
Thème visuel sombre Autodesk Fusion 360 et feuilles de style Qt (QSS).
Définit une esthétique industrielle sobre et moderne avec des accents bleu métallisé,
des ombres portées douces et une hiérarchie visuelle professionnelle.
"""

from __future__ import annotations


FUSION_DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1e1f23;
    color: #e0e2e8;
    font-family: "Segoe UI", "Inter", -apple-system, sans-serif;
    font-size: 12px;
}

/* Infobulles modernes style Windows 11 / Fusion 360 */
QToolTip {
    background-color: #2b2e36;
    color: #ffffff;
    border: 1px solid #444854;
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: 500;
}

/* Barre de menu principale */
QMenuBar {
    background-color: #16171a;
    color: #cccccc;
    border-bottom: 1px solid #282a30;
    padding: 3px 6px;
    font-size: 11px;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
    border-radius: 3px;
}
QMenuBar::item:selected {
    background-color: #2b2d34;
    color: #ffffff;
}

/* Menus déroulants */
QMenu {
    background-color: #212328;
    color: #e0e2e8;
    border: 1px solid #363942;
    border-radius: 5px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px;
    border-radius: 3px;
    font-size: 11px;
}
QMenu::item:selected {
    background-color: #007acc;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background-color: #31343c;
    margin: 4px 6px;
}

/* Barre d'onglets du ruban (Ribbon) */
QTabWidget::pane {
    border-top: 1px solid #2a2c33;
    background-color: #212328;
}
QTabBar::tab {
    background-color: #1a1b1f;
    color: #8f95a3;
    padding: 8px 18px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    font-weight: bold;
    font-size: 11px;
    letter-spacing: 0.5px;
}
QTabBar::tab:hover {
    background-color: #26282e;
    color: #e0e2e8;
}
QTabBar::tab:selected {
    background-color: #212328;
    color: #00a2ff;
    border-bottom: 2px solid #00a2ff;
}

/* Boutons d'action dans le ruban */
QToolButton, QPushButton {
    background-color: #272a31;
    color: #d8dbe2;
    border: 1px solid #383c46;
    border-radius: 4px;
    padding: 5px 10px;
    font-weight: 600;
}
QToolButton:hover, QPushButton:hover {
    background-color: #343842;
    border-color: #007acc;
    color: #ffffff;
}
QToolButton:pressed, QPushButton:pressed {
    background-color: #007acc;
    color: #ffffff;
}

/* Arbre de navigation gauche (Browser) */
QTreeWidget {
    background-color: #17181b;
    border: 1px solid #282a30;
    border-radius: 4px;
    color: #d1d5db;
    padding: 4px;
    font-size: 11px;
}
QTreeWidget::item {
    padding: 5px;
    border-radius: 3px;
}
QTreeWidget::item:hover {
    background-color: #24262c;
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
    background-color: #1e2025;
    padding: 6px 10px;
    border-bottom: 1px solid #2a2c33;
    color: #00a2ff;
    font-size: 10px;
    letter-spacing: 0.5px;
}

/* Contrôles de formulaires et paramètres */
QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox {
    background-color: #131417;
    border: 1px solid #33363e;
    border-radius: 3px;
    color: #f0f2f5;
    padding: 4px 8px;
    min-height: 22px;
    font-size: 11px;
}
QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus, QComboBox:focus {
    border: 1px solid #00a2ff;
    background-color: #18191d;
}

/* Sliders */
QSlider::groove:horizontal {
    height: 4px;
    background: #363942;
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

/* Barre de défilement moderne et discrète */
QScrollBar:vertical {
    background: #17181b;
    width: 7px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #363942;
    border-radius: 3px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #4f5462;
}
QScrollBar:horizontal {
    background: #17181b;
    height: 7px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #363942;
    border-radius: 3px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background: #4f5462;
}
QScrollBar::add-line, QScrollBar::sub-line {
    background: none;
    border: none;
}

/* Barre d'état inférieure */
QStatusBar {
    background-color: #151619;
    border-top: 1px solid #282a30;
    color: #8c93a0;
    font-size: 11px;
    padding: 2px 8px;
}

/* Séparateurs */
QSplitter::handle {
    background-color: #24262c;
}
QSplitter::handle:hover {
    background-color: #00a2ff;
}
"""
