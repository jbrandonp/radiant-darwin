"""
Interface en ligne de commande industrielle (CAD Studio Industrial CLI).
Permet l'exécution sans tête (Headless), l'automatisation CI/CD, l'export de formats,
la génération de G-code 5-axes, le contrôle CMM et l'audit de qualité déterministe.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
import argparse
import sys
import os
import json
from typing import List, Optional

from src.core.types import Vector3D
from src.core.geometry import make_box, Solid
from src.core.document import CADDocument
from src.core.exporter import CADExporter
from src.core.ecosystem_hub import EcosystemMasterHub
from src.cam.five_axis_cam import MachineKinematics5Axis
from src.specialized.ecad_thermal_twin import CopperTrace, SMTComponent


def build_cli_parser() -> argparse.ArgumentParser:
    """Construit l'analyseur de ligne de commande avec ses sous-commandes dédiées."""
    parser = argparse.ArgumentParser(
        prog="cad-studio",
        description="CAD Studio 2026 - Noyau CAO/CAE/CAM Industriel Unifié"
    )
    parser.add_argument("--version", action="version", version="CAD Studio v2.4 (NEXUS-3D SOTA Enterprise)")

    subparsers = parser.add_subparsers(dest="command", help="Sous-commandes disponibles")

    # 1. Commande d'audit
    subparsers.add_parser("audit", help="Exécute l'audit industriel déterministe ISO 25010 / SonarQube")

    # 2. Commande de création de primitive
    box_p = subparsers.add_parser("create-box", help="Génère un parallélépipède et l'exporte en STL")
    box_p.add_argument("--width", type=float, default=40.0, help="Largeur en X (mm)")
    box_p.add_argument("--height", type=float, default=30.0, help="Hauteur en Y (mm)")
    box_p.add_argument("--depth", type=float, default=20.0, help="Profondeur en Z (mm)")
    box_p.add_argument("--output", type=str, default="box_output.stl", help="Fichier de sortie")

    # 3. Commande CAM 5-axes
    cam_p = subparsers.add_parser("cam-5axis", help="Génère un programme G-code 5-axes RTCP sans gouges")
    cam_p.add_argument("--output", type=str, default="output_5axis.gcode", help="Fichier G-code de sortie")

    # 4. Commande ECAD thermique
    ecad_p = subparsers.add_parser("ecad-thermal", help="Simule l'échauffement Joule d'une carte électronique")
    ecad_p.add_argument("--current", type=float, default=3.0, help="Courant de la piste principale (A)")

    # 5. Commande XR LOD streaming
    xr_p = subparsers.add_parser("xr-stream", help="Simule le streaming spatial XR à 90 FPS")
    xr_p.add_argument("--distance", type=float, default=5.0, help="Distance observateur en mètres")

    return parser


def handle_audit_command() -> int:
    """Exécute l'audit industriel officiel déterministe."""
    from scripts.industrial_audit_engine import run_industrial_quality_audit, generate_console_summary
    metrics, is_green, violations = run_industrial_quality_audit()
    print(generate_console_summary(metrics, is_green, violations))
    return 0 if is_green else 1


def handle_create_box_command(args: argparse.Namespace) -> int:
    """Génère une boîte géométrique et l'exporte en STL."""
    solid = make_box(args.width, args.height, args.depth, center=True)
    CADExporter.export_stl({"box": solid}, args.output)
    print(f"[CAD-STUDIO CLI] Boîte {args.width}x{args.height}x{args.depth} mm exportée avec succès vers '{args.output}'.")
    return 0


def handle_cam_5axis_command(args: argparse.Namespace) -> int:
    """Génère le G-code 5-axes pour une trajectoire nominale."""
    doc = CADDocument("CLIDoc")
    hub = EcosystemMasterHub(doc)
    hub.setup_default_production_tooling()

    toolpath = [
        Vector3D(0.0, 0.0, 10.0),
        Vector3D(20.0, 0.0, 10.0),
        Vector3D(40.0, 0.0, 10.0),
        Vector3D(40.0, 20.0, 10.0)
    ]
    norm = Vector3D(0.0, 0.0, 1.0)
    lines = hub.run_5axis_toolpath_planning(toolpath, norm, obstacles=[], kinematics=MachineKinematics5Axis.TABLE_TABLE_AC)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[CAD-STUDIO CLI] Programme 5-axes généré ({len(lines)} lignes) dans '{args.output}'.")
    return 0


def handle_ecad_thermal_command(args: argparse.Namespace) -> int:
    """Résout l'échauffement Joule d'une carte électronique."""
    doc = CADDocument("ECADDoc")
    hub = EcosystemMasterHub(doc)
    trace = CopperTrace("TRACE_MAIN", "TOP_SIGNAL", length_mm=60.0, width_mm=1.5, thickness_um=35.0, current_amps=args.current)
    fet = SMTComponent("MOSFET_1", "TO-220", position_x_mm=40.0, position_y_mm=30.0, power_dissipation_watts=2.5)

    report = hub.solve_mechatronic_pcb_thermal(80.0, 60.0, [trace], [fet])
    print(f"[CAD-STUDIO CLI] Bilan Thermique ECAD (Courant {args.current}A):")
    print(f"  - Puissance Joule & Composants : {report.total_electrical_heat_watts:.2f} W")
    print(f"  - Température Maximale Carte   : {report.max_board_temp_c:.1f} °C")
    print(f"  - Composant le plus chaud      : {report.hottest_component_id}")
    print(f"  - Statut thermique             : {'Sécurisé (SAFE)' if report.is_thermally_safe else 'Surchauffe (OVERHEAT)'}")
    return 0


def handle_xr_stream_command(args: argparse.Namespace) -> int:
    """Évalue la décimation continue pour le streaming spatial WebXR."""
    doc = CADDocument("XRDoc")
    doc.bodies["part_01"] = make_box(50.0, 50.0, 50.0)
    hub = EcosystemMasterHub(doc)

    eye_pos = Vector3D(0.0, args.distance * 1000.0, 0.0)
    report = hub.prepare_spatial_xr_streaming_scene(eye_pos, simulated_gpu_time_ms=7.5)

    print(f"[CAD-STUDIO CLI] Streaming Spatial WebXR à {args.distance}m:")
    print(f"  - Budget trame 90 FPS : {report.frame_budget_ms:.2f} ms (Réel : {report.actual_render_time_ms:.2f} ms)")
    print(f"  - Budget respecté     : {'OUI (FLUIDE 90Hz)' if report.is_frame_budget_respected else 'NON (DÉPOSE DE TRAME)'}")
    print(f"  - Triangles rendus    : {report.total_triangles_rendered}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Point d'entrée principal du CLI."""
    parser = build_cli_parser()
    args = parser.parse_args(argv)

    if args.command == "audit":
        return handle_audit_command()
    elif args.command == "create-box":
        return handle_create_box_command(args)
    elif args.command == "cam-5axis":
        return handle_cam_5axis_command(args)
    elif args.command == "ecad-thermal":
        return handle_ecad_thermal_command(args)
    elif args.command == "xr-stream":
        return handle_xr_stream_command(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
