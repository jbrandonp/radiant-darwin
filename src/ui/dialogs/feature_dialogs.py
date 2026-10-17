"""
Boîtes de dialogue Qt pour CAD Studio.
"""
from __future__ import annotations
from typing import Optional, List, Tuple, Dict, Union, Callable
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QDoubleSpinBox, QComboBox, QPushButton, QLabel, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QFileDialog,
    QTabWidget, QGroupBox, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage

from src.core.types import BooleanOperation, PlaneType, Vector3D
from src.core.geometry import Solid
from src.core.parameters import ParameterTable
from src.materials.material_db import MATERIAL_LIBRARY, PhysicalMaterial
from src.render.pbr_material import PBR_LIBRARY, PBRMaterial
from src.render.raytracer import PBRRaytracer
from src.core.sketch import Sketch2D
from src.core.inspector import measure_points, compute_clearance, compute_interference, generate_inspection_report
from src.core.mesh_tools import diagnose_mesh, repair_mesh, simplify_mesh, flip_mesh_normals, MeshDiagnostic
from src.core.section_tools import slice_solid_contours, create_sketch_from_cross_section, create_cutaway_solid

class ExtrudeDialog(QDialog):
    """Dialogue d'extrusion d'une esquisse 2D."""

    def __init__(self, sketch_ids: List[str], existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Extrusion (Extrude)")
        self.setFixedSize(320, 220)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_sketch = QComboBox()
        for s_id in sketch_ids:
            self.combo_sketch.addItem(s_id, s_id)
        form.addRow("Profil / Esquisse :", self.combo_sketch)

        self.spin_dist = QDoubleSpinBox()
        self.spin_dist.setRange(0.1, 10000.0)
        self.spin_dist.setValue(25.0)
        self.spin_dist.setSuffix(" mm")
        form.addRow("Distance :", self.spin_dist)

        self.combo_op = QComboBox()
        self.combo_op.addItem("Nouveau Corps (New Body)", BooleanOperation.NEW_BODY)
        if existing_bodies:
            self.combo_op.addItem("Joindre (Join)", BooleanOperation.JOIN)
            self.combo_op.addItem("Couper (Cut)", BooleanOperation.CUT)
            self.combo_op.addItem("Intersection", BooleanOperation.INTERSECT)
        form.addRow("Opération :", self.combo_op)

        self.combo_target = QComboBox()
        for b_id in existing_bodies:
            self.combo_target.addItem(b_id, b_id)
        if existing_bodies:
            form.addRow("Corps Cible :", self.combo_target)

        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_ok = QPushButton("Extruder")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def get_values(self) -> Tuple[str, float, BooleanOperation, Optional[str]]:
        sketch_id = self.combo_sketch.currentData()
        op = self.combo_op.currentData()
        target = self.combo_target.currentData() if self.combo_target.count() > 0 else None
        return (sketch_id, self.spin_dist.value(), op, target)


class RevolveDialog(QDialog):
    """Dialogue de révolution 360° d'un profil d'esquisse."""

    def __init__(self, sketch_ids: List[str], existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Révolution (Revolve)")
        self.setFixedSize(320, 220)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_sketch = QComboBox()
        for s_id in sketch_ids:
            self.combo_sketch.addItem(s_id, s_id)
        form.addRow("Profil / Esquisse :", self.combo_sketch)

        self.spin_angle = QDoubleSpinBox()
        self.spin_angle.setRange(1.0, 360.0)
        self.spin_angle.setValue(360.0)
        self.spin_angle.setSuffix(" °")
        form.addRow("Angle :", self.spin_angle)

        self.combo_op = QComboBox()
        self.combo_op.addItem("Nouveau Corps (New Body)", BooleanOperation.NEW_BODY)
        if existing_bodies:
            self.combo_op.addItem("Joindre (Join)", BooleanOperation.JOIN)
            self.combo_op.addItem("Couper (Cut)", BooleanOperation.CUT)
            self.combo_op.addItem("Intersection", BooleanOperation.INTERSECT)
        form.addRow("Opération :", self.combo_op)

        self.combo_target = QComboBox()
        for b_id in existing_bodies:
            self.combo_target.addItem(b_id, b_id)
        if existing_bodies:
            form.addRow("Corps Cible :", self.combo_target)

        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_ok = QPushButton("Appliquer")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def get_values(self) -> Tuple[str, float, BooleanOperation, Optional[str]]:
        sketch_id = self.combo_sketch.currentData()
        op = self.combo_op.currentData()
        target = self.combo_target.currentData() if self.combo_target.count() > 0 else None
        return (sketch_id, self.spin_angle.value(), op, target)


class HoleDialog(QDialog):
    """Dialogue de création de perçage paramétrique (Simple, Lamage, Fraisage)."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Perçage Avancé (Hole Tool)")
        self.setFixedSize(320, 360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_target = QComboBox()
        for b_id in existing_bodies:
            self.combo_target.addItem(b_id, b_id)
        form.addRow("Corps Cible :", self.combo_target)

        self.combo_type = QComboBox()
        self.combo_type.addItem("Simple", "simple")
        self.combo_type.addItem("Lamage (Counterbore)", "counterbore")
        self.combo_type.addItem("Fraisage (Countersink)", "countersink")
        form.addRow("Type de Perçage :", self.combo_type)

        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-5000.0, 5000.0)
        self.spin_x.setValue(0.0)
        self.spin_x.setSuffix(" mm")
        form.addRow("Position X :", self.spin_x)

        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-5000.0, 5000.0)
        self.spin_y.setValue(0.0)
        self.spin_y.setSuffix(" mm")
        form.addRow("Position Y :", self.spin_y)

        self.spin_dia = QDoubleSpinBox()
        self.spin_dia.setRange(0.5, 1000.0)
        self.spin_dia.setValue(6.0)
        self.spin_dia.setSuffix(" mm")
        form.addRow("Diamètre :", self.spin_dia)

        self.spin_depth = QDoubleSpinBox()
        self.spin_depth.setRange(0.5, 1000.0)
        self.spin_depth.setValue(40.0)
        self.spin_depth.setSuffix(" mm")
        form.addRow("Profondeur :", self.spin_depth)

        # Lamage (Counterbore)
        self.spin_cbore_dia = QDoubleSpinBox()
        self.spin_cbore_dia.setRange(0.5, 1000.0)
        self.spin_cbore_dia.setValue(10.0)
        self.spin_cbore_dia.setSuffix(" mm")
        form.addRow("Ø Lamage :", self.spin_cbore_dia)

        self.spin_cbore_depth = QDoubleSpinBox()
        self.spin_cbore_depth.setRange(0.1, 1000.0)
        self.spin_cbore_depth.setValue(5.0)
        self.spin_cbore_depth.setSuffix(" mm")
        form.addRow("Prof. Lamage :", self.spin_cbore_depth)

        # Fraisage (Countersink)
        self.spin_csink_dia = QDoubleSpinBox()
        self.spin_csink_dia.setRange(0.5, 1000.0)
        self.spin_csink_dia.setValue(12.0)
        self.spin_csink_dia.setSuffix(" mm")
        form.addRow("Ø Fraisage :", self.spin_csink_dia)

        self.spin_csink_angle = QDoubleSpinBox()
        self.spin_csink_angle.setRange(10.0, 180.0)
        self.spin_csink_angle.setValue(90.0)
        self.spin_csink_angle.setSuffix(" °")
        form.addRow("Angle Fraisage :", self.spin_csink_angle)

        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_ok = QPushButton("Percer")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def get_values(self) -> Tuple[str, float, float, float, float, str, float, float, float, float]:
        hole_type = str(self.combo_type.currentData())
        return (
            str(self.combo_target.currentData()),
            self.spin_x.value(),
            self.spin_y.value(),
            self.spin_dia.value(),
            self.spin_depth.value(),
            hole_type,
            self.spin_cbore_dia.value(),
            self.spin_cbore_depth.value(),
            self.spin_csink_dia.value(),
            self.spin_csink_angle.value()
        )


class ShellDialog(QDialog):
    """Dialogue d'évidement volumique (Shell)."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Évidement (Shell)")
        self.setFixedSize(300, 150)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_target = QComboBox()
        for b_id in existing_bodies:
            self.combo_target.addItem(b_id, b_id)
        form.addRow("Corps Cible :", self.combo_target)

        self.spin_thick = QDoubleSpinBox()
        self.spin_thick.setRange(0.2, 50.0)
        self.spin_thick.setValue(2.0)
        self.spin_thick.setSuffix(" mm")
        form.addRow("Épaisseur de paroi :", self.spin_thick)

        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_ok = QPushButton("Évider")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def get_values(self) -> Tuple[str, float]:
        return (self.combo_target.currentData(), self.spin_thick.value())


class CombineDialog(QDialog):
    """Dialogue d'opération booléenne explicite."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Combiner les Corps (Combine)")
        self.setFixedSize(320, 200)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_target = QComboBox()
        for b_id in existing_bodies:
            self.combo_target.addItem(b_id, b_id)
        form.addRow("Corps Cible :", self.combo_target)

        self.combo_tool = QComboBox()
        for b_id in existing_bodies:
            self.combo_tool.addItem(b_id, b_id)
        form.addRow("Corps Outil :", self.combo_tool)

        self.combo_op = QComboBox()
        self.combo_op.addItem("Joindre (Join)", BooleanOperation.JOIN)
        self.combo_op.addItem("Couper (Cut)", BooleanOperation.CUT)
        self.combo_op.addItem("Intersection", BooleanOperation.INTERSECT)
        form.addRow("Opération :", self.combo_op)

        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_ok = QPushButton("Appliquer")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def get_values(self) -> Tuple[str, str, BooleanOperation]:
        return (self.combo_target.currentData(), self.combo_tool.currentData(), self.combo_op.currentData())


class LoftDialog(QDialog):
    """Dialogue de création d'un lissage volumique (Loft) entre deux esquisses."""

    def __init__(self, sketches: List[str], existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Lissage Volumique (Loft)")
        self.setFixedSize(360, 320)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_start = QComboBox()
        self.combo_start.addItems(sketches if sketches else ["Aucune esquisse"])
        form.addRow("Profil de Départ :", self.combo_start)

        self.combo_end = QComboBox()
        self.combo_end.addItems(sketches if sketches else ["Aucune esquisse"])
        form.addRow("Profil d'Arrivée :", self.combo_end)

        self.spin_height = QDoubleSpinBox()
        self.spin_height.setRange(0.1, 5000.0)
        self.spin_height.setValue(30.0)
        self.spin_height.setSuffix(" mm")
        form.addRow("Hauteur de Lissage :", self.spin_height)

        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(0.01, 10.0)
        self.spin_scale.setValue(1.0)
        self.spin_scale.setSingleStep(0.1)
        form.addRow("Échelle Supérieure :", self.spin_scale)

        self.spin_segs = QDoubleSpinBox()
        self.spin_segs.setRange(8.0, 120.0)
        self.spin_segs.setValue(36.0)
        self.spin_segs.setDecimals(0)
        form.addRow("Résolution (Segments) :", self.spin_segs)

        self.combo_op = QComboBox()
        self.combo_op.addItems(["Nouveau Corps", "Joindre (Union)", "Couper (Différence)", "Intersection"])
        form.addRow("Opération Booléenne :", self.combo_op)

        self.combo_target = QComboBox()
        self.combo_target.addItems(existing_bodies if existing_bodies else ["Aucun corps"])
        form.addRow("Corps Cible :", self.combo_target)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Générer le Lissage")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def get_values(self) -> Dict[str, Union[str, float, BooleanOperation, Optional[str]]]:
        """Retourne les paramètres validés pour le Loft."""
        ops = [
            BooleanOperation.NEW_BODY,
            BooleanOperation.JOIN,
            BooleanOperation.CUT,
            BooleanOperation.INTERSECT
        ]
        target = self.combo_target.currentText()
        return {
            "start_sketch_id": self.combo_start.currentText(),
            "end_sketch_id": self.combo_end.currentText(),
            "height_offset": self.spin_height.value(),
            "scale_top": self.spin_scale.value(),
            "num_segments": self.spin_segs.value(),
            "operation": ops[self.combo_op.currentIndex()],
            "target_body_id": None if target == "Aucun corps" else target
        }


class SweepDialog(QDialog):
    """Dialogue de balayage volumique (Sweep) d'un profil le long d'une trajectoire."""

    def __init__(self, sketches: List[str], existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Balayage Volumique (Sweep / Pipe)")
        self.setFixedSize(360, 340)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_profile = QComboBox()
        self.combo_profile.addItems(sketches if sketches else ["Profil Circulaire Défaut"])
        form.addRow("Profil 2D :", self.combo_profile)

        self.combo_traj = QComboBox()
        self.combo_traj.addItems(["Arc de Cercle (90°)", "Hélice / Ressort (Helix)", "Courbe S (Spline)", "Ligne Droite (Linear)"])
        form.addRow("Trajectoire Guide :", self.combo_traj)

        self.spin_radius = QDoubleSpinBox()
        self.spin_radius.setRange(1.0, 5000.0)
        self.spin_radius.setValue(30.0)
        self.spin_radius.setSuffix(" mm")
        form.addRow("Rayon de Courbure :", self.spin_radius)

        self.spin_height = QDoubleSpinBox()
        self.spin_height.setRange(1.0, 5000.0)
        self.spin_height.setValue(40.0)
        self.spin_height.setSuffix(" mm")
        form.addRow("Longueur / Hauteur :", self.spin_height)

        self.spin_turns = QDoubleSpinBox()
        self.spin_turns.setRange(0.25, 50.0)
        self.spin_turns.setValue(1.0)
        self.spin_turns.setSingleStep(0.25)
        form.addRow("Spires (Hélice) :", self.spin_turns)

        self.combo_op = QComboBox()
        self.combo_op.addItems(["Nouveau Corps", "Joindre (Union)", "Couper (Différence)", "Intersection"])
        form.addRow("Opération Booléenne :", self.combo_op)

        self.combo_target = QComboBox()
        self.combo_target.addItems(existing_bodies if existing_bodies else ["Aucun corps"])
        form.addRow("Corps Cible :", self.combo_target)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Exécuter le Balayage")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def get_values(self) -> Dict[str, Union[str, float, BooleanOperation, Optional[str]]]:
        """Retourne les paramètres validés pour le Sweep."""
        ops = [
            BooleanOperation.NEW_BODY,
            BooleanOperation.JOIN,
            BooleanOperation.CUT,
            BooleanOperation.INTERSECT
        ]
        traj_map = {0: "arc", 1: "helix", 2: "s_curve", 3: "linear"}
        target = self.combo_target.currentText()
        return {
            "profile_sketch_id": self.combo_profile.currentText(),
            "trajectory_type": traj_map.get(self.combo_traj.currentIndex(), "arc"),
            "radius": self.spin_radius.value(),
            "height": self.spin_height.value(),
            "turns": self.spin_turns.value(),
            "operation": ops[self.combo_op.currentIndex()],
            "target_body_id": None if target == "Aucun corps" else target
        }


class FilletDialog(QDialog):
    """Dialogue de création d'un congé d'arête (Fillet)."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Congé d'Arête (Fillet)")
        self.setFixedSize(300, 180)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_target = QComboBox()
        self.combo_target.addItems(existing_bodies if existing_bodies else ["Aucun corps"])
        form.addRow("Corps Cible :", self.combo_target)

        self.spin_radius = QDoubleSpinBox()
        self.spin_radius.setRange(0.1, 100.0)
        self.spin_radius.setValue(2.0)
        self.spin_radius.setSuffix(" mm")
        form.addRow("Rayon de Congé (R) :", self.spin_radius)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Appliquer le Congé")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def get_values(self) -> Dict[str, Union[str, float]]:
        """Retourne les paramètres du congé."""
        return {
            "target_body_id": self.combo_target.currentText(),
            "radius": self.spin_radius.value(),
            "segments": 16.0
        }


class ChamferDialog(QDialog):
    """Dialogue de création d'un chanfrein d'arêtes (Chamfer)."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chanfrein d'Arête (Chamfer)")
        self.setFixedSize(320, 200)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_target = QComboBox()
        self.combo_target.addItems(existing_bodies if existing_bodies else ["Aucun corps"])
        form.addRow("Corps Cible :", self.combo_target)

        self.spin_dist = QDoubleSpinBox()
        self.spin_dist.setRange(0.1, 100.0)
        self.spin_dist.setValue(2.0)
        self.spin_dist.setSuffix(" mm")
        form.addRow("Distance de Biseau :", self.spin_dist)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Toutes les arêtes (all)", "Arêtes supérieures (top)", "Arêtes inférieures (bottom)", "Arêtes verticales (vertical)"])
        form.addRow("Sélection d'Arêtes :", self.combo_mode)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Appliquer le Chanfrein")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def get_values(self) -> Dict[str, Union[str, float]]:
        """Retourne les paramètres du chanfrein."""
        modes = ["all", "top", "bottom", "vertical"]
        return {
            "target_body_id": self.combo_target.currentText(),
            "distance": self.spin_dist.value(),
            "edges_mode": modes[self.combo_mode.currentIndex()]
        }


class DraftDialog(QDialog):
    """Dialogue de dépouille de moulage (Draft)."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Dépouille de Moulage (Draft)")
        self.setFixedSize(300, 200)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_target = QComboBox()
        self.combo_target.addItems(existing_bodies if existing_bodies else ["Aucun corps"])
        form.addRow("Corps Cible :", self.combo_target)

        self.spin_angle = QDoubleSpinBox()
        self.spin_angle.setRange(0.5, 30.0)
        self.spin_angle.setValue(3.0)
        self.spin_angle.setSuffix(" °")
        form.addRow("Angle de Dépouille :", self.spin_angle)

        self.combo_axis = QComboBox()
        self.combo_axis.addItems(["Axe Z (Vertical)", "Axe Y (Horizontal)", "Axe X (Transversal)"])
        form.addRow("Direction de Tirage :", self.combo_axis)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Appliquer la Dépouille")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def get_values(self) -> Dict[str, Union[str, float]]:
        """Retourne les paramètres de la dépouille."""
        axes = ["Z", "Y", "X"]
        return {
            "target_body_id": self.combo_target.currentText(),
            "draft_angle": self.spin_angle.value(),
            "pull_axis": axes[self.combo_axis.currentIndex()]
        }


