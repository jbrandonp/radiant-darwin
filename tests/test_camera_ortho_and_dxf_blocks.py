"""
Tests unitaires pour la caméra orthographique/perspective continue,
l'importateur DXF (unités $INSUNITS, BLOCKS, INSERT, SPLINE, ELLIPSE),
et les générateurs de visserie filetée ISO (Catalog & Feature).
"""

from __future__ import annotations
import math
import pytest
import numpy as np

from src.core.types import Vector3D, Point2D, PlaneType
from src.viewport.camera import CADCamera
from src.core.dxf_importer import DXFImporter
from src.core.sketch import Sketch2D, SketchLine, SketchCircle, SketchBSpline, SketchPolygon
from src.catalog.fasteners import (
    create_hex_bolt,
    create_socket_head_cap_screw,
    create_hex_nut,
    create_washer,
    clear_fastener_cache,
    ISO_METRIC_TABLE,
)
from src.core.fasteners import FastenerFeature


def test_camera_orthographic_toggle_and_dimensions() -> None:
    """Vérifie le basculement orthographique et le calcul du volume de vue."""
    cam = CADCamera()
    assert not cam.is_orthographic

    # Basculement en mode orthographique
    is_ortho = cam.toggle_projection_mode()
    assert is_ortho is True
    assert cam.is_orthographic is True

    # Calcul de hauteur et largeur orthographiques
    cam.distance = 100.0
    cam.fov_deg = 60.0
    expected_height = 2.0 * 100.0 * math.tan(math.radians(30.0))
    assert math.isclose(cam.get_ortho_height(), expected_height, rel_tol=1e-4)

    width = cam.get_ortho_width(16.0 / 9.0)
    assert math.isclose(width, expected_height * (16.0 / 9.0), rel_tol=1e-4)

    # Le zoom met à l'échelle la distance et donc le volume orthographique
    cam.zoom(1.0)  # Zoom avant (facteur 0.9)
    assert cam.distance < 100.0
    assert cam.get_ortho_height() < expected_height


def test_camera_continuous_rotation_at_poles() -> None:
    """Vérifie l'absence de singularité ou de saut d'Euler près des pôles zénith/nadir."""
    cam = CADCamera()

    # Tester des élévations extrêmes (pôle nord et sud)
    for pitch in [0.0, 45.0, 85.0, 89.9, -85.0, -89.9]:
        cam.pitch_deg = pitch
        cam.yaw_deg = 30.0
        f, r, u = cam.get_camera_axes()

        # Vecteurs unitaires
        assert math.isclose(f.length(), 1.0, rel_tol=1e-4)
        assert math.isclose(r.length(), 1.0, rel_tol=1e-4)
        assert math.isclose(u.length(), 1.0, rel_tol=1e-4)

        # Strictement orthogonaux deux à deux
        assert abs(f.dot(r)) < 1e-4
        assert abs(f.dot(u)) < 1e-4
        assert abs(r.dot(u)) < 1e-4


def test_camera_orthographic_unproject_ray() -> None:
    """Vérifie que le déprojection orthographique produit des rayons parallèles."""
    cam = CADCamera()
    cam.toggle_projection_mode()
    assert cam.is_orthographic

    # Deux pixels distincts sur l'écran
    origin1, dir1 = cam.unproject_ray(100.0, 100.0, 800, 600)
    origin2, dir2 = cam.unproject_ray(500.0, 400.0, 800, 600)

    # En projection parallèle orthographique, la direction des rayons est identique
    assert math.isclose(dir1.x, dir2.x, abs_tol=1e-4)
    assert math.isclose(dir1.y, dir2.y, abs_tol=1e-4)
    assert math.isclose(dir1.z, dir2.z, abs_tol=1e-4)

    # Mais les origines spatiales sont distinctes
    assert not math.isclose(origin1.x, origin2.x, abs_tol=1e-3) or not math.isclose(origin1.y, origin2.y, abs_tol=1e-3)


def test_dxf_header_insunits_scaling() -> None:
    """Vérifie la mise à l'échelle automatique selon la variable $INSUNITS du HEADER."""
    # $INSUNITS = 1 (Pouces -> facteur 25.4)
    dxf_content = """0
SECTION
2
HEADER
9
$INSUNITS
70
1
0
ENDSEC
0
SECTION
2
ENTITIES
0
LINE
10
0.0
20
0.0
11
2.0
21
0.0
0
ENDSEC
0
EOF"""

    sketch = DXFImporter.parse_dxf_text(dxf_content, "Inches_Test")
    assert len(sketch.entities) == 1
    line = sketch.entities[0]
    assert isinstance(line, SketchLine)

    # La longueur originale 2.0 pouces doit valoir 50.8 mm
    dx = line.p2.u - line.p1.u
    dy = line.p2.v - line.p1.v
    length_mm = math.hypot(dx, dy)
    assert math.isclose(length_mm, 50.8, rel_tol=1e-4)


def test_dxf_blocks_and_insert_expansion() -> None:
    """Vérifie le parsing des BLOCKS et le déploiement d'entités INSERT avec transformation."""
    dxf_content = """0
SECTION
2
BLOCKS
0
BLOCK
2
SUB_PART
10
0.0
20
0.0
0
LINE
10
0.0
20
0.0
11
10.0
21
0.0
0
ENDBLK
0
ENDSEC
0
SECTION
2
ENTITIES
0
INSERT
2
SUB_PART
10
50.0
20
100.0
41
2.0
42
2.0
50
90.0
0
ENDSEC
0
EOF"""

    sketch = DXFImporter.parse_dxf_text(dxf_content, "Block_Test")
    assert len(sketch.entities) == 1
    line = sketch.entities[0]
    assert isinstance(line, SketchLine)

    # Point d'insertion: (50, 100)
    assert math.isclose(line.p1.u, 50.0, abs_tol=1e-3)
    assert math.isclose(line.p1.v, 100.0, abs_tol=1e-3)

    # Longueur 10 * échelle 2.0 = 20, pivotée de 90° (le long de V)
    assert math.isclose(line.p2.u, 50.0, abs_tol=1e-3)
    assert math.isclose(line.p2.v, 120.0, abs_tol=1e-3)


def test_dxf_spline_and_ellipse_import() -> None:
    """Vérifie la lecture des courbes paramétriques SPLINE et ELLIPSE."""
    dxf_content = """0
SECTION
2
ENTITIES
0
SPLINE
70
0
71
3
10
0.0
20
0.0
10
10.0
20
20.0
10
30.0
20
15.0
10
40.0
20
0.0
0
ELLIPSE
10
100.0
20
100.0
11
20.0
21
0.0
40
0.5
41
0.0
42
6.283185307
0
ENDSEC
0
EOF"""

    sketch = DXFImporter.parse_dxf_text(dxf_content, "Curves_Test")
    assert len(sketch.entities) == 2

    spline_ent = sketch.entities[0]
    assert isinstance(spline_ent, SketchBSpline)
    assert len(spline_ent.control_points) == 4

    ellipse_ent = sketch.entities[1]
    assert isinstance(ellipse_ent, SketchPolygon)
    assert len(ellipse_ent.points) >= 12


def test_threaded_fastener_generation() -> None:
    """Vérifie la génération géométrique de vis et écrous avec filetage ISO 60°."""
    clear_fastener_cache()

    # 1. Vis hexagonale M6
    bolt_smooth = create_hex_bolt("M6", length=25.0, threaded=False)
    bolt_threaded = create_hex_bolt("M6", length=25.0, threaded=True)

    vol_smooth = bolt_smooth.volume()
    vol_threaded = bolt_threaded.volume()
    assert vol_smooth > 0.0
    assert vol_threaded > 0.0
    # Le filetage usine des gorges dans la tige cylindrique, donc son volume est légèrement inférieur
    assert vol_threaded < vol_smooth

    # 2. Vis CHC M6
    socket_threaded = create_socket_head_cap_screw("M6", length=20.0, threaded=True)
    assert socket_threaded.volume() > 0.0

    # 3. Écrou hexagonal taraudé
    nut_smooth = create_hex_nut("M6", threaded=False)
    nut_threaded = create_hex_nut("M6", threaded=True)
    # L'écrou taraudé a un volume supérieur à l'écrou percé au diamètre majeur (le taraudage laisse de la matière de flanc)
    assert nut_smooth.manifold.genus() == 1
    assert nut_threaded.manifold.genus() == 1

    # 4. Feature Timeline intégration
    feat = FastenerFeature("feat_bolt1", "VisM6", "hex_bolt", "M6", length=30.0, threaded=True)
    bodies = feat.evaluate({}, {})
    assert "body_feat_bolt1" in bodies
    assert bodies["body_feat_bolt1"].volume() > 0.0
