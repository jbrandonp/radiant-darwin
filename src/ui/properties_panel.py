"""
Panneau des propriétés et paramètres (Inspector Panel) situé à droite.
Permet d'éditer en direct les dimensions (largeur, hauteur, rayon, etc.)
de la fonctionnalité actuellement sélectionnée.
"""

from __future__ import annotations
from typing import Optional, Dict, Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QDoubleSpinBox,
    QPushButton, QFrame, QMessageBox
)
from PySide6.QtCore import Qt

from src.core.document import CADDocument
from src.core.feature import Feature


class CADPropertiesPanel(QWidget):
    """Inspecteur de paramètres géométriques."""

    def __init__(self, document: CADDocument, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.document: CADDocument = document
        self.current_feature: Optional[Feature] = None

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(8)

        self.lbl_title = QLabel("PROPRIÉTÉS")
        self.lbl_title.setStyleSheet("color: #8c93a0; font-weight: bold; font-size: 10px; padding: 2px;")
        self.main_layout.addWidget(self.lbl_title)

        self.lbl_info = QLabel("Sélectionnez une opération pour afficher ses paramètres.")
        self.lbl_info.setStyleSheet("color: #656c7a; font-style: italic;")
        self.main_layout.addWidget(self.lbl_info)

        # Formulaire des champs de paramètres
        self.form_widget = QWidget()
        self.form_layout = QFormLayout(self.form_widget)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setSpacing(6)
        self.main_layout.addWidget(self.form_widget)

        # Bouton Supprimer
        self.btn_delete = QPushButton("🗑️ Supprimer l'opération")
        self.btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #802020;
                color: #ffffff;
                border: 1px solid #aa3333;
                border-radius: 4px;
                padding: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #a02828;
            }
        """)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        self.btn_delete.setVisible(False)
        self.main_layout.addWidget(self.btn_delete)

        self.main_layout.addStretch(1)

    def set_feature(self, feature_id: str) -> None:
        """Charge une fonctionnalité dans le panneau pour édition."""
        feat = next((f for f in self.document.features if f.feature_id == feature_id), None)
        self.current_feature = feat

        # Vider les anciens champs
        while self.form_layout.rowCount() > 0:
            self.form_layout.removeRow(0)

        if not feat:
            self.lbl_info.setText("Aucune opération sélectionnée.")
            self.lbl_info.setVisible(True)
            self.btn_delete.setVisible(False)
            return

        self.lbl_info.setVisible(False)
        self.btn_delete.setVisible(True)

        # Générer dynamiquement les spinboxes pour chaque paramètre
        for param_name, param_val in feat.parameters.items():
            spin = QDoubleSpinBox()
            spin.setRange(0.01, 10000.0)
            spin.setDecimals(2)
            spin.setValue(float(param_val))
            spin.setSuffix(" mm")

            # Connexion au changement
            def _make_handler(p_name: str) -> Callable[[float], None]:
                return lambda val: self._on_param_changed(p_name, val)

            spin.valueChanged.connect(_make_handler(param_name))

            label = QLabel(param_name.capitalize())
            label.setStyleSheet("color: #c0c4cc; font-weight: 500;")
            self.form_layout.addRow(label, spin)

    def _on_param_changed(self, param_name: str, new_val: float) -> None:
        """Met à jour le paramètre et recalcule le modèle 3D."""
        if self.current_feature:
            self.current_feature.set_parameter(param_name, new_val)
            self.document.rebuild()

    def _on_delete_clicked(self) -> None:
        """Supprime la fonctionnalité actuellement affichée."""
        if self.current_feature:
            f_id = self.current_feature.feature_id
            self.current_feature = None
            self.set_feature("")
            self.document.remove_feature(f_id)
