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


class ParametersDialog(QDialog):
    """Dialogue de gestion des paramètres et équations globales fx style Fusion 360."""

    def __init__(self, param_table: ParameterTable, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Paramètres Utilisateur (fx)")
        self.resize(520, 360)
        self.param_table = param_table

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Nom", "Expression", "Valeur (mm)", "Commentaire"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # Remplir la table existante
        self._populate_table()

        # Ligne d'ajout de paramètre
        add_box = QHBoxLayout()
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Nom (ex: epaisseur)")
        self.input_expr = QLineEdit()
        self.input_expr.setPlaceholderText("Expression (ex: 2.5 * 2)")
        btn_add = QPushButton("Ajouter fx")
        btn_add.clicked.connect(self._on_add_param)
        add_box.addWidget(self.input_name)
        add_box.addWidget(self.input_expr)
        add_box.addWidget(btn_add)
        layout.addLayout(add_box)

        # Boutons
        btns = QHBoxLayout()
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        btns.addStretch(1)
        btns.addWidget(btn_close)
        layout.addLayout(btns)

    def _populate_table(self) -> None:
        """Remplit le tableau avec les paramètres actuels."""
        self.table.setRowCount(0)
        for name, p in self.param_table.parameters.items():
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(p.name))
            self.table.setItem(r, 1, QTableWidgetItem(p.expression))
            self.table.setItem(r, 2, QTableWidgetItem(f"{p.value:.3f}"))
            self.table.setItem(r, 3, QTableWidgetItem(p.comment))

    def _on_add_param(self) -> None:
        """Ajoute et évalue un nouveau paramètre."""
        name = self.input_name.text().strip()
        expr = self.input_expr.text().strip()
        if name and expr:
            self.param_table.set_parameter(name, expr)
            self._populate_table()
            self.input_name.clear()
            self.input_expr.clear()


class SheetMetalDialog(QDialog):
    """Dialogue de création d'une pièce de tôlerie avec rebord plié."""

    def __init__(self, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tôlerie Industrielle (Sheet Metal)")
        self.setFixedSize(320, 260)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.spin_w = QDoubleSpinBox()
        self.spin_w.setRange(5.0, 5000.0)
        self.spin_w.setValue(60.0)
        self.spin_w.setSuffix(" mm")
        form.addRow("Largeur Tôle :", self.spin_w)

        self.spin_l = QDoubleSpinBox()
        self.spin_l.setRange(5.0, 5000.0)
        self.spin_l.setValue(80.0)
        self.spin_l.setSuffix(" mm")
        form.addRow("Longueur Tôle :", self.spin_l)

        self.spin_t = QDoubleSpinBox()
        self.spin_t.setRange(0.5, 10.0)
        self.spin_t.setValue(2.0)
        self.spin_t.setSuffix(" mm")
        form.addRow("Épaisseur (t) :", self.spin_t)

        self.spin_r = QDoubleSpinBox()
        self.spin_r.setRange(0.5, 10.0)
        self.spin_r.setValue(2.0)
        self.spin_r.setSuffix(" mm")
        form.addRow("Rayon de pliage (R) :", self.spin_r)

        self.spin_flange = QDoubleSpinBox()
        self.spin_flange.setRange(5.0, 500.0)
        self.spin_flange.setValue(25.0)
        self.spin_flange.setSuffix(" mm")
        form.addRow("Hauteur Rebord Plié :", self.spin_flange)

        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_ok = QPushButton("Créer la Tôle")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def get_values(self) -> Tuple[float, float, float, float, float]:
        return (
            self.spin_w.value(),
            self.spin_l.value(),
            self.spin_t.value(),
            self.spin_r.value(),
            self.spin_flange.value()
        )


class RenderDialog(QDialog):
    """Dialogue de rendu photoréaliste PBR (Render Studio) style Fusion 360."""

    def __init__(
        self,
        bodies: Dict[str, Solid],
        parent: Optional[QDialog] = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Atelier de Rendu Photoréaliste (Render Studio)")
        self.resize(720, 560)
        self.bodies = bodies
        self.raytracer = PBRRaytracer()
        self.rendered_image: Optional[QImage] = None

        layout = QVBoxLayout(self)

        # Barre supérieure de configuration
        form = QHBoxLayout()

        form.addWidget(QLabel("Corps à rendre :"))
        self.combo_body = QComboBox()
        for b_id in bodies.keys():
            self.combo_body.addItem(b_id, b_id)
        form.addWidget(self.combo_body)

        form.addWidget(QLabel("Finition PBR :"))
        self.combo_mat = QComboBox()
        for mat_name in PBR_LIBRARY.keys():
            self.combo_mat.addItem(mat_name, mat_name)
        form.addWidget(self.combo_mat)

        form.addWidget(QLabel("Résolution :"))
        self.combo_res = QComboBox()
        self.combo_res.addItem("Aperçu (400x300)", (400, 300))
        self.combo_res.addItem("Standard (640x480)", (640, 480))
        self.combo_res.addItem("HD (1280x720)", (1280, 720))
        form.addWidget(self.combo_res)

        btn_render = QPushButton("Lancer le Rendu")
        btn_render.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; padding: 6px 12px;")
        btn_render.clicked.connect(self._on_start_render)
        form.addWidget(btn_render)

        layout.addLayout(form)

        # Zone d'aperçu de l'image
        self.lbl_preview = QLabel("Cliquez sur 'Lancer le Rendu' pour générer l'image réaliste.")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("""
            QLabel {
                background-color: #1a1c20;
                border: 2px dashed #3a3d45;
                border-radius: 6px;
                color: #8c92a4;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.lbl_preview, 1)

        # Barre inférieure
        bottom_bar = QHBoxLayout()
        self.lbl_info = QLabel("Prêt | Moteur PBR Blinn-Phong & Fresnel Schlick")
        self.lbl_info.setStyleSheet("color: #7a8090; font-size: 11px;")
        bottom_bar.addWidget(self.lbl_info)

        bottom_bar.addStretch(1)

        self.btn_export = QPushButton("Exporter l'Image PNG...")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._on_export_png)
        bottom_bar.addWidget(self.btn_export)

        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_close)

        layout.addLayout(bottom_bar)

        # Lancer un premier rendu si un corps existe
        if bodies:
            self._on_start_render()

    def _on_start_render(self) -> None:
        """Déclenche le calcul du lancer de rayons."""
        body_id = self.combo_body.currentData()
        if not body_id or body_id not in self.bodies:
            return

        mat_name = self.combo_mat.currentData()
        material = PBR_LIBRARY.get(mat_name, list(PBR_LIBRARY.values())[0])
        res_val = self.combo_res.currentData()
        w, h = res_val if isinstance(res_val, tuple) else (400, 300)

        solid = self.bodies[body_id]
        self.lbl_info.setText(f"Calcul du rendu en cours ({w}x{h}, {material.name})...")

        img = self.raytracer.render_solid_to_image(solid, material, width=w, height=h)
        self.rendered_image = img

        pixmap = QPixmap.fromImage(img)
        self.lbl_preview.setPixmap(pixmap.scaled(
            self.lbl_preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))
        self.lbl_info.setText(f"Rendu terminé avec succès ({w}x{h}) | Matériau : {material.name}")
        self.btn_export.setEnabled(True)

    def _on_export_png(self) -> None:
        """Sauvegarde l'image rendue sur disque."""
        if not self.rendered_image:
            return

        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le Rendu Studio", "", "Image PNG (*.png)")
        if path:
            self.rendered_image.save(path, "PNG")
            self.lbl_info.setText(f"Image enregistrée : {path}")


class MeasureDialog(QDialog):
    """Atelier d'Inspection & Métrologie 3D de précision (Measure Workbench)."""

    def __init__(self, bodies: Dict[str, Solid], parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Outil de Mesure 3D & Métrologie")
        self.setFixedSize(480, 460)
        self.bodies = bodies

        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # Onglet 1 : Mesure 3D entre 2 points
        tab_pts = QWidget()
        vbox_pts = QVBoxLayout(tab_pts)

        grp_p1 = QGroupBox("Point 1 (Origine)")
        h_p1 = QHBoxLayout(grp_p1)
        self.sp_p1_x = QDoubleSpinBox()
        self.sp_p1_x.setRange(-10000.0, 10000.0)
        self.sp_p1_y = QDoubleSpinBox()
        self.sp_p1_y.setRange(-10000.0, 10000.0)
        self.sp_p1_z = QDoubleSpinBox()
        self.sp_p1_z.setRange(-10000.0, 10000.0)
        h_p1.addWidget(QLabel("X:"))
        h_p1.addWidget(self.sp_p1_x)
        h_p1.addWidget(QLabel("Y:"))
        h_p1.addWidget(self.sp_p1_y)
        h_p1.addWidget(QLabel("Z:"))
        h_p1.addWidget(self.sp_p1_z)
        vbox_pts.addWidget(grp_p1)

        grp_p2 = QGroupBox("Point 2 (Cible)")
        h_p2 = QHBoxLayout(grp_p2)
        self.sp_p2_x = QDoubleSpinBox()
        self.sp_p2_x.setRange(-10000.0, 10000.0)
        self.sp_p2_x.setValue(20.0)
        self.sp_p2_y = QDoubleSpinBox()
        self.sp_p2_y.setRange(-10000.0, 10000.0)
        self.sp_p2_y.setValue(20.0)
        self.sp_p2_z = QDoubleSpinBox()
        self.sp_p2_z.setRange(-10000.0, 10000.0)
        self.sp_p2_z.setValue(20.0)
        h_p2.addWidget(QLabel("X:"))
        h_p2.addWidget(self.sp_p2_x)
        h_p2.addWidget(QLabel("Y:"))
        h_p2.addWidget(self.sp_p2_y)
        h_p2.addWidget(QLabel("Z:"))
        h_p2.addWidget(self.sp_p2_z)
        vbox_pts.addWidget(grp_p2)

        self.lbl_dist = QLabel("Distance 3D : 0.000 mm")
        self.lbl_dist.setStyleSheet("font-size: 14px; font-weight: bold; color: #00a2ff;")
        self.lbl_deltas = QLabel("ΔX: 0.00 | ΔY: 0.00 | ΔZ: 0.00 mm")
        self.lbl_angle = QLabel("Angle d'élévation : 0.00°")
        self.lbl_midpoint = QLabel("Milieu 3D : (0.00, 0.00, 0.00)")
        vbox_pts.addWidget(self.lbl_dist)
        vbox_pts.addWidget(self.lbl_deltas)
        vbox_pts.addWidget(self.lbl_angle)
        vbox_pts.addWidget(self.lbl_midpoint)
        tabs.addTab(tab_pts, "Distance 3D")

        # Onglet 2 : Jeu et collision entre deux corps
        tab_inter = QWidget()
        vbox_inter = QVBoxLayout(tab_inter)
        form_inter = QFormLayout()

        body_keys = list(self.bodies.keys())
        self.combo_body_a = QComboBox()
        self.combo_body_a.addItems(body_keys if body_keys else ["Aucun corps"])
        form_inter.addRow("Corps A :", self.combo_body_a)

        self.combo_body_b = QComboBox()
        self.combo_body_b.addItems(body_keys if body_keys else ["Aucun corps"])
        if len(body_keys) > 1:
            self.combo_body_b.setCurrentIndex(1)
        form_inter.addRow("Corps B :", self.combo_body_b)
        vbox_inter.addLayout(form_inter)

        self.lbl_clearance = QLabel("Jeu minimal (Clearance) : -- mm")
        self.lbl_clearance.setStyleSheet("font-size: 13px; font-weight: bold; color: #32d74b;")
        self.lbl_collision = QLabel("Collision physique : Aucune")
        self.lbl_collision.setStyleSheet("font-size: 13px; font-weight: bold; color: #ff9f0a;")
        vbox_inter.addWidget(self.lbl_clearance)
        vbox_inter.addWidget(self.lbl_collision)

        btn_calc_inter = QPushButton("Calculer Jeu & Interférence")
        btn_calc_inter.clicked.connect(self._recalc_interference)
        vbox_inter.addWidget(btn_calc_inter)
        tabs.addTab(tab_inter, "Jeu & Collisions")

        # Onglet 3 : Centre de gravité et rapport géométrique
        tab_report = QWidget()
        vbox_rep = QVBoxLayout(tab_report)
        form_rep = QFormLayout()

        self.combo_rep_body = QComboBox()
        self.combo_rep_body.addItems(body_keys if body_keys else ["Aucun corps"])
        form_rep.addRow("Corps Analysé :", self.combo_rep_body)
        vbox_rep.addLayout(form_rep)

        self.lbl_rep_text = QLabel("Sélectionnez un corps pour générer le rapport métrologique.")
        self.lbl_rep_text.setStyleSheet("font-family: monospace; font-size: 11px; background: #26282e; padding: 8px; border-radius: 4px;")
        vbox_rep.addWidget(self.lbl_rep_text)

        btn_rep = QPushButton("Générer le Rapport Métrologique")
        btn_rep.clicked.connect(self._recalc_report)
        vbox_rep.addWidget(btn_rep)
        tabs.addTab(tab_report, "Centre de Gravité")

        layout.addWidget(tabs)

        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

        # Connecter recalcul automatique des points
        for sp in [self.sp_p1_x, self.sp_p1_y, self.sp_p1_z, self.sp_p2_x, self.sp_p2_y, self.sp_p2_z]:
            sp.valueChanged.connect(self._recalc_points)

        self._recalc_points()
        self._recalc_interference()
        self._recalc_report()

    def _recalc_points(self) -> None:
        """Recalcule la distance et les caractéristiques entre P1 et P2."""
        p1 = Vector3D(self.sp_p1_x.value(), self.sp_p1_y.value(), self.sp_p1_z.value())
        p2 = Vector3D(self.sp_p2_x.value(), self.sp_p2_y.value(), self.sp_p2_z.value())
        res = measure_points(p1, p2)
        self.lbl_dist.setText(f"Distance 3D : {res.distance:.3f} mm")
        self.lbl_deltas.setText(f"ΔX: {res.dx:.3f} mm | ΔY: {res.dy:.3f} mm | ΔZ: {res.dz:.3f} mm")
        self.lbl_angle.setText(f"Angle d'élévation : {res.angle_deg:.2f}°")
        self.lbl_midpoint.setText(f"Milieu 3D : ({res.midpoint.x:.2f}, {res.midpoint.y:.2f}, {res.midpoint.z:.2f})")

    def _recalc_interference(self) -> None:
        """Recalcule le jeu minimal et l'éventuelle collision entre corps A et B."""
        kA = self.combo_body_a.currentText()
        kB = self.combo_body_b.currentText()
        if kA not in self.bodies or kB not in self.bodies or kA == kB:
            self.lbl_clearance.setText("Jeu minimal : Sélectionnez 2 corps distincts")
            self.lbl_collision.setText("Collision : N/A")
            return

        solid_a = self.bodies[kA]
        solid_b = self.bodies[kB]
        gap = compute_clearance(solid_a, solid_b)
        has_col, vol_col = compute_interference(solid_a, solid_b)

        if gap == float("inf"):
            self.lbl_clearance.setText("Jeu minimal : Non mesurable")
        else:
            self.lbl_clearance.setText(f"Jeu minimal (Clearance) : {gap:.3f} mm")

        if has_col:
            self.lbl_collision.setText(f"⚠️ Collision DÉTECTÉE ! Volume : {vol_col:.2f} mm³")
            self.lbl_collision.setStyleSheet("font-size: 13px; font-weight: bold; color: #ff453a;")
        else:
            self.lbl_collision.setText("✅ Aucune interférence physique (Pièces dégagées)")
            self.lbl_collision.setStyleSheet("font-size: 13px; font-weight: bold; color: #32d74b;")

    def _recalc_report(self) -> None:
        """Génère le bilan géométrique et barycentrique."""
        k = self.combo_rep_body.currentText()
        if k not in self.bodies:
            self.lbl_rep_text.setText("Aucun corps disponible.")
            return

        solid = self.bodies[k]
        rep = generate_inspection_report(solid)
        com = rep["center_of_mass"]
        com_str = f"({com.x:.2f}, {com.y:.2f}, {com.z:.2f})" if isinstance(com, Vector3D) else str(com)

        txt = (
            f"Nom du solide       : {rep['solid_name']}\n"
            f"Volume total        : {rep['volume_mm3']:.2f} mm³ ({rep['volume_cm3']:.3f} cm³)\n"
            f"Masse (Alu 2.7g/cm³): {rep['mass_grams']:.2f} g ({rep['mass_kg']:.4f} kg)\n"
            f"Surface extérieure  : {rep['surface_area_mm2']:.2f} mm²\n"
            f"Encombrement (AABB) : {rep['box_dx_mm']:.1f} x {rep['box_dy_mm']:.1f} x {rep['box_dz_mm']:.1f} mm\n"
            f"Centre de Gravité   : {com_str}\n"
            f"Genre topologique   : {int(float(rep['genus']))} trou(s)\n"
            f"Facettes / Sommets  : {int(float(rep['faces_count']))} faces / {int(float(rep['vertices_count']))} sommets"
        )
        self.lbl_rep_text.setText(txt)


class MeshAnalysisDialog(QDialog):
    """Atelier d'analyse topologique, diagnostic d'étanchéité et réparation de maillage (Mesh WB)."""

    def __init__(
        self,
        bodies: Dict[str, Solid],
        on_repair_callback: Optional[Callable[[str, Solid], None]] = None,
        parent: Optional[QDialog] = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Atelier de Maillage 3D & Réparation (Mesh Workbench)")
        self.setFixedSize(480, 420)
        self.bodies = bodies
        self.on_repair_callback = on_repair_callback

        layout = QVBoxLayout(self)
        form = QFormLayout()

        body_keys = list(self.bodies.keys())
        self.combo_body = QComboBox()
        self.combo_body.addItems(body_keys if body_keys else ["Aucun corps"])
        self.combo_body.currentIndexChanged.connect(self._update_diagnostic)
        form.addRow("Corps à Auditer :", self.combo_body)
        layout.addLayout(form)

        self.lbl_status = QLabel("Évaluation en cours...")
        self.lbl_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #00a2ff;")
        layout.addWidget(self.lbl_status)

        self.lbl_details = QLabel("")
        self.lbl_details.setStyleSheet("font-family: monospace; font-size: 11px; background: #26282e; padding: 10px; border-radius: 4px;")
        layout.addWidget(self.lbl_details)

        h_actions = QHBoxLayout()
        self.btn_repair = QPushButton("🔧 Réparer Maillage")
        self.btn_repair.clicked.connect(self._on_repair)
        self.btn_simplify = QPushButton("📉 Décimer (-50%)")
        self.btn_simplify.clicked.connect(self._on_simplify)
        self.btn_flip = QPushButton("🔄 Inverser Normales")
        self.btn_flip.clicked.connect(self._on_flip)

        h_actions.addWidget(self.btn_repair)
        h_actions.addWidget(self.btn_simplify)
        h_actions.addWidget(self.btn_flip)
        layout.addLayout(h_actions)

        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

        self._update_diagnostic()

    def _update_diagnostic(self) -> None:
        """Exécute l'audit géométrique et rafraîchit l'affichage."""
        k = self.combo_body.currentText()
        if k not in self.bodies:
            self.lbl_status.setText("Aucun solide sélectionné.")
            self.lbl_details.setText("")
            return

        solid = self.bodies[k]
        diag = diagnose_mesh(solid)

        if diag.is_watertight:
            self.lbl_status.setText("✅ Maillage 2-Manifold CONFORME (Étanche / Watertight)")
            self.lbl_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #32d74b;")
        else:
            self.lbl_status.setText("⚠️ Maillage NON-MANIFOLD (Ouvert / Trous détectés)")
            self.lbl_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #ff453a;")

        txt = (
            f"Sommets / Faces     : {diag.num_vertices} sommets | {diag.num_faces} triangles\n"
            f"Caractéristique     : Euler χ = {diag.euler_number} | Genre g = {diag.genus}\n"
            f"Facettes dégénérées : {diag.degenerate_faces} triangle(s)\n"
            f"Facettes dupliquées : {diag.duplicate_faces} triangle(s)\n"
            f"Sommets orphelins   : {diag.unreferenced_vertices}\n"
            f"Volume exact        : {diag.volume:.2f} mm³\n"
            f"Surface extérieure  : {diag.surface_area:.2f} mm²"
        )
        self.lbl_details.setText(txt)

    def _on_repair(self) -> None:
        """Applique l'algorithme de réparation automatique."""
        k = self.combo_body.currentText()
        if k in self.bodies and self.on_repair_callback:
            repaired = repair_mesh(self.bodies[k])
            self.on_repair_callback(k, repaired)
            self._update_diagnostic()

    def _on_simplify(self) -> None:
        """Simplifie le maillage en divisant par deux le nombre de triangles."""
        k = self.combo_body.currentText()
        if k in self.bodies and self.on_repair_callback:
            decimated = simplify_mesh(self.bodies[k], 0.5)
            self.on_repair_callback(k, decimated)
            self._update_diagnostic()

    def _on_flip(self) -> None:
        """Inverse les normales du maillage."""
        k = self.combo_body.currentText()
        if k in self.bodies and self.on_repair_callback:
            flipped = flip_mesh_normals(self.bodies[k])
            self.on_repair_callback(k, flipped)
            self._update_diagnostic()


class SectionCutDialog(QDialog):
    """Dialogue de coupe dynamique et extraction d'esquisse de section (Part_Section)."""

    def __init__(
        self,
        bodies: Union[Sequence[str], Dict[str, Solid]],
        on_create_sketch_callback: Optional[Callable[[Sketch2D], None]] = None,
        parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Plan de Coupe Dynamique & Extraction 2D (Section)")
        self.setFixedSize(400, 260)
        self.on_create_sketch_callback = on_create_sketch_callback

        if isinstance(bodies, dict):
            self.bodies: Dict[str, Solid] = bodies
            body_keys = list(bodies.keys())
        else:
            self.bodies = {}
            body_keys = list(bodies)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_body = QComboBox()
        self.combo_body.addItems(body_keys if body_keys else ["Aucun corps"])
        form.addRow("Corps Tranché :", self.combo_body)

        self.combo_plane = QComboBox()
        self.combo_plane.addItems(["Plan XY (Axe Z)", "Plan XZ (Axe Y)", "Plan YZ (Axe X)"])
        form.addRow("Plan de Coupe :", self.combo_plane)

        self.spin_offset = QDoubleSpinBox()
        self.spin_offset.setRange(-5000.0, 5000.0)
        self.spin_offset.setValue(0.0)
        self.spin_offset.setSuffix(" mm")
        form.addRow("Décalage (Offset) :", self.spin_offset)

        layout.addLayout(form)

        self.lbl_info = QLabel("Sélectionnez le corps et le plan de coupe.")
        self.lbl_info.setStyleSheet("color: #00a2ff; font-weight: bold;")
        layout.addWidget(self.lbl_info)

        btn_sketch = QPushButton("📐 Créer Esquisse 2D depuis cette Coupe")
        btn_sketch.clicked.connect(self._on_create_sketch)
        layout.addWidget(btn_sketch)

        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def _on_create_sketch(self) -> None:
        """Génère l'esquisse 2D à partir de la coupe courante."""
        k = self.combo_body.currentText()
        if k not in self.bodies:
            self.lbl_info.setText("Aucun solide sélectionné.")
            return

        solid = self.bodies[k]
        axes = ["Z", "Y", "X"]
        axis = axes[self.combo_plane.currentIndex()]
        offset = self.spin_offset.value()

        sk = create_sketch_from_cross_section(
            solid=solid,
            sketch_id=f"sketch_cut_{k}_{int(offset)}",
            name=f"Coupe {axis}={offset}mm",
            axis=axis,
            offset=offset
        )
        if sk and self.on_create_sketch_callback:
            self.on_create_sketch_callback(sk)
            self.lbl_info.setText(f"✅ Esquisse '{sk.name}' créée avec {len(sk.entities)} contours !")
        else:
            self.lbl_info.setText("⚠️ Aucun contour fermé trouvé à cette altitude.")

    def get_values(self) -> Dict[str, Union[str, float, bool]]:
        """Retourne les paramètres de coupe sélectionnés."""
        axes = ["Z", "Y", "X"]
        return {
            "body_id": self.combo_body.currentText(),
            "axis": axes[self.combo_plane.currentIndex()],
            "coordinate": self.spin_offset.value(),
            "offset": self.spin_offset.value(),
            "create_sketch": True
        }

