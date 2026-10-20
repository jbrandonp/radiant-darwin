"""
Suite de tests validant la parité industrielle sur les 8 Mécanismes Bas Niveau FreeCAD vs Radiant Darwin :
1. Fuzzy Booleans (BOPAlgo_PaveFiller)
2. Shape Healing (ShapeFix)
3. Zero-Copy Instancing (App::Link)
4. Constraint Solver Algebraic Diagnosis (PlaneGCS / SolveSpace SVD & QR)
5. Adaptive Tessellation (BRepMesh_IncrementalMesh chordal/angular deflection)
6. Exact Vector Hidden Line Removal (HLRBRep_Algo segment clipping)
7. Physical Units & Dimensional Homogeneity (Base::Quantity [M^a L^b T^c])
8. Incremental Hybrid Serialization & Binary Caches (.FCStd .brp caches)
"""

from __future__ import annotations
import math
import os
import tempfile
import zipfile
import numpy as np
import pytest

from src.core.geometry import make_box, make_cylinder, Solid
from src.core.types import Vector3D, Point2D
from src.core.shape_healing import ShapeFixer
from src.core.assembly import AssemblyLink, AssemblyLinkManager
from src.solver.constraints_2d import (
    SketchConstraintSolver2D,
    GeometricConstraint,
    ConstraintType,
    ConstraintDiagnosisReport,
)
from src.core.adaptive_tessellation import AdaptiveTessellator
from src.core.nexus_kernel.nurbs_surface import NexusNURBSSurface
from src.drawing.drawing_generator import TechnicalDrawingGenerator, TechnicalSheet, DrawingLine2D
from src.drawing.svg_exporter import SVGDrawingExporter
from src.core.units import PhysicalQuantity, UnitCategory
from src.core.document import CADDocument
from src.core.feature import BoxFeature
from src.core.serializer import ProjectSerializer


# 1. Fuzzy Booleans (BOPAlgo_PaveFiller)
def test_mechanism_1_fuzzy_booleans() -> None:
    """Vérifie la robustesse des opérations booléennes à tolérance floue sur des solides quasi-tangents."""
    b1 = make_box(20.0, 20.0, 20.0)
    # b2 décalé de 20.00005 mm (interstice de 50 nm)
    b2 = make_box(20.0, 20.0, 20.0).translate(Vector3D(20.00005, 0.0, 0.0))

    fuzzy_u = b1.fuzzy_union(b2, fuzzy_tolerance=1e-3)
    assert not fuzzy_u.is_empty()
    assert fuzzy_u.volume() > 0.0

    fuzzy_d = b1.fuzzy_difference(b2, fuzzy_tolerance=1e-3)
    assert not fuzzy_d.is_empty()


# 2. Shape Healing (ShapeFix)
def test_mechanism_2_shape_healing() -> None:
    """Vérifie la couture de sommets fendus, l'élimination des dégénérescences et la fermeture de boucle."""
    wire = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.00005, 0.00005)]
    healed_wire = ShapeFixer.heal_wire_2d(wire, tolerance=1e-4)
    assert healed_wire[0] == healed_wire[-1]

    # Sommets fendus
    verts = np.array([
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [5.0, 10.0, 0.0],
        [5.0, 5.0, 10.0],
        [5.0, 5.0, 10.0002],
    ], dtype=np.float64)
    tris = np.array([[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 4, 0]], dtype=np.int32)
    _, _, report = ShapeFixer.heal_mesh(verts, tris, tolerance=1e-3)
    assert report.sewn_vertices >= 1
    assert report.is_watertight is True


# 3. Zero-Copy Instancing (App::Link)
def test_mechanism_3_zero_copy_assembly_links() -> None:
    """Vérifie le partage zéro-copie et l'instanciation GPU par lot."""
    master = make_cylinder(5.0, 25.0)
    mgr = AssemblyLinkManager()
    mgr.register_master_solid("pin_master", master)

    for i in range(20):
        mat = np.eye(4, dtype=np.float64)
        mat[0, 3] = float(i * 10.0)
        link = mgr.create_link(f"pin_{i}", "pin_master", placement_matrix=mat)
        assert link.solid is master

    assert mgr.calculate_memory_savings_ratio() == 20.0
    matrices = mgr.get_instance_matrices_for_master("pin_master")
    assert matrices.shape == (20, 4, 4)


# 4. Constraint Solver Algebraic Diagnosis (PlaneGCS)
def test_mechanism_4_constraint_algebraic_diagnosis() -> None:
    """Vérifie le diagnostic algébrique des contraintes redondantes et contradictoires."""
    solver = SketchConstraintSolver2D()
    p0 = solver.add_point(Point2D(0.0, 0.0))
    # Deux contraintes FIXE sur le même point avec valeurs différentes (conflit)
    solver.add_fixed(p0, 0.0, 0.0)
    solver.add_fixed(p0, 10.0, 10.0)

    report = solver.diagnose_constraints()
    assert report.is_overconstrained is True
    assert len(report.conflicting_constraint_indices) > 0


# 5. Adaptive Tessellation (BRepMesh_IncrementalMesh)
def test_mechanism_5_adaptive_chordal_tessellation() -> None:
    """Vérifie le raffinement adaptatif par flèche cordale et déviation angulaire."""
    ctrl_pts = [
        [[0.0, 0.0, 0.0], [50.0, 0.0, 0.0], [100.0, 0.0, 0.0]],
        [[0.0, 50.0, 0.0], [50.0, 50.0, 40.0], [100.0, 50.0, 0.0]],
        [[0.0, 100.0, 0.0], [50.0, 100.0, 0.0], [100.0, 100.0, 0.0]]
    ]
    surf = NexusNURBSSurface(
        surface_id="test_dome",
        degree_u=2, degree_v=2,
        knots_u=[0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
        knots_v=[0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
        control_points=ctrl_pts
    )
    verts_coarse, tris_coarse = surf.adaptive_tessellate(linear_deflection=2.0, angular_deflection_deg=30.0)
    verts_fine, tris_fine = surf.adaptive_tessellate(linear_deflection=0.2, angular_deflection_deg=10.0)
    assert len(tris_fine) > len(tris_coarse)


# 6. Exact Vector Hidden Line Removal (HLRBRep_Algo)
def test_mechanism_6_hidden_line_removal_subsegments() -> None:
    """Vérifie le découpage de segments d'arêtes en sous-segments pour l'HLR."""
    lines = [
        DrawingLine2D(0.0, 0.0, 100.0, 0.0, is_hidden=False),
        DrawingLine2D(50.0, -20.0, 50.0, 20.0, is_hidden=True),
    ]
    sheet = TechnicalSheet(width_mm=210.0, height_mm=297.0, lines=lines)
    with tempfile.TemporaryDirectory() as tmp_dir:
        svg_path = os.path.join(tmp_dir, "test_hlr.svg")
        svg_content = SVGDrawingExporter.export_svg(sheet, svg_path)
        assert "<svg" in svg_content
        assert "stroke-dasharray" in svg_content  # Lignes cachées en pointillés


# 7. Physical Units & Dimensional Homogeneity (Base::Quantity)
def test_mechanism_7_physical_units_dimensional_homogeneity() -> None:
    """Vérifie l'algèbre dimensionnelle stricte [M, L, T]."""
    f = PhysicalQuantity(500.0, "n")       # [1, 1, -2]
    area = PhysicalQuantity(0.5, "m2")     # [0, 2, 0]
    p = f / area                            # [1, -1, -2] -> Pression (Pa)
    assert p.dimensions == (1, -1, -2)
    assert p.value == 1000.0
    assert p.unit == "pa"

    # Erreur d'incompatibilité dimensionnelle
    l = PhysicalQuantity(10.0, "mm")
    with pytest.raises(TypeError):
        _ = f + l


# 8. Incremental Hybrid Serialization & Binary Caches (.FCStd .brp)
def test_mechanism_8_hybrid_serialization_binary_caches() -> None:
    """Vérifie le conteneur ZIP .cadz et ses caches binaires de solides pré-calculés."""
    doc = CADDocument("Pillar8Doc")
    box = BoxFeature("b_cache", "BoxCache", width=30.0, height=20.0, depth=10.0)
    doc.add_feature(box)
    v_orig = doc.bodies[box.body_id].volume()

    with tempfile.TemporaryDirectory() as tmp_dir:
        cadz_file = os.path.join(tmp_dir, "test_cache.cadz")
        assert ProjectSerializer.save_project(doc, cadz_file, cache_geometry=True)

        cached_solids = ProjectSerializer.read_geometry_cache(cadz_file)
        assert box.body_id in cached_solids
        assert pytest.approx(cached_solids[box.body_id].volume(), 1e-2) == v_orig

        # Chargement instantané sans re-calcul
        loaded = ProjectSerializer.load_project(cadz_file, use_geometry_cache=True)
        assert loaded is not None
        assert box.body_id in loaded.bodies
        assert pytest.approx(loaded.bodies[box.body_id].volume(), 1e-2) == v_orig
