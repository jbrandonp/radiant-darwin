"""
Suite de tests d'ingénierie pour le Hub d'Orchestration Systémique et l'Interface CLI.
Vérifie la coordination de tous les modules industriels et l'exécution headless.
"""

from __future__ import annotations
import os
import pytest
import numpy as np

from src.core.types import Vector3D
from src.core.geometry import make_box
from src.core.document import CADDocument
from src.core.ecosystem_hub import EcosystemMasterHub, EcosystemSystemicSummary
from src.cam.five_axis_cam import MachineKinematics5Axis
from src.specialized.ecad_thermal_twin import CopperTrace, SMTComponent
from src.cli import (
    build_cli_parser,
    handle_create_box_command,
    handle_cam_5axis_command,
    handle_ecad_thermal_command,
    handle_xr_stream_command,
    main as cli_main
)


def test_ecosystem_hub_full_orchestration():
    """Vérifie l'orchestration complète des ateliers via le Master Hub."""
    doc = CADDocument("MasterOrchestrationDoc")
    box = make_box(60.0, 40.0, 20.0, center=True)
    doc.bodies["nominal_part"] = box

    hub = EcosystemMasterHub(doc)
    hub.setup_default_production_tooling()

    # 1. Planification de trajectoire 5-axes RTCP
    pts = [Vector3D(0.0, 0.0, 10.0), Vector3D(10.0, 0.0, 10.0), Vector3D(20.0, 0.0, 10.0)]
    gcode = hub.run_5axis_toolpath_planning(pts, Vector3D(0.0, 0.0, 1.0), obstacles=[])
    assert len(gcode) >= 5
    assert any("G43.4" in line for line in gcode)

    # 2. Contrôle CMM Scan-to-CAD
    # Création d'un nuage de points nominal légèrement bruité (+0.02mm)
    scanned_pts: list[Vector3D] = []
    for i in range(min(10, len(box.mesh.vertices))):
        v = box.mesh.vertices[i]
        scanned_pts.append(Vector3D(float(v[0]), float(v[1]), float(v[2]) + 0.02))

    cmm_rep = hub.inspect_scanned_part_against_cad(scanned_pts, "nominal_part")
    assert cmm_rep.total_points == len(scanned_pts)
    assert cmm_rep.in_tolerance_percentage >= 90.0

    # 3. Jumeau numérique thermique mécatronique
    trace = CopperTrace("TRACE_1", "TOP_SIGNAL", length_mm=40.0, width_mm=1.0, current_amps=3.0)
    fet = SMTComponent("FET_1", "SOIC-8", position_x_mm=20.0, position_y_mm=20.0, power_dissipation_watts=1.8)
    therm_rep = hub.solve_mechatronic_pcb_thermal(50.0, 50.0, [trace], [fet])
    assert therm_rep.max_board_temp_c > 25.0
    assert therm_rep.is_thermally_safe is True

    # 4. Rendu spatial WebXR avec budget 90 FPS
    xr_rep = hub.prepare_spatial_xr_streaming_scene(Vector3D(0.0, 5000.0, 0.0), simulated_gpu_time_ms=8.0)
    assert xr_rep.is_frame_budget_respected is True
    assert xr_rep.total_triangles_rendered > 0

    # 5. Bilan systémique
    summary = hub.get_systemic_summary()
    assert summary.num_cad_bodies == 1
    assert summary.cmm_metrology_conformance_pct >= 90.0
    assert summary.ecad_thermal_max_c > 25.0


def test_cli_parser_and_commands(tmp_path):
    """Vérifie le fonctionnement de l'interface en ligne de commande industrielle."""
    parser = build_cli_parser()

    # Test create-box
    out_stl = str(tmp_path / "cli_box.stl")
    args_box = parser.parse_args(["create-box", "--width", "30", "--height", "20", "--depth", "10", "--output", out_stl])
    code_box = handle_create_box_command(args_box)
    assert code_box == 0
    assert os.path.exists(out_stl)

    # Test cam-5axis
    out_gcode = str(tmp_path / "cli_5axis.gcode")
    args_cam = parser.parse_args(["cam-5axis", "--output", out_gcode])
    code_cam = handle_cam_5axis_command(args_cam)
    assert code_cam == 0
    assert os.path.exists(out_gcode)

    # Test ecad-thermal
    args_ecad = parser.parse_args(["ecad-thermal", "--current", "2.5"])
    code_ecad = handle_ecad_thermal_command(args_ecad)
    assert code_ecad == 0

    # Test xr-stream
    args_xr = parser.parse_args(["xr-stream", "--distance", "8.0"])
    code_xr = handle_xr_stream_command(args_xr)
    assert code_xr == 0

    # Test CLI main entry with no args (prints help)
    assert cli_main([]) == 0
