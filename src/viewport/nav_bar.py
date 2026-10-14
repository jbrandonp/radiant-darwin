"""
Barre de navigation flottante inférieure du Viewport 3D (style Autodesk Fusion 360).
Positionnée au centre bas du viewport pour contrôler rapidement les modes de caméra,
l'affichage de la grille, des arêtes et les captures d'écran.
"""

from __future__ import annotations
from typing import Optional
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QFrame
from PySide6.QtCore import Qt, Signal


class ViewportNavBar(QWidget):
    """
    Barre de navigation compacte et translucide superposée au bas du viewport 3D.
    Fournit un accès rapide aux outils essentiels de navigation CAO.
    """

    orbit_requested = Signal()
    pan_requested = Signal()
    zoom_fit_requested = Signal()
    toggle_grid_requested = Signal()
    toggle_edges_requested = Signal()
    snapshot_requested = Signal()
    toggle_shading_requested = Signal()
    toggle_snap_requested = Signal()
    toggle_gizmo_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialise la barre de navigation avec style translucide sombre."""
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(4)

        btn_style = """
            QPushButton {
                background-color: rgba(36, 39, 46, 210);
                color: #d8dbe2;
                border: 1px solid rgba(68, 72, 82, 180);
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #007acc;
                border-color: #3399ff;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #005999;
            }
            QPushButton:checked {
                background-color: #094771;
                border-color: #00a2ff;
                color: #ffffff;
            }
        """

        self.btn_orbit = QPushButton("🔄 Orbite")
        self.btn_orbit.setStyleSheet(btn_style)
        self.btn_orbit.setToolTip("Vue Initiale / Orbite Isométrique (H)")
        self.btn_orbit.clicked.connect(self.orbit_requested.emit)
        layout.addWidget(self.btn_orbit)

        self.btn_pan = QPushButton("✋ Pan")
        self.btn_pan.setStyleSheet(btn_style)
        self.btn_pan.setToolTip("Panoramique (Shift + Clic Molette)")
        self.btn_pan.clicked.connect(self.pan_requested.emit)
        layout.addWidget(self.btn_pan)

        self.btn_fit = QPushButton("🎯 Recadrer")
        self.btn_fit.setStyleSheet(btn_style)
        self.btn_fit.setToolTip("Recadrer sur l'ensemble du modèle (F)")
        self.btn_fit.clicked.connect(self.zoom_fit_requested.emit)
        layout.addWidget(self.btn_fit)

        # Séparateur subtil
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: rgba(70, 75, 85, 180);")
        layout.addWidget(sep1)

        self.btn_grid = QPushButton("📐 Grille")
        self.btn_grid.setStyleSheet(btn_style)
        self.btn_grid.setCheckable(True)
        self.btn_grid.setChecked(True)
        self.btn_grid.setToolTip("Afficher / Masquer la grille de référence au sol")
        self.btn_grid.clicked.connect(self.toggle_grid_requested.emit)
        layout.addWidget(self.btn_grid)

        self.btn_edges = QPushButton("◼️ Arêtes")
        self.btn_edges.setStyleSheet(btn_style)
        self.btn_edges.setCheckable(True)
        self.btn_edges.setChecked(True)
        self.btn_edges.setToolTip("Afficher / Masquer les arêtes contrastées du solide")
        self.btn_edges.clicked.connect(self.toggle_edges_requested.emit)
        layout.addWidget(self.btn_edges)

        self.btn_shading = QPushButton("🎨 Shading")
        self.btn_shading.setStyleSheet(btn_style)
        self.btn_shading.setToolTip("Basculer le style de rendu (CAO, Clay, Red Wax, Chrome, Zébrures, Dépouille)")
        self.btn_shading.clicked.connect(self.toggle_shading_requested.emit)
        layout.addWidget(self.btn_shading)

        self.btn_magnetic_snap = QPushButton("🧲 Snap")
        self.btn_magnetic_snap.setStyleSheet(btn_style)
        self.btn_magnetic_snap.setCheckable(True)
        self.btn_magnetic_snap.setChecked(True)
        self.btn_magnetic_snap.setToolTip("Activer / Désactiver l'accrochage magnétique intelligent (Blender Snap)")
        self.btn_magnetic_snap.clicked.connect(self.toggle_snap_requested.emit)
        layout.addWidget(self.btn_magnetic_snap)

        self.btn_gizmo = QPushButton("🧭 Gizmo")
        self.btn_gizmo.setStyleSheet(btn_style)
        self.btn_gizmo.setCheckable(True)
        self.btn_gizmo.setChecked(True)
        self.btn_gizmo.setToolTip("Afficher / Masquer le manipulateur 3D interactif")
        self.btn_gizmo.clicked.connect(self.toggle_gizmo_requested.emit)
        layout.addWidget(self.btn_gizmo)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: rgba(70, 75, 85, 180);")
        layout.addWidget(sep2)

        self.btn_snap = QPushButton("📷 Capture")
        self.btn_snap.setStyleSheet(btn_style)
        self.btn_snap.setToolTip("Capturer une image haute résolution de la vue 3D")
        self.btn_snap.clicked.connect(self.snapshot_requested.emit)
        layout.addWidget(self.btn_snap)

        self.adjustSize()
