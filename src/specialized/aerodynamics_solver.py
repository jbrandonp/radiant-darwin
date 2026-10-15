"""
Atelier Mécanique des Fluides Numérique, Aérodynamique & Mécanique des Structures.
CFD Aerodynamics & Structural Mechanics Workbench.

Permet:
1. L'évaluation rapide des écoulements fluides autour des corps solides (CFD).
2. La polaire aérodynamique analytique des profils minces (Thin Airfoil Theory):
   - Coefficient de portance Cl = 2*pi*alpha (ou correction d'allongement fini)
   - Traînée induite Cdi = Cl^2 / (pi * AR * e)
   - Moment de tangage au foyer quart-arrière Cm_1/4
3. La résolution aérodynamique par réseau de tourbillons discrets (Vortex Lattice Method - VLM).
4. La résolution analytique et numérique de la flexion de poutres sous charges réparties:
   - Théorie des poutres d'Euler-Bernoulli (flexion pure)
   - Théorie des poutres épaisses de Timoshenko (flexion + distorsion de cisaillement transverse)
   - Distributions d'efforts tranchants V(x), de moments fléchissants M(x), de rotations theta(x)
     et de contraintes normales de flexion sigma(x).
   - Prise en charge des conditions aux limites : encastrée-libre (cantilever),
     simplement appuyée (simply supported) et bi-encastrée (clamped-clamped).
5. Couplage aéroélastique aile-longeron (répartition de portance VLM vers déformation de poutre).

Typage statique exhaustif inviolable (strict typing) et complexité cognitive <= 25.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Tuple, Union
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
    camber_ratio: float = 0.0             # Cambrure relative (ex: 0.02 pour 2%)
    oswald_efficiency: float = 0.85       # Facteur d'efficacité d'envergure d'Oswald e
    zero_lift_angle_deg: float = 0.0      # Angle d'incidence à portance nulle alpha_0


@dataclass
class AerodynamicForces:
    """Résultantes des forces et rendements aérodynamiques calculés."""
    lift_force_n: float
    drag_force_n: float
    lift_to_drag_ratio: float
    lift_coefficient_cl: float
    drag_coefficient_cd: float
    induced_drag_coefficient_cdi: float = 0.0
    pitching_moment_cm14: float = 0.0
    pitching_moment_n_m: float = 0.0


@dataclass
class ThinAirfoilPolar:
    """Polaire aérodynamique issue de la théorie des profils minces et de la ligne portante."""
    alpha_deg: float
    alpha_rad: float
    lift_coefficient_cl: float
    induced_drag_cdi: float
    profile_drag_cd0: float
    total_drag_cd: float
    pitching_moment_cm14: float
    aerodynamic_center_x_c: float = 0.25
    lift_to_drag_ratio: float = 0.0


@dataclass
class VortexLatticeResult:
    """Résultats de distribution de circulation et de forces par réseau de tourbillons (VLM)."""
    spanwise_y: np.ndarray
    chordwise_x: np.ndarray
    circulation_gamma: np.ndarray
    sectional_lift_n_m: np.ndarray
    downwash_m_s: np.ndarray
    total_lift_coefficient_cl: float
    induced_drag_coefficient_cdi: float
    oswald_efficiency_e: float
    pitching_moment_cm14: float
    total_lift_n: float
    total_induced_drag_n: float


class BeamBoundaryCondition(str, Enum):
    """Conditions aux limites structurales pour l'analyse de flexion de poutre."""
    CANTILEVER = "cantilever"
    SIMPLY_SUPPORTED = "simply_supported"
    CLAMPED_CLAMPED = "clamped_clamped"


@dataclass
class BeamCrossSection:
    """Caractéristiques géométriques, sectionnelles et élastiques d'une poutre."""
    area_m2: float
    second_moment_i_m4: float
    height_m: float
    shear_correction_factor_kappa: float = 5.0 / 6.0
    youngs_modulus_e_pa: float = 70.0e9
    poissons_ratio_nu: float = 0.33
    shear_modulus_g_pa: Optional[float] = None

    def get_shear_modulus(self) -> float:
        """Calcule ou restitue le module de cisaillement G = E / (2 * (1 + nu))."""
        if self.shear_modulus_g_pa is not None:
            return self.shear_modulus_g_pa
        return self.youngs_modulus_e_pa / (2.0 * (1.0 + self.poissons_ratio_nu))

    @classmethod
    def create_rectangular(
        cls,
        width_m: float,
        height_m: float,
        youngs_modulus_e_pa: float = 70.0e9,
        poissons_ratio_nu: float = 0.33,
        shear_correction_factor_kappa: float = 5.0 / 6.0
    ) -> BeamCrossSection:
        """Crée une section rectangulaire pleine de largeur b et hauteur h."""
        w = max(1e-6, width_m)
        h = max(1e-6, height_m)
        return cls(
            area_m2=w * h,
            second_moment_i_m4=(w * (h ** 3)) / 12.0,
            height_m=h,
            shear_correction_factor_kappa=shear_correction_factor_kappa,
            youngs_modulus_e_pa=youngs_modulus_e_pa,
            poissons_ratio_nu=poissons_ratio_nu
        )

    @classmethod
    def create_circular(
        cls,
        diameter_m: float,
        youngs_modulus_e_pa: float = 70.0e9,
        poissons_ratio_nu: float = 0.33,
        shear_correction_factor_kappa: float = 0.9
    ) -> BeamCrossSection:
        """Crée une section cylindrique pleine de diamètre d."""
        d = max(1e-6, diameter_m)
        return cls(
            area_m2=float(np.pi) * (d ** 2) / 4.0,
            second_moment_i_m4=float(np.pi) * (d ** 4) / 64.0,
            height_m=d,
            shear_correction_factor_kappa=shear_correction_factor_kappa,
            youngs_modulus_e_pa=youngs_modulus_e_pa,
            poissons_ratio_nu=poissons_ratio_nu
        )

    @classmethod
    def create_thin_walled_tube(
        cls,
        outer_diameter_m: float,
        wall_thickness_m: float,
        youngs_modulus_e_pa: float = 70.0e9,
        poissons_ratio_nu: float = 0.33,
        shear_correction_factor_kappa: float = 0.5
    ) -> BeamCrossSection:
        """Crée une section tubulaire à paroi mince."""
        d_out = max(1e-6, outer_diameter_m)
        t = max(1e-7, min(wall_thickness_m, d_out * 0.49))
        d_in = d_out - 2.0 * t
        return cls(
            area_m2=float(np.pi) * ((d_out ** 2) - (d_in ** 2)) / 4.0,
            second_moment_i_m4=float(np.pi) * ((d_out ** 4) - (d_in ** 4)) / 64.0,
            height_m=d_out,
            shear_correction_factor_kappa=shear_correction_factor_kappa,
            youngs_modulus_e_pa=youngs_modulus_e_pa,
            poissons_ratio_nu=poissons_ratio_nu
        )


@dataclass
class BeamStructuralAnalysisResult:
    """Résultats d'analyse statique de poutre (Euler-Bernoulli et Timoshenko)."""
    x_stations_m: np.ndarray
    distributed_load_q_n_m: np.ndarray
    shear_force_v_n: np.ndarray
    bending_moment_m_nm: np.ndarray
    euler_bernoulli_deflection_w_m: np.ndarray
    timoshenko_shear_deflection_w_m: np.ndarray
    timoshenko_total_deflection_w_m: np.ndarray
    rotation_slope_theta_rad: np.ndarray
    bending_stress_sigma_pa: np.ndarray
    max_deflection_euler_bernoulli_m: float
    max_deflection_timoshenko_m: float
    max_bending_moment_nm: float
    max_shear_force_n: float
    max_bending_stress_pa: float


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
    """Solveur d'écoulement aérodynamique, polaires minces, VLM et forces CFD."""

    def calculate_reynolds_number(
        self,
        flow: FluidFlowProperties,
        chord_length: float
    ) -> float:
        """Calcule le nombre adimensionnel de Reynolds Re = (rho * V * L) / mu."""
        if flow.dynamic_viscosity <= 0.0:
            return 1e6
        return (flow.air_density * flow.velocity_m_s * max(0.001, chord_length)) / flow.dynamic_viscosity

    def calculate_thin_airfoil_polar(
        self,
        alpha_deg: float,
        aspect_ratio: Optional[float] = None,
        oswald_efficiency: float = 0.85,
        zero_lift_angle_deg: float = 0.0,
        camber_cm0: float = 0.0,
        cd0: float = 0.008
    ) -> ThinAirfoilPolar:
        """
        Calcule les coefficients de portance Cl, traînée induite Cdi et moment de tangage Cm_1/4.
        Théorie mince 2D : Cl = 2*pi*(alpha - alpha_0).
        Ligne portante 3D : Cl = 2*pi / (1 + 2 / (AR * e)) * (alpha - alpha_0).
        Traînée induite : Cdi = Cl^2 / (pi * AR * e).
        Moment au foyer quart-arrière : Cm_1/4 = camber_cm0 (invariant selon alpha).
        """
        alpha_rad = float(np.radians(alpha_deg))
        alpha_0_rad = float(np.radians(zero_lift_angle_deg))
        eff_alpha = alpha_rad - alpha_0_rad

        if aspect_ratio is None or aspect_ratio <= 0.0:
            cl = 2.0 * float(np.pi) * eff_alpha
            cdi = 0.0
        else:
            ar = max(0.1, aspect_ratio)
            e = max(0.1, min(1.0, oswald_efficiency))
            cl_slope = 2.0 * float(np.pi) / (1.0 + (2.0 / (ar * e)))
            cl = float(cl_slope * eff_alpha)
            cdi = float((cl ** 2) / (np.pi * ar * e))

        cm14 = float(camber_cm0)
        cd_tot = float(cd0 + cdi)
        ld_ratio = float(cl / max(1e-6, cd_tot))

        return ThinAirfoilPolar(
            alpha_deg=alpha_deg,
            alpha_rad=alpha_rad,
            lift_coefficient_cl=cl,
            induced_drag_cdi=cdi,
            profile_drag_cd0=cd0,
            total_drag_cd=cd_tot,
            pitching_moment_cm14=cm14,
            aerodynamic_center_x_c=0.25,
            lift_to_drag_ratio=ld_ratio
        )

    def solve_aerodynamic_forces(
        self,
        flow: FluidFlowProperties,
        airfoil: AirfoilSurfaceData
    ) -> AerodynamicForces:
        """
        Calcule la portance, la traînée, le moment de tangage et la finesse du profil.
        """
        planform_area = max(0.001, airfoil.chord * airfoil.span)
        aspect_ratio = airfoil.span / max(0.01, airfoil.chord)
        e = max(0.1, min(1.0, airfoil.oswald_efficiency))

        polar = self.calculate_thin_airfoil_polar(
            alpha_deg=airfoil.angle_of_attack_deg,
            aspect_ratio=aspect_ratio,
            oswald_efficiency=e,
            zero_lift_angle_deg=airfoil.zero_lift_angle_deg,
            camber_cm0=-float(np.pi) * 0.5 * airfoil.camber_ratio
        )

        q_dyn = 0.5 * flow.air_density * (flow.velocity_m_s ** 2)
        lift_n = float(q_dyn * planform_area * polar.lift_coefficient_cl)
        drag_n = float(q_dyn * planform_area * polar.total_drag_cd)
        pitching_moment_n_m = float(q_dyn * planform_area * airfoil.chord * polar.pitching_moment_cm14)
        ratio = lift_n / max(1e-6, drag_n)

        return AerodynamicForces(
            lift_force_n=lift_n,
            drag_force_n=drag_n,
            lift_to_drag_ratio=ratio,
            lift_coefficient_cl=polar.lift_coefficient_cl,
            drag_coefficient_cd=polar.total_drag_cd,
            induced_drag_coefficient_cdi=polar.induced_drag_cdi,
            pitching_moment_cm14=polar.pitching_moment_cm14,
            pitching_moment_n_m=pitching_moment_n_m
        )

    def solve_vortex_lattice(
        self,
        flow: FluidFlowProperties,
        airfoil: AirfoilSurfaceData,
        num_spanwise_panels: int = 20,
        oswald_efficiency: float = 0.85,
        zero_lift_angle_deg: float = 0.0,
        camber_cm0: float = 0.0
    ) -> VortexLatticeResult:
        """
        Méthode du réseau de tourbillons (VLM) à tourbillons en fer à cheval (horseshoe vortices).
        Évalue la distribution de circulation spanwise Gamma(y), la portance locale L'(y),
        le coefficient de portance global Cl, la traînée induite Cdi et le facteur d'Oswald e.
        """
        n_panels = max(4, num_spanwise_panels)
        span = max(0.01, airfoil.span)
        chord = max(0.001, airfoil.chord)
        planform_area = span * chord
        aspect_ratio = span / chord

        alpha_rad = float(np.radians(airfoil.angle_of_attack_deg))
        alpha_0_rad = float(np.radians(zero_lift_angle_deg))
        eff_alpha = alpha_rad - alpha_0_rad

        dy = span / float(n_panels)
        y_edges = np.linspace(-span * 0.5, span * 0.5, n_panels + 1)
        y_centers = 0.5 * (y_edges[:-1] + y_edges[1:])

        x_bv = chord * 0.25
        x_cp = chord * 0.75
        x0 = x_cp - x_bv

        aic_matrix, aic_trailing = self._build_vortex_lattice_aic(y_centers, y_edges, x0, n_panels)

        v_inf = max(0.01, flow.velocity_m_s)
        rhs = np.full(n_panels, -v_inf * np.sin(eff_alpha), dtype=np.float64)
        gamma = np.linalg.solve(aic_matrix, rhs)

        rho = flow.air_density
        q_dyn = 0.5 * rho * (v_inf ** 2)

        sectional_lift = rho * v_inf * gamma
        total_lift = float(np.sum(sectional_lift) * dy)
        cl = float(total_lift / max(1e-6, q_dyn * planform_area))

        w_ind = aic_trailing @ gamma
        induced_drag_n = float(-rho * np.sum(w_ind * gamma) * dy)
        cdi = float(induced_drag_n / max(1e-6, q_dyn * planform_area))

        denom = float(np.pi) * aspect_ratio * max(1e-9, cdi)
        calc_e = float(np.clip((cl ** 2) / denom, 0.4, 1.0)) if cdi > 1e-7 else oswald_efficiency

        cm14 = float(camber_cm0)
        x_centers = np.full(n_panels, x_cp, dtype=np.float64)

        return VortexLatticeResult(
            spanwise_y=y_centers,
            chordwise_x=x_centers,
            circulation_gamma=gamma,
            sectional_lift_n_m=sectional_lift,
            downwash_m_s=w_ind,
            total_lift_coefficient_cl=cl,
            induced_drag_coefficient_cdi=cdi,
            oswald_efficiency_e=calc_e,
            pitching_moment_cm14=cm14,
            total_lift_n=total_lift,
            total_induced_drag_n=induced_drag_n
        )

    def _build_vortex_lattice_aic(
        self,
        y_centers: np.ndarray,
        y_edges: np.ndarray,
        x0: float,
        n_panels: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Construit la matrice des coefficients d'influence aérodynamique (AIC)."""
        aic = np.zeros((n_panels, n_panels), dtype=np.float64)
        aic_trail = np.zeros((n_panels, n_panels), dtype=np.float64)
        four_pi = 4.0 * float(np.pi)

        for i in range(n_panels):
            yi = float(y_centers[i])
            for j in range(n_panels):
                y1 = float(y_edges[j])
                y2 = float(y_edges[j + 1])
                r1 = float(np.sqrt((x0 ** 2) + ((yi - y1) ** 2)))
                r2 = float(np.sqrt((x0 ** 2) + ((yi - y2) ** 2)))

                wt1 = -(1.0 / (four_pi * (yi - y1))) * (1.0 + (x0 / r1))
                wt2 = (1.0 / (four_pi * (yi - y2))) * (1.0 + (x0 / r2))
                wb = -(1.0 / (four_pi * x0)) * (((yi - y1) / r1) - ((yi - y2) / r2))

                aic[i, j] = wt1 + wt2 + wb
                aic_trail[i, j] = wt1 + wt2

        return aic, aic_trail

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


class StructuralBeamSolver:
    """
    Solveur d'élasticité et de mécanique des structures pour poutres sous charges réparties.
    Prend en charge les modèles d'Euler-Bernoulli (flexion pure) et de Timoshenko (flexion + cisaillement).
    """

    def solve_beam_deflection(
        self,
        length_m: float,
        cross_section: BeamCrossSection,
        distributed_load: Union[float, Sequence[float], np.ndarray],
        boundary_condition: BeamBoundaryCondition = BeamBoundaryCondition.CANTILEVER,
        num_stations: int = 101
    ) -> BeamStructuralAnalysisResult:
        """
        Calcule les distributions d'effort tranchant V(x), moment fléchissant M(x),
        flèche d'Euler-Bernoulli w_eb(x), flèche de cisaillement de Timoshenko w_shear(x),
        flèche totale Timoshenko w_tot(x) et contraintes de flexion sigma(x).
        """
        n_pts = max(11, num_stations)
        l_span = max(1e-4, float(length_m))
        x_stations = np.linspace(0.0, l_span, n_pts, dtype=np.float64)
        dx = float(x_stations[1] - x_stations[0])

        q = self._normalize_distributed_load(distributed_load, n_pts)

        e_mod = max(1e3, cross_section.youngs_modulus_e_pa)
        i_z = max(1e-12, cross_section.second_moment_i_m4)
        e_i = e_mod * i_z

        g_mod = max(1e3, cross_section.get_shear_modulus())
        area = max(1e-8, cross_section.area_m2)
        kappa = max(0.1, cross_section.shear_correction_factor_kappa)
        kappa_g_a = kappa * g_mod * area

        if boundary_condition == BeamBoundaryCondition.CANTILEVER:
            v, m, theta, w_eb, w_shear, w_tot = self._solve_cantilever(q, dx, n_pts, e_i, kappa_g_a)
        elif boundary_condition == BeamBoundaryCondition.SIMPLY_SUPPORTED:
            v, m, theta, w_eb, w_shear, w_tot = self._solve_simply_supported(x_stations, q, dx, n_pts, l_span, e_i, kappa_g_a)
        else:
            v, m, theta, w_eb, w_shear, w_tot = self._solve_clamped_clamped(x_stations, q, dx, n_pts, l_span, e_i, kappa_g_a)

        c_dist = cross_section.height_m * 0.5
        sigma_bending = (np.abs(m) * c_dist) / i_z

        return BeamStructuralAnalysisResult(
            x_stations_m=x_stations,
            distributed_load_q_n_m=q,
            shear_force_v_n=v,
            bending_moment_m_nm=m,
            euler_bernoulli_deflection_w_m=w_eb,
            timoshenko_shear_deflection_w_m=w_shear,
            timoshenko_total_deflection_w_m=w_tot,
            rotation_slope_theta_rad=theta,
            bending_stress_sigma_pa=sigma_bending,
            max_deflection_euler_bernoulli_m=float(np.max(np.abs(w_eb))),
            max_deflection_timoshenko_m=float(np.max(np.abs(w_tot))),
            max_bending_moment_nm=float(np.max(np.abs(m))),
            max_shear_force_n=float(np.max(np.abs(v))),
            max_bending_stress_pa=float(np.max(sigma_bending))
        )

    def solve_wing_aeroelastic_spar(
        self,
        airfoil: AirfoilSurfaceData,
        flow: FluidFlowProperties,
        spar_cross_section: BeamCrossSection,
        num_stations: int = 51
    ) -> Tuple[VortexLatticeResult, BeamStructuralAnalysisResult]:
        """
        Couplage aéroélastique : évalue la distribution de portance VLM et calcule la flexion
        du longeron d'aile encastré à l'emplanture (poutre cantilever).
        """
        aero_solver = AerodynamicsSolver()
        vlm_result = aero_solver.solve_vortex_lattice(
            flow=flow,
            airfoil=airfoil,
            num_spanwise_panels=max(10, num_stations - 1)
        )

        semi_span = airfoil.span * 0.5
        half_n = len(vlm_result.spanwise_y) // 2
        half_lift = vlm_result.sectional_lift_n_m[half_n:]

        beam_result = self.solve_beam_deflection(
            length_m=semi_span,
            cross_section=spar_cross_section,
            distributed_load=half_lift,
            boundary_condition=BeamBoundaryCondition.CANTILEVER,
            num_stations=num_stations
        )

        return vlm_result, beam_result

    def _normalize_distributed_load(
        self,
        distributed_load: Union[float, Sequence[float], np.ndarray],
        num_pts: int
    ) -> np.ndarray:
        """Interpole ou uniformise la charge répartie sur le maillage 1D."""
        if isinstance(distributed_load, (int, float)):
            return np.full(num_pts, float(distributed_load), dtype=np.float64)
        arr = np.asarray(distributed_load, dtype=np.float64)
        if len(arr) == num_pts:
            return arr
        x_orig = np.linspace(0.0, 1.0, len(arr))
        x_new = np.linspace(0.0, 1.0, num_pts)
        return np.interp(x_new, x_orig, arr)

    def _solve_cantilever(
        self,
        q: np.ndarray,
        dx: float,
        num_pts: int,
        e_i: float,
        kappa_g_a: float
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Résolution de poutre encastrée-libre (Cantilever)."""
        v = np.zeros(num_pts, dtype=np.float64)
        for i in range(num_pts - 2, -1, -1):
            v[i] = v[i + 1] + 0.5 * (q[i] + q[i + 1]) * dx

        m = np.zeros(num_pts, dtype=np.float64)
        for i in range(num_pts - 2, -1, -1):
            m[i] = m[i + 1] + 0.5 * (v[i] + v[i + 1]) * dx

        theta = np.zeros(num_pts, dtype=np.float64)
        curv = m / e_i
        for i in range(1, num_pts):
            theta[i] = theta[i - 1] + 0.5 * (curv[i - 1] + curv[i]) * dx

        w_eb = np.zeros(num_pts, dtype=np.float64)
        for i in range(1, num_pts):
            w_eb[i] = w_eb[i - 1] + 0.5 * (theta[i - 1] + theta[i]) * dx

        w_shear = np.zeros(num_pts, dtype=np.float64)
        gamma = v / kappa_g_a
        for i in range(1, num_pts):
            w_shear[i] = w_shear[i - 1] + 0.5 * (gamma[i - 1] + gamma[i]) * dx

        w_tot = w_eb + w_shear
        return v, m, theta, w_eb, w_shear, w_tot

    def _solve_simply_supported(
        self,
        x: np.ndarray,
        q: np.ndarray,
        dx: float,
        num_pts: int,
        length: float,
        e_i: float,
        kappa_g_a: float
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Résolution de poutre simplement appuyée (Simply Supported)."""
        total_load = float(np.sum(0.5 * (q[:-1] + q[1:]) * dx))
        x_mid = 0.5 * (x[:-1] + x[1:])
        q_mid = 0.5 * (q[:-1] + q[1:])
        moment_0 = float(np.sum(x_mid * q_mid * dx))

        r_b = moment_0 / max(1e-6, length)
        r_a = total_load - r_b

        cum_q = np.zeros(num_pts, dtype=np.float64)
        for i in range(1, num_pts):
            cum_q[i] = cum_q[i - 1] + 0.5 * (q[i - 1] + q[i]) * dx
        v = r_a - cum_q

        m = np.zeros(num_pts, dtype=np.float64)
        for i in range(1, num_pts):
            m[i] = m[i - 1] + 0.5 * (v[i - 1] + v[i]) * dx

        curv = m / e_i
        cum_curv = np.zeros(num_pts, dtype=np.float64)
        for i in range(1, num_pts):
            cum_curv[i] = cum_curv[i - 1] + 0.5 * (curv[i - 1] + curv[i]) * dx

        int_cum_curv = float(np.sum(0.5 * (cum_curv[:-1] + cum_curv[1:]) * dx))
        theta_0 = int_cum_curv / max(1e-6, length)
        theta = theta_0 - cum_curv

        w_eb = np.zeros(num_pts, dtype=np.float64)
        for i in range(1, num_pts):
            w_eb[i] = w_eb[i - 1] + 0.5 * (theta[i - 1] + theta[i]) * dx

        gamma = v / kappa_g_a
        w_shear = np.zeros(num_pts, dtype=np.float64)
        for i in range(1, num_pts):
            w_shear[i] = w_shear[i - 1] + 0.5 * (gamma[i - 1] + gamma[i]) * dx

        w_tot = w_eb + w_shear
        return v, m, theta, w_eb, w_shear, w_tot

    def _solve_clamped_clamped(
        self,
        x: np.ndarray,
        q: np.ndarray,
        dx: float,
        num_pts: int,
        length: float,
        e_i: float,
        kappa_g_a: float
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Résolution de poutre bi-encastrée (Clamped-Clamped)."""
        l_span = max(1e-4, length)
        l_minus_x = l_span - x
        int_1 = 0.5 * (l_minus_x ** 2) * q
        int_2 = (1.0 / 6.0) * (l_minus_x ** 3) * q

        k1 = float(np.sum(0.5 * (int_1[:-1] + int_1[1:]) * dx))
        k2 = float(np.sum(0.5 * (int_2[:-1] + int_2[1:]) * dx))

        l2 = l_span ** 2
        l3 = l_span ** 3
        m_a = (6.0 * k2 - 2.0 * l_span * k1) / l2
        r_a = (6.0 * l_span * k1 - 12.0 * k2) / l3

        cum_q = np.zeros(num_pts, dtype=np.float64)
        for i in range(1, num_pts):
            cum_q[i] = cum_q[i - 1] + 0.5 * (q[i - 1] + q[i]) * dx
        v = r_a - cum_q

        m = np.zeros(num_pts, dtype=np.float64)
        m[0] = m_a
        for i in range(1, num_pts):
            m[i] = m[i - 1] + 0.5 * (v[i - 1] + v[i]) * dx

        curv = -m / e_i
        theta = np.zeros(num_pts, dtype=np.float64)
        for i in range(1, num_pts):
            theta[i] = theta[i - 1] + 0.5 * (curv[i - 1] + curv[i]) * dx

        w_eb = np.zeros(num_pts, dtype=np.float64)
        for i in range(1, num_pts):
            w_eb[i] = w_eb[i - 1] + 0.5 * (theta[i - 1] + theta[i]) * dx

        gamma = v / kappa_g_a
        w_shear = np.zeros(num_pts, dtype=np.float64)
        for i in range(1, num_pts):
            w_shear[i] = w_shear[i - 1] + 0.5 * (gamma[i - 1] + gamma[i]) * dx

        w_tot = w_eb + w_shear
        return v, m, theta, w_eb, w_shear, w_tot


# Alias de clarification technique
NacaAnalyticPolar = AerodynamicsSolver
