"""
Module de placement automatisé de fibres continues (Automated Fiber Placement - AFP).
Génère des trajectoires de dépose robotisée de mèches de carbone/verre guidées par
les tenseurs de contraintes principales maximales (σ₁) issus de l'analyse CutFEM/FEA.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import math
from typing import List, Tuple, Optional
import numpy as np

from src.core.types import Vector3D


@dataclass
class StressTensor3D:
    """Tenseur des contraintes symétrique de Cauchy en un point matériel."""
    sig_xx: float
    sig_yy: float
    sig_zz: float
    tau_xy: float
    tau_yz: float
    tau_xz: float

    def to_matrix(self) -> np.ndarray:
        """Convertit le tenseur en matrice symétrique 3x3."""
        return np.array([
            [self.sig_xx, self.tau_xy, self.tau_xz],
            [self.tau_xy, self.sig_yy, self.tau_yz],
            [self.tau_xz, self.tau_yz, self.sig_zz]
        ], dtype=np.float64)

    def compute_principal_stresses(self) -> Tuple[Tuple[float, float, float], Tuple[Vector3D, Vector3D, Vector3D]]:
        """
        Calcule les trois contraintes principales (valeurs propres σ₁ ≥ σ₂ ≥ σ₃)
        et les directions principales associées (vecteurs propres unitaires v₁, v₂, v₃).
        """
        mat = self.to_matrix()
        evals, evecs = np.linalg.eigh(mat)

        # Inversion pour avoir l'ordre décroissant σ₁ ≥ σ₂ ≥ σ₃
        idx = np.argsort(evals)[::-1]
        s1, s2, s3 = float(evals[idx[0]]), float(evals[idx[1]]), float(evals[idx[2]])

        v1 = Vector3D(float(evecs[0, idx[0]]), float(evecs[1, idx[0]]), float(evecs[2, idx[0]])).normalized()
        v2 = Vector3D(float(evecs[0, idx[1]]), float(evecs[1, idx[1]]), float(evecs[2, idx[1]])).normalized()
        v3 = Vector3D(float(evecs[0, idx[2]]), float(evecs[1, idx[2]]), float(evecs[2, idx[2]])).normalized()

        return (s1, s2, s3), (v1, v2, v3)


@dataclass
class FiberTowWaypoint:
    """Point de passage d'une mèche de fibre continue (Tow)."""
    position: Vector3D
    tangent_direction: Vector3D
    principal_tension_mpa: float
    roller_compaction_force_n: float
    deposition_speed_mm_s: float
    local_steering_radius_mm: float


@dataclass
class FiberTowTrajectory:
    """Trajectoire complète d'une bande de fibres continues (Ply Tow)."""
    tow_id: str
    material_name: str
    tow_width_mm: float
    tow_thickness_mm: float
    waypoints: List[FiberTowWaypoint] = field(default_factory=list)

    @property
    def total_length_mm(self) -> float:
        """Calcule la longueur curviligne totale de la mèche déposée."""
        if len(self.waypoints) < 2:
            return 0.0
        dist = 0.0
        for i in range(len(self.waypoints) - 1):
            dist += (self.waypoints[i + 1].position - self.waypoints[i].position).length()
        return dist


class AutomatedFiberPlacementEngine:
    """
    Générateur de trajectoires de dépose robotisée de fibres continues guidées par la physique.
    Trace les lignes de courant du champ vectoriel des contraintes principales maximales
    tout en respectant le rayon de courbure minimal pour éviter le plissement hors-plan (wrinkling).
    """

    def __init__(
        self,
        tow_width_mm: float = 6.35,        # Largeur de bande standard 1/4 pouce
        tow_thickness_mm: float = 0.15,    # Épaisseur pli pré-imprégné 150 µm
        min_steering_radius_mm: float = 250.0, # Rayon de braquage minimal avant flambement
        nominal_compaction_n: float = 200.0,
        nominal_speed_mm_s: float = 150.0
    ) -> None:
        self.tow_width: float = tow_width_mm
        self.tow_thickness: float = tow_thickness_mm
        self.min_steering_radius: float = min_steering_radius_mm
        self.nominal_compaction: float = nominal_compaction_n
        self.nominal_speed: float = nominal_speed_mm_s

    def trace_fiber_trajectory_from_stress_field(
        self,
        tow_id: str,
        material: str,
        seed_point: Vector3D,
        stress_field_fn: type, # Callable[[Vector3D], StressTensor3D]
        step_size_mm: float = 2.0,
        max_steps: int = 100,
        preferred_initial_direction: Optional[Vector3D] = None
    ) -> FiberTowTrajectory:
        """
        Intègre la trajectoire de la fibre le long du champ directeur de traction maximale σ₁.
        Applique un limiteur de courbure pour garantir l'absence de défauts de drapage.
        """
        traj = FiberTowTrajectory(
            tow_id=tow_id,
            material_name=material,
            tow_width_mm=self.tow_width,
            tow_thickness_mm=self.tow_thickness
        )

        current_pos = seed_point
        # Évaluation initiale au point de départ
        initial_tensor = stress_field_fn(current_pos)
        (s1, _, _), (v1, _, _) = initial_tensor.compute_principal_stresses()
        prev_dir = v1
        if preferred_initial_direction is not None and prev_dir.dot(preferred_initial_direction) < 0.0:
            prev_dir = -prev_dir

        # Enregistrement du premier point
        traj.waypoints.append(FiberTowWaypoint(
            position=current_pos,
            tangent_direction=prev_dir,
            principal_tension_mpa=s1,
            roller_compaction_force_n=self.nominal_compaction,
            deposition_speed_mm_s=self.nominal_speed,
            local_steering_radius_mm=float("inf")
        ))

        for _ in range(max_steps):
            tensor = stress_field_fn(current_pos)
            (sig_max, _, _), (dir_max, _, _) = tensor.compute_principal_stresses()

            # Alignement de polarité (évite les retournements à 180° du champ non orienté)
            if dir_max.dot(prev_dir) < 0.0:
                dir_max = dir_max * -1.0

            # Vérification et limitation de la courbure de braquage
            delta_angle = math.acos(max(-1.0, min(1.0, dir_max.dot(prev_dir))))
            local_radius = float("inf") if delta_angle < 1e-5 else (step_size_mm / delta_angle)

            steered_dir = dir_max
            if local_radius < self.min_steering_radius:
                # Saturation de la déviation angulaire au rayon maximal admissible
                max_d_theta = step_size_mm / self.min_steering_radius
                # Interpolation sphérique entre prev_dir et dir_max
                t_ratio = max_d_theta / max(1e-6, delta_angle)
                steered_dir = Vector3D(
                    prev_dir.x + t_ratio * (dir_max.x - prev_dir.x),
                    prev_dir.y + t_ratio * (dir_max.y - prev_dir.y),
                    prev_dir.z + t_ratio * (dir_max.z - prev_dir.z)
                ).normalized()
                local_radius = self.min_steering_radius

            # Progression spatiale (Schéma d'Euler pour la ligne de courant)
            next_pos = current_pos + (steered_dir * step_size_mm)
            current_pos = next_pos
            prev_dir = steered_dir

            traj.waypoints.append(FiberTowWaypoint(
                position=current_pos,
                tangent_direction=steered_dir,
                principal_tension_mpa=sig_max,
                roller_compaction_force_n=self.nominal_compaction,
                deposition_speed_mm_s=self.nominal_speed,
                local_steering_radius_mm=local_radius
            ))

        return traj

    def generate_afp_gcode(self, trajectory: FiberTowTrajectory) -> List[str]:
        """Génère le flux d'instructions robotiques AFP pour tête de dépose multi-axes."""
        commands: List[str] = [
            f"; --- TRAJECTOIRE AFP FIBRES CONTINUES : {trajectory.tow_id} ---",
            f"; MATÉRIAU: {trajectory.material_name} | LARGEUR: {trajectory.tow_width_mm}mm | ÉP: {trajectory.tow_thickness_mm}mm",
            "M100 ; INITIALISATION TÊTE AFP (CHAUFFE LASER ET COMPACTEUR)",
            f"M106 P0 S{int(self.nominal_compaction)} ; RÉGULATION FORCE ROULEAU (N)"
        ]

        for i, wp in enumerate(trajectory.waypoints):
            cmd_type = "G00" if i == 0 else "G01"
            commands.append(
                f"{cmd_type} X{wp.position.x:.3f} Y{wp.position.y:.3f} Z{wp.position.z:.3f} "
                f"I{wp.tangent_direction.x:.4f} J{wp.tangent_direction.y:.4f} K{wp.tangent_direction.z:.4f} "
                f"F{wp.deposition_speed_mm_s * 60.0:.1f}"
            )

        commands.append("M101 ; COUPE FIBRE ET DÉGAGEMENT TÊTE AFP")
        return commands
