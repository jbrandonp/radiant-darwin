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

class CreateBoxDialog(QDialog):
    """Dialogue de création d'une boîte paramétrique."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Créer une Boîte (Box)")
        self.setFixedSize(300, 240)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.spin_w = QDoubleSpinBox()
        self.spin_w.setRange(0.1, 10000.0)
        self.spin_w.setValue(30.0)
        self.spin_w.setSuffix(" mm")
        form.addRow("Largeur (X) :", self.spin_w)

        self.spin_h = QDoubleSpinBox()
        self.spin_h.setRange(0.1, 10000.0)
        self.spin_h.setValue(20.0)
        self.spin_h.setSuffix(" mm")
        form.addRow("Longueur (Y) :", self.spin_h)

        self.spin_d = QDoubleSpinBox()
        self.spin_d.setRange(0.1, 10000.0)
        self.spin_d.setValue(15.0)
        self.spin_d.setSuffix(" mm")
        form.addRow("Hauteur (Z) :", self.spin_d)

        self.chk_center = QCheckBox("Centrer sur l'origine")
        form.addRow("", self.chk_center)

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
        btn_ok = QPushButton("Créer")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def get_values(self) -> Tuple[float, float, float, bool, BooleanOperation, Optional[str]]:
        op = self.combo_op.currentData()
        target = self.combo_target.currentData() if self.combo_target.count() > 0 else None
        return (self.spin_w.value(), self.spin_h.value(), self.spin_d.value(), self.chk_center.isChecked(), op, target)


class CreateCylinderDialog(QDialog):
    """Dialogue de création d'un cylindre paramétrique."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Créer un Cylindre")
        self.setFixedSize(300, 220)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.spin_rad = QDoubleSpinBox()
        self.spin_rad.setRange(0.1, 5000.0)
        self.spin_rad.setValue(15.0)
        self.spin_rad.setSuffix(" mm")
        form.addRow("Rayon :", self.spin_rad)

        self.spin_h = QDoubleSpinBox()
        self.spin_h.setRange(0.1, 10000.0)
        self.spin_h.setValue(40.0)
        self.spin_h.setSuffix(" mm")
        form.addRow("Hauteur :", self.spin_h)

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
        btn_ok = QPushButton("Créer")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def get_values(self) -> Tuple[float, float, BooleanOperation, Optional[str]]:
        op = self.combo_op.currentData()
        target = self.combo_target.currentData() if self.combo_target.count() > 0 else None
        return (self.spin_rad.value(), self.spin_h.value(), op, target)


class CreateSphereDialog(QDialog):
    """Dialogue de création d'une sphère paramétrique."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Créer une Sphère")
        self.setFixedSize(300, 200)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.spin_rad = QDoubleSpinBox()
        self.spin_rad.setRange(0.1, 5000.0)
        self.spin_rad.setValue(20.0)
        self.spin_rad.setSuffix(" mm")
        form.addRow("Rayon :", self.spin_rad)

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
        btn_ok = QPushButton("Créer")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def get_values(self) -> Tuple[float, BooleanOperation, Optional[str]]:
        op = self.combo_op.currentData()
        target = self.combo_target.currentData() if self.combo_target.count() > 0 else None
        return (self.spin_rad.value(), op, target)


class CreateConeDialog(QDialog):
    """Dialogue de création d'un cône ou tronc de cône paramétrique."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Créer un Cône / Tronc de Cône")
        self.setFixedSize(320, 240)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.spin_r_bot = QDoubleSpinBox()
        self.spin_r_bot.setRange(0.0, 5000.0)
        self.spin_r_bot.setValue(15.0)
        self.spin_r_bot.setSuffix(" mm")
        form.addRow("Rayon Base (R1) :", self.spin_r_bot)

        self.spin_r_top = QDoubleSpinBox()
        self.spin_r_top.setRange(0.0, 5000.0)
        self.spin_r_top.setValue(0.0)
        self.spin_r_top.setSuffix(" mm")
        form.addRow("Rayon Sommet (R2) :", self.spin_r_top)

        self.spin_h = QDoubleSpinBox()
        self.spin_h.setRange(0.1, 5000.0)
        self.spin_h.setValue(30.0)
        self.spin_h.setSuffix(" mm")
        form.addRow("Hauteur :", self.spin_h)

        self.combo_op = QComboBox()
        self.combo_op.addItems(["Nouveau Corps", "Joindre (Union)", "Couper (Différence)", "Intersection"])
        form.addRow("Opération Booléenne :", self.combo_op)

        self.combo_target = QComboBox()
        self.combo_target.addItems(existing_bodies if existing_bodies else ["Aucun corps"])
        form.addRow("Corps Cible :", self.combo_target)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Créer le Cône")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def get_values(self) -> Dict[str, Union[float, int, BooleanOperation, Optional[str]]]:
        """Retourne les paramètres validés pour le cône."""
        ops = [
            BooleanOperation.NEW_BODY,
            BooleanOperation.JOIN,
            BooleanOperation.CUT,
            BooleanOperation.INTERSECT
        ]
        target = self.combo_target.currentText()
        return {
            "radius_bottom": self.spin_r_bot.value(),
            "radius_top": self.spin_r_top.value(),
            "height": self.spin_h.value(),
            "segments": 36,
            "operation": ops[self.combo_op.currentIndex()],
            "target_body_id": None if target == "Aucun corps" else target
        }


class CreateTorusDialog(QDialog):
    """Dialogue de création d'un tore (donut) paramétrique."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Créer un Tore (Torus)")
        self.setFixedSize(320, 220)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.spin_r_maj = QDoubleSpinBox()
        self.spin_r_maj.setRange(0.5, 5000.0)
        self.spin_r_maj.setValue(25.0)
        self.spin_r_maj.setSuffix(" mm")
        form.addRow("Rayon Majeur (R) :", self.spin_r_maj)

        self.spin_r_min = QDoubleSpinBox()
        self.spin_r_min.setRange(0.1, 500.0)
        self.spin_r_min.setValue(6.0)
        self.spin_r_min.setSuffix(" mm")
        form.addRow("Rayon Tube (r) :", self.spin_r_min)

        self.combo_op = QComboBox()
        self.combo_op.addItems(["Nouveau Corps", "Joindre (Union)", "Couper (Différence)", "Intersection"])
        form.addRow("Opération Booléenne :", self.combo_op)

        self.combo_target = QComboBox()
        self.combo_target.addItems(existing_bodies if existing_bodies else ["Aucun corps"])
        form.addRow("Corps Cible :", self.combo_target)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Créer le Tore")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def get_values(self) -> Dict[str, Union[float, int, BooleanOperation, Optional[str]]]:
        """Retourne les paramètres validés pour le tore."""
        ops = [
            BooleanOperation.NEW_BODY,
            BooleanOperation.JOIN,
            BooleanOperation.CUT,
            BooleanOperation.INTERSECT
        ]
        target = self.combo_target.currentText()
        return {
            "major_radius": self.spin_r_maj.value(),
            "minor_radius": self.spin_r_min.value(),
            "segments": 36,
            "operation": ops[self.combo_op.currentIndex()],
            "target_body_id": None if target == "Aucun corps" else target
        }


class CreateWedgeDialog(QDialog):
    """Dialogue de création d'un coin (Wedge) paramétrique FreeCAD."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Créer un Coin (Wedge)")
        self.setFixedSize(320, 290)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.spin_dx = QDoubleSpinBox()
        self.spin_dx.setRange(0.1, 5000.0)
        self.spin_dx.setValue(30.0)
        self.spin_dx.setSuffix(" mm")
        form.addRow("Largeur Base (dx) :", self.spin_dx)

        self.spin_dy = QDoubleSpinBox()
        self.spin_dy.setRange(0.1, 5000.0)
        self.spin_dy.setValue(20.0)
        self.spin_dy.setSuffix(" mm")
        form.addRow("Longueur Base (dy) :", self.spin_dy)

        self.spin_dz = QDoubleSpinBox()
        self.spin_dz.setRange(0.1, 5000.0)
        self.spin_dz.setValue(15.0)
        self.spin_dz.setSuffix(" mm")
        form.addRow("Hauteur (dz) :", self.spin_dz)

        self.spin_dx_top = QDoubleSpinBox()
        self.spin_dx_top.setRange(0.0, 5000.0)
        self.spin_dx_top.setValue(0.0)
        self.spin_dx_top.setSuffix(" mm")
        form.addRow("Largeur Sommet (dx_top) :", self.spin_dx_top)

        self.spin_dy_top = QDoubleSpinBox()
        self.spin_dy_top.setRange(0.0, 5000.0)
        self.spin_dy_top.setValue(20.0)
        self.spin_dy_top.setSuffix(" mm")
        form.addRow("Longueur Sommet (dy_top) :", self.spin_dy_top)

        self.combo_op = QComboBox()
        self.combo_op.addItems(["Nouveau Corps", "Joindre (Union)", "Couper (Différence)", "Intersection"])
        form.addRow("Opération Booléenne :", self.combo_op)

        self.combo_target = QComboBox()
        self.combo_target.addItems(existing_bodies if existing_bodies else ["Aucun corps"])
        form.addRow("Corps Cible :", self.combo_target)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Créer le Coin")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def get_values(self) -> Dict[str, Union[float, BooleanOperation, Optional[str]]]:
        ops = [
            BooleanOperation.NEW_BODY,
            BooleanOperation.JOIN,
            BooleanOperation.CUT,
            BooleanOperation.INTERSECT
        ]
        target = self.combo_target.currentText()
        return {
            "dx": self.spin_dx.value(),
            "dy": self.spin_dy.value(),
            "dz": self.spin_dz.value(),
            "dx_top": self.spin_dx_top.value(),
            "dy_top": self.spin_dy_top.value(),
            "operation": ops[self.combo_op.currentIndex()],
            "target_body_id": None if target == "Aucun corps" else target
        }


class CreatePipeDialog(QDialog):
    """Dialogue de création d'un tuyau 3D (Pipe Feature) paramétrique FreeCAD."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Créer un Tuyau 3D (Pipe)")
        self.setFixedSize(340, 270)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.spin_outer_r = QDoubleSpinBox()
        self.spin_outer_r.setRange(0.2, 500.0)
        self.spin_outer_r.setValue(6.0)
        self.spin_outer_r.setSuffix(" mm")
        form.addRow("Rayon Extérieur :", self.spin_outer_r)

        self.chk_hollow = QCheckBox("Tuyau Creux (Hollow)")
        self.chk_hollow.setChecked(True)
        form.addRow("", self.chk_hollow)

        self.spin_inner_r = QDoubleSpinBox()
        self.spin_inner_r.setRange(0.1, 500.0)
        self.spin_inner_r.setValue(4.0)
        self.spin_inner_r.setSuffix(" mm")
        form.addRow("Rayon Intérieur :", self.spin_inner_r)

        self.combo_path = QComboBox()
        self.combo_path.addItem("Coude en L (0,0,0 -> 0,0,50 -> 40,0,50)", 0)
        self.combo_path.addItem("Double Coude en S (0,0,0 -> 0,0,30 -> 30,0,30 -> 30,40,30)", 1)
        self.combo_path.addItem("Segment Droit (0,0,0 -> 0,0,60)", 2)
        form.addRow("Trajectoire 3D :", self.combo_path)

        self.combo_op = QComboBox()
        self.combo_op.addItems(["Nouveau Corps", "Joindre (Union)", "Couper (Différence)", "Intersection"])
        form.addRow("Opération Booléenne :", self.combo_op)

        self.combo_target = QComboBox()
        self.combo_target.addItems(existing_bodies if existing_bodies else ["Aucun corps"])
        form.addRow("Corps Cible :", self.combo_target)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Créer le Tuyau")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def get_values(self) -> Dict[str, Union[float, List[Tuple[float, float, float]], BooleanOperation, Optional[str], Optional[float]]]:
        ops = [
            BooleanOperation.NEW_BODY,
            BooleanOperation.JOIN,
            BooleanOperation.CUT,
            BooleanOperation.INTERSECT
        ]
        target = self.combo_target.currentText()
        path_idx = int(self.combo_path.currentData())
        if path_idx == 0:
            path_pts: List[Tuple[float, float, float]] = [(0.0, 0.0, 0.0), (0.0, 0.0, 50.0), (40.0, 0.0, 50.0)]
        elif path_idx == 1:
            path_pts = [(0.0, 0.0, 0.0), (0.0, 0.0, 30.0), (30.0, 0.0, 30.0), (30.0, 40.0, 30.0)]
        else:
            path_pts = [(0.0, 0.0, 0.0), (0.0, 0.0, 60.0)]

        inner_rad: Optional[float] = self.spin_inner_r.value() if self.chk_hollow.isChecked() else None
        if inner_rad is not None and inner_rad >= self.spin_outer_r.value():
            inner_rad = None

        return {
            "outer_radius": self.spin_outer_r.value(),
            "inner_radius": inner_rad,
            "path_points": path_pts,
            "operation": ops[self.combo_op.currentIndex()],
            "target_body_id": None if target == "Aucun corps" else target
        }


class FastenerDialog(QDialog):
    """Dialogue de création de quincaillerie et visserie ISO normalisée."""

    def __init__(
        self,
        existing_bodies: Optional[Union[Sequence[str], str]] = None,
        fastener_type: str = "hex_bolt",
        parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Visserie Métrique Normalisée (Fasteners)")
        self.setFixedSize(360, 260)

        resolved_type = fastener_type
        resolved_bodies: List[str] = []
        if isinstance(existing_bodies, str):
            resolved_type = existing_bodies
        elif existing_bodies:
            resolved_bodies = list(existing_bodies)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_type = QComboBox()
        self.combo_type.addItems([
            "Vis Tête Hexagonale (ISO 4017)",
            "Vis CHC / BTR Six Pans (ISO 4762)",
            "Écrou Hexagonal (ISO 4032)",
            "Rondelle Plate (ISO 7089)"
        ])
        type_indices = {
            "hex_bolt": 0,
            "socket_cap": 1,
            "socket_screw": 1,
            "hex_nut": 2,
            "washer": 3
        }
        if resolved_type in type_indices:
            self.combo_type.setCurrentIndex(type_indices[resolved_type])

        form.addRow("Type de Quincaillerie :", self.combo_type)

        self.combo_size = QComboBox()
        self.combo_size.addItems(["M3", "M4", "M5", "M6", "M8", "M10", "M12", "M16", "M20"])
        self.combo_size.setCurrentText("M8")
        form.addRow("Taille Métrique :", self.combo_size)

        self.spin_len = QDoubleSpinBox()
        self.spin_len.setRange(2.0, 500.0)
        self.spin_len.setValue(30.0)
        self.spin_len.setSuffix(" mm")
        form.addRow("Longueur Sous Tête :", self.spin_len)

        self.combo_op = QComboBox()
        self.combo_op.addItems(["Nouveau Corps", "Joindre (Union)", "Couper (Différence)", "Intersection"])
        form.addRow("Opération Booléenne :", self.combo_op)

        self.combo_target = QComboBox()
        self.combo_target.addItems(resolved_bodies if resolved_bodies else ["Aucun corps"])
        form.addRow("Corps Cible :", self.combo_target)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Générer la Pièce")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def get_values(self) -> Dict[str, Union[str, float, BooleanOperation, Optional[str], bool]]:
        """Retourne les paramètres de la quincaillerie."""
        types_map = {0: "hex_bolt", 1: "socket_screw", 2: "hex_nut", 3: "washer"}
        ops = [
            BooleanOperation.NEW_BODY,
            BooleanOperation.JOIN,
            BooleanOperation.CUT,
            BooleanOperation.INTERSECT
        ]
        target = self.combo_target.currentText()
        selected_type = types_map.get(self.combo_type.currentIndex(), "hex_bolt")
        return {
            "fastener_type": selected_type,
            "standard_size": self.combo_size.currentText(),
            "thread_size": self.combo_size.currentText(),
            "length": self.spin_len.value(),
            "operation": ops[self.combo_op.currentIndex()],
            "target_body_id": None if target == "Aucun corps" else target,
            "has_washer": False
        }


