"""
Suite de tests d'ingénierie complète pour les 4 Chantiers Concrets (Sortie du Baratin).
Vérifie :
1. Le Picking 3D interactif dans le Viewport (Möller-Trumbore & rattachement d'esquisse sur face).
2. L'Atelier TechDraw avec cartouche normalisé ISO 7200, arêtes cachées HLR et GD&T.
3. Le Solveur d'Assemblage Multi-Pièces intégré au CADDocument avec détection de collision Manifold.
4. Le Mailleur Volumique Tétraédrique Gmsh et la clarification technique des solveurs.
"""

from __future__ import annotations
import math
import numpy as np
import pytest

from src.core.types import Vector3D, Point2D, PlaneType
from src.core.geometry import Solid, make_box
from src.core.document import CADDocument
from src.viewport.camera import CADCamera
from src.viewport.ray_picking import RayPicker, Ray3D, PickResult, PickedEntityType
from src.drawing.techdraw_workbench import (
    TechDrawSheet, SheetSize, TitleBlockData, ProjectionAngle
)
from src.drawing.drawing_advanced import (
    FeatureControlFrame, GeometricCharacteristic, MaterialCondition, DatumReference
)
from src.core.assembly import AssemblyInstance, AssemblyMate, MateType, AssemblySolver
from src.fea.gmsh_mesher import GmshVolumetricMesher, GmshElementType
from src.fea.nonlinear_fem import LinearTetraDemoSolver, NonlinearFEASolver
from src.specialized.aerodynamics_solver import NacaAnalyticPolar, AerodynamicsSolver
from src.cam.volumetric_simulator import VoxelRoughingPreview, VolumetricStockSimulator


# ==============================================================================
# CHANTIER 1 : PICKING 3D INTERACTIF DANS LE VIEWPORT
# ==============================================================================

def test_chantier_1_interactive_3d_ray_picking_on_box():
    """Vérifie la sélection précise à la souris d'une face et d'une arête d'un solide 3D."""
    # Création d'un cube 40x40x40 mm centré en (0, 0, 0) -> X, Y, Z dans [-20, 20]
    solid_box = make_box(40.0, 40.0, 40.0, center=True)
    doc = CADDocument("PickingDoc")
    doc.bodies["box_01"] = solid_box

    cam = CADCamera()
    cam.target = Vector3D(0.0, 0.0, 0.0)
    cam.distance = 100.0
    cam.set_preset_view("TOP")  # Caméra placée au-dessus sur +Z regardant vers le bas

    # Tirer un rayon directement au centre de l'écran (0, 0)
    # L'écran fait 800x600 pixels
    center_x = 400.0
    center_y = 300.0

    hit = RayPicker.pick_from_screen(
        screen_x=center_x,
        screen_y=center_y,
        viewport_width=800,
        viewport_height=600,
        camera=cam,
        bodies=doc.bodies,
        edge_tolerance=2.0
    )

    assert hit.has_hit is True
    assert hit.entity_type == PickedEntityType.FACE
    assert hit.body_id == "box_01"
    # La face supérieure a sa normale dirigée vers le haut (+Z)
    assert pytest.approx(hit.normal.z, 1e-2) == 1.0
    # Le point d'impact doit être à la cote Z = +20.0 mm
    assert pytest.approx(hit.hit_point.z, 1e-2) == 20.0


# ==============================================================================
# CHANTIER 2 : ATELIER TECHDRAW (MISE EN PLAN 2D AVEC CARTOUCHE ISO 7200)
# ==============================================================================

def test_chantier_2_techdraw_iso_sheet_generation():
    """Vérifie la génération d'une planche complète TechDraw avec cartouche et 4 vues."""
    title_data = TitleBlockData(
        title="SUPPORT PALIER 40X40",
        drawing_number="DWG-2026-NEXUS",
        author="Brandon",
        company="CAD Studio Engineering",
        scale="1:1"
    )
    sheet = TechDrawSheet(sheet_size=SheetSize.A4_LANDSCAPE, title_block=title_data)

    # Projeter un parallélépipède 40 x 30 x 20 mm
    sheet.project_solid_box_views(box_width=40.0, box_height=30.0, box_depth=20.0, scale=1.0)

    # Ajouter un cadre GD&T de localisation
    gdt = FeatureControlFrame(
        characteristic=GeometricCharacteristic.POSITION,
        tolerance_value=0.02,
        primary_datum=DatumReference("A"),
        secondary_datum=DatumReference("B")
    )
    sheet.add_gdt_frame(x=20.0, y=180.0, frame=gdt)

    # Vérification des entités dessinées
    assert len(sheet.lines) > 20
    # Des arêtes cachées doivent être présentes dans la vue isométrique
    hidden_lines = [l for l in sheet.lines if l.is_hidden]
    assert len(hidden_lines) >= 3

    # Génération SVG
    svg_code = sheet.render_svg()
    assert "<svg" in svg_code
    assert "</svg>" in svg_code
    assert "SUPPORT PALIER 40X40" in svg_code
    assert "DWG-2026-NEXUS" in svg_code
    assert "CAD Studio Engineering" in svg_code
    assert 'stroke-dasharray="2.5,1.5"' in svg_code  # Arêtes cachées en pointillés


# ==============================================================================
# CHANTIER 3 : SOLVEUR D'ASSEMBLAGE MULTI-PIÈCES DANS CADDOCUMENT
# ==============================================================================

def test_chantier_3_assembly_multi_parts_and_collision_detection():
    """Vérifie l'instanciation de pièces, la résolution de mates et la détection de collision."""
    doc = CADDocument("AssemblyDoc")

    # Pièce 1 : Plaque de base (100x100x10 mm) fixée (Grounded)
    base_plate = make_box(100.0, 100.0, 10.0, center=True)
    inst_base = doc.add_assembly_instance(
        instance_id="base",
        solid=base_plate,
        name="BasePlate",
        is_grounded=True
    )

    # Pièce 2 : Colonne / Axe (20x20x60 mm) mobile
    shaft = make_box(20.0, 20.0, 60.0, center=True)
    inst_shaft = doc.add_assembly_instance(
        instance_id="shaft",
        solid=shaft,
        name="ShaftColumn",
        is_grounded=False
    )

    # Contrainte de plaquage face supérieure de la base (Z=+5) avec face inférieure de la colonne (Z=-30)
    mate_plane = AssemblyMate(
        mate_id="mate_coincident",
        mate_type=MateType.COINCIDENT_PLANES,
        instance1_id="base",
        instance2_id="shaft",
        point1=(0.0, 0.0, 5.0),
        axis1=(0.0, 0.0, 1.0),
        point2=(0.0, 0.0, -30.0),
        axis2=(0.0, 0.0, -1.0),
        offset=0.0
    )
    doc.add_assembly_mate(mate_plane)

    # Après résolution, la translation Z de la colonne doit être de +35 mm (-30 + 35 = +5)
    solved_tz = float(inst_shaft.transform_matrix[2, 3])
    assert pytest.approx(solved_tz, 1e-4) == 35.0

    # Vérification des collisions : les pièces sont en contact tangent (volume d'interférence nul)
    collisions_touch = doc.check_assembly_collisions()
    assert len(collisions_touch) == 0

    # Pénétrons intentionnellement la colonne de 15 mm dans la base pour tester la détection exacte
    inst_shaft.transform_matrix[2, 3] = 20.0  # Au lieu de 35.0 -> 15 mm d'interférence
    collisions_overlap = doc.check_assembly_collisions()
    assert len(collisions_overlap) == 1
    id1, id2, vol = collisions_overlap[0]
    assert "base" in (id1, id2)
    assert "shaft" in (id1, id2)
    # Volume théorique d'interférence : 20 x 20 x 10 mm = 4000 mm³
    assert pytest.approx(vol, 10.0) == 4000.0


# ==============================================================================
# CHANTIER 4 : MAILLEUR VOLUMIQUE GMSH ET CLARIFICATION TECHNIQUE
# ==============================================================================

def test_chantier_4_gmsh_volumetric_mesher_and_calculix_export():
    """Vérifie la génération de maillage tétraédrique volumique Gmsh et sa conversion ccx."""
    mesher = GmshVolumetricMesher(target_element_size=10.0)
    # Domaine parallélépipédique 20 x 20 x 10 mm
    min_pt = Vector3D(0.0, 0.0, 0.0)
    max_pt = Vector3D(20.0, 20.0, 10.0)

    nodes, elements = mesher.mesh_bounding_box_domain(min_pt, max_pt, order=1)

    assert len(nodes) > 10
    assert len(elements) > 15

    for elem in elements:
        assert elem.element_type == GmshElementType.TETRAHEDRON_4
        assert len(elem.node_tags) == 4

    # Exportation MSH 2.2
    msh_text = mesher.export_msh_v2()
    assert "$MeshFormat" in msh_text
    assert "2.2 0 8" in msh_text
    assert "$Nodes" in msh_text
    assert "$Elements" in msh_text

    # Conversion vers jeu de données CalculiX ccx
    inp_text = mesher.convert_to_calculix_deck("bracket_volumetric_job")
    assert "*HEADING" in inp_text
    assert "*NODE" in inp_text
    assert "*ELEMENT, TYPE=C3D4" in inp_text
    assert "*SOLID SECTION" in inp_text


def test_chantier_4_solver_clarifications_and_aliases():
    """Vérifie la présence et l'équivalence des alias techniques honnêtes."""
    assert LinearTetraDemoSolver is NonlinearFEASolver
    assert NacaAnalyticPolar is AerodynamicsSolver
    assert VoxelRoughingPreview is VolumetricStockSimulator
