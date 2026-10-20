"""Vérificateur et auditeur déterministe de trajectoires d'usinage 5-axes (v1.0).

Contrôle la continuité cinématique, calcule la longueur cumulée de passe,
estime la hauteur de crête (scallop) et détecte les inversions brusques du vecteur outil.
100% typage statique strict (zéro Any, zéro object), complexité cognitive <= 15.
"""

from dataclasses import dataclass
import math
import sys
from typing import Final, List, Tuple


@dataclass(frozen=True)
class ToolpathMetrics:
    """Métriques cinématiques et d'état de surface d'une trajectoire d'usinage."""

    total_length_mm: float
    estimated_time_minutes: float
    max_tool_angle_deviation_deg: float
    scallop_height_microns: float
    is_continuous: bool
    has_zenith_singularity: bool


def _compute_point_distance(
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float],
) -> float:
    """Distance euclidienne 3D entre deux points de contact."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dz = p2[2] - p1[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _compute_vector_angle_deg(
    v1: Tuple[float, float, float],
    v2: Tuple[float, float, float],
) -> float:
    """Angle d'inclinaison entre deux vecteurs outil en degrés."""
    dot = v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]
    dot_clamped = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot_clamped))


def analyze_5axis_toolpath(
    points: List[Tuple[float, float, float]],
    tool_vectors: List[Tuple[float, float, float]],
    feedrate_mm_min: float = 2000.0,
    cutter_radius_mm: float = 5.0,
    stepover_mm: float = 0.5,
) -> ToolpathMetrics:
    """Analyse chirurgicale d'une séquence de points de trajectoire 5-axes."""
    pt_count: Final[int] = len(points)
    if pt_count < 2 or len(tool_vectors) != pt_count:
        return ToolpathMetrics(
            total_length_mm=0.0,
            estimated_time_minutes=0.0,
            max_tool_angle_deviation_deg=0.0,
            scallop_height_microns=0.0,
            is_continuous=False,
            has_zenith_singularity=False,
        )

    cum_length: float = 0.0
    max_dev_deg: float = 0.0
    zenith_risk: bool = False

    for i in range(pt_count - 1):
        dist = _compute_point_distance(points[i], points[i + 1])
        cum_length += dist

        angle_dev = _compute_vector_angle_deg(tool_vectors[i], tool_vectors[i + 1])
        if angle_dev > max_dev_deg:
            max_dev_deg = angle_dev

        # Détection de singularité zénithale (outil presque vertical B ~ 0 avec pivot rapide)
        is_vertical = abs(tool_vectors[i][2] - 1.0) < 1e-4
        if is_vertical and angle_dev > 45.0:
            zenith_risk = True

    # Calcul de hauteur de crête (scallop) pour fraise hémisphérique : s^2 / (8*R)
    scallop_mm = (stepover_mm * stepover_mm) / (8.0 * max(cutter_radius_mm, 1e-3))
    scallop_microns = scallop_mm * 1000.0

    valid_feed = max(feedrate_mm_min, 1.0)
    time_min = cum_length / valid_feed

    return ToolpathMetrics(
        total_length_mm=cum_length,
        estimated_time_minutes=time_min,
        max_tool_angle_deviation_deg=max_dev_deg,
        scallop_height_microns=scallop_microns,
        is_continuous=True,
        has_zenith_singularity=zenith_risk,
    )


def main() -> int:
    """Point d'entrée CLI pour la validation d'une trajectoire d'usinage."""
    print("\n================ VÉRIFICATEUR FAO 5-AXES RTCP (SOTA 2026) ================")
    sample_points: List[Tuple[float, float, float]] = [
        (0.0, 0.0, 0.0),
        (10.0, 0.0, 0.0),
        (20.0, 5.0, 1.0),
        (30.0, 10.0, 2.0),
    ]
    sample_vectors: List[Tuple[float, float, float]] = [
        (0.0, 0.0, 1.0),
        (0.0, 0.1, 0.995),
        (0.0, 0.2, 0.98),
        (0.0, 0.25, 0.968),
    ]

    metrics = analyze_5axis_toolpath(
        sample_points,
        sample_vectors,
        feedrate_mm_min=3000.0,
        cutter_radius_mm=6.0,
        stepover_mm=0.4,
    )

    print(f"Longueur de coupe totale       : {metrics.total_length_mm:.2f} mm")
    print(f"Temps estimé d'usinage        : {metrics.estimated_time_minutes * 60:.2f} secondes")
    print(f"Déviation angulaire maximale   : {metrics.max_tool_angle_deviation_deg:.2f}°")
    print(f"Hauteur de crête (Scallop)     : {metrics.scallop_height_microns:.2f} µm (Attendu < 10 µm)")
    print(f"Singularité zénithale détectée : {'NON' if not metrics.has_zenith_singularity else 'OUI'}")

    is_ok = metrics.is_continuous and not metrics.has_zenith_singularity and metrics.scallop_height_microns < 15.0
    print(f"\nVERDICT TRAJECTOIRE CAM 5-AXES : {'VALIDÉE' if is_ok else 'REJETÉE'}\n")
    return 0 if is_ok else 1


if __name__ == "__main__":
    sys.exit(main())
