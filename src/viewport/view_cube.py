"""
Widget ViewCube interactif style Autodesk Fusion 360.
Superposé dans le coin supérieur droit du viewport 3D pour orienter rapidement la vue.
"""

from __future__ import annotations
from typing import Callable, Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGridLayout
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor


class ViewCubeOverlay(QWidget):
    """
    Contrôleur de navigation cubique rapide style Autodesk Fusion 360.
    Permet de basculer instantanément la caméra vers Haut, Face, Droite, Gauche,
    Bas, Arrière ou Vue Isométrique / Recadrer.
    """

    view_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialise le ViewCube avec une disposition claire et ergonomique."""
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(165, 155)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(3)

        # Barre supérieure : boutons Vue ISO et Recadrer
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(3)

        btn_top_style = """
            QPushButton {
                background-color: rgba(45, 48, 55, 220);
                color: #e0e0e0;
                border: 1px solid #444852;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                padding: 2px 4px;
            }
            QPushButton:hover {
                background-color: #007acc;
                border-color: #3399ff;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #005999;
            }
        """

        home_btn = QPushButton("🏠 ISO")
        home_btn.setFixedHeight(22)
        home_btn.setStyleSheet(btn_top_style)
        home_btn.setToolTip("Vue Isométrique par défaut (H)")
        home_btn.clicked.connect(lambda: self.view_selected.emit("HOME"))
        top_bar.addWidget(home_btn)

        fit_btn = QPushButton("🎯 Recadrer")
        fit_btn.setFixedHeight(22)
        fit_btn.setStyleSheet(btn_top_style)
        fit_btn.setToolTip("Recadrer sur l'ensemble du modèle (F)")
        fit_btn.clicked.connect(lambda: self.view_selected.emit("FIT"))
        top_bar.addWidget(fit_btn)

        main_layout.addLayout(top_bar)

        # Grille de sélection des faces du cube
        grid = QGridLayout()
        grid.setSpacing(3)

        btn_style = """
            QPushButton {
                background-color: rgba(50, 54, 62, 230);
                color: #cfd3dc;
                border: 1px solid #3c404a;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                padding: 1px 2px;
            }
            QPushButton:hover {
                background-color: #007acc;
                color: #ffffff;
                border-color: #55aaff;
            }
            QPushButton:pressed {
                background-color: #005999;
            }
        """

        btn_top = QPushButton("HAUT")
        btn_top.setFixedHeight(24)
        btn_top.setStyleSheet(btn_style)
        btn_top.setToolTip("Vue du dessus (Plan XY)")
        btn_top.clicked.connect(lambda: self.view_selected.emit("TOP"))
        grid.addWidget(btn_top, 0, 1)

        btn_left = QPushButton("GAUCHE")
        btn_left.setFixedHeight(24)
        btn_left.setStyleSheet(btn_style)
        btn_left.setToolTip("Vue de gauche (Plan YZ)")
        btn_left.clicked.connect(lambda: self.view_selected.emit("LEFT"))
        grid.addWidget(btn_left, 1, 0)

        btn_front = QPushButton("FACE")
        btn_front.setFixedHeight(24)
        btn_front.setStyleSheet(btn_style)
        btn_front.setToolTip("Vue de face (Plan XZ)")
        btn_front.clicked.connect(lambda: self.view_selected.emit("FRONT"))
        grid.addWidget(btn_front, 1, 1)

        btn_right = QPushButton("DROITE")
        btn_right.setFixedHeight(24)
        btn_right.setStyleSheet(btn_style)
        btn_right.setToolTip("Vue de droite")
        btn_right.clicked.connect(lambda: self.view_selected.emit("RIGHT"))
        grid.addWidget(btn_right, 1, 2)

        btn_back = QPushButton("ARR")
        btn_back.setFixedHeight(24)
        btn_back.setStyleSheet(btn_style)
        btn_back.setToolTip("Vue arrière")
        btn_back.clicked.connect(lambda: self.view_selected.emit("BACK"))
        grid.addWidget(btn_back, 2, 0)

        btn_bottom = QPushButton("BAS")
        btn_bottom.setFixedHeight(24)
        btn_bottom.setStyleSheet(btn_style)
        btn_bottom.setToolTip("Vue de dessous")
        btn_bottom.clicked.connect(lambda: self.view_selected.emit("BOTTOM"))
        grid.addWidget(btn_bottom, 2, 1)

        main_layout.addLayout(grid)
