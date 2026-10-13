"""
Boîtes de dialogue modales pour la création de solides et d'opérations CAO.
Permet à l'utilisateur de saisir les dimensions et l'opération booléenne (New Body, Join, Cut).
"""

from __future__ import annotations
from typing import Optional, List, Tuple
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QDoubleSpinBox, QComboBox, QPushButton, QLabel, QCheckBox
)
from PySide6.QtCore import Qt

from src.core.types import BooleanOperation, PlaneType


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

        # Boutons OK / Annuler
        btns = QHBoxLayout()
        btn_ok = QPushButton("Créer")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def get_values(self) -> Tuple[float, float, float, bool, BooleanOperation, Optional[str]]:
        """Retourne (width, height, depth, center, operation, target_body)."""
        op = self.combo_op.currentData()
        target = self.combo_target.currentData() if self.combo_target.count() > 0 else None
        return (
            self.spin_w.value(),
            self.spin_h.value(),
            self.spin_d.value(),
            self.chk_center.isChecked(),
            op,
            target
        )


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


class CombineDialog(QDialog):
    """Dialogue d'opération booléenne explicite (Combine) entre deux corps."""

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
        return (
            self.combo_target.currentData(),
            self.combo_tool.currentData(),
            self.combo_op.currentData()
        )
