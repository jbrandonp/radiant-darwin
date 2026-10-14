"""
Suite de tests de robustesse et de validation des cas limites (Exhaustive Bug Hunt).
Vérifie tous les correctifs appliqués :
1. Surfaçage CAM avec boîte englobante (generate_facing_toolpath).
2. Évidement en coque (Shell) avec validation stricte de l'épaisseur de paroi.
3. Résistance aux disparités de maillage dans la cartographie FEA.
4. Sécurité des chanfreins 2D face aux distances nulles ou quasi-nulles.
5. Normalisation des vecteurs 3D nuls.
6. Résistance aux quaternions doubles sur axes dégénérés.
7. Résistance du moteur de script et du bridge face aux cas extrêmes.
"""

from __future__ import annotations
import pytest
import numpy as np

from src.core.types import Vector3D, Point2D, MeshBuffer, ColorRGBA
from src.core.geometry import make_box, make_cylinder, Solid
from src.core.document import CADDocument
from src.core.sketch import Sketch2D
from src.core.nexus_kernel.dual_quaternions import Quaternion, DualQuaternion
from src.fea.fea_solver import FEASimulator, FEAResult
from src.cam.cam_engine import CAMEngine, CNCTool, ToolType
from src.ai.cad_ai_full_suite import CADFullSuiteOrchestrator
from src.ai.cad_ai_bridge import CADAIBridge
from src.ai.cad_script_engine import CADScriptEngine


# =========================================================================
# 1. Validation du Correctif CAM Facing Toolpath
# =========================================================================

def test_cam_facing_toolpath_with_solid_bounding_box() -> None:
    box = make_box(60.0, 40.0, 20.0, center=True)
    # Vérification que run_cam supporte bien l'opération 'facing' sans erreur
    res = CADFullSuiteOrchestrator.run_cam(
        solid=box,
        operation_type="facing",
        tool_diameter_mm=8.0,
        depth_mm=4.0
    )
    assert res is not None
    assert "Usinage Facing" in res.operation_name
    assert res.total_cut_length_mm > 0.0
    assert res.total_passes >= 1
    assert "G0" in res.gcode_preview or "G1" in res.gcode_preview


# =========================================================================
# 2. Validation du Correctif Direct Modeling Shell (Oversized Wall)
# =========================================================================

def test_shell_valid_wall_thickness() -> None:
    box = make_box(50.0, 50.0, 30.0, center=True)
    res = CADFullSuiteOrchestrator.direct_modeling_shell(box, wall_thickness_mm=3.0)
    assert res.solid is not None
    assert res.volume_after_mm3 < res.volume_before_mm3
    assert res.volume_after_mm3 > 0.0


def test_shell_oversized_wall_thickness_raises_value_error() -> None:
    box = make_box(20.0, 20.0, 10.0, center=True)
    # Épaisseur de 15 mm impossible sur une largeur de 20 mm (max autorisé < 10 mm)
    with pytest.raises(ValueError) as excinfo:
        CADFullSuiteOrchestrator.direct_modeling_shell(box, wall_thickness_mm=15.0)
    assert "dépasse la géométrie" in str(excinfo.value)


# =========================================================================
# 3. Validation du Correctif FEA Heatmap Shape Mismatch
# =========================================================================

def test_fea_heatmap_mismatched_mesh_handled_gracefully() -> None:
    sim = FEASimulator()
    b1 = make_box(30, 30, 30)
    res_fea = sim.run_static_analysis(b1, applied_force_newtons=1000.0)
    assert res_fea is not None

    # On passe un solide différent avec un nombre différent de sommets
    b2 = make_cylinder(10, 40, segments=64)
    # Ne doit pas lever de ValueError broadcasting crash
    heatmap_buf = sim.generate_stress_heatmap_mesh(b2, res_fea)
    assert heatmap_buf is not None
    assert not heatmap_buf.is_empty()


# =========================================================================
# 4. Validation du Correctif Chanfrein 2D (Distance Nulle)
# =========================================================================

def test_sketch_chamfer_zero_distance_safe() -> None:
    sketch = Sketch2D("TestChamfer")
    l1 = sketch.add_line(Point2D(0.0, 0.0), Point2D(50.0, 0.0))
    l2 = sketch.add_line(Point2D(50.0, 0.0), Point2D(50.0, 50.0))

    # Distance nulle ou négative -> doit renvoyer None sans diviser par zéro
    res_zero = sketch.chamfer_2d_lines(l1.entity_id, l2.entity_id, distance=0.0)
    assert res_zero is None

    res_neg = sketch.chamfer_2d_lines(l1.entity_id, l2.entity_id, distance=-5.0)
    assert res_neg is None

    # Distance valide
    res_valid = sketch.chamfer_2d_lines(l1.entity_id, l2.entity_id, distance=5.0)
    assert res_valid is not None


# =========================================================================
# 5. Validation de la Normalisation Vector3D Nulle
# =========================================================================

def test_vector3d_zero_norm_safe() -> None:
    zero_vec = Vector3D(0.0, 0.0, 0.0)
    unit_zero = zero_vec.normalized()
    assert unit_zero.x == 0.0
    assert unit_zero.y == 0.0
    assert unit_zero.z == 0.0
    assert unit_zero.length() == 0.0


# =========================================================================
# 6. Validation Quaternion sur Axe Dégénéré
# =========================================================================

def test_quaternion_zero_axis_safe() -> None:
    q = Quaternion.from_axis_angle([0.0, 0.0, 0.0], angle_rad=1.57)
    assert q.w == 1.0
    assert q.x == 0.0
    assert q.y == 0.0
    assert q.z == 0.0


# =========================================================================
# 7. Robustesse Bridge et Script Engine sur Requêtes Anormales
# =========================================================================

def test_bridge_empty_and_whitespace_prompt() -> None:
    doc = CADDocument("Empty Doc")
    bridge = CADAIBridge(doc)
    res = bridge.execute_prompt("   ")
    assert res.success is False
    assert len(res.suggested_prompts) > 0


def test_script_engine_atomic_rollback_on_syntax_error() -> None:
    doc = CADDocument("Syntax Error Doc")
    doc.bodies["Init"] = make_box(10, 10, 10)
    bad_code = "b = cad.box(20, 20, 20\n"  # Parenthèse non fermée
    res = CADScriptEngine.execute_script(doc, bad_code)
    assert res.success is False
    assert "Erreur de syntaxe" in res.message
    # Le document reste intact
    assert len(doc.bodies) == 1
    assert "Init" in doc.bodies
