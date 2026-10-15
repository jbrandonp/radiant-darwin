"""
Module de jumeau numérique mécatronique ECAD / MCAD (IPC-2581 / ODB++ / Gerber).
Modélise la structure multi-couches de cartes électroniques (pistes, vias, composants),
calcule la dissipation par effet Joule et résout le couplage thermique 2D/3D avec le boîtier.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import List, Dict, Tuple, Optional
import numpy as np


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
    thickness_um: float = 35.0
    current_amps: float = 1.0
    start_x_mm: float = 0.0
    start_y_mm: float = 0.0
    end_x_mm: float = 0.0
    end_y_mm: float = 0.0

    def has_spatial_coordinates(self) -> bool:
        """Indique si la piste dispose de coordonnées cartésiennes de départ et de fin distinctes."""
        has_start = self.start_x_mm != 0.0 or self.start_y_mm != 0.0
        has_end = self.end_x_mm != 0.0 or self.end_y_mm != 0.0
        return has_start or has_end

    def compute_electrical_resistance(self, temperature_c: float = 25.0) -> float:
        """
        Calcule la résistance ohmique de la piste en tenant compte
        du coefficient de température du cuivre (alpha = 0.00393 K^-1).
        """
        rho_0 = 1.68e-8
        alpha = 0.00393
        delta_t = temperature_c - 20.0
        rho_t = rho_0 * (1.0 + alpha * delta_t)

        length_m = self.length_mm * 1e-3
        area_m2 = (self.width_mm * 1e-3) * (self.thickness_um * 1e-6)
        return rho_t * (length_m / max(1e-12, area_m2))

    def compute_joule_heat_watts(self, temperature_c: float = 25.0) -> float:
        """Calcule la puissance thermique dissipée par effet Joule : P = R * I^2 (Watts)."""
        r = self.compute_electrical_resistance(temperature_c)
        return r * (self.current_amps ** 2)


@dataclass
class SMTComponent:
    """Composant actif monté en surface (Microcontrôleur, MOSFET, Régulateur)."""
    designator: str
    package_name: str
    position_x_mm: float
    position_y_mm: float
    power_dissipation_watts: float
    thermal_resistance_jc_k_w: float = 2.5
    max_junction_temp_c: float = 125.0


@dataclass
class ECADThermalReport:
    """Bilan thermique complet de la carte et du boîtier mécanique."""
    ambient_temp_c: float
    max_board_temp_c: float
    hottest_component_id: str
    total_electrical_heat_watts: float
    is_thermally_safe: bool
    temperature_grid: np.ndarray
    copper_density_grid: np.ndarray = field(default_factory=lambda: np.zeros((1, 1), dtype=np.float64))
    conductivity_grid: np.ndarray = field(default_factory=lambda: np.zeros((1, 1), dtype=np.float64))


class ECADThermalTwin:
    """
    Solveur de diffusion thermique couplée ECAD <-> MCAD avec matrice de conductivité 2D.
    Intègre les sources de chaleur Joule des pistes de cuivre et composants actifs
    dans la plaque FR4 et modélise la conduction hétérogène à travers les couches de cuivre.
    """

    def __init__(
        self,
        board_width_mm: float,
        board_length_mm: float,
        board_thickness_mm: float = 1.6,
        substrate_conductivity_k: float = 0.3,
        copper_conductivity_k: float = 385.0,
        layer_count: int = 4
    ) -> None:
        self.width_mm: float = float(board_width_mm)
        self.length_mm: float = float(board_length_mm)
        self.thickness_mm: float = float(board_thickness_mm)
        self.k_fr4: float = float(substrate_conductivity_k)
        self.k_cu: float = float(copper_conductivity_k)
        self.layer_count: int = int(layer_count)

        self.traces: List[CopperTrace] = []
        self.components: List[SMTComponent] = []
        self.copper_planes: Dict[str, float] = {}

    def add_copper_trace(self, trace: CopperTrace) -> None:
        """Enregistre une piste conductrice issue du schéma IPC-2581 ou Gerber."""
        self.traces.append(trace)

    def add_component(self, comp: SMTComponent) -> None:
        """Enregistre un composant dissipatif."""
        self.components.append(comp)

    def add_copper_plane(self, layer_name: str, coverage: float = 1.0) -> None:
        """Enregistre un plan continu de cuivre (alimentation ou masse)."""
        self.copper_planes[layer_name] = max(0.0, min(1.0, float(coverage)))

    def compute_copper_density_grid(self, grid_resolution: int = 20) -> np.ndarray:
        """
        Calcule la matrice 2D de densité volumique de cuivre en superposant
        les pistes discrètes et les plans continus sur la grille.
        """
        nx = grid_resolution
        ny = grid_resolution
        dx = (self.width_mm * 1e-3) / nx
        dy = (self.length_mm * 1e-3) / ny

        density_grid = np.zeros((nx, ny), dtype=np.float64)

        if self.copper_planes:
            avg_plane_coverage = sum(self.copper_planes.values()) / max(1, self.layer_count)
            density_grid += avg_plane_coverage

        for tr in self.traces:
            self._rasterize_trace_density(tr, density_grid, nx, ny, dx, dy)

        return np.clip(density_grid, 0.0, 1.0)

    def _rasterize_trace_density(
        self,
        trace: CopperTrace,
        density_grid: np.ndarray,
        nx: int,
        ny: int,
        dx: float,
        dy: float
    ) -> None:
        """Projette une piste de cuivre sur la matrice de densité."""
        if not trace.has_spatial_coordinates():
            trace_area = (trace.length_mm * trace.width_mm)
            board_area = max(1e-6, self.width_mm * self.length_mm)
            density_grid += min(0.15, trace_area / board_area)
            return

        x0 = max(0.0, min(self.width_mm, trace.start_x_mm))
        y0 = max(0.0, min(self.length_mm, trace.start_y_mm))
        x1 = max(0.0, min(self.width_mm, trace.end_x_mm))
        y1 = max(0.0, min(self.length_mm, trace.end_y_mm))

        dist = math.hypot(x1 - x0, y1 - y0)
        steps = max(2, int(dist / max(1e-3, min(dx * 1e3, dy * 1e3)) * 2))

        weight = min(1.0, (trace.width_mm * 1e-3) / max(1e-6, dx))
        for step in range(steps + 1):
            ratio = float(step) / float(steps)
            x_pos = x0 + ratio * (x1 - x0)
            y_pos = y0 + ratio * (y1 - y0)
            ix = min(nx - 1, max(0, int((x_pos / max(1e-3, self.width_mm)) * nx)))
            iy = min(ny - 1, max(0, int((y_pos / max(1e-3, self.length_mm)) * ny)))
            density_grid[ix, iy] = min(1.0, density_grid[ix, iy] + weight)

    def compute_effective_conductivity_grid(self, grid_resolution: int = 20) -> np.ndarray:
        """
        Calcule la matrice 2D de conductivité thermique équivalente k_eff(x, y).
        Pondère la conductivité FR4 de base par la fraction volumique locale de cuivre.
        """
        copper_density = self.compute_copper_density_grid(grid_resolution)
        cu_fraction_total = min(0.35, (self.layer_count * 35e-6) / max(1e-6, self.thickness_mm * 1e-3))
        k_eff = self.k_fr4 + (0.05 + copper_density * cu_fraction_total) * self.k_cu
        return k_eff

    def _build_conductance_matrices(
        self,
        k_grid: np.ndarray,
        dx: float,
        dy: float,
        h_coeff: float,
        nx: int,
        ny: int
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Construit les matrices de conductance finies avec moyennes harmoniques d'interface."""
        ke = np.zeros((nx, ny), dtype=np.float64)
        kw = np.zeros((nx, ny), dtype=np.float64)
        kn = np.zeros((nx, ny), dtype=np.float64)
        ks = np.zeros((nx, ny), dtype=np.float64)

        ke[:-1, :] = (2.0 * k_grid[:-1, :] * k_grid[1:, :]) / (k_grid[:-1, :] + k_grid[1:, :] + 1e-12)
        kw[1:, :] = (2.0 * k_grid[1:, :] * k_grid[:-1, :]) / (k_grid[1:, :] + k_grid[:-1, :] + 1e-12)
        kn[:, :-1] = (2.0 * k_grid[:, :-1] * k_grid[:, 1:]) / (k_grid[:, :-1] + k_grid[:, 1:] + 1e-12)
        ks[:, 1:] = (2.0 * k_grid[:, 1:] * k_grid[:, :-1]) / (k_grid[:, 1:] + k_grid[:, :-1] + 1e-12)

        inv_dx2 = 1.0 / max(1e-12, dx ** 2)
        inv_dy2 = 1.0 / max(1e-12, dy ** 2)

        ce = ke * inv_dx2
        cw = kw * inv_dx2
        cn = kn * inv_dy2
        cs = ks * inv_dy2
        cdiag = ce + cw + cn + cs + h_coeff

        return ce, cw, cn, cs, cdiag

    def solve_thermal_equilibrium(
        self,
        ambient_temp_c: float = 25.0,
        convection_coeff_h: float = 15.0,
        grid_resolution: int = 20,
        max_iterations: int = 80
    ) -> ECADThermalReport:
        """
        Résout l'équation de Fourier k(x,y) nabla^2 T + q = h (T - T_amb) par relaxation
        sur la matrice hétérogène 2D représentant les pistes et couches de cuivre.
        """
        nx = grid_resolution
        ny = grid_resolution
        dx = (self.width_mm * 1e-3) / nx
        dy = (self.length_mm * 1e-3) / ny
        vol_cell = dx * dy * (self.thickness_mm * 1e-3)

        heat_sources = np.zeros((nx, ny), dtype=np.float64)
        total_heat_watts = self._accumulate_heat_sources(heat_sources, ambient_temp_c, nx, ny, dx, dy)

        k_grid = self.compute_effective_conductivity_grid(grid_resolution)
        h_coeff = (2.0 * convection_coeff_h) / max(1e-6, self.thickness_mm * 1e-3)

        ce, cw, cn, cs, cdiag = self._build_conductance_matrices(k_grid, dx, dy, h_coeff, nx, ny)

        temp_grid = np.full((nx, ny), ambient_temp_c, dtype=np.float64)
        source_vol = heat_sources / vol_cell

        for _ in range(max_iterations):
            te = np.roll(temp_grid, -1, axis=0)
            te[-1, :] = 0.0
            tw = np.roll(temp_grid, 1, axis=0)
            tw[0, :] = 0.0
            tn = np.roll(temp_grid, -1, axis=1)
            tn[:, -1] = 0.0
            ts = np.roll(temp_grid, 1, axis=1)
            ts[:, 0] = 0.0

            rhs = ce * te + cw * tw + cn * tn + cs * ts + h_coeff * ambient_temp_c + source_vol
            t_next = rhs / cdiag
            temp_grid = 0.85 * t_next + 0.15 * temp_grid

        max_temp, hottest_comp, is_safe = self._evaluate_component_temperatures(temp_grid, nx, ny)

        copper_density = self.compute_copper_density_grid(grid_resolution)
        return ECADThermalReport(
            ambient_temp_c=ambient_temp_c,
            max_board_temp_c=max_temp,
            hottest_component_id=hottest_comp,
            total_electrical_heat_watts=total_heat_watts,
            is_thermally_safe=is_safe,
            temperature_grid=temp_grid,
            copper_density_grid=copper_density,
            conductivity_grid=k_grid
        )

    def _accumulate_heat_sources(
        self,
        heat_sources: np.ndarray,
        ambient_temp_c: float,
        nx: int,
        ny: int,
        dx: float,
        dy: float
    ) -> float:
        """Agrège les sources de chaleur des pistes et des composants discrets."""
        total_heat_watts = 0.0

        for tr in self.traces:
            p_joule = tr.compute_joule_heat_watts(ambient_temp_c)
            total_heat_watts += p_joule
            if tr.has_spatial_coordinates():
                self._distribute_trace_joule_heat(tr, p_joule, heat_sources, nx, ny, dx, dy)
            else:
                heat_sources += p_joule / (nx * ny)

        for comp in self.components:
            total_heat_watts += comp.power_dissipation_watts
            gx = min(nx - 1, max(0, int((comp.position_x_mm / max(1e-3, self.width_mm)) * nx)))
            gy = min(ny - 1, max(0, int((comp.position_y_mm / max(1e-3, self.length_mm)) * ny)))
            heat_sources[gx, gy] += comp.power_dissipation_watts

        return total_heat_watts

    def _distribute_trace_joule_heat(
        self,
        trace: CopperTrace,
        p_joule: float,
        heat_sources: np.ndarray,
        nx: int,
        ny: int,
        dx: float,
        dy: float
    ) -> None:
        """Répartit la puissance Joule d'une piste le long de ses cellules de passage."""
        x0 = max(0.0, min(self.width_mm, trace.start_x_mm))
        y0 = max(0.0, min(self.length_mm, trace.start_y_mm))
        x1 = max(0.0, min(self.width_mm, trace.end_x_mm))
        y1 = max(0.0, min(self.length_mm, trace.end_y_mm))

        dist = math.hypot(x1 - x0, y1 - y0)
        steps = max(2, int(dist / max(1e-3, min(dx * 1e3, dy * 1e3)) * 2))

        fraction = p_joule / float(steps + 1)
        for step in range(steps + 1):
            ratio = float(step) / float(steps)
            px = x0 + ratio * (x1 - x0)
            py = y0 + ratio * (y1 - y0)
            ix = min(nx - 1, max(0, int((px / max(1e-3, self.width_mm)) * nx)))
            iy = min(ny - 1, max(0, int((py / max(1e-3, self.length_mm)) * ny)))
            heat_sources[ix, iy] += fraction

    def _evaluate_component_temperatures(
        self,
        temp_grid: np.ndarray,
        nx: int,
        ny: int
    ) -> Tuple[float, str, bool]:
        """Évalue les températures de jonction et vérifie les seuils de sécurité thermique."""
        max_temp = float(np.max(temp_grid))
        hottest_comp = "None"
        is_safe = True

        for comp in self.components:
            gx = min(nx - 1, max(0, int((comp.position_x_mm / max(1e-3, self.width_mm)) * nx)))
            gy = min(ny - 1, max(0, int((comp.position_y_mm / max(1e-3, self.length_mm)) * ny)))
            local_t = float(temp_grid[gx, gy])
            tj = local_t + comp.thermal_resistance_jc_k_w * comp.power_dissipation_watts
            if tj > comp.max_junction_temp_c:
                is_safe = False
            if local_t >= max_temp - 0.5:
                hottest_comp = comp.designator

        return max_temp, hottest_comp, is_safe
