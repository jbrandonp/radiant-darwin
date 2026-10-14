"""
Suite de tests d'ingénierie complète pour la parité totale sur les 8 Piliers Industriels.
Vérifie la robustesse mathématique, l'absence de régression et la conformité aux standards
(ISO 1101, ASME Y14.5, IGES 5.3, glTF 2.0, CalculiX ccx, OpenFOAM, SolveSpace).
"""

from __future__ import annotations
import math
import tempfile
import os
import json
import pytest

from src.core.types import Vector3D, Point2D
from src.core.units import (
    PhysicalQuantity, UnitCategory, UnitsParser
)
from src.core.undo_redo import (
    UndoRedoManager, AddFeatureCommand, RemoveFeatureCommand, ModifyParameterCommand
)
from src.core.live_sketch_solver import (
    LiveDragSolver, DragConstraint, DragConstraintType, diagnose_degrees_of_freedom,
    DofDiagnosticStatus
)
from src.core.rolling_ball_blend import RollingBallBlendEngine, SetbackCorner
from src.core.assembly_kinematics import (
    GearMate, RackPinionMate, ScrewMate, BallJointMate, ExplodedViewGenerator, TransmissionSense
)
from src.drawing.drawing_advanced import (
    FeatureControlFrame, GeometricCharacteristic, MaterialCondition, DatumReference,
    BrokenOutSectionView
)
from src.core.iges_exporter import IgesExporter
from src.core.gltf_exporter import GltfExporter, PbrMaterial
from src.fea.calculix_bridge import (
    CalculixSimulationDeck, FeaMaterial, FeaElementType, CalculixResultParser
)
from src.fea.openfoam_bridge import OpenFoamCase, CfdFluidType, CfdTurbulenceModel


# ==============================================================================
# PILIER 8 : SYSTÈME D'UNITÉS PHYSIQUES & ANNULATION TRANSACTIONNELLE
# ==============================================================================

def test_pillar_8_physical_units_and_expressions():
    """Vérifie la conversion et les opérations arithmétiques sur les grandeurs physiques."""
    # 1. Longueurs et additions inter-unités
    q_inch = PhysicalQuantity(2.0, "in")
    q_mm = PhysicalQuantity(10.0, "mm")

    # 2.0 pouces = 50.8 mm -> 50.8 mm + 10 mm = 60.8 mm
    q_sum = q_inch + q_mm
    assert q_sum.category == UnitCategory.LENGTH
    assert pytest.approx(q_sum.value_si, 1e-6) == 0.0608
    assert pytest.approx(q_sum.to("mm").value, 1e-4) == 60.8

    # 2. Évaluation d'expressions textuelles complexes
    val_parsed = UnitsParser.parse_expression("2.5 in + 10 mm", target_unit="mm")
    # 2.5 * 25.4 + 10 = 63.5 + 10 = 73.5 mm
    assert pytest.approx(val_parsed, 1e-4) == 73.5

    # 3. Pression et contrainte
    stress_mpa = PhysicalQuantity(250.0, "mpa")
    assert stress_mpa.category == UnitCategory.PRESSURE
    assert pytest.approx(stress_mpa.value_si, 1e-3) == 2.5e8  # 250 MPa = 2.5e8 Pa


def test_pillar_8_transactional_undo_redo():
    """Vérifie la pile de commandes Undo/Redo sans perte d'état."""
    from src.core.document import CADDocument
    from src.core.feature import BoxFeature

    doc = CADDocument(name="UndoRedoTestDoc")
    manager = UndoRedoManager(document=doc, max_history_depth=20)

    # Étape 1 : Ajout d'une boîte
    box = BoxFeature(feature_id="box_01", name="Box01", width=10.0, height=20.0, depth=30.0)
    cmd1 = AddFeatureCommand(box)
    manager.execute_command(cmd1)

    assert len(doc.features) == 1
    assert doc.get_feature("box_01") is not None
    assert manager.can_undo is True
    assert manager.can_redo is False

    # Étape 2 : Modification du paramètre de hauteur
    cmd2 = ModifyParameterCommand(feature_id="box_01", param_name="height", new_value=50.0)
    manager.execute_command(cmd2)
    assert doc.get_feature("box_01").parameters["height"] == 50.0

    # Étape 3 : Annulation (Undo)
    assert manager.undo() is True
    assert doc.get_feature("box_01").parameters["height"] == 20.0
    assert manager.can_redo is True

    # Étape 4 : Rétablissement (Redo)
    assert manager.redo() is True
    assert doc.get_feature("box_01").parameters["height"] == 50.0

    # Étape 5 : Annuler jusqu'à la racine
    assert manager.undo() is True  # Revient à height 20.0
    assert manager.undo() is True  # Supprime box_01
    assert len(doc.features) == 0
    assert manager.can_undo is False


# ==============================================================================
# PILIER 3 : SOLVEUR D'ESQUISSE INTERACTIF 60 FPS & DIAGNOSTIC DOF
# ==============================================================================

def test_pillar_3_live_drag_solver_and_dof_diagnostic():
    """Vérifie le glisser-déplacer d'esquisse en temps réel et le diagnostic des degrés de liberté."""
    solver = LiveDragSolver(tolerance=1e-5)

    # Contrainte horizontale sur Y = 10.0
    h_constraint = DragConstraint(
        id="c_horiz",
        constraint_type=DragConstraintType.HORIZONTAL,
        entity_indices=(0,),
        target_val=10.0
    )
    # L'utilisateur déplace le curseur vers (55.0, 32.0)
    dragged_pos = Point2D(55.0, 32.0)
    solved_pos = solver.live_drag_step(
        dragged_index=0,
        target_pos=dragged_pos,
        active_constraints=[h_constraint]
    )

    # Y doit être projeté exactement sur la droite horizontale Y=10.0
    assert pytest.approx(solved_pos.x, 1e-4) == 55.0
    assert pytest.approx(solved_pos.y, 1e-4) == 10.0

    # Diagnostic DoF
    diag_under = diagnose_degrees_of_freedom(num_points=3, num_independent_constraints=4)
    assert diag_under.status == DofDiagnosticStatus.UNDER_CONSTRAINED
    assert diag_under.degrees_of_freedom == 2  # 3*2 - 4 = 2
    assert diag_under.color_hex == "#2563eb"  # Bleu sous-contraint

    diag_fully = diagnose_degrees_of_freedom(num_points=2, num_independent_constraints=4)
    assert diag_fully.status == DofDiagnosticStatus.FULLY_CONSTRAINED
    assert diag_fully.degrees_of_freedom == 0
    assert diag_fully.color_hex == "#16a34a"  # Vert entièrement contraint


# ==============================================================================
# PILIER 1 : CONGÉS ANALYTIQUES À SPHÈRE ROULANTE & COINS À RETRAIT
# ==============================================================================

def test_pillar_1_rolling_ball_blend_and_setback_corner():
    """Vérifie le calcul de la trajectoire de la sphère roulante et des coins à retrait."""
    engine = RollingBallBlendEngine(tolerance=1e-6)

    # Arête le long de l'axe X entre deux plans perpendiculaires (Y=0 et Z=0)
    edge_start = Vector3D(0.0, 0.0, 0.0)
    edge_end = Vector3D(100.0, 0.0, 0.0)
    normal_a = Vector3D(0.0, 1.0, 0.0)  # Face horizontale
    normal_b = Vector3D(0.0, 0.0, 1.0)  # Face verticale
    radius = 5.0

    spines = engine.compute_spine_trajectory(
        edge_start=edge_start,
        edge_end=edge_end,
        normal_face_a=normal_a,
        normal_face_b=normal_b,
        radius=radius,
        num_samples=10
    )
    assert len(spines) == 11
    # La sphère doit être décalée de (R, R) sur le plan YZ
    first_center = spines[0].center
    assert pytest.approx(first_center.y, 1e-4) == radius
    assert pytest.approx(first_center.z, 1e-4) == radius

    # Génération du maillage de congé
    verts, tris = engine.generate_blend_mesh(spines, arc_subdivisions=6)
    assert len(verts) > 50
    assert len(tris) > 50

    # Coin à retrait au sommet (0, 0, 0) où 3 arêtes se rencontrent
    vertex = Vector3D(0.0, 0.0, 0.0)
    edges = [
        ("e_x", vertex, Vector3D(100.0, 0.0, 0.0)),
        ("e_y", vertex, Vector3D(0.0, 100.0, 0.0)),
        ("e_z", vertex, Vector3D(0.0, 0.0, 100.0)),
    ]
    corner = engine.compute_setback_corner(vertex, edges, setback=8.0)
    assert len(corner.corner_patch_vertices) == 4  # 1 centre + 3 sommets rognés
    assert len(corner.corner_patch_triangles) == 3


# ==============================================================================
# PILIER 4 : LIAISONS CINÉMATIQUES AVANCÉES & VUES ÉCLATÉES
# ==============================================================================

def test_pillar_4_assembly_kinematics_and_exploded_views():
    """Vérifie la cinématique des engrenages, pignons-crémaillères, vis et vues éclatées."""
    # 1. GearMate
    gear = GearMate(
        id="gear_pair_01",
        part_a_id="pinion",
        part_b_id="wheel",
        axis_a_origin=Vector3D(0, 0, 0),
        axis_a_direction=Vector3D(0, 0, 1),
        axis_b_origin=Vector3D(100, 0, 0),
        axis_b_direction=Vector3D(0, 0, 1),
        teeth_a=20,
        teeth_b=60,
        transmission=TransmissionSense.OPPOSITE
    )
    # Rapport 1/3, sens inverse
    angle_b = gear.compute_driven_angle(math.pi)
    assert pytest.approx(angle_b, 1e-6) == -math.pi / 3.0

    # 2. RackPinionMate
    rp = RackPinionMate(
        id="rp_01",
        pinion_part_id="p1",
        rack_part_id="r1",
        pinion_axis_origin=Vector3D(0, 0, 0),
        pinion_axis_direction=Vector3D(0, 0, 1),
        rack_linear_axis=Vector3D(1, 0, 0),
        pitch_radius_mm=25.0
    )
    # delta_x = 25 * pi mm
    disp = rp.compute_rack_displacement(math.pi)
    assert pytest.approx(disp.x, 1e-4) == 25.0 * math.pi
    assert disp.y == 0.0

    # 3. ScrewMate
    screw = ScrewMate(
        id="screw_01",
        screw_part_id="lead_screw",
        nut_part_id="carriage",
        axis_origin=Vector3D(0, 0, 0),
        axis_direction=Vector3D(0, 0, 1),
        pitch_mm=5.0  # 5 mm par tour
    )
    # 2 tours (4*pi rad) -> 10 mm
    advance = screw.compute_axial_advance(4.0 * math.pi)
    assert pytest.approx(advance.z, 1e-4) == 10.0

    # 4. BallJointMate
    ball = BallJointMate(
        id="bj_01",
        part_a_id="socket",
        part_b_id="ball_stud",
        pivot_center_a=Vector3D(10, 20, 30),
        pivot_center_b=Vector3D(10, 20, 30)
    )
    assert ball.evaluate_constraint_residual() == 0.0

    # 5. ExplodedViewGenerator
    exploded_gen = ExplodedViewGenerator()
    exploded_gen.add_step(part_id="nut", direction=Vector3D(0, 0, 1), distance_mm=80.0, order=1)
    exploded_gen.add_step(part_id="washer", direction=Vector3D(0, 0, 1), distance_mm=50.0, order=2)

    positions = {
        "nut": Vector3D(0, 0, 10),
        "washer": Vector3D(0, 0, 8),
        "body": Vector3D(0, 0, 0)
    }
    exploded_pos = exploded_gen.compute_exploded_positions(positions, explosion_factor=1.0)
    assert pytest.approx(exploded_pos["nut"].z, 1e-4) == 90.0
    assert pytest.approx(exploded_pos["washer"].z, 1e-4) == 58.0
    assert exploded_pos["body"].z == 0.0


# ==============================================================================
# PILIER 5 : TECHDRAW COUPES BRISÉES & CADRES GD&T ISO 1101 / ASME Y14.5
# ==============================================================================

def test_pillar_5_techdraw_broken_sections_and_gdt():
    """Vérifie la génération des coupes brisées et des cadres de tolérancement GD&T."""
    # 1. Feature Control Frame (Localisation avec Datum A, B, C)
    fcf = FeatureControlFrame(
        characteristic=GeometricCharacteristic.POSITION,
        tolerance_value=0.05,
        is_diameter_zone=True,
        material_condition=MaterialCondition.MAXIMUM_MATERIAL,
        primary_datum=DatumReference("A"),
        secondary_datum=DatumReference("B", MaterialCondition.MAXIMUM_MATERIAL),
        tertiary_datum=DatumReference("C")
    )
    svg_output = fcf.render_svg(x=100.0, y=150.0)
    assert "<rect" in svg_output
    assert "⌖" in svg_output
    assert "Ø 0.050 M" in svg_output
    assert "A" in svg_output
    assert "B M" in svg_output
    assert "C" in svg_output

    # 2. Broken-Out Section View
    polygon = [
        Point2D(0.0, 0.0),
        Point2D(50.0, 0.0),
        Point2D(50.0, 30.0),
        Point2D(0.0, 30.0)
    ]
    broken_sec = BrokenOutSectionView(
        view_id="view_front",
        boundary_polygon=polygon,
        cutting_depth_mm=12.5,
        hatch_spacing_mm=5.0
    )
    # Point au centre doit être à l'intérieur
    assert broken_sec.is_point_inside_cutout(Point2D(25.0, 15.0)) is True
    # Point extérieur
    assert broken_sec.is_point_inside_cutout(Point2D(60.0, 15.0)) is False

    hatch_lines = broken_sec.generate_hatch_lines(bounding_box=(0.0, 0.0, 50.0, 30.0))
    assert len(hatch_lines) > 0


# ==============================================================================
# PILIER 6 : EXPORTATEURS IGES 5.3 & GLTF 2.0 PBR
# ==============================================================================

def test_pillar_6_iges_and_gltf_exporters():
    """Vérifie la structure stricte des fichiers IGES 5.3 (80 colonnes) et glTF 2.0 JSON."""
    verts = [
        Vector3D(0.0, 0.0, 0.0),
        Vector3D(10.0, 0.0, 0.0),
        Vector3D(0.0, 10.0, 0.0)
    ]
    tris = [(0, 1, 2)]
    lines = [(Vector3D(0, 0, 0), Vector3D(10, 0, 0))]

    # 1. IGES 5.3
    iges_exp = IgesExporter()
    iges_text = iges_exp.export_iges_lines_and_mesh(lines, verts, tris)
    # Chaque ligne doit comporter exactement 80 caractères + '\n' = 81 caractères
    for idx, line in enumerate(iges_text.splitlines()):
        assert len(line) == 80, f"Line {idx} length is {len(line)} != 80"
    assert "S      1" in iges_text
    assert "G      1" in iges_text
    assert "D      1" in iges_text
    assert "P      1" in iges_text
    assert "T      1" in iges_text

    # 2. glTF 2.0 PBR
    gltf_exp = GltfExporter()
    mat = PbrMaterial(name="Titanium", base_color_rgba=(0.9, 0.9, 0.9, 1.0), metallic_factor=0.9, roughness_factor=0.1)
    gltf_str = gltf_exp.export_mesh_to_gltf(verts, tris, mat)
    gltf_obj = json.loads(gltf_str)

    assert gltf_obj["asset"]["version"] == "2.0"
    assert len(gltf_obj["materials"]) == 1
    assert gltf_obj["materials"][0]["name"] == "Titanium"
    assert gltf_obj["materials"][0]["pbrMetallicRoughness"]["metallicFactor"] == 0.9
    assert "data:application/octet-stream;base64," in gltf_obj["buffers"][0]["uri"]


# ==============================================================================
# PILIER 7 : PASSERELLES CALCULIX FEA & OPENFOAM CFD
# ==============================================================================

def test_pillar_7_calculix_and_openfoam_bridges():
    """Vérifie la génération des jeux de données CalculiX .inp et de l'arborescence OpenFOAM."""
    # 1. CalculiX Simulation Deck
    deck = CalculixSimulationDeck(
        job_name="bracket_stress_analysis",
        material=FeaMaterial(name="Steel_S235", young_modulus_mpa=210000.0, poisson_ratio=0.3),
        element_type=FeaElementType.C3D4
    )
    deck.add_node(1, Vector3D(0, 0, 0))
    deck.add_node(2, Vector3D(10, 0, 0))
    deck.add_node(3, Vector3D(0, 10, 0))
    deck.add_node(4, Vector3D(0, 0, 10))
    deck.add_tetrahedron(1, [1, 2, 3, 4])
    deck.fix_node(1)
    deck.apply_load(node_id=2, direction_dof=3, magnitude_n=-500.0)

    inp_content = deck.generate_inp_deck()
    assert "*HEADING" in inp_content
    assert "*NODE" in inp_content
    assert "1, 0.000000, 0.000000, 0.000000" in inp_content
    assert "*ELEMENT, TYPE=C3D4, ELSET=EALL" in inp_content
    assert "*MATERIAL, NAME=STEEL_S235" in inp_content
    assert "*BOUNDARY" in inp_content
    assert "NFIXED, 1, 3, 0.0" in inp_content
    assert "*CLOAD" in inp_content
    assert "2, 3, -500.0000" in inp_content

    # Parseur de résultats
    sample_frd = """
    -4  DISP
    1  0.000000  0.000000  0.000000
    2  0.001200 -0.000300 -0.045000
    -3
    """
    parser = CalculixResultParser()
    disp_results = parser.parse_nodal_displacements(sample_frd)
    assert 2 in disp_results
    assert pytest.approx(disp_results[2].z, 1e-6) == -0.045000

    # 2. OpenFOAM CFD Case Directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        cfd_case = OpenFoamCase(
            case_name="airfoil_cfd_test",
            domain_min=Vector3D(-50, -20, -5),
            domain_max=Vector3D(100, 20, 5),
            fluid=CfdFluidType.AIR_20C,
            turbulence_model=CfdTurbulenceModel.K_EPSILON,
            inlet_velocity=Vector3D(25.0, 0.0, 0.0),
            max_iterations=300
        )
        written_files = cfd_case.write_case_to_directory(tmp_dir)

        # Vérification des fichiers écrits
        assert os.path.exists(os.path.join(tmp_dir, "0", "U"))
        assert os.path.exists(os.path.join(tmp_dir, "0", "p"))
        assert os.path.exists(os.path.join(tmp_dir, "constant", "transportProperties"))
        assert os.path.exists(os.path.join(tmp_dir, "constant", "turbulenceProperties"))
        assert os.path.exists(os.path.join(tmp_dir, "system", "controlDict"))
        assert os.path.exists(os.path.join(tmp_dir, "system", "blockMeshDict"))

        with open(os.path.join(tmp_dir, "0", "U"), "r", encoding="utf-8") as f:
            u_text = f.read()
            assert "uniform (25.0 0.0 0.0);" in u_text
            assert "class       volVectorField;" in u_text
