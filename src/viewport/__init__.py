"""
Module de visualisation 3D et esquisse interactive.
"""

from src.viewport.camera import CADCamera
from src.viewport.gl_renderer import GLRenderer
from src.viewport.view_cube import ViewCubeOverlay
from src.viewport.nav_bar import ViewportNavBar
from src.viewport.viewport_widget import CADViewportWidget
from src.viewport.sketch_mode import ViewportSketchController, InteractiveTool, SketchInteractionState
from src.viewport.viewport_shading import ViewportShadingManager, ShadingMode
from src.viewport.snap_engine import MagneticSnapEngine, SnapTarget, SnapResult
from src.viewport.transform_gizmo import TransformGizmo, GizmoMode, GizmoAxis

__all__ = [
    "CADCamera",
    "GLRenderer",
    "ViewCubeOverlay",
    "ViewportNavBar",
    "CADViewportWidget",
    "ViewportSketchController",
    "InteractiveTool",
    "SketchInteractionState",
    "ViewportShadingManager",
    "ShadingMode",
    "MagneticSnapEngine",
    "SnapTarget",
    "SnapResult",
    "TransformGizmo",
    "GizmoMode",
    "GizmoAxis",
]
