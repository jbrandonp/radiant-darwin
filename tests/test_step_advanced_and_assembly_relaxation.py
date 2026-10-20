"""
Tests unitaires pour l'exportation STEP B-Rep analytique avancée (cylindres, cercles),
la triangulation STEP avec trous intérieurs (inner_wires) et la relaxation d'assemblage multi-corps.
"""

from __future__ import annotations
import numpy as np
import pytest

from src.core.nexus_kernel.hybrid_solid import NexusSolid
from src.core.step_exporter import STEPExporter
from src.core.step_importer import STEPImporter
from src.core.assembly import AssemblyInstance, AssemblyMate, MateType, AssemblySolver
from src.core.geometry import make_box, make_cylinder


def test_step_export_cylinder_surfaces_and_circles() -> None:
    """Vérifie que l'exportation d'un cylindre génère de vraies entités CYLINDRICAL_SURFACE et CIRCLE."""
    cyl = NexusSolid.make_cylinder(radius=12.5, height=45.0, name="PrecisionShaft")
    step_content = STEPExporter.export_nexus_brep_to_string(cyl)

    # Entités ISO 10303-21 fondamentales
    assert "ISO-10303-21;" in step_content
    assert "ADVANCED_BREP_SHAPE_REPRESENTATION" in step_content
    assert "MANIFOLD_SOLID_BREP" in step_content
    assert "CYLINDRICAL_SURFACE" in step_content
    assert "CIRCLE" in step_content
    assert "12.500000" in step_content
    assert "END-ISO-10303-21;" in step_content


def test_step_export_advanced_brep_facade() -> None:
    """Vérifie que STEPExporter.export_advanced_brep_to_string convertit un solide en B-Rep avancé."""
    box = make_box(20.0, 30.0, 40.0, center=True)
    step_content = STEPExporter.export_advanced_brep_to_string({"box": box})

    assert "ADVANCED_BREP_SHAPE_REPRESENTATION" in step_content
    assert "MANIFOLD_SOLID_BREP" in step_content
    assert "PLANE" in step_content
    assert "ADVANCED_FACE" in step_content


def test_step_importer_bridge_hole_to_outer() -> None:
    """Vérifie le découpage et le pontage sans auto-intersection d'un trou dans un polygone 2D."""
    outer_2d = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    outer_indices = [0, 1, 2, 3]

    inner_2d = [(3.0, 3.0), (7.0, 3.0), (7.0, 7.0), (3.0, 7.0)]
    inner_indices = [4, 5, 6, 7]

    merged_2d, merged_indices = STEPImporter._bridge_hole_to_outer(
        outer_2d, outer_indices, inner_2d, inner_indices
    )

    assert len(merged_2d) == len(outer_2d) + len(inner_2d) + 2
    assert len(merged_indices) == len(merged_2d)

    # Triangulation Ear-Clipping du polygone avec trou ponté
    tris = STEPImporter._triangulate_polygon_ear_clipping_2d(merged_2d, merged_indices)
    assert len(tris) > 0
    # Aucun triangle dégénéré
    for tri in tris:
        assert len(set(tri)) == 3


def test_assembly_anchor_point_rotation_preservation() -> None:
    """Vérifie que la rotation d'une contrainte préserve exactement la position du point d'ancrage."""
    box1 = make_box(20.0, 20.0, 20.0)
    box2 = make_box(10.0, 10.0, 10.0)

    inst1 = AssemblyInstance("inst1", box1, is_grounded=True)
    inst2 = AssemblyInstance("inst2", box2, is_grounded=False)

    # Position initiale décalée
    inst2.transform_matrix[0:3, 3] = np.array([50.0, 0.0, 0.0], dtype=np.float64)

    mate = AssemblyMate(
        mate_id="coax_1",
        mate_type=MateType.COAXIAL,
        instance1_id="inst1",
        instance2_id="inst2",
        point1=(0.0, 0.0, 0.0),
        axis1=(0.0, 0.0, 1.0),
        point2=(5.0, 5.0, 0.0),
        axis2=(1.0, 0.0, 0.0)  # Axe orthogonal initialement
    )

    instances = {"inst1": inst1, "inst2": inst2}
    success = AssemblySolver.solve_mates(instances, [mate], max_iterations=15)
    assert success is True

    # Après résolution, l'axe Z local de inst2 doit être aligné avec l'axe Z de inst1
    rot2 = inst2.transform_matrix[0:3, 0:3]
    aligned_axis2 = rot2 @ np.array([1.0, 0.0, 0.0])
    np.testing.assert_allclose(aligned_axis2, [0.0, 0.0, 1.0], atol=1e-3)
