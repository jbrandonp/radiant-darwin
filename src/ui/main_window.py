"""
Fenêtre principale de CAD Studio (Suite Complète Fusion 360).
Intègre la Conception Solide, l'Esquisse paramétrique avec Solveur 2D,
l'Assemblage, la Simulation Statique FEA, la Fabrication CAM G-Code,
la Mise en Plan Technique 2D ISO et la Persistance de Projets (.cadproj).
"""

from __future__ import annotations
import os
from typing import Optional, List
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QDockWidget,
    QFileDialog, QMessageBox, QStatusBar, QLabel
)
from PySide6.QtCore import Qt

from src.core.document import CADDocument
from src.core.types import BooleanOperation, PlaneType, Point2D, Vector3D
from src.core.sketch import Sketch2D
from src.core.feature import BoxFeature, CylinderFeature, SphereFeature, ExtrudeFeature, BooleanFeature
from src.core.operations_advanced import (
    RevolveFeature, LinearPatternFeature, CircularPatternFeature,
    MirrorFeature, HoleFeature, ShellFeature
)
from src.core.exporter import CADExporter
from src.core.serializer import ProjectSerializer
from src.core.parameters import ParameterTable
from src.solver.constraints_2d import SketchConstraintSolver2D
from src.materials.material_db import MATERIAL_LIBRARY, MaterialCalculator
from src.fea.fea_solver import FEASimulator
from src.cam.cam_engine import CAMEngine, ToolpathOperation
from src.assembly.assembly_manager import AssemblyManager, JointType
from src.drawing.drawing_generator import TechnicalDrawingGenerator, TechnicalSheet
from src.drawing.svg_exporter import SVGDrawingExporter
from src.sheetmetal.sheet_metal import SheetMetalPart, SheetMetalRule, FlatPattern, SheetMetalFeature
from src.sheetmetal.dxf_exporter import DXFExporter
from src.viewport.viewport_widget import CADViewportWidget
from src.viewport.sketch_mode import ViewportSketchController
from src.ui.ribbon import CADRibbonBar
from src.ui.browser_tree import CADBrowserTree
from src.ui.timeline import CADTimeline
from src.ui.properties_panel import CADPropertiesPanel
from src.ui.dialogs import (
    CreateBoxDialog, CreateCylinderDialog, CreateSphereDialog,
    ExtrudeDialog, RevolveDialog, HoleDialog, ShellDialog,
    CombineDialog, FEADialog, ParametersDialog, SheetMetalDialog,
    RenderDialog
)
from src.ui.theme import FUSION_DARK_STYLESHEET


class CADMainWindow(QMainWindow):
    """Fenêtre maîtresse de CAO complète équivalente à Autodesk Fusion 360."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("CAD Studio - Suite CAO / FEA / CAM / Dessin Complète")
        self.resize(1440, 900)
        self.setStyleSheet(FUSION_DARK_STYLESHEET)

        # Modèle de données central
        self.document = CADDocument("Projet Mécanique 1")
        self.param_table = ParameterTable()
        self._init_default_parameters()
        self.cam_engine = CAMEngine()
        self.cam_operations: List[ToolpathOperation] = []
        self.assembly_mgr = AssemblyManager()
        self.drawing_gen = TechnicalDrawingGenerator()
        self.sketch_ctrl = ViewportSketchController()
        self.active_sheet: Optional[TechnicalSheet] = None
        self.active_sheet_metal: Optional[SheetMetalPart] = None
        self.active_flat_pattern: Optional[FlatPattern] = None
        self._feature_seq = 0
        self._sketch_seq = 0

        # Initialisation UI
        self._setup_ui()
        self._connect_signals()

        # Composant initial élégant
        self._create_initial_sample()

    def _init_default_parameters(self) -> None:
        """Initialise les équations et paramètres globaux par défaut."""
        self.param_table.set_parameter("epaisseur_tole", "2.0", "mm", "Épaisseur nominale tôle")
        self.param_table.set_parameter("largeur_base", "60.0", "mm", "Largeur platine de base")
        self.param_table.set_parameter("longueur_base", "80.0", "mm", "Longueur platine de base")
        self.param_table.set_parameter("rayon_pliage", "2.0", "mm", "Rayon intérieur de pliage")
        self.param_table.set_parameter("rebord_hauteur", "25.0", "mm", "Hauteur du rebord plié")

    def _setup_ui(self) -> None:
        """Organise l'agencement des panneaux et widgets."""
        central_container = QWidget()
        central_layout = QVBoxLayout(central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # 1. Ruban multi-ateliers
        self.ribbon = CADRibbonBar()
        central_layout.addWidget(self.ribbon)

        # 2. Viewport 3D
        self.viewport = CADViewportWidget(self.document)
        central_layout.addWidget(self.viewport, 1)

        # 3. Timeline d'historique
        self.timeline = CADTimeline(self.document)
        central_layout.addWidget(self.timeline)

        self.setCentralWidget(central_container)

        # 4. Navigateur gauche
        self.browser_dock = QDockWidget("Navigateur", self)
        self.browser_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.browser = CADBrowserTree(self.document)
        self.browser_dock.setWidget(self.browser)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.browser_dock)

        # 5. Inspecteur droit
        self.props_dock = QDockWidget("Paramètres", self)
        self.props_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.props_panel = CADPropertiesPanel(self.document)
        self.props_dock.setWidget(self.props_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.props_dock)

        # Barre d'état
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Prêt | Moteur Manifold3D | Solveur 2D | FEA Linéaire | Moteur CAM G-Code | Mise en Plan ISO")
        self.status_bar.addWidget(self.status_label)

    def _connect_signals(self) -> None:
        """Connecte tous les boutons du ruban et de la timeline."""
        # Fichier
        self.ribbon.save_project_requested.connect(self._on_save_project)
        self.ribbon.load_project_requested.connect(self._on_load_project)
        self.ribbon.manage_parameters_requested.connect(self._on_action_manage_parameters)

        # Solide
        self.ribbon.create_box_requested.connect(self._on_action_create_box)
        self.ribbon.create_cylinder_requested.connect(self._on_action_create_cylinder)
        self.ribbon.create_sphere_requested.connect(self._on_action_create_sphere)
        self.ribbon.extrude_requested.connect(self._on_action_extrude)
        self.ribbon.revolve_requested.connect(self._on_action_revolve)
        self.ribbon.hole_requested.connect(self._on_action_hole)
        self.ribbon.shell_requested.connect(self._on_action_shell)
        self.ribbon.pattern_requested.connect(self._on_action_pattern)
        self.ribbon.combine_requested.connect(self._on_action_combine)

        # Esquisse
        self.ribbon.new_sketch_xy_requested.connect(lambda: self._create_sketch(PlaneType.XY))
        self.ribbon.new_sketch_xz_requested.connect(lambda: self._create_sketch(PlaneType.XZ))
        self.ribbon.new_sketch_yz_requested.connect(lambda: self._create_sketch(PlaneType.YZ))
        self.ribbon.add_sketch_rect_requested.connect(self._add_rect_to_active_sketch)
        self.ribbon.add_sketch_circle_requested.connect(self._add_circle_to_active_sketch)
        self.ribbon.solve_constraints_requested.connect(self._on_action_solve_constraints)
        self.ribbon.toggle_sketch_mode_requested.connect(self._on_toggle_sketch_mode)

        # Tôlerie Industrielle
        self.ribbon.create_sheet_metal_requested.connect(self._on_action_create_sheet_metal)
        self.ribbon.flat_pattern_requested.connect(self._on_action_flat_pattern)
        self.ribbon.export_dxf_laser_requested.connect(self._on_action_export_dxf_laser)

        # Assemblage
        self.ribbon.add_joint_requested.connect(self._on_action_add_joint)
        self.ribbon.check_interference_requested.connect(self._on_action_check_interference)

        # Simulation
        self.ribbon.material_selector_requested.connect(self._on_action_material_info)
        self.ribbon.run_fea_requested.connect(self._on_action_run_fea)

        # Rendu Photoréaliste PBR
        self.ribbon.open_render_studio_requested.connect(self._on_action_open_render_studio)

        # CAM
        self.ribbon.cam_facing_requested.connect(self._on_action_cam_facing)
        self.ribbon.cam_contour_requested.connect(self._on_action_cam_contour)
        self.ribbon.export_gcode_requested.connect(self._on_export_gcode)

        # Dessin 2D
        self.ribbon.generate_drawing_requested.connect(self._on_generate_drawing)
        self.ribbon.export_drawing_svg_requested.connect(self._on_export_drawing_svg)

        # Affichage
        self.ribbon.fit_view_requested.connect(self.viewport.fit_view)
        self.ribbon.home_view_requested.connect(lambda: self.viewport.camera.set_preset_view("HOME"))

        # Export 3D
        self.ribbon.export_stl_requested.connect(self._on_export_stl)
        self.ribbon.export_obj_requested.connect(self._on_export_obj)
        self.ribbon.export_ply_requested.connect(self._on_export_ply)

        # Sélection
        self.timeline.feature_selected.connect(self.props_panel.set_feature)
        self.browser.body_selected.connect(self._on_body_selected)
        self.browser.sketch_selected.connect(self._on_sketch_selected)

    def _create_initial_sample(self) -> None:
        """Génère un exemple initial : Platine usinée avec alésage central."""
        self._feature_seq += 1
        box_feat = BoxFeature(
            feature_id=f"feat_{self._feature_seq}",
            name="Platine Support",
            width=60.0,
            height=40.0,
            depth=12.0,
            center=True,
            operation=BooleanOperation.NEW_BODY
        )
        self.document.add_feature(box_feat)

        self._feature_seq += 1
        hole_feat = HoleFeature(
            feature_id=f"feat_{self._feature_seq}",
            name="Alésage Central Ø16mm",
            target_body_id=box_feat.body_id,
            pos_x=0.0,
            pos_y=0.0,
            diameter=16.0,
            depth=30.0
        )
        self.document.add_feature(hole_feat)

    # --- Persistance Projet ---
    def _on_save_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Sauvegarder le Projet CAO", "", "Projet CAD Studio (*.cadproj *.json)")
        if path:
            ok = ProjectSerializer.save_project(self.document, path)
            if ok:
                QMessageBox.information(self, "Sauvegarde", f"Projet sauvegardé avec succès :\n{path}")

    def _on_load_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un Projet CAO", "", "Projet CAD Studio (*.cadproj *.json)")
        if path:
            new_doc = ProjectSerializer.load_project(path)
            if new_doc:
                self.document = new_doc
                self.viewport.document = new_doc
                self.timeline.document = new_doc
                self.browser.document = new_doc
                self.props_panel.document = new_doc
                self.document.register_change_listener(self.viewport.on_document_changed)
                self.document.register_change_listener(self.timeline.refresh)
                self.document.register_change_listener(self.browser.refresh)
                self.viewport.on_document_changed()
                self.timeline.refresh()
                self.browser.refresh()
                QMessageBox.information(self, "Projet Ouvert", f"Projet chargé avec succès :\n{new_doc.name} ({len(new_doc.features)} opérations)")

    # --- Paramètres Utilisateur fx ---
    def _on_action_manage_parameters(self) -> None:
        """Ouvre la boîte de dialogue de gestion des paramètres et formules globales."""
        dlg = ParametersDialog(self.param_table, self)
        dlg.exec()
        self.status_bar.showMessage("Table des paramètres fx mise à jour", 3000)

    # --- Tôlerie Industrielle (Sheet Metal) ---
    def _on_action_create_sheet_metal(self) -> None:
        """Crée une pièce de tôlerie avec rebord plié et l'ajoute à la timeline."""
        dlg = SheetMetalDialog(self)
        if dlg.exec():
            w, l, t, r, flange = dlg.get_values()
            self._feature_seq += 1
            feat = SheetMetalFeature(
                feature_id=f"feat_{self._feature_seq}",
                name=f"Tôlerie {self._feature_seq}",
                base_width=w,
                base_length=l,
                thickness=t,
                bend_radius=r,
                flange_length=flange,
                k_factor=0.44
            )
            self.document.add_feature(feat)
            self.active_sheet_metal = feat.get_sheet_metal_part()
            self.active_flat_pattern = self.active_sheet_metal.generate_flat_pattern()
            self.status_bar.showMessage(f"Pièce de tôlerie créée : {w}x{l} mm (t={t} mm)", 4000)
            QMessageBox.information(
                self, "Tôlerie Créée",
                f"Pièce de tôlerie générée avec succès !\n"
                f"• Base : {w:.1f} x {l:.1f} mm\n"
                f"• Épaisseur : {t:.1f} mm, Rayon : {r:.1f} mm\n"
                f"• Rebord : {flange:.1f} mm (90°)\n"
                f"• Facteur K : 0.44 (Acier standard)"
            )

    def _on_action_flat_pattern(self) -> None:
        """Calcule et affiche les dimensions du flan de tôle déplié à plat."""
        if not self.active_sheet_metal:
            for feat in self.document.features:
                if isinstance(feat, SheetMetalFeature):
                    self.active_sheet_metal = feat.get_sheet_metal_part()
                    break

        if not self.active_sheet_metal:
            QMessageBox.information(self, "Mise à Plat", "Veuillez d'abord créer une pièce de tôlerie.")
            return

        self.active_flat_pattern = self.active_sheet_metal.generate_flat_pattern()
        fp = self.active_flat_pattern
        bend = self.active_sheet_metal.bends[0] if self.active_sheet_metal.bends else None
        bd_str = f"{bend.bend_deduction_mm:.2f} mm" if bend else "0.0 mm"
        ba_str = f"{bend.bend_allowance_mm:.2f} mm" if bend else "0.0 mm"

        QMessageBox.information(
            self, "Flan Déplié à Plat (Flat Pattern)",
            f"Calcul du déplié terminé selon la fibre neutre (K-Factor = {self.active_sheet_metal.rule.k_factor}) :\n\n"
            f"• Longueur développée totale : {fp.total_length_mm:.2f} mm\n"
            f"• Largeur du flan : {fp.total_width_mm:.2f} mm\n"
            f"• Épaisseur : {fp.thickness_mm:.2f} mm\n"
            f"• Déduction de pliage (BD) : {bd_str}\n"
            f"• Développement du pli (BA) : {ba_str}\n"
            f"• Nombre d'axes de pliage : {len(fp.bend_centerlines)}\n\n"
            f"Prêt pour découpe laser CNC (Format DXF) !"
        )

    def _on_action_export_dxf_laser(self) -> None:
        """Exporte le flan déplié en fichier AutoCAD DXF (calques CUT et BEND)."""
        if not self.active_flat_pattern:
            self._on_action_flat_pattern()
        if not self.active_flat_pattern:
            return

        path, _ = QFileDialog.getSaveFileName(self, "Exporter le Patron Déplié Laser", "", "AutoCAD DXF (*.dxf)")
        if path:
            DXFExporter.export_flat_pattern_dxf(self.active_flat_pattern, path)
            QMessageBox.information(
                self, "Exportation Laser DXF",
                f"Fichier DXF généré avec succès :\n{path}\n\n"
                f"• Calque 'CUT' : Découpe laser extérieure\n"
                f"• Calque 'BEND' : Axes de pliage pour plieuse CNC"
            )

    # --- Mode Esquisse Interactif ---
    def _on_toggle_sketch_mode(self) -> None:
        if self.sketch_ctrl.state.is_active:
            self.sketch_ctrl.finish_sketch()
            self.status_bar.showMessage("Mode esquisse interactif désactivé", 3000)
            QMessageBox.information(self, "Mode Esquisse", "Mode esquisse interactif terminé.")
        else:
            self.sketch_ctrl.start_sketch(PlaneType.XY)
            self.viewport.camera.set_preset_view("TOP")
            self.viewport.update()
            self.status_bar.showMessage("Mode esquisse actif : Cliquez dans le viewport pour tracer", 5000)
            QMessageBox.information(self, "Mode Esquisse", "Mode esquisse actif (Vue de dessus verrouillée).\nAccrochage sur grille activé.")

    # --- Mise en Plan 2D ISO ---
    def _on_generate_drawing(self) -> None:
        bodies = list(self.document.bodies.values())
        if not bodies:
            QMessageBox.information(self, "Mise en Plan", "Aucun corps existant à projeter.")
            return

        sheet = self.drawing_gen.generate_sheet(
            solid=bodies[0],
            title=self.document.name,
            author="Brandon",
            material_name="Aluminium 6061-T6"
        )
        self.active_sheet = sheet
        QMessageBox.information(
            self, "Mise en Plan 2D (ISO 128)",
            f"Planche technique générée avec succès !\n"
            f"• Format : A3 Paysage ({sheet.width_mm} x {sheet.height_mm} mm)\n"
            f"• 4 Projections : Face, Dessus, Droite, Isométrique 3D\n"
            f"• Cotations : Largeur, Hauteur, Profondeur\n"
            f"• Cartouche : Échelle {sheet.title_block.scale}, Norme ISO 128"
        )

    def _on_export_drawing_svg(self) -> None:
        if not self.active_sheet:
            self._on_generate_drawing()
        if not self.active_sheet:
            return

        path, _ = QFileDialog.getSaveFileName(self, "Exporter la Planche Technique en SVG", "", "Vecteur SVG (*.svg)")
        if path:
            SVGDrawingExporter.export_svg(self.active_sheet, path)
            QMessageBox.information(self, "Exportation SVG", f"Plan technique vectoriel exporté :\n{path}")

    # --- Actions Solide ---
    def _on_action_create_box(self) -> None:
        bodies = self.document.get_active_body_ids()
        dlg = CreateBoxDialog(bodies, self)
        if dlg.exec():
            w, h, d, center, op, target = dlg.get_values()
            self._feature_seq += 1
            feat = BoxFeature(f"feat_{self._feature_seq}", f"Boîte {self._feature_seq}", w, h, d, center, op, target)
            self.document.add_feature(feat)

    def _on_action_create_cylinder(self) -> None:
        bodies = self.document.get_active_body_ids()
        dlg = CreateCylinderDialog(bodies, self)
        if dlg.exec():
            rad, h, op, target = dlg.get_values()
            self._feature_seq += 1
            feat = CylinderFeature(f"feat_{self._feature_seq}", f"Cylindre {self._feature_seq}", rad, h, 36, op, target)
            self.document.add_feature(feat)

    def _on_action_create_sphere(self) -> None:
        bodies = self.document.get_active_body_ids()
        dlg = CreateSphereDialog(bodies, self)
        if dlg.exec():
            rad, op, target = dlg.get_values()
            self._feature_seq += 1
            feat = SphereFeature(f"feat_{self._feature_seq}", f"Sphère {self._feature_seq}", rad, 36, op, target)
            self.document.add_feature(feat)

    def _on_action_extrude(self) -> None:
        if not self.document.sketches:
            QMessageBox.information(self, "Extrusion", "Créez d'abord une esquisse 2D.")
            return
        sketch_ids = list(self.document.sketches.keys())
        bodies = self.document.get_active_body_ids()
        dlg = ExtrudeDialog(sketch_ids, bodies, self)
        if dlg.exec():
            s_id, dist, op, target = dlg.get_values()
            self._feature_seq += 1
            feat = ExtrudeFeature(f"feat_{self._feature_seq}", f"Extrusion {self._feature_seq}", s_id, dist, op, target)
            self.document.add_feature(feat)

    def _on_action_revolve(self) -> None:
        if not self.document.sketches:
            QMessageBox.information(self, "Révolution", "Créez d'abord une esquisse 2D.")
            return
        sketch_ids = list(self.document.sketches.keys())
        bodies = self.document.get_active_body_ids()
        dlg = RevolveDialog(sketch_ids, bodies, self)
        if dlg.exec():
            s_id, angle, op, target = dlg.get_values()
            self._feature_seq += 1
            feat = RevolveFeature(f"feat_{self._feature_seq}", f"Révolution {self._feature_seq}", s_id, angle, 48, op, target)
            self.document.add_feature(feat)

    def _on_action_hole(self) -> None:
        bodies = self.document.get_active_body_ids()
        if not bodies:
            QMessageBox.information(self, "Perçage", "Aucun corps existant à percer.")
            return
        dlg = HoleDialog(bodies, self)
        if dlg.exec():
            target, px, py, dia, dep = dlg.get_values()
            self._feature_seq += 1
            feat = HoleFeature(f"feat_{self._feature_seq}", f"Perçage Ø{dia}mm", target, px, py, dia, dep)
            self.document.add_feature(feat)

    def _on_action_shell(self) -> None:
        bodies = self.document.get_active_body_ids()
        if not bodies:
            QMessageBox.information(self, "Évidement", "Aucun corps existant à évider.")
            return
        dlg = ShellDialog(bodies, self)
        if dlg.exec():
            target, thick = dlg.get_values()
            self._feature_seq += 1
            feat = ShellFeature(f"feat_{self._feature_seq}", f"Évidement {thick}mm", target, thick)
            self.document.add_feature(feat)

    def _on_action_pattern(self) -> None:
        bodies = self.document.get_active_body_ids()
        if not bodies:
            return
        self._feature_seq += 1
        feat = LinearPatternFeature(f"feat_{self._feature_seq}", f"Répétition {self._feature_seq}", bodies[0], count_x=2, spacing_x=50.0)
        self.document.add_feature(feat)
        self.status_bar.showMessage("Répétition linéaire appliquée", 3000)

    def _on_action_combine(self) -> None:
        bodies = self.document.get_active_body_ids()
        if len(bodies) < 2:
            QMessageBox.information(self, "Combiner", "Il faut au moins 2 corps solides pour combiner.")
            return
        dlg = CombineDialog(bodies, self)
        if dlg.exec():
            target, tool, op = dlg.get_values()
            self._feature_seq += 1
            feat = BooleanFeature(f"feat_{self._feature_seq}", f"Combiner {self._feature_seq}", target, tool, op)
            self.document.add_feature(feat)

    # --- Actions Esquisse & Solveur ---
    def _create_sketch(self, plane: PlaneType) -> None:
        self._sketch_seq += 1
        s_id = f"sketch_{self._sketch_seq}"
        sketch = Sketch2D(s_id, f"Esquisse {self._sketch_seq}", plane=plane)
        sketch.add_rectangle(Point2D(-20.0, -15.0), 40.0, 30.0)
        self.document.add_sketch(sketch)

    def _add_rect_to_active_sketch(self) -> None:
        if not self.document.sketches:
            self._create_sketch(PlaneType.XY)
            return
        last_sketch = list(self.document.sketches.values())[-1]
        last_sketch.add_rectangle(Point2D(-10.0, -10.0), 20.0, 20.0)
        self.document.rebuild()

    def _add_circle_to_active_sketch(self) -> None:
        if not self.document.sketches:
            self._create_sketch(PlaneType.XY)
            return
        last_sketch = list(self.document.sketches.values())[-1]
        last_sketch.add_circle(Point2D(0.0, 0.0), 10.0)
        self.document.rebuild()

    def _on_action_solve_constraints(self) -> None:
        solver = SketchConstraintSolver2D()
        p0 = solver.add_point(Point2D(0.0, 0.0))
        p1 = solver.add_point(Point2D(25.0, 2.0))
        p2 = solver.add_point(Point2D(24.0, 18.0))

        solver.add_fixed(p0, 0.0, 0.0)
        solver.add_horizontal(p0, p1)
        solver.add_vertical(p1, p2)
        solver.add_distance(p0, p1, 50.0)
        solver.add_distance(p1, p2, 30.0)

        success, solved_pts = solver.solve()
        if success:
            self._sketch_seq += 1
            s_id = f"sketch_{self._sketch_seq}"
            sketch = Sketch2D(s_id, "Esquisse Contrainte 2D", plane=PlaneType.XY)
            sketch.add_polygon(solved_pts)
            self.document.add_sketch(sketch)
            QMessageBox.information(self, "Solveur 2D", f"Solveur géométrique convergent !\nPoints calculés :\n{solved_pts}")

    # --- Actions Assemblage & Collisions ---
    def _on_action_add_joint(self) -> None:
        bodies = self.document.get_active_body_ids()
        if len(bodies) < 2:
            QMessageBox.information(self, "Liaison", "Il faut au moins 2 corps pour créer une liaison.")
            return
        joint = self.assembly_mgr.add_joint("j1", "Pivot Principal", JointType.REVOLUTE, bodies[0], bodies[1])
        QMessageBox.information(self, "Assemblage", f"Liaison créée avec succès :\n{joint.name} ({joint.joint_type.value}) reliant {bodies[0]} et {bodies[1]}")

    def _on_action_check_interference(self) -> None:
        bodies = list(self.document.bodies.items())
        if len(bodies) < 2:
            QMessageBox.information(self, "Interférences", "Il faut au moins 2 corps pour vérifier les collisions.")
            return
        res = AssemblyManager.check_interference(bodies[0][1], bodies[1][1], bodies[0][0], bodies[1][0])
        if res.has_collision:
            QMessageBox.warning(self, "Collision Détectée !", f"Interférence physique entre {res.body_a_id} et {res.body_b_id} !\nVolume de chevauchement : {res.overlap_volume_mm3:.2f} mm³")
        else:
            QMessageBox.information(self, "Aucune Collision", f"Aucune interférence entre {res.body_a_id} et {res.body_b_id}.\nLes pièces respectent les tolérances de jeu.")

    # --- Actions Simulation FEA & Matériaux ---
    def _on_action_material_info(self) -> None:
        bodies = self.document.bodies
        if not bodies:
            return
        first_body = list(bodies.values())[0]
        mat = MATERIAL_LIBRARY["Acier Inoxydable 304"]
        mass_g = MaterialCalculator.calculate_mass_grams(first_body.volume(), mat)
        com = MaterialCalculator.calculate_center_of_mass(first_body)
        QMessageBox.information(
            self, "Propriétés Physiques",
            f"Matériau : {mat.name} ({mat.category})\n"
            f"Densité : {mat.density_g_cm3} g/cm³\n"
            f"Module d'Young : {mat.young_modulus_gpa} GPa\n"
            f"Limite d'élasticité : {mat.yield_strength_mpa} MPa\n"
            f"----------------------------------------\n"
            f"Volume : {first_body.volume():.1f} mm³\n"
            f"Masse calculée : {mass_g:.2f} g ({mass_g/1000:.3f} kg)\n"
            f"Centre de gravité : X={com.x:.1f}, Y={com.y:.1f}, Z={com.z:.1f}"
        )

    def _on_action_run_fea(self) -> None:
        bodies = self.document.get_active_body_ids()
        if not bodies:
            QMessageBox.information(self, "Simulation", "Aucun corps existant à simuler.")
            return

        dlg = FEADialog(bodies, self)
        if dlg.exec():
            b_id, mat_name, force = dlg.get_values()
            mat = MATERIAL_LIBRARY.get(mat_name, MATERIAL_LIBRARY["Acier Carbone C45"])
            sim = FEASimulator(mat)
            solid = self.document.bodies[b_id]
            res = sim.run_static_analysis(solid, applied_force_newtons=force)

            if res:
                heat_buf = sim.generate_stress_heatmap_mesh(solid, res)
                self.viewport.cached_buffers = [heat_buf]
                self.viewport.update()

                status = "✅ Résistance assurée" if res.is_safe else "⚠️ Risque de déformation plastique"
                QMessageBox.information(
                    self, "Résultats de l'Analyse FEA",
                    f"Résultats Statiques Linéaires (von Mises) :\n\n"
                    f"• Charge appliquée : {force:.1f} N\n"
                    f"• Contrainte maximale : {res.max_stress_mpa:.2f} MPa\n"
                    f"• Limite élastique : {mat.yield_strength_mpa:.1f} MPa\n"
                    f"• Déplacement maximal : {res.max_displacement_mm * 1000.0:.2f} µm\n"
                    f"• Facteur de sécurité : {res.safety_factor:.2f}\n\n"
                    f"Verdict : {status}\n\n(Le gradient de contraintes est affiché dans le Viewport 3D)"
                )

    # --- Atelier Rendu Photoréaliste PBR (Render Studio) ---
    def _on_action_open_render_studio(self) -> None:
        """Ouvre le studio de rendu photoréaliste PBR."""
        if not self.document.bodies:
            QMessageBox.information(self, "Rendu Studio", "Aucun corps existant à rendre.")
            return
        dlg = RenderDialog(self.document.bodies, self)
        dlg.exec()

    # --- Actions CAM & G-Code ---
    def _on_action_cam_facing(self) -> None:
        bodies = list(self.document.bodies.values())
        if not bodies:
            return
        b_min, b_max = bodies[0].bounding_box()
        op = self.cam_engine.generate_facing_toolpath(b_min.x, b_max.x, b_min.y, b_max.y, b_max.z + 2.0, b_max.z)
        self.cam_operations.append(op)
        QMessageBox.information(self, "FAO / CAM", f"Opération générée : {op.name}\nNombre de points : {len(op.points)}")

    def _on_action_cam_contour(self) -> None:
        bodies = list(self.document.bodies.values())
        if not bodies:
            return
        op = self.cam_engine.generate_contour_toolpath(bodies[0], depth_mm=10.0)
        self.cam_operations.append(op)
        QMessageBox.information(self, "FAO / CAM", f"Opération générée : {op.name}\nNombre de points : {len(op.points)}")

    def _on_export_gcode(self) -> None:
        if not self.cam_operations:
            self._on_action_cam_contour()

        path, _ = QFileDialog.getSaveFileName(self, "Exporter le programme G-Code CNC", "", "G-Code CNC (*.gcode *.nc)")
        if path:
            self.cam_engine.export_gcode(self.cam_operations, path)
            QMessageBox.information(self, "Exportation G-Code", f"Fichier G-Code machine généré avec succès :\n{path}")

    # --- Export 3D ---
    def _on_export_stl(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en STL", "", "Fichiers STL (*.stl)")
        if path:
            ok = CADExporter.export_stl(self.document.bodies, path, binary=True)
            if ok:
                QMessageBox.information(self, "Exportation", f"Modèle exporté avec succès :\n{path}")

    def _on_export_obj(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en OBJ", "", "Fichiers OBJ (*.obj)")
        if path:
            ok = CADExporter.export_obj(self.document.bodies, path)
            if ok:
                QMessageBox.information(self, "Exportation", f"Modèle exporté avec succès :\n{path}")

    def _on_export_ply(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en PLY", "", "Fichiers PLY (*.ply)")
        if path:
            ok = CADExporter.export_ply(self.document.bodies, path)
            if ok:
                QMessageBox.information(self, "Exportation", f"Modèle exporté avec succès :\n{path}")

    def _on_body_selected(self, body_id: str) -> None:
        """Affiche les informations d'un corps solide sélectionné dans le navigateur."""
        if body_id in self.document.bodies:
            body = self.document.bodies[body_id]
            self.status_bar.showMessage(f"Corps sélectionné : {body.name} (Volume: {body.volume():.1f} mm³)", 3000)

    def _on_sketch_selected(self, sketch_id: str) -> None:
        """Affiche les informations d'une esquisse sélectionnée dans le navigateur."""
        if sketch_id in self.document.sketches:
            sketch = self.document.sketches[sketch_id]
            ent_count = len(sketch.entities)
            self.status_bar.showMessage(
                f"Esquisse sélectionnée : {sketch.name} [Plan: {sketch.plane.value}] ({ent_count} entités)",
                3000
            )
