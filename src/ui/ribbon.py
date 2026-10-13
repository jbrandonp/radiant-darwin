"""
Ruban d'outils supérieur (Ribbon Bar) inspiré d'Autodesk Fusion 360.
Organisé en onglets thématiques : SOLIDE, ESQUISSE, MODIFIER, EXPORT.
"""

from __future__ import annotations
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QTabWidget, QHBoxLayout, QVBoxLayout,
    QToolButton, QLabel, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize


class RibbonButton(QToolButton):
    """Bouton grand format du ruban d'outils avec icône et libellé."""

    def __init__(self, text: str, emoji_icon: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setText(f"{emoji_icon}\n{text}")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setFixedSize(68, 64)
        self.setStyleSheet("""
            QToolButton {
                background-color: #26282e;
                color: #e0e2e8;
                border: 1px solid #363940;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
                text-align: center;
                padding: 4px;
            }
            QToolButton:hover {
                background-color: #32353d;
                border-color: #00a2ff;
                color: #ffffff;
            }
            QToolButton:pressed {
                background-color: #007acc;
            }
        """)


def _create_ribbon_group(title: str, buttons: list[QToolButton]) -> QWidget:
    """Crée une section d'outils encadrée avec son intitulé en bas."""
    group_widget = QWidget()
    vbox = QVBoxLayout(group_widget)
    vbox.setContentsMargins(4, 2, 4, 2)
    vbox.setSpacing(2)

    # Ligne des boutons horizontaux
    btn_row = QHBoxLayout()
    btn_row.setContentsMargins(0, 0, 0, 0)
    btn_row.setSpacing(4)
    for btn in buttons:
        btn_row.addWidget(btn)
    vbox.addLayout(btn_row)

    # Libellé de la section
    lbl = QLabel(title.upper())
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet("color: #7b8190; font-size: 9px; font-weight: bold; letter-spacing: 1px;")
    vbox.addWidget(lbl)

    # Séparateur vertical à droite
    wrapper = QWidget()
    h_wrap = QHBoxLayout(wrapper)
    h_wrap.setContentsMargins(0, 0, 0, 0)
    h_wrap.addWidget(group_widget)

    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setStyleSheet("color: #2f3239;")
    h_wrap.addWidget(sep)

    return wrapper


class CADRibbonBar(QTabWidget):
    """Barre de ruban principale avec onglets de fonctionnalités."""

    # Signaux émis pour les actions CAO
    create_box_requested = Signal()
    create_cylinder_requested = Signal()
    create_sphere_requested = Signal()
    extrude_requested = Signal()
    combine_requested = Signal()

    new_sketch_xy_requested = Signal()
    new_sketch_xz_requested = Signal()
    new_sketch_yz_requested = Signal()
    add_sketch_rect_requested = Signal()
    add_sketch_circle_requested = Signal()

    fit_view_requested = Signal()
    home_view_requested = Signal()

    export_stl_requested = Signal()
    export_obj_requested = Signal()
    export_ply_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(105)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._init_solid_tab()
        self._init_sketch_tab()
        self._init_tools_tab()
        self._init_export_tab()

    def _init_solid_tab(self) -> None:
        """Onglet SOLIDE : Création de primitives, extrusions, booléens."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_box = RibbonButton("Boîte", "📦")
        btn_box.clicked.connect(self.create_box_requested.emit)

        btn_cyl = RibbonButton("Cylindre", "🥫")
        btn_cyl.clicked.connect(self.create_cylinder_requested.emit)

        btn_sph = RibbonButton("Sphère", "🔮")
        btn_sph.clicked.connect(self.create_sphere_requested.emit)

        btn_ext = RibbonButton("Extrusion", "⬆️")
        btn_ext.clicked.connect(self.extrude_requested.emit)

        layout.addWidget(_create_ribbon_group("Créer", [btn_box, btn_cyl, btn_sph, btn_ext]))

        btn_comb = RibbonButton("Combiner", "🔀")
        btn_comb.clicked.connect(self.combine_requested.emit)

        layout.addWidget(_create_ribbon_group("Modifier", [btn_comb]))

        self.addTab(tab, "SOLIDE")

    def _init_sketch_tab(self) -> None:
        """Onglet ESQUISSE : Choix du plan 2D, formes d'esquisse."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_xy = RibbonButton("Plan XY", "📐")
        btn_xy.clicked.connect(self.new_sketch_xy_requested.emit)

        btn_xz = RibbonButton("Plan XZ", "📐")
        btn_xz.clicked.connect(self.new_sketch_xz_requested.emit)

        btn_yz = RibbonButton("Plan YZ", "📐")
        btn_yz.clicked.connect(self.new_sketch_yz_requested.emit)

        layout.addWidget(_create_ribbon_group("Nouveau Plan", [btn_xy, btn_xz, btn_yz]))

        btn_rect = RibbonButton("Rectangle", "▭")
        btn_rect.clicked.connect(self.add_sketch_rect_requested.emit)

        btn_circ = RibbonButton("Cercle", "◯")
        btn_circ.clicked.connect(self.add_sketch_circle_requested.emit)

        layout.addWidget(_create_ribbon_group("Formes 2D", [btn_rect, btn_circ]))

        self.addTab(tab, "ESQUISSE")

    def _init_tools_tab(self) -> None:
        """Onglet OUTILS : Caméra et affichage."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_fit = RibbonButton("Recadrer", "🎯")
        btn_fit.clicked.connect(self.fit_view_requested.emit)

        btn_home = RibbonButton("Vue Home", "🏠")
        btn_home.clicked.connect(self.home_view_requested.emit)

        layout.addWidget(_create_ribbon_group("Caméra", [btn_fit, btn_home]))

        self.addTab(tab, "AFFICHAGE")

    def _init_export_tab(self) -> None:
        """Onglet EXPORT : Formats STL, OBJ, PLY."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_stl = RibbonButton("STL (3D)", "🖨️")
        btn_stl.clicked.connect(self.export_stl_requested.emit)

        btn_obj = RibbonButton("Wavefront", "📄")
        btn_obj.clicked.connect(self.export_obj_requested.emit)

        btn_ply = RibbonButton("Polygon PLY", "📊")
        btn_ply.clicked.connect(self.export_ply_requested.emit)

        layout.addWidget(_create_ribbon_group("Impression & Export", [btn_stl, btn_obj, btn_ply]))

        self.addTab(tab, "EXPORT")
