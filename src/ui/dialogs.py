"""
Boîtes de dialogue modales pour la création de solides et d'opérations CAO.
Permet à l'utilisateur de saisir les dimensions et l'opération booléenne (New Body, Join, Cut).
"""

from __future__ import annotations
from typing import Optional, List, Tuple
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QDoubleSpinBox, QSpinBox, QComboBox, QPushButton, QLabel, QCheckBox
)
from PySide6.QtCore import Qt

from src.core.types import BooleanOperation, PlaneType, Vector3D
from src.materials.material_db import MATERIAL_LIBRARY, PhysicalMaterial
from src.assembly.assembly_manager import JointType


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
    """Dialogue de création de perçage paramétrique."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Perçage (Hole Tool)")
        self.setFixedSize(300, 220)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_target = QComboBox()
        for b_id in existing_bodies:
            self.combo_target.addItem(b_id, b_id)
        form.addRow("Corps Cible :", self.combo_target)

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

        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_ok = QPushButton("Percer")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def get_values(self) -> Tuple[str, float, float, float, float]:
        return (
            self.combo_target.currentData(),
            self.spin_x.value(),
            self.spin_y.value(),
            self.spin_dia.value(),
            self.spin_depth.value()
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


class FEADialog(QDialog):
    """Dialogue de configuration d'étude par éléments finis (FEA)."""

    def __init__(self, existing_bodies: List[str], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Simulation Statique Linéaire (FEA)")
        self.setFixedSize(320, 220)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_target = QComboBox()
        for b_id in existing_bodies:
            self.combo_target.addItem(b_id, b_id)
        form.addRow("Corps analysé :", self.combo_target)

        self.combo_mat = QComboBox()
        for mat_name in MATERIAL_LIBRARY.keys():
            self.combo_mat.addItem(mat_name, mat_name)
        form.addRow("Matériau :", self.combo_mat)

        self.spin_force = QDoubleSpinBox()
        self.spin_force.setRange(1.0, 1000000.0)
        self.spin_force.setValue(1500.0)
        self.spin_force.setSuffix(" N")
        form.addRow("Charge appliquée :", self.spin_force)

        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_ok = QPushButton("Lancer le Calcul FEA")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def get_values(self) -> Tuple[str, str, float]:
        return (self.combo_target.currentData(), self.combo_mat.currentData(), self.spin_force.value())
