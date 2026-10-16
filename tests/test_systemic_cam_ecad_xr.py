"""
Suite de tests unitaires et d'intégration pour les piliers d'intégration systémique :
1. CAM 5-axes sans gouges avec orientation d'outil et enveloppe porte-outil.
2. Placement robotisé de fibres continues (AFP) aligné sur les contraintes principales σ₁.
3. Contrôle CMM & métrologie laser par recalage SVD-ICP et tolérancement GD&T.
4. Jumeau mécatronique ECAD <-> MCAD avec dissipation Joule des pistes de cuivre et couplage thermique.
5. Rendu spatial XR à 90 FPS avec décimation continue LOD et régulation de budget de trame.
"""

from __future__ import annotations
import math
import numpy as np
import pytest

from src.core.types import Vector3D
from src.cam.five_axis_cam import (
    ToolHolderGeometry, FiveAxisGougeChecker, FiveAxisToolPoint, MachineKinematics5Axis
)
from src.cam.fiber_placement_afp import (
    StressTensor3D, AutomatedFiberPlacementEngine, FiberTowTrajectory
)
from src.cam.metrology_cmm_icp import (
    IterativeClosestPointAligner, MetrologyInspectionReport
)
from src.specialized.ecad_thermal_twin import (
    CopperTrace, SMTComponent, ECADThermalTwin, ECADThermalReport
)
from src.viewport.spatial_xr_lod import (
    SpatialMeshChunk, LODStage, ContinuousLODDecimator, XRStreamingFrameReport
)


# ==============================================================================
# TEST 1 : CAM 5-AXES SANS GOUGES & ENVELOPPE PORTE-OUTIL
# ==============================================================================

def test_five_axis_gouge_avoidance_and_rtcp() -> None:
    """Vérifie l'orientation d'outil 5-axes, la détection de collision et le G-code."""
    holder = ToolHolderGeometry(
        cutter_radius=5.0,
        flute_length=20.0,
        shank_radius=6.0,
        shank_length=30.0,
        holder_bottom_radius=25.0,
        holder_top_radius=35.0,
        holder_length=60.0
    )
    checker = FiveAxisGougeChecker(holder, safety_clearance_mm=2.0)

    # 1. Orientation nominale avec Lead = 15° et Tilt = 5°
    surf_norm = Vector3D(0.0, 0.0, 1.0)
    feed_dir = Vector3D(1.0, 0.0, 0.0)
    init_vec = checker.compute_initial_orientation(surf_norm, feed_dir, lead_angle_deg=15.0, tilt_angle_deg=5.0)

    assert pytest.approx(init_vec.length(), 1e-4) == 1.0
    # L'outil doit avoir une composante positive le long de l'avance (+X) et de la normale (+Z)
    assert init_vec.z > 0.9
    assert init_vec.x > 0.2

    # 2. Détection d'obstacle dans l'enveloppe du porte-outil (ex: paroi voisine haute)
    tip_pos = Vector3D(0.0, 0.0, 0.0)
    # Point d'obstacle situé à Z = 60 mm et X = 28 mm (proche de l'enveloppe de rayon ~26.7 mm)
    obstacle = Vector3D(28.0, 0.0, 60.0)

    report = checker.check_and_correct_point(tip_pos, init_vec, [obstacle], max_tilt_correction_deg=30.0)
    assert report.is_safe is True
    assert report.min_clearance_mm >= 2.0
    assert report.corrected_tool_vector is not None

    # 3. Conversion cinématique et génération de G-code
    pt = FiveAxisToolPoint(
        position=Vector3D(10.0, 20.0, 30.0),
        tool_vector=report.corrected_tool_vector,
        surface_normal=surf_norm
    )
    gcode = checker.generate_5axis_gcode_block(pt, MachineKinematics5Axis.TABLE_TABLE_AC)
    assert "G01 X10.0000 Y20.0000 Z30.0000" in gcode
    assert "A" in gcode and "C" in gcode


# ==============================================================================
# TEST 2 : PLACEMENT AUTOMATISÉ DE FIBRES CONTINUES (AFP) GUIDÉ PAR σ₁
# ==============================================================================

def test_afp_continuous_fiber_placement_stress_aligned() -> None:
    """Vérifie le traçage de mèches de carbone alignées sur les contraintes principales."""
    # Fonction de champ de contrainte : flexion pure avec traction en X et cisaillement XY
    def mock_stress_field(pos: Vector3D) -> StressTensor3D:
        return StressTensor3D(
            sig_xx=150.0 + 10.0 * pos.x, # Forte traction en X
            sig_yy=20.0,
            sig_zz=0.0,
            tau_xy=15.0,
            tau_yz=0.0,
            tau_xz=0.0
        )

    engine = AutomatedFiberPlacementEngine(
        tow_width_mm=6.35,
        min_steering_radius_mm=200.0
    )

    seed = Vector3D(0.0, 0.0, 0.0)
    traj = engine.trace_fiber_trajectory_from_stress_field(
        tow_id="TOW_001_CARBON_IM7",
        material="HexTow_IM7_Epoxy",
        seed_point=seed,
        stress_field_fn=mock_stress_field,
        step_size_mm=5.0,
        max_steps=20,
        preferred_initial_direction=Vector3D(1.0, 0.0, 0.0)
    )

    assert len(traj.waypoints) == 21
    assert traj.total_length_mm > 90.0
    # La trajectoire doit être orientée principalement selon +X (axe de traction max)
    assert traj.waypoints[-1].position.x > 80.0

    # Vérification du respect du rayon de braquage minimal
    for wp in traj.waypoints:
        assert wp.local_steering_radius_mm >= 200.0 or math.isinf(wp.local_steering_radius_mm)

    gcode_lines = engine.generate_afp_gcode(traj)
    assert any("M100" in line for line in gcode_lines)
    assert any("G01 X" in line for line in gcode_lines)
    assert any("M101" in line for line in gcode_lines)


# ==============================================================================
# TEST 3 : CONTRÔLE CMM ET RECALAGE LASER SCAN PAR ICP
# ==============================================================================

def test_cmm_metrology_svd_icp_alignment() -> None:
    """Vérifie l'alignement rigide SVD-ICP et la détection d'écarts d'usinage."""
    # Modèle nominal : grille de points sur un plan horizontal Z = 0 avec normale +Z
    nominal_pts: list[Vector3D] = []
    nominal_norms: list[Vector3D] = []
    for x in range(0, 50, 10):
        for y in range(0, 50, 10):
            nominal_pts.append(Vector3D(float(x), float(y), 0.0))
            nominal_norms.append(Vector3D(0.0, 0.0, 1.0))

    # Nuage scanné simulé : translaté de +2mm en X et un défaut local de surépaisseur (+0.08mm) sur un point
    scanned_pts: list[Vector3D] = []
    for i, pt in enumerate(nominal_pts):
        local_defect = 0.08 if i == 0 else 0.0
        scanned_pts.append(Vector3D(pt.x + 2.0, pt.y, pt.z + local_defect))

    aligner = IterativeClosestPointAligner(
        max_iterations=30,
        upper_gdt_limit_mm=0.05,
        lower_gdt_limit_mm=-0.05
    )

    report = aligner.align_and_inspect(scanned_pts, nominal_pts, nominal_norms)

    assert report.total_points == len(nominal_pts)
    # L'alignement doit compenser la translation en X
    assert pytest.approx(report.rigid_transform_translation.x, 0.1) == -2.0
    # Le défaut local (+0.08 mm) dépasse la tolérance de 0.05 mm -> un point hors tolérance (96% conformité)
    assert report.max_positive_deviation_mm > 0.06
    assert report.in_tolerance_percentage == 96.0


# ==============================================================================
# TEST 4 : JUMEAU NUMÉRIQUE ÉLECTRO-THERMIQUE ECAD ↔ MCAD (IPC-2581)
# ==============================================================================

def test_ecad_thermal_twin_joule_heating() -> None:
    """Vérifie le calcul des pertes Joule des pistes de cuivre et la diffusion thermique."""
    twin = ECADThermalTwin(board_width_mm=100.0, board_length_mm=80.0, board_thickness_mm=1.6)

    # Ajout d'une piste de puissance : 50mm de long, 1.0mm de large, 35µm d'épaisseur, courant 4.0 A
    trace = CopperTrace(
        trace_id="PWR_VCC_12V",
        layer_name="TOP_SIGNAL",
        length_mm=50.0,
        width_mm=1.0,
        thickness_um=35.0,
        current_amps=4.0
    )
    twin.add_copper_trace(trace)

    # Résistance ohmique théorique ~ R = 1.68e-8 * 0.05 / (1e-3 * 35e-6) = 0.024 Ω
    r_calc = trace.compute_electrical_resistance(25.0)
    assert 0.020 < r_calc < 0.030
    # Pertes Joule P = R * I^2 = 0.024 * 16 ~ 0.38 W
    p_joule = trace.compute_joule_heat_watts(25.0)
    assert 0.3 < p_joule < 0.5

    # Ajout d'un composant actif (MOSFET de puissance Q1 dissipant 2.0 W)
    mosfet = SMTComponent(
        designator="Q1",
        package_name="DPAK",
        position_x_mm=50.0,
        position_y_mm=40.0,
        power_dissipation_watts=2.0,
        max_junction_temp_c=125.0
    )
    twin.add_component(mosfet)

    report = twin.solve_thermal_equilibrium(ambient_temp_c=25.0, grid_resolution=15)

    assert report.total_electrical_heat_watts > 2.3
    # L'échauffement doit élever la température au-dessus de l'ambiant (25°C)
    assert report.max_board_temp_c > 26.0
    assert report.hottest_component_id == "Q1"
    assert report.is_thermally_safe is True


# ==============================================================================
# TEST 5 : STREAMING GRAPHIQUE XR & DÉCIMATION CONTINUE LOD (90 FPS)
# ==============================================================================

def test_spatial_xr_lod_streaming_at_90fps() -> None:
    """Vérifie la sélection de niveau de détail (LOD) et le régulateur de budget de trame."""
    decimator = ContinuousLODDecimator(target_fps=90.0)
    assert pytest.approx(decimator.frame_budget_ms, 1e-2) == 11.11

    eye_pos = Vector3D(0.0, 0.0, 0.0)

    # Création de 4 chunks situés à différentes distances (1m, 6m, 15m, 40m)
    dummy_verts = np.zeros((100, 3), dtype=np.float32)
    dummy_tris = np.zeros((100, 3), dtype=np.int32)

    chunk_near = SpatialMeshChunk("CH_01", dummy_verts, dummy_tris, Vector3D(0.0, 1000.0, 0.0), 100.0) # 1m
    chunk_mid = SpatialMeshChunk("CH_02", dummy_verts, dummy_tris, Vector3D(0.0, 6000.0, 0.0), 100.0)  # 6m
    chunk_far = SpatialMeshChunk("CH_03", dummy_verts, dummy_tris, Vector3D(0.0, 15000.0, 0.0), 100.0) # 15m
    chunk_dist = SpatialMeshChunk("CH_04", dummy_verts, dummy_tris, Vector3D(0.0, 40000.0, 0.0), 100.0)# 40m

    assert decimator.select_lod_for_chunk(chunk_near, eye_pos) == LODStage.LOD_0_FULL
    assert decimator.select_lod_for_chunk(chunk_mid, eye_pos) == LODStage.LOD_1_MEDIUM
    assert decimator.select_lod_for_chunk(chunk_far, eye_pos) == LODStage.LOD_2_COARSE
    assert decimator.select_lod_for_chunk(chunk_dist, eye_pos) == LODStage.LOD_3_PROXY

    # Test de la décimation
    v_out, i_out = decimator.decimate_mesh_chunk(chunk_far, LODStage.LOD_2_COARSE)
    assert len(i_out) < len(dummy_tris)

    # Test du régulateur de budget : simulation d'un frame drop (14 ms > 11.11 ms)
    report = decimator.evaluate_frame_stream([chunk_near, chunk_mid], eye_pos, simulated_gpu_time_ms=14.0)
    assert report.is_frame_budget_respected is False
    # Le biais adaptatif doit augmenter pour réduire la charge
    assert decimator.lod_bias > 1.0


def test_cnc_post_processor_registry_dialects() -> None:
    """Vérifie la génération de code G spécialisé Fanuc, Siemens, Heidenhain et Haas."""
    from src.cam.volumetric_simulator import CNCPostProcessorRegistry, ToolpathPoint

    pts = [
        ToolpathPoint(x=10.0, y=20.0, z=-5.0, feed_rate=1200.0, spindle_rpm=10000, a_deg=15.0, c_deg=45.0),
        ToolpathPoint(x=30.0, y=40.0, z=-5.0, feed_rate=1500.0, spindle_rpm=10000, a_deg=20.0, c_deg=90.0)
    ]

    prog_fanuc = CNCPostProcessorRegistry.generate_program("FANUC", pts, "1234")
    assert "O1234" in prog_fanuc
    assert "G01 X10.000 Y20.000 Z-5.000 F1200.0" in prog_fanuc
    assert "M30" in prog_fanuc

    prog_siemens = CNCPostProcessorRegistry.generate_program("SIEMENS_840D", pts, "PROG1")
    assert "TRAORI" in prog_siemens
    assert "A=15.00 C=45.00" in prog_siemens
    assert "TRAFOOF" in prog_siemens

    prog_heidenhain = CNCPostProcessorRegistry.generate_program("HEIDENHAIN", pts, "HEID_01")
    assert "BEGIN PGM HEID_01 MM" in prog_heidenhain
    assert "TOOL CALL 1 Z S10000" in prog_heidenhain
    assert "END PGM HEID_01 MM" in prog_heidenhain

    prog_generic = CNCPostProcessorRegistry.generate_program("GENERIC_HAAS", pts, "HAAS_01")
    assert "(HAAS/GENERIC ISO PROGRAM HAAS_01)" in prog_generic
    assert "G21 G90 G54" in prog_generic
