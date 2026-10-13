"""
Tests unitaires pour le contrôleur d'esquisse interactif 2D avec accrochage (Snapping).
"""

import pytest

from src.core.sketch import Sketch2D
from src.core.types import PlaneType, Point2D
from src.viewport.sketch_mode import ViewportSketchController, InteractiveTool


def test_sketch_mode_workflow() -> None:
    """Vérifie le cycle complet de dessin interactif : début, clic 1, clic 2, fin."""
    ctrl = ViewportSketchController()
    sketch = Sketch2D("s_test", "Esquisse Interactive", PlaneType.XY)

    assert not ctrl.state.is_active
    ctrl.start_sketch(PlaneType.XY)
    assert ctrl.state.is_active

    # Clic 1 à (10.2, 19.8) -> aimanté à (10.0, 20.0)
    finished = ctrl.handle_mouse_click(10.2, 19.8, sketch)
    assert not finished
    assert ctrl.state.start_point == Point2D(10.0, 20.0)

    # Clic 2 à (51.1, 40.3) -> aimanté à (50.0, 40.0)
    ctrl.state.tool = InteractiveTool.RECTANGLE
    finished = ctrl.handle_mouse_click(51.1, 40.3, sketch)
    assert finished
    assert len(sketch.entities) == 1

    ctrl.finish_sketch()
    assert not ctrl.state.is_active


def test_snapping_precision() -> None:
    """Vérifie l'arrondi sur la grille du pas de 5mm."""
    ctrl = ViewportSketchController()
    assert ctrl.snap_coordinate(0.0) == 0.0
    assert ctrl.snap_coordinate(2.4) == 0.0
    assert ctrl.snap_coordinate(2.6) == 5.0
    assert ctrl.snap_coordinate(11.8) == 10.0
    assert ctrl.snap_coordinate(14.9) == 15.0
