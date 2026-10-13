"""
Fenêtre principale de l'application de CAO (CAD Studio).
Intègre le ruban d'outils supérieur, le navigateur gauche, le viewport 3D central,
l'inspecteur de propriétés droit et la timeline historique en bas.
"""

from __future__ import annotations
import os
from typing import Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QDockWidget,
    QFileDialog, QMessageBox, QStatusBar, QLabel
)
from PySide6.QtCore import Qt

from src.core.document import CADDocument
from src.core.types import BooleanOperation, PlaneType, Point2D
from src.core.sketch import Sketch2D
from src.core.feature import BoxFeature, CylinderFeature, SphereFeature, ExtrudeFeature, BooleanFeature
from src.core.exporter import CADExporter
from src.viewport.viewport_widget import CADViewportWidget
from src.ui.ribbon import CADRibbonBar
from src.ui.browser_tree import CADBrowserTree
from src.ui.timeline import CADTimeline
from src.ui.properties_panel import CADPropertiesPanel
from src.ui.dialogs import (
    CreateBoxDialog, CreateCylinderDialog, CreateSphereDialog,
    ExtrudeDialog, CombineDialog
)
from src.ui.theme import FUSION_DARK_STYLESHEET


class CADMainWindow(QMainWindow):
    """Fenêtre maîtresse de CAO inspirée d'Autodesk Fusion 360."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("CAD Studio - Conception Paramétrique 3D")
        self.resize(1380, 850)
        self.setStyleSheet(FUSION_DARK_STYLESHEET)

        # Modèle de données central
        self.document = CADDocument("Pièce 1")
        self._feature_seq = 0
        self._sketch_seq = 0

        # Initialisation des composants UI
        self._setup_ui()
        self._connect_signals()

        # Création d'un premier exemple de démarrage élégant (Boîte paramétrique)
        self._create_initial_sample()

    def _setup_ui(self) -> None:
        """Organise l'agencement des panneaux et widgets."""
        central_container = QWidget()
        central_layout = QVBoxLayout(central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # 1. Ruban d'outils en haut
        self.ribbon = CADRibbonBar()
        central_layout.addWidget(self.ribbon)

        # 2. Viewport 3D au centre
        self.viewport = CADViewportWidget(self.document)
        central_layout.addWidget(self.viewport, 1)

        # 3. Timeline d'historique en bas
        self.timeline = CADTimeline(self.document)
        central_layout.addWidget(self.timeline)

        self.setCentralWidget(central_container)

        # 4. Panneau Dock gauche : Navigateur de modèle (Browser)
        self.browser_dock = QDockWidget("Navigateur", self)
        self.browser_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.browser = CADBrowserTree(self.document)
        self.browser_dock.setWidget(self.browser)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.browser_dock)

        # 5. Panneau Dock droit : Inspecteur des propriétés
        self.props_dock = QDockWidget("Paramètres", self)
        self.props_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.props_panel = CADPropertiesPanel(self.document)
        self.props_dock.setWidget(self.props_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.props_dock)

        # Barre d'état inférieure
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Prêt | Moteur Manifold3D actif | Rendu OpenGL matériel")
        self.status_bar.addWidget(self.status_label)

    def _connect_signals(self) -> None:
        """Interconnecte les signaux du ruban, de la timeline et des panneaux."""
        # Ruban Solide
        self.ribbon.create_box_requested.connect(self._on_action_create_box)
        self.ribbon.create_cylinder_requested.connect(self._on_action_create_cylinder)
        self.ribbon.create_sphere_requested.connect(self._on_action_create_sphere)
        self.ribbon.extrude_requested.connect(self._on_action_extrude)
        self.ribbon.combine_requested.connect(self._on_action_combine)

        # Ruban Esquisse
        self.ribbon.new_sketch_xy_requested.connect(lambda: self._create_sketch(PlaneType.XY))
        self.ribbon.new_sketch_xz_requested.connect(lambda: self._create_sketch(PlaneType.XZ))
        self.ribbon.new_sketch_yz_requested.connect(lambda: self._create_sketch(PlaneType.YZ))
        self.ribbon.add_sketch_rect_requested.connect(self._add_rect_to_active_sketch)
        self.ribbon.add_sketch_circle_requested.connect(self._add_circle_to_active_sketch)

        # Ruban Affichage
        self.ribbon.fit_view_requested.connect(self.viewport.fit_view)
        self.ribbon.home_view_requested.connect(lambda: self.viewport.camera.set_preset_view("HOME"))

        # Ruban Export
        self.ribbon.export_stl_requested.connect(self._on_export_stl)
        self.ribbon.export_obj_requested.connect(self._on_export_obj)
        self.ribbon.export_ply_requested.connect(self._on_export_ply)

        # Timeline & Browser vers Properties
        self.timeline.feature_selected.connect(self.props_panel.set_feature)
        self.browser.body_selected.connect(self._on_body_selected)

    def _create_initial_sample(self) -> None:
        """Génère un composant de démonstration initial (Platine mécanique avec cylindre)."""
        self._feature_seq += 1
        box_feat = BoxFeature(
            feature_id=f"feat_{self._feature_seq}",
            name="Platine Base",
            width=50.0,
            height=30.0,
            depth=8.0,
            center=True,
            operation=BooleanOperation.NEW_BODY
        )
        self.document.add_feature(box_feat)

        self._feature_seq += 1
        cyl_feat = CylinderFeature(
            feature_id=f"feat_{self._feature_seq}",
            name="Arbre Cylindrique",
            radius=8.0,
            height=25.0,
            operation=BooleanOperation.JOIN,
            target_body_id=box_feat.body_id
        )
        self.document.add_feature(cyl_feat)

    def _on_action_create_box(self) -> None:
        """Ouvre le dialogue de création de boîte et l'ajoute au document."""
        bodies = self.document.get_active_body_ids()
        dlg = CreateBoxDialog(bodies, self)
        if dlg.exec():
            w, h, d, center, op, target = dlg.get_values()
            self._feature_seq += 1
            feat = BoxFeature(
                feature_id=f"feat_{self._feature_seq}",
                name=f"Boîte {self._feature_seq}",
                width=w, height=h, depth=d,
                center=center,
                operation=op,
                target_body_id=target
            )
            self.document.add_feature(feat)
            self.status_bar.showMessage(f"Boîte créée : {w}x{h}x{d} mm", 3000)

    def _on_action_create_cylinder(self) -> None:
        """Ouvre le dialogue de création de cylindre et l'ajoute au document."""
        bodies = self.document.get_active_body_ids()
        dlg = CreateCylinderDialog(bodies, self)
        if dlg.exec():
            rad, h, op, target = dlg.get_values()
            self._feature_seq += 1
            feat = CylinderFeature(
                feature_id=f"feat_{self._feature_seq}",
                name=f"Cylindre {self._feature_seq}",
                radius=rad, height=h,
                operation=op,
                target_body_id=target
            )
            self.document.add_feature(feat)
            self.status_bar.showMessage(f"Cylindre créé : R={rad}mm H={h}mm", 3000)

    def _on_action_create_sphere(self) -> None:
        """Ouvre le dialogue de création de sphère et l'ajoute au document."""
        bodies = self.document.get_active_body_ids()
        dlg = CreateSphereDialog(bodies, self)
        if dlg.exec():
            rad, op, target = dlg.get_values()
            self._feature_seq += 1
            feat = SphereFeature(
                feature_id=f"feat_{self._feature_seq}",
                name=f"Sphère {self._feature_seq}",
                radius=rad,
                operation=op,
                target_body_id=target
            )
            self.document.add_feature(feat)
            self.status_bar.showMessage(f"Sphère créée : R={rad}mm", 3000)

    def _create_sketch(self, plane: PlaneType) -> None:
        """Crée une nouvelle esquisse sur le plan choisi."""
        self._sketch_seq += 1
        s_id = f"sketch_{self._sketch_seq}"
        sketch = Sketch2D(s_id, f"Esquisse {self._sketch_seq}", plane=plane)
        # Profil rectangle par défaut
        sketch.add_rectangle(Point2D(-15.0, -10.0), 30.0, 20.0)
        self.document.add_sketch(sketch)
        self.status_bar.showMessage(f"Esquisse {sketch.name} créée sur le plan {plane.value}", 4000)

    def _add_rect_to_active_sketch(self) -> None:
        """Ajoute un contour rectangle dans la dernière esquisse existante."""
        if not self.document.sketches:
            self._create_sketch(PlaneType.XY)
            return
        last_sketch = list(self.document.sketches.values())[-1]
        last_sketch.add_rectangle(Point2D(-20.0, -15.0), 40.0, 30.0)
        self.document.rebuild()
        self.status_bar.showMessage(f"Rectangle ajouté dans {last_sketch.name}", 3000)

    def _add_circle_to_active_sketch(self) -> None:
        """Ajoute un contour cercle dans la dernière esquisse existante."""
        if not self.document.sketches:
            self._create_sketch(PlaneType.XY)
            return
        last_sketch = list(self.document.sketches.values())[-1]
        last_sketch.add_circle(Point2D(0.0, 0.0), 12.0)
        self.document.rebuild()
        self.status_bar.showMessage(f"Cercle ajouté dans {last_sketch.name}", 3000)

    def _on_action_extrude(self) -> None:
        """Ouvre le dialogue d'extrusion."""
        if not self.document.sketches:
            QMessageBox.information(self, "Extrusion", "Veuillez d'abord créer une esquisse 2D.")
            return

        sketch_ids = list(self.document.sketches.keys())
        bodies = self.document.get_active_body_ids()
        dlg = ExtrudeDialog(sketch_ids, bodies, self)
        if dlg.exec():
            s_id, dist, op, target = dlg.get_values()
            self._feature_seq += 1
            feat = ExtrudeFeature(
                feature_id=f"feat_{self._feature_seq}",
                name=f"Extrusion {self._feature_seq}",
                sketch_id=s_id,
                distance=dist,
                operation=op,
                target_body_id=target
            )
            self.document.add_feature(feat)
            self.status_bar.showMessage(f"Extrusion réalisée sur {dist} mm", 3000)

    def _on_action_combine(self) -> None:
        """Ouvre le dialogue pour fusionner ou couper deux corps."""
        bodies = self.document.get_active_body_ids()
        if len(bodies) < 2:
            QMessageBox.information(self, "Combiner", "Il faut au moins 2 corps solides pour combiner.")
            return

        dlg = CombineDialog(bodies, self)
        if dlg.exec():
            target, tool, op = dlg.get_values()
            if target == tool:
                QMessageBox.warning(self, "Erreur", "Le corps cible et l'outil doivent être différents.")
                return
            self._feature_seq += 1
            feat = BooleanFeature(
                feature_id=f"feat_{self._feature_seq}",
                name=f"Combiner {self._feature_seq}",
                target_body_id=target,
                tool_body_id=tool,
                operation=op
            )
            self.document.add_feature(feat)
            self.status_bar.showMessage("Opération booléenne appliquée", 3000)

    def _on_body_selected(self, body_id: str) -> None:
        """Sélectionne le corps dans l'arborescence."""
        if body_id in self.document.bodies:
            body = self.document.bodies[body_id]
            self.status_bar.showMessage(f"Corps sélectionné : {body.name} (Volume: {body.volume():.1f} mm³)", 3000)

    def _on_export_stl(self) -> None:
        """Boîte de dialogue pour exporter vers un fichier STL."""
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en STL", "", "Fichiers STL (*.stl)")
        if path:
            ok = CADExporter.export_stl(self.document.bodies, path, binary=True)
            if ok:
                QMessageBox.information(self, "Exportation", f"Modèle exporté avec succès :\n{path}")
            else:
                QMessageBox.warning(self, "Erreur", "Impossible d'exporter le fichier STL.")

    def _on_export_obj(self) -> None:
        """Boîte de dialogue pour exporter vers un fichier Wavefront OBJ."""
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en OBJ", "", "Fichiers OBJ (*.obj)")
        if path:
            ok = CADExporter.export_obj(self.document.bodies, path)
            if ok:
                QMessageBox.information(self, "Exportation", f"Modèle exporté avec succès :\n{path}")
            else:
                QMessageBox.warning(self, "Erreur", "Impossible d'exporter le fichier OBJ.")

    def _on_export_ply(self) -> None:
        """Boîte de dialogue pour exporter vers un fichier PLY."""
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en PLY", "", "Fichiers PLY (*.ply)")
        if path:
            ok = CADExporter.export_ply(self.document.bodies, path)
            if ok:
                QMessageBox.information(self, "Exportation", f"Modèle exporté avec succès :\n{path}")
            else:
                QMessageBox.warning(self, "Erreur", "Impossible d'exporter le fichier PLY.")
