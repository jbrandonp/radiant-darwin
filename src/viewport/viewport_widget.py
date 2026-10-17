"""
Widget principal du Viewport 3D basé sur QOpenGLWidget.
Gère l'affichage de la scène, la capture des événements souris (orbite, zoom, pan)
et l'intégration du ViewCube.
"""

from __future__ import annotations
from typing import Optional, List, Callable
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QMouseEvent, QWheelEvent, QKeyEvent, QSurfaceFormat, QCloseEvent

from src.core.document import CADDocument
from src.core.types import MeshBuffer, Vector3D
from src.viewport.camera import CADCamera
from src.viewport.gl_renderer import GLRenderer
from src.viewport.view_cube import ViewCubeOverlay
from src.viewport.nav_bar import ViewportNavBar
from src.viewport.ray_picking import RayPicker, PickResult, PickedEntityType
from src.viewport.viewport_shading import ShadingMode
from src.viewport.snap_engine import SnapResult
from src.viewport.transform_gizmo import GizmoAxis, GizmoMode
from src.core.push_pull import PushPullEngine


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
        self.current_snap: Optional[SnapResult] = None
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
        self.nav_bar.toggle_shading_requested.connect(self._cycle_shading_mode)
        self.nav_bar.toggle_snap_requested.connect(self._toggle_snapping)
        self.nav_bar.toggle_gizmo_requested.connect(self._toggle_gizmo)
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
            selected_pick=self.selected_pick,
            snap_result=self.current_snap
        )

    def _cycle_shading_mode(self) -> None:
        """Bascule séquentiellement entre les modes d'affichage (Blender MatCaps & Fusion 360)."""
        modes = [
            ShadingMode.SHADED_EDGES,
            ShadingMode.MATCAP_CLAY,
            ShadingMode.MATCAP_RED_WAX,
            ShadingMode.MATCAP_CHROME,
            ShadingMode.ZEBRA_STRIPES,
            ShadingMode.DRAFT_ANGLE,
            ShadingMode.WIREFRAME
        ]
        cur = self.renderer.shading_manager.active_mode
        idx = (modes.index(cur) + 1) % len(modes)
        self.renderer.shading_manager.set_shading_mode(modes[idx])
        self.update()

    def _toggle_snapping(self) -> None:
        """Active ou désactive l'accrochage magnétique intelligent (Blender Snap)."""
        self.renderer.snap_engine.is_enabled = not self.renderer.snap_engine.is_enabled
        self.nav_bar.btn_magnetic_snap.setChecked(self.renderer.snap_engine.is_enabled)
        self.update()

    def _toggle_gizmo(self) -> None:
        """Affiche ou masque le manipulateur 3D interactif (Transform Gizmo)."""
        self.renderer.transform_gizmo.is_visible = not self.renderer.transform_gizmo.is_visible
        self.nav_bar.btn_gizmo.setChecked(self.renderer.transform_gizmo.is_visible)
        self.update()

    def execute_press_pull(self, offset_dist: float = 10.0) -> bool:
        """Applique la modélisation directe Press-Pull Fusion 360 sur l'entité sélectionnée."""
        if self.selected_pick is None or not self.selected_pick.has_hit:
            return False
        body_id = self.selected_pick.body_id
        if not body_id or body_id not in self.document.bodies:
            return False
        solid = self.document.bodies[body_id]
        res = PushPullEngine.execute_press_pull(
            solid,
            self.selected_pick.hit_point,
            self.selected_pick.normal,
            offset_dist
        )
        if res.success:
            self.document.bodies[body_id] = res.modified_solid
            self.document.notify_listeners()
            return True
        return False

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
            self.renderer.transform_gizmo.set_target(self.selected_pick.hit_point)
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
            # 1. Vérifier si on clique sur un axe du gizmo de transformation actif
            if self.renderer.transform_gizmo.is_visible:
                r_orig, r_dir = self.camera.unproject_ray(
                    float(event.position().x()), float(event.position().y()), self.width(), self.height()
                )
                hit_axis = self.renderer.transform_gizmo.hit_test(r_orig, r_dir)
                if hit_axis != GizmoAxis.NONE:
                    self.renderer.transform_gizmo.start_drag(
                        hit_axis, float(event.position().x()), float(event.position().y()), r_orig, r_dir
                    )
                    self.update()
                    return

            self._handle_interactive_pick(event.position())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Gère le déplacement de la souris lors des opérations d'orbite, de pan, de gizmo et d'accrochage."""
        current_pos = event.position().toPoint()
        delta = current_pos - self._last_mouse_pos
        dx = float(delta.x())
        dy = float(delta.y())
        self._last_mouse_pos = current_pos

        # Manipulation interactive directe via TransformGizmo 3D
        if self.renderer.transform_gizmo.is_dragging:
            r_orig, r_dir = self.camera.unproject_ray(
                float(current_pos.x()), float(current_pos.y()), self.width(), self.height()
            )
            delta_t, delta_rot, delta_s = self.renderer.transform_gizmo.update_drag(
                float(current_pos.x()), float(current_pos.y()), r_orig, r_dir
            )
            self.renderer.transform_gizmo.position = self.renderer.transform_gizmo._drag_start_pos + delta_t
            self.update()
            return

        if self._is_orbiting:
            self.camera.orbit(dx * 0.45, -dy * 0.45)
            self.update()
        elif self._is_panning:
            self.camera.pan(dx, dy, self.height())
            self.update()
        else:
            if self.renderer.snap_engine.is_enabled:
                self.current_snap = self.renderer.snap_engine.find_best_snap(
                    current_pos.x(), current_pos.y(),
                    self.width(), self.height(),
                    self.camera, self.cached_buffers
                )
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Relâche les verrous de navigation et de manipulation gizmo lors du relâchement du clic."""
        if self.renderer.transform_gizmo.is_dragging:
            self.renderer.transform_gizmo.end_drag()
            self.update()
        self._is_orbiting = False
        self._is_panning = False

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Gère le zoom fluide à la molette."""
        delta = event.angleDelta().y()
        self.camera.zoom(float(delta))
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Gère les raccourcis clavier pratiques (F=fit, H=home, Q=press-pull, M=shading, S=snap, G=gizmo)."""
        if event.key() == Qt.Key.Key_F:
            self.fit_view()
        elif event.key() == Qt.Key.Key_H:
            self.camera.set_preset_view("HOME")
            self.update()
        elif event.key() == Qt.Key.Key_Q:
            self.execute_press_pull(10.0)
        elif event.key() == Qt.Key.Key_M:
            self._cycle_shading_mode()
        elif event.key() == Qt.Key.Key_S:
            self._toggle_snapping()
        elif event.key() == Qt.Key.Key_G:
            self._toggle_gizmo()
        else:
            super().keyPressEvent(event)

    def cleanup(self) -> None:
        """Libère les tampons de maillage OpenGL et les sélections pour éviter les fuites mémoire."""
        self.cached_buffers.clear()
        self.selected_pick = None
        self.current_snap = None

    def closeEvent(self, event: QCloseEvent) -> None:
        """Garantit la libération propre des ressources OpenGL lors de la fermeture de la vue."""
        self.cleanup()
        super().closeEvent(event)

