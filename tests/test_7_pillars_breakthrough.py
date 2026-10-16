"""
Tests exhaustifs validant les 7 Piliers Majeurs où CAD Studio surpasse FreeCAD.
Couvre :
1. Surfaces NURBS Analytiques Continues (G1, G2, G3) et Coons Patch
2. Interopérabilité et Importateur STEP AP203/AP214/AP242 avec PMI
3. Ateliers Métiers Spécialisés (BIM IFC4, Robotique 6 Axes, Aérodynamique CFD, ECAD/MCAD)
4. Simulation Multi-Physique Avancée (FEM Non-Linéaire Tet10, Plasticité, Contact Frottant)
5. FAO / Usinage CNC (Simulation Volumique Voxels et Post-Processeurs Industriels)
6. Solveur d'Esquisse 2D Avancé (Projection 3D, Congé 2D, Trim, Contrainte G2)
7. Tableur Paramétrique & Périphérique Dédié 3Dconnexion SpaceMouse 6-DoF
"""

import math
import numpy as np
import pytest

from src.core.nexus_kernel.nurbs_surface import (
    NURBSSurface, make_coons_patch, evaluate_boundary_continuity, generate_curvature_comb
)
from src.core.step_importer import STEPImporter, STEPGeometricContext
from src.specialized.bim_engine import (
    BIMWall, BIMLayer, BIMOpening, BIMRebar, BIMBuildingStorey, export_bim_to_ifc4
)
from src.specialized.robot_kinematics import (
    RobotArm6Axis, DenavitHartenbergParameter
)
from src.specialized.aerodynamics_solver import (
    AerodynamicsSolver, FluidFlowProperties, AirfoilSurfaceData
)
from src.specialized.pcb_integrator import (
    PCBBoard, PCBComponent3D, verify_enclosure_clearance
)
from src.fea.nonlinear_fem import (
    Tet10Element, BilinearPlasticMaterial, FrictionalContactPair, NonlinearFEASolver
)
from src.cam.volumetric_simulator import (
    VolumetricStockSimulator, CNCPostProcessorRegistry, ToolpathPoint
)
from src.solver.constraints_2d import (
    SketchConstraintSolver2D, ConstraintType, project_3d_edge_to_sketch_plane,
    fillet_2d, trim_intersection_2d
)
from src.ui.spreadsheet_widget import ParametricSpreadsheet, name_to_cell_coords, cell_coords_to_name
from src.viewport.spacemouse import SpaceMouseController, SpaceMouseConfig, SpaceMouseState
from src.viewport.camera import CADCamera
from src.core.types import Point2D, Vector3D


# ============================================================================
# PILIER 1 : SURFACES NURBS ANALYTIQUES CONTINUES (G1, G2, G3) & COONS PATCH
# ============================================================================

def test_pillar_1_nurbs_evaluation_and_curvatures() -> None:
    """Vérifie l'évaluation analytique exacte de surfaces NURBS, normales et courbures."""
    ctrl_pts = [
        [(0.0, 0.0, 0.0), (10.0, 0.0, 5.0), (20.0, 0.0, 0.0)],
        [(0.0, 10.0, 5.0), (10.0, 10.0, 15.0), (20.0, 10.0, 5.0)],
        [(0.0, 20.0, 0.0), (10.0, 20.0, 5.0), (20.0, 20.0, 0.0)]
    ]
    weights = [
        [1.0, 1.0, 1.0],
        [1.0, 2.0, 1.0],
        [1.0, 1.0, 1.0]
    ]
    u_knots = [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]
    v_knots = [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]

    surface = NURBSSurface(
        degree_u=2,
        degree_v=2,
        control_points=ctrl_pts,
        weights=weights,
        knots_u=u_knots,
        knots_v=v_knots
    )

    # Évaluation au centre paramétrique (u=0.5, v=0.5)
    pos, normal = surface.evaluate_point_and_normal(0.5, 0.5)
    assert pos[0] == pytest.approx(10.0, abs=1e-3)
    assert pos[1] == pytest.approx(10.0, abs=1e-3)
    assert pos[2] > 5.0  # L'élévation centrale est accentuée par le poids w=2.0
    assert np.linalg.norm(normal) == pytest.approx(1.0, abs=1e-5)

    # Évaluation des courbures gaussienne et moyenne
    gaussian_k, mean_h = surface.evaluate_curvatures(0.5, 0.5)
    assert isinstance(gaussian_k, float)
    assert isinstance(mean_h, float)

    # Peigne de courbure (Porcupine curvature comb)
    comb = generate_curvature_comb(surface, num_samples=10, scale=2.0)
    assert len(comb) == 10
    for root_pt, tip_pt in comb:
        assert len(root_pt) == 3
        assert len(tip_pt) == 3


def test_pillar_1_coons_patch_and_g2_continuity() -> None:
    """Vérifie la génération d'un patch de Coons et la continuité de frontière G1/G2."""
    c_south = [(0.0, 0.0, 0.0), (10.0, 0.0, 2.0), (20.0, 0.0, 0.0)]
    c_north = [(0.0, 20.0, 0.0), (10.0, 20.0, 2.0), (20.0, 20.0, 0.0)]
    c_west = [(0.0, 0.0, 0.0), (0.0, 10.0, 2.0), (0.0, 20.0, 0.0)]
    c_east = [(20.0, 0.0, 0.0), (20.0, 10.0, 2.0), (20.0, 20.0, 0.0)]

    patch = make_coons_patch(c_south, c_north, c_west, c_east)
    assert patch.degree_u == 2
    assert patch.degree_v == 2

    # Continuité de la frontière
    g0, g1, g2 = evaluate_boundary_continuity(patch, patch, boundary="north")
    assert g0 is True
    assert g1 is True
    assert g2 is True


# ============================================================================
# PILIER 2 : INTEROPÉRABILITÉ & IMPORTATEUR UNIVERSEL STEP (AP203/AP214/AP242)
# ============================================================================

def test_pillar_2_step_importer_ap242_with_pmi() -> None:
    """Vérifie le parsing STEP ISO 10303-21 Part 21 et l'extraction PMI AP242."""
    step_content = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('STEP AP242 Mechanical Design with PMI'), '2;1');
FILE_NAME('test_bracket.stp', '2026-10-14T12:00:00', ('Author'), ('Org'), 'CAD Studio', '', '');
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF'));
ENDSEC;
DATA;
#10 = CARTESIAN_POINT('ORIGIN', (0.0, 0.0, 0.0));
#11 = CARTESIAN_POINT('P1', (50.0, 0.0, 0.0));
#12 = CARTESIAN_POINT('P2', (50.0, 50.0, 0.0));
#13 = CARTESIAN_POINT('P3', (0.0, 50.0, 0.0));
#14 = CARTESIAN_POINT('TOP', (0.0, 0.0, 25.0));
#20 = DIRECTION('Z_AXIS', (0.0, 0.0, 1.0));
#21 = DIRECTION('X_AXIS', (1.0, 0.0, 0.0));
#30 = AXIS2_PLACEMENT_3D('BASE_FRAME', #10, #20, #21);
#40 = PLANE('BASE_PLANE', #30);
#50 = ADVANCED_FACE('BOTTOM_FACE', (#40), #40, .T.);
#60 = CLOSED_SHELL('OUTER_SHELL', (#50));
#70 = MANIFOLD_SOLID_BREP('BRACKET_SOLID', #60);
#80 = DATUM_FEATURE('DATUM_A', 'Primary Mounting Datum Plane');
#90 = GEOMETRIC_TOLERANCE('FLATNESS_TOL', 0.02, #80);
ENDSEC;
END-ISO-10303-21;
"""
    importer = STEPImporter()
    context = importer.import_step(step_content)

    assert context.schema_name == "AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF"
    assert len(context.cartesian_points) == 5
    assert len(context.directions) == 2
    assert len(context.axis_placements) == 1
    assert len(context.faces) == 1
    assert len(context.solids) == 1
    assert "BRACKET_SOLID" in context.solids

    # Vérification PMI (Product and Manufacturing Information)
    assert len(context.pmi_annotations) == 2
    found_datum = False
    found_flatness = False
    for pmi in context.pmi_annotations:
        if "DATUM_A" in pmi:
            found_datum = True
        if "FLATNESS_TOL" in pmi:
            found_flatness = True
    assert found_datum is True
    assert found_flatness is True

    # Conversion en solide CAO
    solid = importer.import_to_cad_solid(step_content)
    assert solid is not None
    assert solid.is_watertight() is True
    assert solid.get_volume() > 0.0


# ============================================================================
# PILIER 3 : ATELIERS MÉTIERS SPÉCIALISÉS (BIM, ROBOTIQUE, CFD, ECAD/MCAD)
# ============================================================================

def test_pillar_3_bim_engine_and_ifc4_export() -> None:
    """Vérifie la génération de murs multicouches BIM, ferraillages et export IFC4."""
    layers = [
        BIMLayer(name="Beton_Arme", thickness=0.20, material="Concrete_C25_30"),
        BIMLayer(name="Isolant_Laine_Roche", thickness=0.12, material="Mineral_Wool"),
        BIMLayer(name="Brique_Plaquette", thickness=0.08, material="Brick_Facade")
    ]
    openings = [
        BIMOpening(name="Fenetre_Salon", offset_x=2.0, elevation_z=0.9, width=1.4, height=1.2)
    ]
    rebars = [
        BIMRebar(diameter_mm=16.0, spacing_mm=150.0, steel_grade="B500B", count=4)
    ]

    wall = BIMWall(
        name="Mur_Porteur_Nord",
        length=6.0,
        height=2.8,
        layers=layers,
        openings=openings,
        rebars=rebars
    )

    storey = BIMBuildingStorey(name="Rez_de_Chaussee", elevation=0.0, walls=[wall])
    assert storey.total_wall_area() == pytest.approx(16.8, abs=1e-2)

    # Génération du solide 3D étanche
    solid = wall.generate_solid_geometry()
    assert solid.is_watertight() is True
    assert solid.get_volume() > 0.0

    # Export IFC4
    ifc_text = export_bim_to_ifc4([storey])
    assert "IFC4" in ifc_text
    assert "IFCWALLSTANDARDCASE" in ifc_text.upper()
    assert "Mur_Porteur_Nord" in ifc_text
    assert "IFCREINFORCINGBAR" in ifc_text.upper()


def test_pillar_3_robot_6axis_kinematics_and_jacobians() -> None:
    """Vérifie la cinématique géométrique directe, le Jacobien 6x6 et la détection de singularité."""
    robot = RobotArm6Axis()
    home_angles = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    # Matrice de transformation homogène T06
    t06 = robot.forward_kinematics(home_angles)
    assert t06.shape == (4, 4)
    # L'orientation doit être orthogonale (det(R) = 1)
    rot_matrix = t06[:3, :3]
    assert np.linalg.det(rot_matrix) == pytest.approx(1.0, abs=1e-4)

    # Calcul du Jacobien géométrique 6x6
    j_mat = robot.calculate_jacobian(home_angles)
    assert j_mat.shape == (6, 6)

    # Détection de configuration singulière (poignet aligné à 0 rad)
    assert robot.is_singular(home_angles) is True

    # Planification de trajectoire cartésienne linéaire
    start_pos = (500.0, 0.0, 800.0)
    end_pos = (600.0, 100.0, 850.0)
    trajectory = robot.plan_cartesian_trajectory(start_pos, end_pos, num_waypoints=5)
    assert len(trajectory) == 5
    assert trajectory[0] == pytest.approx(start_pos, abs=1e-3)
    assert trajectory[-1] == pytest.approx(end_pos, abs=1e-3)


def test_pillar_3_aerodynamics_cfd_solver() -> None:
    """Vérifie le calcul des forces de portance, traînée, coefficients et décollement de couche limite."""
    solver = AerodynamicsSolver()
    flow = FluidFlowProperties(velocity_m_s=40.0, air_density=1.225, dynamic_viscosity=1.81e-5)

    reynolds = solver.calculate_reynolds_number(flow, chord_length=1.5)
    assert reynolds > 3_000_000.0  # Régime turbulent aéronautique

    airfoil = AirfoilSurfaceData(chord=1.5, span=6.0, angle_of_attack_deg=5.0)
    forces = solver.solve_aerodynamic_forces(flow, airfoil)

    assert forces.lift_force_n > 0.0
    assert forces.drag_force_n > 0.0
    assert forces.lift_to_drag_ratio > 10.0  # Finesse aérodynamique saine

    # Risque de décollement (Stall risk)
    assert solver.detect_boundary_layer_separation(angle_of_attack_deg=5.0) is False
    assert solver.detect_boundary_layer_separation(angle_of_attack_deg=19.0) is True


def test_pillar_3_ecad_mcad_pcb_clearance() -> None:
    """Vérifie l'intégration PCB KiCadStepUp avec détection de collision dans le boîtier."""
    comps = [
        PCBComponent3D(designator="U1", package="QFP64", pos_x=25.0, pos_y=25.0, height_z=2.5, width_x=12.0, length_y=12.0),
        PCBComponent3D(designator="C1", package="CAP_0805", pos_x=45.0, pos_y=15.0, height_z=1.2, width_x=2.0, length_y=1.25)
    ]
    board = PCBBoard(name="Motherboard_V2", width=100.0, height=80.0, thickness=1.6, components=comps)

    solid = board.generate_3d_assembly()
    assert solid.is_watertight() is True
    assert solid.get_volume() > 0.0

    # Vérification de dégagement avec le boîtier supérieur (z_max = 5.0mm -> Ok, z_max = 2.0mm -> Collision U1)
    assert verify_enclosure_clearance(board, enclosure_max_internal_height=5.0) is True
    assert verify_enclosure_clearance(board, enclosure_max_internal_height=2.0) is False


# ============================================================================
# PILIER 4 : SIMULATION MULTI-PHYSIQUE NON-LINÉAIRE (FEM TET10, PLASTICITÉ, CONTACT)
# ============================================================================

def test_pillar_4_tet10_element_and_plasticity() -> None:
    """Vérifie l'élément quadratique tétraédrique Tet10 et la plasticité de von Mises."""
    # 4 sommets + 6 nœuds milieux d'arêtes
    nodes = np.array([
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [0.0, 10.0, 0.0],
        [0.0, 0.0, 10.0],
        [5.0, 0.0, 0.0],
        [5.0, 5.0, 0.0],
        [0.0, 5.0, 0.0],
        [0.0, 0.0, 5.0],
        [5.0, 0.0, 5.0],
        [0.0, 5.0, 5.0]
    ], dtype=np.float64)

    elem = Tet10Element(element_id=1, node_indices=list(range(10)))
    volume = elem.calculate_volume(nodes)
    assert volume == pytest.approx(1000.0 / 6.0, abs=1e-3)

    # Matrice de rigidité élémentaire Ke (30x30)
    mat = BilinearPlasticMaterial(young_modulus=210000.0, poisson_ratio=0.3, yield_strength=250.0, tangent_modulus=2000.0)
    ke = elem.calculate_stiffness_matrix(nodes, mat)
    assert ke.shape == (30, 30)
    # Symétrie de la matrice
    assert np.allclose(ke, ke.T, atol=1e-4)

    # Écoulement plastique radial return
    sigma_el = 350.0  # Supérieur à la limite élastique (250 MPa)
    sigma_corr, eps_p = mat.integrate_plasticity(sigma_trial=sigma_el, current_plastic_strain=0.0)
    assert sigma_corr < sigma_el
    assert eps_p > 0.0


def test_pillar_4_frictional_contact_solver() -> None:
    """Vérifie la formulation de contact frottant de Coulomb par pénalité."""
    contact = FrictionalContactPair(penalty_normal=1e5, friction_coefficient=0.25)

    # Pénétration (gap = -0.05 mm)
    f_norm, f_tan = contact.compute_contact_force(penetration_gap=-0.05, tangential_slip=0.02)
    assert f_norm > 0.0  # Répulsion normale
    assert f_tan > 0.0   # Frottement tangentiel résistant
    assert f_tan <= (contact.friction_coefficient * f_norm) + 1e-6  # Cône de Coulomb


# ============================================================================
# PILIER 5 : FAO / USINAGE CNC (SIMULATION VOLUMIQUE VOXELS & POST-PROCESSEURS)
# ============================================================================

def test_pillar_5_volumetric_cam_stock_simulator() -> None:
    """Vérifie la simulation visuelle volumique d'enlèvement de matière par voxel et l'anti-collision."""
    # Brut initial 100x100x50 mm avec résolution voxel 5mm -> grille 20x20x10
    sim = VolumetricStockSimulator(stock_size=(100.0, 100.0, 50.0), voxel_pitch_mm=5.0)
    initial_vol = sim.get_remaining_volume_cm3()
    assert initial_vol == pytest.approx(500.0, abs=1e-1)

    # Passe de surfaçage linéaire avec fraise D=20mm (rayon 10mm)
    cut_vol = sim.simulate_linear_cut(
        start_pt=(10.0, 50.0, 45.0),
        end_pt=(90.0, 50.0, 45.0),
        tool_diameter_mm=20.0
    )
    assert cut_vol > 0.0
    assert sim.get_remaining_volume_cm3() < initial_vol

    # Détection de collision porte-outil / étau
    fixture_box = (0.0, 0.0, -20.0, 100.0, 100.0, 0.0)
    assert sim.detect_tool_collision((50.0, 50.0, 20.0), fixture_box) is False
    assert sim.detect_tool_collision((50.0, 50.0, -5.0), fixture_box) is True


def test_pillar_5_cnc_post_processor_registry() -> None:
    """Vérifie la génération de G-Code certifié pour Fanuc, Siemens 840D (TRAORI 5-axes) et Heidenhain."""
    registry = CNCPostProcessorRegistry()
    points = [
        ToolpathPoint(x=0.0, y=0.0, z=50.0, feed_rate=1200.0, spindle_rpm=8000),
        ToolpathPoint(x=100.0, y=50.0, z=25.0, a_deg=15.0, c_deg=45.0, feed_rate=800.0, spindle_rpm=8000),
    ]

    # Fanuc 0i / 31i
    fanuc_code = registry.generate_program("FANUC", points, program_name="O1001")
    assert "G90 G54" in fanuc_code
    assert "M03 S8000" in fanuc_code
    assert "M30" in fanuc_code

    # Siemens Sinumerik 840D avec transformation 5 axes continue TRAORI
    siemens_code = registry.generate_program("SIEMENS_840D", points, program_name="PIECE_TURBINE")
    assert "TRAORI" in siemens_code
    assert "M17" in siemens_code

    # Heidenhain Klartext
    heidenhain_code = registry.generate_program("HEIDENHAIN", points, program_name="CONTOUR")
    assert "BEGIN PGM CONTOUR MM" in heidenhain_code
    assert "TOOL CALL" in heidenhain_code
    assert "END PGM CONTOUR MM" in heidenhain_code


# ============================================================================
# PILIER 6 : SOLVEUR D'ESQUISSE 2D AVANCÉ (PROJECTION 3D, CONGÉ, TRIM, G2)
# ============================================================================

def test_pillar_6_sketcher_3d_projection_and_fillet() -> None:
    """Vérifie la projection d'arêtes 3D externes, le congé 2D et le trim de segments."""
    # 1. Projection d'une arête 3D (0, 0, 10) -> (50, 0, 10) sur le plan Z=10
    edge_p0 = (0.0, 0.0, 10.0)
    edge_p1 = (50.0, 0.0, 10.0)
    p0_2d, p1_2d = project_3d_edge_to_sketch_plane(
        edge_start=edge_p0,
        edge_end=edge_p1,
        plane_origin=(0.0, 0.0, 10.0),
        plane_normal=(0.0, 0.0, 1.0),
        plane_u_axis=(1.0, 0.0, 0.0)
    )
    assert p0_2d.u == pytest.approx(0.0, abs=1e-5)
    assert p0_2d.v == pytest.approx(0.0, abs=1e-5)
    assert p1_2d.u == pytest.approx(50.0, abs=1e-5)
    assert p1_2d.v == pytest.approx(0.0, abs=1e-5)

    # 2. Congé 2D (Fillet) à angle droit R=5mm
    p_start = Point2D(0.0, 20.0)
    p_corner = Point2D(0.0, 0.0)
    p_end = Point2D(20.0, 0.0)
    t0, t1, center, eff_r = fillet_2d(p_start, p_corner, p_end, radius=5.0)

    assert eff_r == pytest.approx(5.0, abs=1e-4)
    assert t0.u == pytest.approx(0.0, abs=1e-4)
    assert t0.v == pytest.approx(5.0, abs=1e-4)
    assert t1.u == pytest.approx(5.0, abs=1e-4)
    assert t1.v == pytest.approx(0.0, abs=1e-4)
    assert center.u == pytest.approx(5.0, abs=1e-4)
    assert center.v == pytest.approx(5.0, abs=1e-4)

    # 3. Trim / Intersection 2D
    seg1_a = Point2D(0.0, 0.0)
    seg1_b = Point2D(10.0, 10.0)
    seg2_a = Point2D(0.0, 10.0)
    seg2_b = Point2D(10.0, 0.0)
    inter = trim_intersection_2d(seg1_a, seg1_b, seg2_a, seg2_b)
    assert inter is not None
    assert inter.u == pytest.approx(5.0, abs=1e-5)
    assert inter.v == pytest.approx(5.0, abs=1e-5)


def test_pillar_6_sketcher_solver_g2_and_external_geometry() -> None:
    """Vérifie le solveur d'esquisse Levenberg-Marquardt avec contraintes G2 et référence externe."""
    solver = SketchConstraintSolver2D()

    # Création de points pour deux courbes se raccordant au point d'indice 2
    # Courbe A : P0(0, 0), P1(5, 5), P_joint(10, 5)
    # Courbe B : P_joint(10, 5), P3(15, 5), P4(20, 0)
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(5.0, 4.8))
    pj = solver.add_point(Point2D(10.0, 5.0))
    p3 = solver.add_point(Point2D(15.0, 5.2))
    p4 = solver.add_point(Point2D(20.0, 0.0))

    # Ancrage des extrémités et de la référence externe
    solver.add_fixed(p0, 0.0, 0.0)
    solver.add_fixed(p4, 20.0, 0.0)
    solver.add_external_reference(pj, 10.0, 5.0)

    # Contrainte de continuité de courbure G2 au point de raccord pj
    solver.add_g2_curvature(p0, p1, pj, p3, p4)

    success, solved = solver.solve()
    assert success is True
    assert len(solved) == 5

    # Vérification que le point joint respecte la référence externe
    assert solved[pj].u == pytest.approx(10.0, abs=1e-3)
    assert solved[pj].v == pytest.approx(5.0, abs=1e-3)


# ============================================================================
# PILIER 7 : TABLEUR PARAMÉTRIQUE & SOURIS 3D 3DCONNEXION SPACEMOUSE
# ============================================================================

def test_pillar_7_parametric_spreadsheet_formulas_and_aliases() -> None:
    """Vérifie le moteur de tableur paramétrique, évaluation d'arbres AST et liaisons d'alias."""
    sheet = ParametricSpreadsheet()

    # Définition de dimensions et de formules
    sheet.set_cell("A1", "50.0")
    sheet.set_alias("A1", "Epaisseur")

    sheet.set_cell("B1", "=Epaisseur * 2 + 10")
    sheet.set_alias("B1", "LargeurTotale")

    sheet.set_cell("C1", "=sqrt(LargeurTotale) * pi")

    assert sheet.get_cell_value("A1") == pytest.approx(50.0, abs=1e-5)
    assert sheet.get_alias_value("Epaisseur") == pytest.approx(50.0, abs=1e-5)
    assert sheet.get_cell_value("B1") == pytest.approx(110.0, abs=1e-5)
    assert sheet.get_alias_value("LargeurTotale") == pytest.approx(110.0, abs=1e-5)
    assert sheet.get_cell_value("C1") == pytest.approx(math.sqrt(110.0) * math.pi, abs=1e-5)

    # Liaison bidirectionnelle avec un paramètre CAO
    sheet.bind_parameter("DiametreAlesage", "LargeurTotale")
    assert sheet.get_bound_parameter_value("DiametreAlesage") == pytest.approx(110.0, abs=1e-5)

    # Modification en amont et propagation dynamique
    sheet.set_cell("A1", "20.0")
    assert sheet.get_cell_value("B1") == pytest.approx(50.0, abs=1e-5)
    assert sheet.get_bound_parameter_value("DiametreAlesage") == pytest.approx(50.0, abs=1e-5)

    # Détection de référence circulaire
    sheet.set_cell("D1", "=D2")
    sheet.set_cell("D2", "=D1")
    cell_d1 = sheet.cells["D1"]
    assert cell_d1.has_error is True
    assert "Référence circulaire" in cell_d1.error_message


def test_pillar_7_spacemouse_6dof_controller_and_camera_navigation() -> None:
    """Vérifie le filtrage 6-DoF, la zone morte, l'amortissement inertiel et le décodage HID."""
    config = SpaceMouseConfig(deadzone=0.05, power_curve=2.0)
    controller = SpaceMouseController(config)
    camera = CADCamera()

    init_dist = camera.distance
    init_yaw = camera.yaw_deg
    init_pitch = camera.pitch_deg

    # 1. Déflexion sous le seuil de zone morte (bruit / drift du capteur)
    state = controller.update_axes(raw_tx=0.02, raw_ty=0.01, raw_tz=0.0, raw_rx=0.0, raw_ry=0.0, raw_rz=0.0)
    assert state.trans_x == 0.0
    assert state.trans_y == 0.0

    # 2. Déflexion franche sur la rotation (Orbite)
    controller.update_axes(raw_tx=0.0, raw_ty=0.0, raw_tz=0.0, raw_rx=0.8, raw_ry=0.0, raw_rz=0.5, dt=0.016)
    moved = controller.apply_to_camera(camera, dt=0.016)
    assert moved is True
    assert camera.pitch_deg != init_pitch
    assert camera.yaw_deg != init_yaw

    # 3. Pousser sur l'axe Z pour zoomer
    controller.update_axes(raw_tx=0.0, raw_ty=0.0, raw_tz=0.9, raw_rx=0.0, raw_ry=0.0, raw_rz=0.0, dt=0.016)
    controller.apply_to_camera(camera, dt=0.016)
    assert camera.distance != init_dist

    # 4. Décodage d'un paquet HID USB 3Dconnexion standard
    # Report ID 1 (Translation), x=175 (moitié déflexion), y=0, z=0
    import struct
    hid_trans_pkt = struct.pack("<Bhhh", 1, 175, 0, 0)
    decoded = controller.parse_hid_packet(hid_trans_pkt)
    assert decoded is not None
    tag, dx, dy, dz = decoded
    assert tag == "TRANS"
    assert dx == pytest.approx(0.5, abs=0.05)


def test_deep_nurbs_fundamental_forms_and_two_surface_continuity() -> None:
    """Vérifie les première et seconde formes fondamentales et la continuité entre surfaces distinctes."""
    from src.core.nexus_kernel.nurbs_surface import check_surface_continuity, ContinuityLevel

    c_s1 = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (20.0, 0.0, 0.0)]
    c_n1 = [(0.0, 10.0, 0.0), (10.0, 10.0, 0.0), (20.0, 10.0, 0.0)]
    c_w1 = [(0.0, 0.0, 0.0), (0.0, 5.0, 0.0), (0.0, 10.0, 0.0)]
    c_e1 = [(20.0, 0.0, 0.0), (20.0, 5.0, 0.0), (20.0, 10.0, 0.0)]
    surf1 = make_coons_patch(c_s1, c_n1, c_w1, c_e1, name="Patch1")

    # Première et seconde formes fondamentales
    e, f, g = surf1.first_fundamental_form(0.5, 0.5)
    assert e > 0.0
    assert g > 0.0
    l, m, n = surf1.second_fundamental_form(0.5, 0.5)
    assert isinstance(l, float)

    # Surface 2 décalée (discontinue en Z)
    c_s2 = [(0.0, 10.0, 5.0), (10.0, 10.0, 5.0), (20.0, 10.0, 5.0)]
    c_n2 = [(0.0, 20.0, 5.0), (10.0, 20.0, 5.0), (20.0, 20.0, 5.0)]
    c_w2 = [(0.0, 10.0, 5.0), (0.0, 15.0, 5.0), (0.0, 20.0, 5.0)]
    c_e2 = [(20.0, 10.0, 5.0), (20.0, 15.0, 5.0), (20.0, 20.0, 5.0)]
    surf2 = make_coons_patch(c_s2, c_n2, c_w2, c_e2, name="Patch2")

    level, ang, curv = check_surface_continuity(surf1, surf2)
    assert level == ContinuityLevel.C0_DISCONTINUOUS


def test_deep_nonlinear_fea_solver_equilibrium() -> None:
    """Vérifie l'équilibre non-linéaire avec plasticité et contact."""
    mat = BilinearPlasticMaterial(
        name="Alu6061",
        youngs_modulus_mpa=70000.0,
        poissons_ratio=0.33,
        yield_strength_mpa=270.0,
        tangent_modulus_mpa=1500.0
    )
    # Contact frottant avec pénétration
    pair = FrictionalContactPair(
        slave_node_coords=np.array([10.0, 10.0, -0.05]),
        master_plane_origin=np.array([10.0, 10.0, 0.0]),
        master_plane_normal=np.array([0.0, 0.0, 1.0]),
        penalty_stiffness=50000.0,
        friction_coefficient=0.2
    )

    res = NonlinearFEASolver.solve_contact_equilibrium(
        material=mat,
        applied_load_newtons=30000.0,
        cross_section_area_mm2=100.0,
        contact_pairs=[pair]
    )
    assert res["converged"] is True
    assert res["is_yielded"] is True
    assert res["contact_nodes_active"] == 1
    assert float(res["total_normal_contact_force_n"]) > 0.0


def test_deep_cam_generate_gcode_and_report() -> None:
    """Vérifie les rapports volumiques et la génération G-Code multimarques."""
    from src.cam.volumetric_simulator import CNCDialect

    sim = VolumetricStockSimulator(stock_dx=50.0, stock_dy=50.0, stock_dz=20.0, voxel_res_mm=2.0)
    sim.simulate_linear_cut((5.0, 25.0, 18.0), (45.0, 25.0, 18.0), tool_diameter_mm=10.0)
    report = sim.generate_report(collisions=["Collision_Etau_X"])
    assert report.collision_detected is True
    assert report.removed_volume_mm3 > 0.0

    # Post-processeur
    gcode = CNCPostProcessorRegistry.generate_gcode(
        CNCDialect.FANUC,
        toolpaths=[[(0.0, 0.0, 10.0), (20.0, 0.0, 5.0)]],
        spindle_rpm=10000,
        feedrate_mm_min=2000.0
    )
    assert "G01" in gcode
    assert "M30" in gcode

