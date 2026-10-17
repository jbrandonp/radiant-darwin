"""
Tests unitaires pour la détection d'arcs G02/G03 et la compensation de rayon G41/G42 dans les post-processeurs CNC.
"""

import math
from src.core.types import Vector3D
from src.cam.cam_engine import CNCTool, ToolpathOperation, ToolpathPoint, ToolType
from src.cam.post_processors import IndustrialPostProcessor


def test_post_processor_arc_detection_and_cutter_comp() -> None:
    tool = CNCTool(tool_id=1, name="Fraise Ø10", tool_type=ToolType.END_MILL, diameter_mm=10.0, flute_length_mm=30.0, feedrate_mm_min=1000.0)

    # 3 points formant un arc de cercle de rayon R=20 centré en (20, 0)
    # Angle 0°: (0, 0), Angle 45°: (20 - 20*cos45, 20*sin45), Angle 90°: (20, 20)
    cx, cy, r = 20.0, 0.0, 20.0
    p0 = Vector3D(cx - r, cy, -5.0)
    p1 = Vector3D(cx - r * math.cos(math.pi / 4), cy + r * math.sin(math.pi / 4), -5.0)
    p2 = Vector3D(cx, cy + r, -5.0)

    points = [
        ToolpathPoint(p0, is_rapid=False),
        ToolpathPoint(p1, is_rapid=False),
        ToolpathPoint(p2, is_rapid=False),
    ]

    op = ToolpathOperation(name="Usinage Arc", tool=tool, points=points)

    # Avec détection d'arcs et compensation à gauche G41
    gcode = IndustrialPostProcessor.post_process_haas(
        [op],
        enable_arcs=True,
        cutter_comp="left"
    )

    assert "G41 D01" in gcode
    assert ("G02" in gcode or "G03" in gcode)
    assert "I" in gcode and "J" in gcode
    assert "G40" in gcode
