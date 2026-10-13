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
    Contrôleur de navigation cubique rapide.
    Permet de basculer instantanément la caméra vers Haut, Face, Droite, ou Vue Initiale (Home).
    """

    view_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialise le ViewCube avec une disposition compacte et moderne."""
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(130, 130)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(2)

        # Bouton Home au-dessus
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        home_btn = QPushButton("🏠 Home")
        home_btn.setFixedHeight(22)
        home_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(45, 48, 55, 200);
                color: #e0e0e0;
                border: 1px solid #444852;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #007acc;
                border-color: #3399ff;
            }
        """)
        home_btn.clicked.connect(lambda: self.view_selected.emit("HOME"))
        top_bar.addWidget(home_btn)
        main_layout.addLayout(top_bar)

        # Grille de sélection des faces du cube
        grid = QGridLayout()
        grid.setSpacing(2)

        btn_style = """
            QPushButton {
                background-color: rgba(50, 54, 62, 220);
                color: #cfd3dc;
                border: 1px solid #3c404a;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
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

        btn_top = QPushButton("TOP")
        btn_top.setFixedHeight(24)
        btn_top.setStyleSheet(btn_style)
        btn_top.clicked.connect(lambda: self.view_selected.emit("TOP"))
        grid.addWidget(btn_top, 0, 1)

        btn_left = QPushButton("LEFT")
        btn_left.setFixedHeight(24)
        btn_left.setStyleSheet(btn_style)
        btn_left.clicked.connect(lambda: self.view_selected.emit("LEFT"))
        grid.addWidget(btn_left, 1, 0)

        btn_front = QPushButton("FRONT")
        btn_front.setFixedHeight(24)
        btn_front.setStyleSheet(btn_style)
        btn_front.clicked.connect(lambda: self.view_selected.emit("FRONT"))
        grid.addWidget(btn_front, 1, 1)

        btn_right = QPushButton("RIGHT")
        btn_right.setFixedHeight(24)
        btn_right.setStyleSheet(btn_style)
        btn_right.clicked.connect(lambda: self.view_selected.emit("RIGHT"))
        grid.addWidget(btn_right, 1, 2)

        btn_bottom = QPushButton("BTM")
        btn_bottom.setFixedHeight(24)
        btn_bottom.setStyleSheet(btn_style)
        btn_bottom.clicked.connect(lambda: self.view_selected.emit("BOTTOM"))
        grid.addWidget(btn_bottom, 2, 1)

        main_layout.addLayout(grid)
