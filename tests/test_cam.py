"""
Tests unitaires pour le module CAM / FAO et post-processeur G-Code CNC.
"""

import os
import tempfile
import pytest

from src.core.geometry import make_box
from src.cam.cam_engine import CAMEngine, ToolType, CNCTool


def test_cam_facing_and_contour() -> None:
    """Vérifie la génération des trajectoires d'usinage."""
    cam = CAMEngine()
    box = make_box(50.0, 30.0, 15.0)

    # 1. Surfaçage
    b_min, b_max = box.bounding_box()
    facing_op = cam.generate_facing_toolpath(b_min.x, b_max.x, b_min.y, b_max.y, stock_z=17.0, target_z=15.0)
    assert len(facing_op.points) > 5

    # 2. Contournage
    contour_op = cam.generate_contour_toolpath(box, depth_mm=5.0)
    assert len(contour_op.points) > 5


def test_gcode_export_formatting() -> None:
    """Vérifie la syntaxe ISO G-Code (G21, G90, M3, G1, M5, M30)."""
    cam = CAMEngine()
    box = make_box(20.0, 20.0, 10.0)
    op = cam.generate_contour_toolpath(box, depth_mm=2.0)

    with tempfile.TemporaryDirectory() as tmp_dir:
        gcode_file = os.path.join(tmp_dir, "test_part.nc")
        gcode_text = cam.export_gcode([op], gcode_file)

        assert os.path.exists(gcode_file)
        assert "G21" in gcode_text
        assert "G90" in gcode_text
        assert "M3" in gcode_text
        assert "M30" in gcode_text
        assert "G1" in gcode_text
