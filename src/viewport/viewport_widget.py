"""
Widget principal du Viewport 3D basé sur QOpenGLWidget.
Gère l'affichage de la scène, la capture des événements souris (orbite, zoom, pan)
et l'intégration du ViewCube.
"""

from __future__ import annotations
from typing import Optional, List, Callable
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QMouseEvent, QWheelEvent, QKeyEvent, QSurfaceFormat

from src.core.document import CADDocument
from src.core.types import MeshBuffer, Vector3D
from src.viewport.camera import CADCamera
from src.viewport.gl_renderer import GLRenderer
from src.viewport.view_cube import ViewCubeOverlay
from src.viewport.nav_bar import ViewportNavBar
from src.viewport.ray_picking import RayPicker, PickResult, PickedEntityType


class CADViewportWidget(QOpenGLWidget):
    """
    Fenêtre de visualisation 3D interactive pour la conception mécanique.
    Supporte les raccourcis et gestes de navigation de Fusion 360 :
    - Clic Molette (ou Clic Droit) + Déplacement : Orbite 3D
    - Shift + Clic Molette + Déplacement : Panoramique (Pan)
    - Molette de défilement : Zoom avant / arrière
    """

    def __init__(self, document: CADDocument, parent: Optional[QOpenGLWidget] = None) -> None:
        """Initialise le widget avec le document actif et le contexte OpenGL."""
        super().__init__(parent)
        self.document: CADDocument = document
        self.camera: CADCamera = CADCamera()
        self.renderer: GLRenderer = GLRenderer()
        self.cached_buffers: List[MeshBuffer] = []
        self.selected_pick: Optional[PickResult] = None
        self._pick_listeners: List[Callable[[PickResult], None]] = []

        self._last_mouse_pos: QPoint = QPoint()
        self._is_orbiting: bool = False
        self._is_panning: bool = False

        # Configurer le format de surface (anti-aliasing 4x)
        fmt = QSurfaceFormat()
        fmt.setSamples(4)
        fmt.setDepthBufferSize(24)
        self.setFormat(fmt)

        # Widget ViewCube superposé (en haut à droite)
        self.view_cube: ViewCubeOverlay = ViewCubeOverlay(self)
        self.view_cube.view_selected.connect(self._on_viewcube_selected)

        # Barre de navigation flottante au bas du viewport (style Fusion 360)
        self.nav_bar: ViewportNavBar = ViewportNavBar(self)
        self.nav_bar.orbit_requested.connect(self._on_nav_orbit)
        self.nav_bar.pan_requested.connect(self._on_nav_pan)
        self.nav_bar.zoom_fit_requested.connect(self.fit_view)
        self.nav_bar.toggle_grid_requested.connect(self._toggle_grid)
        self.nav_bar.toggle_edges_requested.connect(self._toggle_edges)
        self.nav_bar.snapshot_requested.connect(self._take_snapshot)

        # Écouter les modifications du modèle pour redessiner
        self.document.register_change_listener(self.on_document_changed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def initializeGL(self) -> None:
        """Appelé une fois par Qt lors de l'initialisation du contexte OpenGL."""
        self.renderer.initialize_gl()
        self.on_document_changed()

    def resizeGL(self, w: int, h: int) -> None:
        """Appelé lors du redimensionnement de la fenêtre."""
        self.renderer.resize_gl(w, h, self.camera)
        # Positionner le ViewCube dans le coin supérieur droit
        self.view_cube.move(w - self.view_cube.width() - 15, 15)
        # Centrer la barre de navigation au bas du viewport
        nav_x = max(10, (w - self.nav_bar.width()) // 2)
        nav_y = max(10, h - self.nav_bar.height() - 12)
        self.nav_bar.move(nav_x, nav_y)

    def _on_nav_orbit(self) -> None:
        """Réinitialise la vue en vue isométrique Fusion 360."""
        self.camera.set_preset_view("HOME")
        self.update()

    def _on_nav_pan(self) -> None:
        """Recentre légèrement la caméra."""
        self.camera.target = Vector3D(0.0, 0.0, 0.0)
        self.update()

    def _toggle_grid(self) -> None:
        """Bascule l'affichage de la grille de référence au sol."""
        self.renderer.show_grid = not self.renderer.show_grid
        self.nav_bar.btn_grid.setChecked(self.renderer.show_grid)
        self.update()

    def _toggle_edges(self) -> None:
        """Bascule l'affichage des arêtes contrastées du modèle."""
        self.renderer.show_edges = not self.renderer.show_edges
        self.nav_bar.btn_edges.setChecked(self.renderer.show_edges)
        self.update()

    def _take_snapshot(self) -> None:
        """Capture la vue 3D actuelle et la place dans le presse-papiers."""
        from PySide6.QtGui import QGuiApplication
        img = self.grabFramebuffer()
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setImage(img)

    def register_pick_listener(self, callback: Callable[[PickResult], None]) -> None:
        """Enregistre un écouteur appelé lorsqu'une entité 3D est cliquée avec la souris."""
        self._pick_listeners.append(callback)

    def clear_selection(self) -> None:
        """Désélectionne toute entité active et redessine."""
        self.selected_pick = None
        self.update()

    def paintGL(self) -> None:
        """Effectue le rendu graphique de la scène."""
        self.renderer.render_scene(
            self.camera,
            self.cached_buffers,
            self.width(),
            self.height(),
            selected_pick=self.selected_pick
        )

    def on_document_changed(self) -> None:
        """Met à jour les maillages mis en cache et redessine la scène."""
        self.cached_buffers = self.document.get_all_mesh_buffers()
        self.update()

    def fit_view(self) -> None:
        """Recadre la caméra pour afficher tous les objets à l'écran."""
        if not self.document.bodies:
            self.camera.distance = 120.0
            self.camera.target = Vector3D(0.0, 0.0, 0.0)
            self.update()
            return

        min_all = Vector3D(1e9, 1e9, 1e9)
        max_all = Vector3D(-1e9, -1e9, -1e9)

        for body in self.document.bodies.values():
            if body.is_empty():
                continue
            b_min, b_max = body.bounding_box()
            min_all = Vector3D(min(min_all.x, b_min.x), min(min_all.y, b_min.y), min(min_all.z, b_min.z))
            max_all = Vector3D(max(max_all.x, b_max.x), max(max_all.y, b_max.y), max(max_all.z, b_max.z))

        if min_all.x < 1e8:
            self.camera.fit_all(min_all, max_all)
            self.update()

    def _on_viewcube_selected(self, view_name: str) -> None:
        """Applique l'orientation de vue demandée par le ViewCube."""
        if view_name.upper() in ("FIT", "RECADRER"):
            self.fit_view()
        else:
            self.camera.set_preset_view(view_name)
            self.update()

    def _handle_navigation_press(self, btn: Qt.MouseButton, mods: Qt.KeyboardModifier) -> bool:
        """Détecte et active le mode panoramique (Pan) ou rotation d'orbite."""
        is_shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        is_alt = bool(mods & Qt.KeyboardModifier.AltModifier)

        if is_shift and btn in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._is_panning = True
            return True
        if btn in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._is_orbiting = True
            return True
        if btn == Qt.MouseButton.LeftButton and is_alt:
            self._is_orbiting = True
            return True
        return False

    def _handle_interactive_pick(self, pos: QPointF) -> None:
        """Exécute le ray picking interactif 3D lors d'un clic gauche."""
        hit = RayPicker.pick_from_screen(
            screen_x=float(pos.x()),
            screen_y=float(pos.y()),
            viewport_width=self.width(),
            viewport_height=self.height(),
            camera=self.camera,
            bodies=self.document.bodies,
            edge_tolerance=3.0
        )
        self.selected_pick = hit if hit.has_hit else None
        if self.selected_pick is not None:
            for cb in self._pick_listeners:
                try:
                    cb(self.selected_pick)
                except Exception as err:
                    print(f"Erreur callback sélection 3D : {err}")
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Gère l'appui sur les boutons de la souris."""
        self._last_mouse_pos = event.position().toPoint()
        if self._handle_navigation_press(event.button(), event.modifiers()):
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._handle_interactive_pick(event.position())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Gère le déplacement de la souris lors des opérations d'orbite et de pan."""
        current_pos = event.position().toPoint()
        delta = current_pos - self._last_mouse_pos
        dx = float(delta.x())
        dy = float(delta.y())
        self._last_mouse_pos = current_pos

        if self._is_orbiting:
            self.camera.orbit(dx * 0.45, -dy * 0.45)
            self.update()
        elif self._is_panning:
            self.camera.pan(dx, dy, self.height())
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Relâche les verrous de navigation lors du relâchement du clic."""
        self._is_orbiting = False
        self._is_panning = False

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Gère le zoom fluide à la molette."""
        delta = event.angleDelta().y()
        self.camera.zoom(float(delta))
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Gère les raccourcis clavier pratiques (F pour recadrer, H pour vue initiale)."""
        if event.key() == Qt.Key.Key_F:
            self.fit_view()
        elif event.key() == Qt.Key.Key_H:
            self.camera.set_preset_view("HOME")
            self.update()
        else:
            super().keyPressEvent(event)
