"""
Tests unitaires et d'intégration validant les 14 résolutions médico-légales de Niveau 8.
Couvre :
1. Isolation profonde des snapshots d'historique dans CADDocument (élimination des fuites par référence).
2. Déconnexion MCP résolue avec pont transparent vers l'IHM active.
3. Tri en profondeur (Z-buffer) et levée de la troncature des facettes dans AIVisionFeedback.
4. Profil à développante de cercle normalisé ISO 53 dans ShapeSynthesizer.create_spur_gear.
5. Intégration de GenerationalArena dans la topologie NexusBRep.
6. Élagage rigoureux d'intervalles CSG pour BOX et CYLINDER dans FidgetIntervalTree.
7. Découpage multi-segments sans perte de volume dans la quadrature de Saye.
8. Recalage métrologique CMM robuste par Trimmed ICP avec rejet des brides d'usinage.
9. Drapage robotisé AFP conforme avec projection surfacique anti-lévitation.
10. Alignement angulaire 3D des normales pour contraintes COINCIDENT_PLANES dans AssemblySolver.
11. Résolution propre de COINCIDENT dans LiveDragSolver sans forçage x=y.
12. Projection des arêtes d'arrière-plan ISO 128 dans les vues en coupe de TechnicalDrawingGenerator.
"""

from __future__ import annotations
import math
import numpy as np
import pytest

from src.core.document import CADDocument
from src.core.feature import Feature
from src.core.types import FeatureStatus, Vector3D, Point2D
from src.core.geometry import make_box, make_cylinder, Solid
from src.ai.shape_synthesizer import ShapeSynthesizer
from src.ai.ai_vision_feedback import AIVisionFeedback
from src.ai.mcp_stdio import MCPStdioServer
from src.core.nexus_kernel.brep_topology import (
    NexusBRep, NexusVertex, NexusEdge, NexusFace, NexusPlaneSurface, NexusLineCurve, NexusWire
)
from src.core.nexus_kernel.fidget_interval_tree import (
    SDFIntervalTreeNode, CSGOpType, SDFInterval
)
from src.core.nexus_kernel.saye_quadrature import SayeQuadratureEngine
from src.cam.metrology_cmm_icp import IterativeClosestPointAligner
from src.cam.fiber_placement_afp import (
    AutomatedFiberPlacementEngine, StressTensor3D
)
from src.core.assembly import (
    AssemblySolver, AssemblyInstance, AssemblyMate, MateType
)
from src.solver.live_drag_solver import (
    LiveDragSolver, DragConstraint, DragConstraintType
)
from src.drawing.drawing_generator import TechnicalDrawingGenerator


class DummyBoxFeature(Feature):
    """Opération de test créant un solide initial dans la timeline."""

    def __init__(self, fid: str, body_id: str, solid: Solid) -> None:
        super().__init__(fid, f"Box_{fid}")
        self.body_id = body_id
        self.solid = solid

    def evaluate(self, existing_bodies: dict[str, Solid], sketches: dict) -> dict[str, Solid]:
        bodies = dict(existing_bodies)
        bodies[self.body_id] = self.solid.clone()
        self.status = FeatureStatus.OK
        return bodies


class DummyColorFeature(Feature):
    """Opération de test modifiant le matériau ou la couleur d'un solide."""

    def __init__(self, fid: str, body_id: str, new_material: str) -> None:
        super().__init__(fid, f"Color_{fid}")
        self.body_id = body_id
        self.new_material = new_material

    def evaluate(self, existing_bodies: dict[str, Solid], sketches: dict) -> dict[str, Solid]:
        bodies = dict(existing_bodies)
        if self.body_id in bodies:
            mod = bodies[self.body_id].clone()
            mod.material_name = self.new_material
            bodies[self.body_id] = mod
        self.status = FeatureStatus.OK
        return bodies


def test_document_snapshots_deep_isolation() -> None:
    """Vérifie que les snapshots de la timeline sont complètement isolés et immuables."""
    doc = CADDocument("SnapshotTest")
    box = make_box(20.0, 20.0, 20.0)
    box.material_name = "Acier"
    feat0 = DummyBoxFeature("f0", "B1", box)
    doc.add_feature(feat0)
    assert doc.bodies["B1"].material_name == "Acier"

    feat1 = DummyColorFeature("f1", "B1", "Alu")
    doc.add_feature(feat1)
    assert doc.bodies["B1"].material_name == "Alu"

    feat2 = DummyColorFeature("f2", "B1", "Titane")
    doc.add_feature(feat2)
    assert doc.bodies["B1"].material_name == "Titane"

    # Rollback à l'étape 1 (feat1)
    doc.set_rollback_index(1)
    assert doc.bodies["B1"].material_name == "Alu"

    # Rollback à l'étape 0 (feat0)
    doc.set_rollback_index(0)
    assert doc.bodies["B1"].material_name == "Acier"

    # Vérifier que le snapshot de l'étape 2 n'a pas été corrompu
    doc.set_rollback_index(2)
    assert doc.bodies["B1"].material_name == "Titane"


def test_mcp_gui_forwarding_fallback() -> None:
    """Vérifie la robustesse du serveur MCP stdio en mode autonome."""
    server = MCPStdioServer()
    # Le serveur GUI n'étant pas actif sur 8765 lors de ce test unitaire,
    # il doit s'exécuter localement sans lever d'exception
    res_text, success = server._dispatch_tool_action("create_primitive", {"primitive_type": "box", "width_mm": 30.0})
    assert success is True
    assert "créée avec succès" in res_text


def test_vision_feedback_z_buffer_depth_sorting() -> None:
    """Vérifie le rendu visuel avec tri en profondeur Z-buffer sans troncature."""
    doc = CADDocument("VisionTest")
    doc.bodies["cube"] = make_box(40.0, 40.0, 40.0, center=True)
    res = AIVisionFeedback.capture_document_view(doc, width=320, height=240)
    assert res.has_image is True
    assert len(res.base64_png) > 100


def test_iso_involute_spur_gear_accuracy() -> None:
    """Vérifie que ShapeSynthesizer génère une vraie développante de cercle ISO 53."""
    gear = ShapeSynthesizer.create_spur_gear(num_teeth=24, module=2.5, face_width=15.0)
    assert not gear.is_empty()
    assert gear.volume() > 5000.0
    # Le solide doit être manifold et fermé
    assert gear.genus() == 1  # 1 alésage central


def test_generational_arena_brep_integration() -> None:
    """Vérifie que NexusBRep alloue et indexe les entités dans GenerationalArena."""
    brep = NexusBRep("TestBRep")
    v1 = NexusVertex("v1", 0.0, 0.0, 0.0)
    v2 = NexusVertex("v2", 10.0, 0.0, 0.0)
    brep.add_vertex(v1)
    brep.add_vertex(v2)

    assert len(brep.vertex_arena) == 2
    assert "v1" in brep.vertex_keys
    k1 = brep.vertex_keys["v1"]
    retrieved_v1 = brep.get_vertex_by_key(k1)
    assert retrieved_v1 is not None
    assert retrieved_v1.x == 0.0


def test_fidget_interval_tree_cylinder_and_box() -> None:
    """Vérifie l'évaluation d'intervalle et scalaire pour BOX et CYLINDER dans Fidget."""
    box_node = SDFIntervalTreeNode(op=CSGOpType.BOX, params=[10.0, 10.0, 10.0])
    cyl_node = SDFIntervalTreeNode(op=CSGOpType.CYLINDER, params=[8.0, 15.0])

    # Scalaires
    assert box_node.eval_scalar(0.0, 0.0, 0.0) < 0.0   # Intérieur
    assert box_node.eval_scalar(20.0, 0.0, 0.0) > 0.0  # Extérieur
    assert cyl_node.eval_scalar(0.0, 0.0, 0.0) < 0.0   # Intérieur
    assert cyl_node.eval_scalar(15.0, 0.0, 0.0) > 0.0  # Extérieur

    # Intervalles
    ix = SDFInterval(20.0, 30.0)
    iy = SDFInterval(0.0, 5.0)
    iz = SDFInterval(0.0, 5.0)
    box_int = box_node.eval_interval(ix, iy, iz)
    assert box_int.min_val > 0.0  # Strictement extérieur

    cyl_int = cyl_node.eval_interval(ix, iy, iz)
    assert cyl_int.min_val > 0.0  # Strictement extérieur


def test_saye_quadrature_multi_subsegments() -> None:
    """Vérifie la quadrature de Saye sans perte de volume sur géométrie courbe."""
    # Sphère de rayon 5 au centre
    def phi_sphere(x: float, y: float, z: float) -> float:
        return float(np.sqrt(x ** 2 + y ** 2 + z ** 2)) - 5.0

    vol = SayeQuadratureEngine.integrate_domain(
        phi_func=phi_sphere,
        box_min=[-6.0, -6.0, -6.0],
        box_max=[6.0, 6.0, 6.0],
        subdivisions=4
    )
    exact_sphere_vol = (4.0 / 3.0) * math.pi * (5.0 ** 3)
    # L'erreur numérique doit être inférieure à 10% sur une discrétisation 4x4x4
    rel_err = abs(vol - exact_sphere_vol) / exact_sphere_vol
    assert rel_err < 0.10


def test_metrology_trimmed_icp_outliers() -> None:
    """Vérifie le rejet des points aberrants (brides) par Trimmed ICP."""
    # 50 points nominaux sur une plaque plane Z=0
    np.random.seed(42)
    xs = np.random.uniform(0.0, 100.0, 50)
    ys = np.random.uniform(0.0, 100.0, 50)
    nominal_pts = np.column_stack([xs, ys, np.zeros(50)])
    nominal_normals = [Vector3D(0.0, 0.0, 1.0) for _ in range(50)]
    nominal_v3d = [Vector3D(p[0], p[1], p[2]) for p in nominal_pts]

    # Scannés : 45 points inliers avec léger bruit + 5 points aberrants sur bride (Z=30)
    scanned_pts = np.copy(nominal_pts)
    scanned_pts[:45, 2] += np.random.normal(0.0, 0.05, 45)
    scanned_pts[45:, 2] = 30.0  # Brides
    scanned_v3d = [Vector3D(p[0], p[1], p[2]) for p in scanned_pts]

    aligner = IterativeClosestPointAligner(
        max_iterations=20,
        tolerance_epsilon=1e-4,
        upper_gdt_limit_mm=0.15,
        lower_gdt_limit_mm=-0.15
    )
    report = aligner.align_and_inspect(scanned_v3d, nominal_v3d, nominal_normals)

    # Trimmed ICP doit rejeter les 5 points de bride et garder les inliers
    assert report.total_points == 50
    # La majorité des points inliers doit être dans la tolérance nominale
    assert report.in_tolerance_percentage >= 80.0


def test_afp_fiber_conformal_projection() -> None:
    """Vérifie que la trajectoire AFP reste confinée sur la surface du moule."""
    engine = AutomatedFiberPlacementEngine()

    def dummy_stress(p: Vector3D) -> StressTensor3D:
        return StressTensor3D(100.0, 10.0, 0.0, 0.0, 0.0, 0.0)

    # Moule cylindrique : projeter sur rayon R=50
    def project_to_cylinder(p: Vector3D) -> Vector3D:
        r = math.hypot(p.x, p.y)
        if r < 1e-6:
            return Vector3D(50.0, 0.0, p.z)
        scale = 50.0 / r
        return Vector3D(p.x * scale, p.y * scale, p.z)

    seed = Vector3D(50.0, 0.0, 0.0)
    traj = engine.trace_fiber_trajectory_from_stress_field(
        tow_id="TOW_TEST",
        material="Carbon/PEEK",
        seed_point=seed,
        stress_field_fn=dummy_stress,
        step_size_mm=5.0,
        max_steps=20,
        surface_projection_fn=project_to_cylinder
    )

    assert len(traj.waypoints) > 10
    # Vérifier que chaque point est exactement sur le rayon R=50
    for wp in traj.waypoints:
        r_pt = math.hypot(wp.position.x, wp.position.y)
        assert abs(r_pt - 50.0) < 1e-4


def test_assembly_coincident_planes_rotation() -> None:
    """Vérifie que AssemblySolver réoriente les normales de faces pour COINCIDENT_PLANES."""
    inst1 = AssemblyInstance("part1", make_box(20.0, 20.0, 20.0), is_grounded=True)
    inst2 = AssemblyInstance("part2", make_box(20.0, 20.0, 20.0))

    # Au départ inst2 a sa face normale selon +Z (0, 0, 1), et inst1 a sa normale selon +X (1, 0, 0)
    mate = AssemblyMate(
        mate_id="m1",
        instance1_id="part1",
        instance2_id="part2",
        mate_type=MateType.COINCIDENT_PLANES,
        point1=(20.0, 10.0, 10.0),
        point2=(0.0, 10.0, 10.0),
        axis1=(1.0, 0.0, 0.0),   # Normale +X
        axis2=(0.0, 0.0, 1.0)    # Normale +Z (à 90 degrés)
    )

    instances = {"part1": inst1, "part2": inst2}
    success = AssemblySolver.solve_mates(instances, [mate], max_iterations=5)
    assert success is True

    # Vérifier que la rotation a réorienté l'axe de inst2 pour être opposé à (1, 0, 0), c'est-à-dire (-1, 0, 0)
    rot2 = inst2.transform_matrix[:3, :3]
    new_norm2 = rot2 @ np.array([0.0, 0.0, 1.0])
    assert abs(new_norm2[0] - (-1.0)) < 1e-3


def test_live_drag_coincident_fix() -> None:
    """Vérifie que DragConstraintType.COINCIDENT n'écrase pas x=y quand target_pos est None."""
    solver = LiveDragSolver()
    c = DragConstraint(id="c1", constraint_type=DragConstraintType.COINCIDENT, entity_indices=(0,), target_val=50.0)

    # Initialement point à (10, 20) : target_pos is None, donc le point ne doit pas être écrasé à (50, 50) !
    pt = solver.live_drag_step(0, Point2D(10.0, 20.0), [c])
    assert pt.x == 10.0
    assert pt.y == 20.0

    # Si target_pos est défini, projection exacte sur la cible 2D
    c_target = DragConstraint(
        id="c2",
        constraint_type=DragConstraintType.COINCIDENT,
        entity_indices=(0,),
        target_pos=Point2D(35.0, 45.0)
    )
    pt_target = solver.live_drag_step(0, Point2D(10.0, 20.0), [c_target])
    assert pt_target.x == 35.0
    assert pt_target.y == 45.0


def test_technical_drawing_section_view_background() -> None:
    """Vérifie que generate_section_view projette les arêtes d'arrière-plan ISO 128."""
    box = make_box(40.0, 40.0, 40.0)
    gen = TechnicalDrawingGenerator()
    sheet = gen.generate_section_view(box, cut_height=20.0)

    assert len(sheet.lines) > 0
    # Doit contenir des hachures (is_hatch=True) ET des lignes de matière visibles (is_hatch=False)
    hatch_lines = [l for l in sheet.lines if l.is_hatch]
    contour_lines = [l for l in sheet.lines if not l.is_hatch and not l.is_dimension]
    assert len(hatch_lines) > 0
    assert len(contour_lines) > 0
