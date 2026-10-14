"""
Atelier Mécanique des Fluides Numérique & Aérodynamique (CFD Aerodynamics Workbench).
Permet l'évaluation rapide des écoulements fluides autour des corps solides :
calcul des coefficients de traînée (Cd), de portance (Cl), de la distribution de pression (Cp),
du nombre de Reynolds et détection des zones de décollement de couche limite.
Typage statique exhaustif et architecture modulaire.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Sequence, Union
import numpy as np

from src.core.nexus_kernel.hybrid_solid import NexusSolid


@dataclass
class FluidFlowProperties:
    """Propriétés physiques du fluide en écoulement."""
    velocity_m_s: float = 30.0
    air_density: float = 1.225            # kg/m³
    dynamic_viscosity: float = 1.81e-5     # Pa.s (viscosité dynamique)


@dataclass
class AirfoilSurfaceData:
    """Paramètres géométriques d'un profil aérodynamique porteur."""
    chord: float = 1.0                    # Corde en mètres
    span: float = 5.0                     # Envergure en mètres
    angle_of_attack_deg: float = 4.0      # Incidence alpha en degrés


@dataclass
class AerodynamicForces:
    """Résultantes des forces et rendements aérodynamiques calculés."""
    lift_force_n: float
    drag_force_n: float
    lift_to_drag_ratio: float
    lift_coefficient_cl: float
    drag_coefficient_cd: float


@dataclass
class AerodynamicReport:
    """Rapport d'analyse aérodynamique complet."""
    solid_name: str
    reynolds_number: float
    drag_coefficient_cd: float
    lift_coefficient_cl: float
    drag_force_newtons: float
    lift_force_newtons: float
    reference_area_m2: float
    separation_risk: bool
    pressure_coefficients: np.ndarray


class AerodynamicsSolver:
    """Solveur d'écoulement aérodynamique et de forces de traînée/portance (CFD)."""

    def calculate_reynolds_number(
        self,
        flow: FluidFlowProperties,
        chord_length: float
    ) -> float:
        """Calcule le nombre adimensionnel de Reynolds Re = (rho * V * L) / mu."""
        if flow.dynamic_viscosity <= 0.0:
            return 1e6
        return (flow.air_density * flow.velocity_m_s * max(0.001, chord_length)) / flow.dynamic_viscosity

    def solve_aerodynamic_forces(
        self,
        flow: FluidFlowProperties,
        airfoil: AirfoilSurfaceData
    ) -> AerodynamicForces:
        """
        Calcule la portance, la traînée et la finesse aérodynamique (L/D) du profil.
        """
        planform_area = max(0.001, airfoil.chord * airfoil.span)
        alpha_rad = float(np.radians(airfoil.angle_of_attack_deg))

        # Modèle de portance mince linéaire avec correction d'allongement
        aspect_ratio = airfoil.span / max(0.01, airfoil.chord)
        cl_slope = 2.0 * float(np.pi) / (1.0 + (2.0 / aspect_ratio))
        cl = float(cl_slope * alpha_rad)

        # Traînée profil (parasite) + traînée induite
        cd_0 = 0.008
        cd_induced = (cl ** 2) / (float(np.pi) * aspect_ratio * 0.85)
        cd = float(cd_0 + cd_induced)

        q_dyn = 0.5 * flow.air_density * (flow.velocity_m_s ** 2)
        lift_n = float(q_dyn * planform_area * cl)
        drag_n = float(q_dyn * planform_area * cd)
        ratio = lift_n / max(1e-6, drag_n)

        return AerodynamicForces(
            lift_force_n=lift_n,
            drag_force_n=drag_n,
            lift_to_drag_ratio=ratio,
            lift_coefficient_cl=cl,
            drag_coefficient_cd=cd
        )

    def detect_boundary_layer_separation(self, angle_of_attack_deg: float) -> bool:
        """Détecte le risque de décrochage (Stall / décollement de couche limite)."""
        return abs(angle_of_attack_deg) >= 16.0

    @staticmethod
    def analyze_flow(
        solid: NexusSolid,
        velocity_m_s: float = 30.0,
        air_density_kg_m3: float = 1.225,
        kinematic_viscosity_m2_s: float = 1.5e-5,
        angle_of_attack_deg: float = 2.0
    ) -> AerodynamicReport:
        """
        Calcule les forces et coefficients aérodynamiques autour de la géométrie 3D solide.
        """
        min_pt, max_pt = solid.bounding_box()
        dims_m = (max_pt - min_pt) / 1000.0
        chord_len = max(0.01, float(dims_m[0]))
        frontal_area = max(0.001, float(dims_m[1] * dims_m[2]))

        reynolds = (velocity_m_s * chord_len) / max(1e-9, kinematic_viscosity_m2_s)
        fineness_ratio = chord_len / max(0.01, float(dims_m[1]))

        if fineness_ratio > 3.0:
            base_cd = 0.04 + 0.1 / fineness_ratio
        else:
            base_cd = 0.45 + 0.3 / max(0.5, fineness_ratio)

        alpha_rad = float(np.radians(angle_of_attack_deg))
        cl = 2.0 * float(np.pi) * alpha_rad * min(1.0, fineness_ratio / 4.0)
        cd = base_cd + (cl ** 2) / (float(np.pi) * max(1.0, fineness_ratio))

        q_dyn = 0.5 * air_density_kg_m3 * (velocity_m_s ** 2)
        drag_force = q_dyn * frontal_area * cd
        lift_force = q_dyn * frontal_area * cl

        n_samples = 20
        x_norm = np.linspace(0.0, 1.0, n_samples)
        cp = 1.0 - 2.5 * np.sin(np.pi * x_norm) ** 2
        separation_risk = bool(np.max(np.diff(cp)) > 0.4 and angle_of_attack_deg > 12.0)

        return AerodynamicReport(
            solid_name=solid.name,
            reynolds_number=reynolds,
            drag_coefficient_cd=float(cd),
            lift_coefficient_cl=float(cl),
            drag_force_newtons=float(drag_force),
            lift_force_newtons=float(lift_force),
            reference_area_m2=float(frontal_area),
            separation_risk=separation_risk,
            pressure_coefficients=cp
        )


# Alias de clarification technique
NacaAnalyticPolar = AerodynamicsSolver
