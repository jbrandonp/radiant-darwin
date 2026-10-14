"""
Module de jumeau numérique mécatronique ECAD <-> MCAD (IPC-2581 / ODB++).
Modélise la structure multi-couches de cartes électroniques (pistes, vias, composants),
calcule la dissipation par effet Joule et résout le couplage thermique 3D avec le boîtier.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import List, Dict, Tuple, Optional
import numpy as np

from src.core.types import Vector3D


class IPCLayerType(Enum):
    """Types de couches normalisées selon IPC-2581 / ODB++."""
    TOP_SIGNAL = "top_signal"
    INNER_SIGNAL = "inner_signal"
    POWER_PLANE = "power_plane"
    GROUND_PLANE = "ground_plane"
    BOTTOM_SIGNAL = "bottom_signal"
    DIELECTRIC_CORE = "dielectric_core"
    PREPREG = "prepreg"


@dataclass
class CopperTrace:
    """Piste de cuivre conductrice avec dimensions et courant nominal."""
    trace_id: str
    layer_name: str
    length_mm: float
    width_mm: float
    thickness_um: float = 35.0  # 1 oz/ft² standard = 35 µm
    current_amps: float = 1.0   # Courant traversant la piste (A)

    def compute_electrical_resistance(self, temperature_c: float = 25.0) -> float:
        """
        Calcule la résistance ohmique de la piste en tenant compte
        du coefficient de température du cuivre (α = 0.00393 K⁻¹).
        """
        rho_0 = 1.68e-8  # Résistivité cuivre à 20°C (Ω·m)
        alpha = 0.00393
        delta_t = temperature_c - 20.0
        rho_t = rho_0 * (1.0 + alpha * delta_t)

        length_m = self.length_mm * 1e-3
        area_m2 = (self.width_mm * 1e-3) * (self.thickness_um * 1e-6)
        return rho_t * (length_m / max(1e-12, area_m2))

    def compute_joule_heat_watts(self, temperature_c: float = 25.0) -> float:
        """Calcule la puissance thermique dissipée par effet Joule : P = R · I² (Watts)."""
        r = self.compute_electrical_resistance(temperature_c)
        return r * (self.current_amps ** 2)


@dataclass
class SMTComponent:
    """Composant actif monté en surface (Microcontrôleur, MOSFET, Régulateur)."""
    designator: str          # Ex: U1, Q3, R12
    package_name: str        # Ex: QFN-32, TO-220, 0805
    position_x_mm: float
    position_y_mm: float
    power_dissipation_watts: float
    thermal_resistance_jc_k_w: float = 2.5 # Résistance jonction-boîtier (°C/W)
    max_junction_temp_c: float = 125.0


@dataclass
class ECADThermalReport:
    """Bilan thermique complet de la carte et du boîtier mécanique."""
    ambient_temp_c: float
    max_board_temp_c: float
    hottest_component_id: str
    total_electrical_heat_watts: float
    is_thermally_safe: bool
    temperature_grid: np.ndarray # Matrice 2D/3D des températures


class ECADThermalTwin:
    """
    Solveur de diffusion thermique couplée ECAD ↔ MCAD.
    Intègre les sources de chaleur Joule des pistes de cuivre et composants actifs
    dans la plaque FR4 et modélise la conduction vers les parois du boîtier mécanique.
    """

    def __init__(
        self,
        board_width_mm: float,
        board_length_mm: float,
        board_thickness_mm: float = 1.6,
        substrate_conductivity_k: float = 0.3, # Conductivité thermique FR4 (W/m·K)
        copper_conductivity_k: float = 385.0   # Conductivité thermique Cuivre (W/m·K)
    ) -> None:
        self.width_mm: float = board_width_mm
        self.length_mm: float = board_length_mm
        self.thickness_mm: float = board_thickness_mm
        self.k_fr4: float = substrate_conductivity_k
        self.k_cu: float = copper_conductivity_k

        self.traces: List[CopperTrace] = []
        self.components: List[SMTComponent] = []

    def add_copper_trace(self, trace: CopperTrace) -> None:
        """Enregistre une piste conductrice issue du schéma IPC-2581."""
        self.traces.append(trace)

    def add_component(self, comp: SMTComponent) -> None:
        """Enregistre un composant dissipatif."""
        self.components.append(comp)

    def solve_thermal_equilibrium(
        self,
        ambient_temp_c: float = 25.0,
        convection_coeff_h: float = 15.0, # Convection naturelle (W/m²·K)
        grid_resolution: int = 20
    ) -> ECADThermalReport:
        """
        Résout l'équation de Fourier k ∇²T + q = h (T - T_amb) par différences finies
        sur un maillage régulier de la carte électronique.
        """
        nx = grid_resolution
        ny = grid_resolution
        dx = (self.width_mm * 1e-3) / nx
        dy = (self.length_mm * 1e-3) / ny

        # Puissance volumique injectée (W) répartie sur la grille
        heat_sources = np.zeros((nx, ny), dtype=np.float64)
        total_heat_watts = 0.0

        # 1. Sommation des pertes Joule des pistes
        for tr in self.traces:
            p_joule = tr.compute_joule_heat_watts(ambient_temp_c)
            total_heat_watts += p_joule
            # Répartition uniforme sur la carte
            heat_sources += p_joule / (nx * ny)

        # 2. Sommation des composants discrets localisés
        for comp in self.components:
            total_heat_watts += comp.power_dissipation_watts
            # Localisation sur la grille
            gx = min(nx - 1, max(0, int((comp.position_x_mm / max(1e-3, self.width_mm)) * nx)))
            gy = min(ny - 1, max(0, int((comp.position_y_mm / max(1e-3, self.length_mm)) * ny)))
            heat_sources[gx, gy] += comp.power_dissipation_watts

        # 3. Résolution itérative par relaxation de Gauss-Seidel (k_eff ∇²T = h(T - T_amb) - q)
        # Conductivité effective équivalente (FR4 + fraction volumique de cuivre)
        k_eff = self.k_fr4 + 0.05 * self.k_cu
        temp_grid = np.full((nx, ny), ambient_temp_c, dtype=np.float64)

        surface_cell = dx * dy
        vol_cell = surface_cell * (self.thickness_mm * 1e-3)

        # Résolution itérative par relaxation de Gauss-Seidel inconditionnellement stable
        # Équation: -k_eff ∇²T + (2h/t)(T - T_amb) = q_v
        k_eff = self.k_fr4 + 0.05 * self.k_cu
        h_coeff = (2.0 * convection_coeff_h) / max(1e-6, self.thickness_mm * 1e-3)
        inv_dx2 = k_eff / max(1e-12, dx ** 2)
        diag = 4.0 * inv_dx2 + h_coeff

        temp_grid = np.full((nx, ny), ambient_temp_c, dtype=np.float64)

        # 60 itérations de relaxation de Gauss-Seidel
        for _ in range(60):
            for i in range(1, nx - 1):
                for j in range(1, ny - 1):
                    neighbor_sum = inv_dx2 * (temp_grid[i+1, j] + temp_grid[i-1, j] + temp_grid[i, j+1] + temp_grid[i, j-1])
                    q_in = heat_sources[i, j] / vol_cell
                    rhs = neighbor_sum + h_coeff * ambient_temp_c + q_in
                    temp_grid[i, j] = rhs / diag

        max_temp = float(np.max(temp_grid))
        hottest_comp = "None"
        is_safe = True

        for comp in self.components:
            gx = min(nx - 1, max(0, int((comp.position_x_mm / max(1e-3, self.width_mm)) * nx)))
            gy = min(ny - 1, max(0, int((comp.position_y_mm / max(1e-3, self.length_mm)) * ny)))
            local_t = float(temp_grid[gx, gy])
            # Température de jonction = Température locale carte + R_th · P
            tj = local_t + comp.thermal_resistance_jc_k_w * comp.power_dissipation_watts
            if tj > comp.max_junction_temp_c:
                is_safe = False
            if local_t >= max_temp - 0.5:
                hottest_comp = comp.designator

        return ECADThermalReport(
            ambient_temp_c=ambient_temp_c,
            max_board_temp_c=max_temp,
            hottest_component_id=hottest_comp,
            total_electrical_heat_watts=total_heat_watts,
            is_thermally_safe=is_safe,
            temperature_grid=temp_grid
        )
