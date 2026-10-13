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
    """
    Inspecteur de paramètres géométriques et propriétés physiques.
    Affiche les dimensions globales, volume et masse du modèle, ou
    permet d'éditer en direct les paramètres de l'opération sélectionnée.
    """

    def __init__(self, document: CADDocument, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.document: CADDocument = document
        self.current_feature: Optional[Feature] = None

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(8)

        self.lbl_title = QLabel("PROPRIÉTÉS DU MODÈLE")
        self.lbl_title.setStyleSheet("color: #00a2ff; font-weight: bold; font-size: 11px; padding: 2px;")
        self.main_layout.addWidget(self.lbl_title)

        self.lbl_info = QLabel("Vue d'ensemble physique du composant 3D :")
        self.lbl_info.setStyleSheet("color: #8c93a0; font-size: 10px; font-style: italic;")
        self.main_layout.addWidget(self.lbl_info)

        # Formulaire des champs
        self.form_widget = QWidget()
        self.form_layout = QFormLayout(self.form_widget)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setSpacing(6)
        self.main_layout.addWidget(self.form_widget)

        # Bouton Supprimer l'opération
        self.btn_delete = QPushButton("🗑️ Supprimer l'opération")
        self.btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #802020;
                color: #ffffff;
                border: 1px solid #aa3333;
                border-radius: 4px;
                padding: 6px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #a02828;
            }
        """)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        self.btn_delete.setVisible(False)
        self.main_layout.addWidget(self.btn_delete)

        self.main_layout.addStretch(1)

        # Écouter les modifications du document pour rafraîchir les propriétés globales
        self.document.register_change_listener(self._on_document_changed)
        self._show_model_overview()

    def _on_document_changed(self) -> None:
        """Rafraîchit l'affichage si aucune opération n'est verrouillée."""
        if self.current_feature is None:
            self._show_model_overview()

    def _show_model_overview(self) -> None:
        """Affiche les métriques physiques réelles du composant complet."""
        self.lbl_title.setText("PROPRIÉTÉS PHYSIQUES (CAO)")
        self.lbl_info.setText("Propriétés géométriques globales du solide :")
        self.btn_delete.setVisible(False)

        while self.form_layout.rowCount() > 0:
            self.form_layout.removeRow(0)

        # Calcul des grandeurs physiques
        total_vol_mm3 = 0.0
        min_all = [1e9, 1e9, 1e9]
        max_all = [-1e9, -1e9, -1e9]
        active_bodies = 0

        for body in self.document.bodies.values():
            if body.is_empty():
                continue
            active_bodies += 1
            total_vol_mm3 += body.volume()
            b_min, b_max = body.bounding_box()
            min_all[0] = min(min_all[0], b_min.x)
            min_all[1] = min(min_all[1], b_min.y)
            min_all[2] = min(min_all[2], b_min.z)
            max_all[0] = max(max_all[0], b_max.x)
            max_all[1] = max(max_all[1], b_max.y)
            max_all[2] = max(max_all[2], b_max.z)

        has_geom = active_bodies > 0 and min_all[0] < 1e8
        dim_x = (max_all[0] - min_all[0]) if has_geom else 0.0
        dim_y = (max_all[1] - min_all[1]) if has_geom else 0.0
        dim_z = (max_all[2] - min_all[2]) if has_geom else 0.0

        vol_cm3 = total_vol_mm3 / 1000.0
        mass_alu_g = vol_cm3 * 2.70
        mass_acier_g = vol_cm3 * 7.85

        def _add_stat(label_text: str, val_text: str) -> None:
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #8c93a0; font-weight: 500; font-size: 11px;")
            val = QLabel(val_text)
            val.setStyleSheet("color: #e0e2e8; font-weight: bold; font-size: 11px;")
            self.form_layout.addRow(lbl, val)

        _add_stat("Corps Solides :", f"{active_bodies}")
        _add_stat("Opérations :", f"{len(self.document.features)}")
        _add_stat("Encombrement :", f"{dim_x:.1f} × {dim_y:.1f} × {dim_z:.1f} mm")
        _add_stat("Volume Net :", f"{vol_cm3:.2f} cm³ ({total_vol_mm3:,.0f} mm³)")
        _add_stat("Masse (Alu 6061) :", f"{mass_alu_g:.1f} g")
        _add_stat("Masse (Acier C45) :", f"{mass_acier_g:.1f} g")

    def set_feature(self, feature_id: str) -> None:
        """Charge une fonctionnalité dans le panneau pour édition."""
        feat = next((f for f in self.document.features if f.feature_id == feature_id), None)
        self.current_feature = feat

        # Vider les anciens champs
        while self.form_layout.rowCount() > 0:
            self.form_layout.removeRow(0)

        if not feat:
            self._show_model_overview()
            return

        self.lbl_title.setText(f"PARAMÈTRES : {feat.name.upper()}")
        self.lbl_info.setText(f"Édition dynamique de l'opération [{feat.feature_id}] :")
        self.lbl_info.setVisible(True)
        self.btn_delete.setVisible(True)

        # Générer dynamiquement les spinboxes pour chaque paramètre
        for param_name, param_val in feat.parameters.items():
            spin = QDoubleSpinBox()
            spin.setRange(0.01, 10000.0)
            spin.setDecimals(2)
            spin.setValue(float(param_val))
            spin.setSuffix(" mm")

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
            self.document.invalidate_cache()
            self.document.rebuild()

    def _on_delete_clicked(self) -> None:
        """Supprime la fonctionnalité actuellement affichée."""
        if self.current_feature:
            f_id = self.current_feature.feature_id
            self.current_feature = None
            self.document.remove_feature(f_id)
            self._show_model_overview()
