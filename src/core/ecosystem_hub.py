"""
Hub d'orchestration systémique unifié (Ecosystem Master Hub).
Connecte le document de CAO, le noyau géométrique B-Rep, les solveurs multiphysiques,
la chaîne de fabrication CAM (5-axes & AFP), la métrologie CMM et le rendu spatial XR.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
import numpy as np

from src.core.types import Vector3D
from src.core.geometry import Solid
from src.core.document import CADDocument
from src.cam.five_axis_cam import (
    FiveAxisGougeChecker, ToolHolderGeometry, FiveAxisToolPoint, MachineKinematics5Axis
)
from src.cam.fiber_placement_afp import (
    AutomatedFiberPlacementEngine, StressTensor3D, FiberTowTrajectory
)
from src.cam.metrology_cmm_icp import (
    IterativeClosestPointAligner, MetrologyInspectionReport
)
from src.specialized.ecad_thermal_twin import (
    ECADThermalTwin, CopperTrace, SMTComponent, ECADThermalReport
)
from src.viewport.spatial_xr_lod import (
    ContinuousLODDecimator, SpatialMeshChunk, XRStreamingFrameReport
)


@dataclass
class EcosystemSystemicSummary:
    """Bilan global des capacités et analyses actives de l'écosystème."""
    num_cad_bodies: int
    num_assembly_instances: int
    cam_5axis_gcode_lines: int
    afp_trajectories_count: int
    cmm_metrology_conformance_pct: float
    ecad_thermal_max_c: float
    xr_lod_active_triangles: int


class EcosystemMasterHub:
    """
    Super-conducteur systémique reliant tous les ateliers industriels de CAD Studio.
    Fournit une API unifiée de haut niveau pour l'automatisation, les tests et le CLI.
    """

    def __init__(self, document: CADDocument) -> None:
        """Initialise le hub avec le document CAO actif."""
        self.doc: CADDocument = document
        self.cam_checker: Optional[FiveAxisGougeChecker] = None
        self.afp_engine: Optional[AutomatedFiberPlacementEngine] = None
        self.cmm_aligner: Optional[IterativeClosestPointAligner] = None
        self.ecad_twin: Optional[ECADThermalTwin] = None
        self.xr_decimator: ContinuousLODDecimator = ContinuousLODDecimator()

        self.last_afp_trajectories: List[FiberTowTrajectory] = []
        self.last_metrology_report: Optional[MetrologyInspectionReport] = None
        self.last_thermal_report: Optional[ECADThermalReport] = None

    def setup_default_production_tooling(self) -> None:
        """Configure les outils industriels par défaut (broche 5-axes, tête AFP, palpeur CMM)."""
        holder = ToolHolderGeometry(
            cutter_radius=5.0,
            flute_length=25.0,
            shank_radius=6.0,
            shank_length=35.0,
            holder_bottom_radius=25.0,
            holder_top_radius=38.0,
            holder_length=65.0
        )
        self.cam_checker = FiveAxisGougeChecker(holder, safety_clearance_mm=2.0)
        self.afp_engine = AutomatedFiberPlacementEngine(tow_width_mm=6.35, min_steering_radius_mm=200.0)
        self.cmm_aligner = IterativeClosestPointAligner(max_iterations=40, upper_gdt_limit_mm=0.05, lower_gdt_limit_mm=-0.05)

    def run_5axis_toolpath_planning(
        self,
        toolpath_points: List[Vector3D],
        surface_normal: Vector3D,
        obstacles: List[Vector3D],
        kinematics: MachineKinematics5Axis = MachineKinematics5Axis.TABLE_TABLE_AC
    ) -> List[str]:
        """Génère le flux G-code 5-axes sans gouges pour une suite de points de passage."""
        if self.cam_checker is None:
            self.setup_default_production_tooling()
        assert self.cam_checker is not None

        gcode_program: List[str] = [
            "; --- CAD STUDIO 5-AXIS RTCP G-CODE ---",
            "G90 G94 G17 G21",
            "G43.4 ; RTCP ON"
        ]

        feed_dir = Vector3D(1.0, 0.0, 0.0)
        init_vec = self.cam_checker.compute_initial_orientation(surface_normal, feed_dir, lead_angle_deg=12.0, tilt_angle_deg=4.0)

        for pt in toolpath_points:
            report = self.cam_checker.check_and_correct_point(pt, init_vec, obstacles)
            tool_v = report.corrected_tool_vector if report.corrected_tool_vector is not None else init_vec
            p_5ax = FiveAxisToolPoint(position=pt, tool_vector=tool_v, surface_normal=surface_normal)
            line = self.cam_checker.generate_5axis_gcode_block(p_5ax, kinematics)
            gcode_program.append(line)

        gcode_program.append("G49 ; RTCP OFF")
        gcode_program.append("M30 ; FIN PROGRAMME")
        return gcode_program

    def inspect_scanned_part_against_cad(
        self,
        scanned_points: List[Vector3D],
        nominal_body_id: str
    ) -> MetrologyInspectionReport:
        """Compare un nuage de points réels mesurés (scanner/CMM) avec le solide nominal du document."""
        if self.cmm_aligner is None:
            self.setup_default_production_tooling()
        assert self.cmm_aligner is not None

        if nominal_body_id not in self.doc.bodies:
            raise ValueError(f"Le corps '{nominal_body_id}' n'existe pas dans le document.")

        solid = self.doc.bodies[nominal_body_id]
        mesh = solid.mesh

        # Échantillonnage des sommets et normales nominales
        nominal_points: List[Vector3D] = []
        nominal_normals: List[Vector3D] = []
        for i in range(len(mesh.vertices)):
            nominal_points.append(Vector3D(float(mesh.vertices[i, 0]), float(mesh.vertices[i, 1]), float(mesh.vertices[i, 2])))
            if len(mesh.normals) > i:
                nominal_normals.append(Vector3D(float(mesh.normals[i, 0]), float(mesh.normals[i, 1]), float(mesh.normals[i, 2])))
            else:
                nominal_normals.append(Vector3D(0.0, 0.0, 1.0))

        report = self.cmm_aligner.align_and_inspect(scanned_points, nominal_points, nominal_normals)
        self.last_metrology_report = report
        return report

    def solve_mechatronic_pcb_thermal(
        self,
        board_width_mm: float,
        board_length_mm: float,
        traces: List[CopperTrace],
        components: List[SMTComponent]
    ) -> ECADThermalReport:
        """Résout le couplage thermique ECAD ↔ MCAD et vérifie la tenue en température."""
        twin = ECADThermalTwin(board_width_mm=board_width_mm, board_length_mm=board_length_mm)
        for tr in traces:
            twin.add_copper_trace(tr)
        for comp in components:
            twin.add_component(comp)

        self.ecad_twin = twin
        report = twin.solve_thermal_equilibrium(ambient_temp_c=25.0)
        self.last_thermal_report = report
        return report

    def prepare_spatial_xr_streaming_scene(
        self,
        eye_position: Vector3D,
        simulated_gpu_time_ms: float = 8.0
    ) -> XRStreamingFrameReport:
        """Génère la scène WebXR avec décimation continue LOD et respect du budget 90 FPS."""
        chunks: List[SpatialMeshChunk] = []

        for b_id, body in self.doc.bodies.items():
            mesh = body.mesh
            # Calcul du centre géométrique
            if len(mesh.vertices) > 0:
                c_x = float(np.mean(mesh.vertices[:, 0]))
                c_y = float(np.mean(mesh.vertices[:, 1]))
                c_z = float(np.mean(mesh.vertices[:, 2]))
                center = Vector3D(c_x, c_y, c_z)
                radius = float(np.max(np.linalg.norm(mesh.vertices - np.array([c_x, c_y, c_z]), axis=1)))
            else:
                center = Vector3D(0.0, 0.0, 0.0)
                radius = 10.0

            chunks.append(SpatialMeshChunk(
                chunk_id=b_id,
                vertices=mesh.vertices,
                indices=mesh.indices,
                bounding_center=center,
                bounding_radius_mm=radius
            ))

        return self.xr_decimator.evaluate_frame_stream(chunks, eye_position, simulated_gpu_time_ms)

    def get_systemic_summary(self) -> EcosystemSystemicSummary:
        """Produit un rapport d'état instantané de l'ensemble de l'écosystème."""
        c_pct = self.last_metrology_report.in_tolerance_percentage if self.last_metrology_report is not None else 100.0
        t_max = self.last_thermal_report.max_board_temp_c if self.last_thermal_report is not None else 25.0

        return EcosystemSystemicSummary(
            num_cad_bodies=len(self.doc.bodies),
            num_assembly_instances=len(self.doc.assembly_instances),
            cam_5axis_gcode_lines=0,
            afp_trajectories_count=len(self.last_afp_trajectories),
            cmm_metrology_conformance_pct=c_pct,
            ecad_thermal_max_c=t_max,
            xr_lod_active_triangles=0
        )
