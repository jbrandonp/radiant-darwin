"""
Atelier d'Inspection & Métrologie 3D de précision (Inspection / Measure Workbench).
Permet de mesurer les distances 3D, angles, surfaces, volumes, centres de gravité (CoG),
moments d'inertie, jeux/dégagements minimaux (clearance) et détection de collisions/interférences.
Strictement typé sans utilisation d'Any.
"""

from __future__ import annotations
from typing import Dict, Tuple, Union, Optional
from dataclasses import dataclass
import numpy as np

from src.core.types import Vector3D
from src.core.geometry import Solid


@dataclass(frozen=True)
class MeasureResult:
    """Résultat complet d'une mesure 3D entre deux coordonnées dans l'espace."""
    p1: Vector3D
    p2: Vector3D
    distance: float
    dx: float
    dy: float
    dz: float
    angle_deg: float
    midpoint: Vector3D


def measure_points(p1: Vector3D, p2: Vector3D) -> MeasureResult:
    """
    Calcule la distance euclidienne 3D exacte, les composantes cartésiennes delta X, Y, Z
    et l'angle d'élévation par rapport au plan XY.
    """
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    dz = p2.z - p1.z
    dist = float(np.sqrt(dx * dx + dy * dy + dz * dz))

    # Angle avec le plan horizontal XY
    horiz_dist = float(np.hypot(dx, dy))
    angle_deg = float(np.degrees(np.arctan2(dz, max(1e-9, horiz_dist))))

    midpoint = Vector3D(
        (p1.x + p2.x) * 0.5,
        (p1.y + p2.y) * 0.5,
        (p1.z + p2.z) * 0.5
    )

    return MeasureResult(
        p1=p1,
        p2=p2,
        distance=dist,
        dx=dx,
        dy=dy,
        dz=dz,
        angle_deg=angle_deg,
        midpoint=midpoint
    )


def measure_angle_vectors(v1: Vector3D, v2: Vector3D) -> float:
    """Calcule l'angle exact en degrés entre deux vecteurs 3D."""
    dot = v1.x * v2.x + v1.y * v2.y + v1.z * v2.z
    norm1 = np.sqrt(v1.x * v1.x + v1.y * v1.y + v1.z * v1.z)
    norm2 = np.sqrt(v2.x * v2.x + v2.y * v2.y + v2.z * v2.z)
    if norm1 < 1e-9 or norm2 < 1e-9:
        return 0.0
    cos_theta = max(-1.0, min(1.0, dot / (norm1 * norm2)))
    return float(np.degrees(np.arccos(cos_theta)))


def compute_center_of_mass(solid: Solid) -> Vector3D:
    """
    Calcule le centre de gravité (barycentre volumique) exact du solide
    par décomposition tétraédrique du maillage selon le théorème d'Ostrogradski.
    """
    if solid.is_empty():
        return Vector3D(0.0, 0.0, 0.0)

    mesh = solid.manifold.to_mesh()
    vert_props = np.array(mesh.vert_properties, dtype=np.float64)[:, :3]
    tri_verts = np.array(mesh.tri_verts, dtype=np.int64)

    if len(vert_props) == 0 or len(tri_verts) == 0:
        return Vector3D(0.0, 0.0, 0.0)

    v0 = vert_props[tri_verts[:, 0]]
    v1 = vert_props[tri_verts[:, 1]]
    v2 = vert_props[tri_verts[:, 2]]

    # Volume signé de chaque tétraèdre formé avec l'origine (0, 0, 0)
    v_tet = np.einsum("ij,ij->i", np.cross(v0, v1), v2) / 6.0
    c_tet = (v0 + v1 + v2) / 4.0

    total_vol = float(np.sum(v_tet))
    if abs(total_vol) < 1e-9:
        b_min, b_max = solid.bounding_box()
        return Vector3D((b_min.x + b_max.x) * 0.5, (b_min.y + b_max.y) * 0.5, (b_min.z + b_max.z) * 0.5)

    com = np.sum(v_tet[:, None] * c_tet, axis=0) / total_vol
    return Vector3D(float(com[0]), float(com[1]), float(com[2]))


def compute_clearance(solid_a: Solid, solid_b: Solid, max_search: float = 1000.0) -> float:
    """Calcule la distance minimale (jeu mécanique / clearance) entre deux pièces solides."""
    if solid_a.is_empty() or solid_b.is_empty():
        return float("inf")
    return solid_a.min_gap(solid_b, max_search)


def compute_interference(solid_a: Solid, solid_b: Solid) -> Tuple[bool, float]:
    """
    Détecte les interférences / collisions physiques entre deux solides.
    Retourne (collision_detectee, volume_intersection_mm3).
    """
    if solid_a.is_empty() or solid_b.is_empty():
        return (False, 0.0)
    inter = solid_a.intersection(solid_b)
    vol = inter.volume()
    return (vol > 1e-4, vol)


def generate_inspection_report(
    solid: Solid,
    material_name: str = "Aluminium 6061",
    density_g_cm3: float = 2.7
) -> Dict[str, Union[str, float, Vector3D]]:
    """Génère un rapport métrologique complet pour un corps solide."""
    vol_mm3 = solid.volume()
    vol_cm3 = vol_mm3 / 1000.0
    mass_g = vol_cm3 * density_g_cm3
    surf_mm2 = solid.surface_area()
    b_min, b_max = solid.bounding_box()
    dx = b_max.x - b_min.x
    dy = b_max.y - b_min.y
    dz = b_max.z - b_min.z
    com = compute_center_of_mass(solid)

    return {
        "solid_name": solid.name,
        "material": material_name,
        "density_g_cm3": density_g_cm3,
        "volume_mm3": vol_mm3,
        "volume_cm3": vol_cm3,
        "surface_area_mm2": surf_mm2,
        "mass_grams": mass_g,
        "mass_kg": mass_g / 1000.0,
        "box_dx_mm": dx,
        "box_dy_mm": dy,
        "box_dz_mm": dz,
        "box_min": b_min,
        "box_max": b_max,
        "center_of_mass": com,
        "genus": float(solid.genus()),
        "vertices_count": float(solid.num_vertices()),
        "faces_count": float(solid.num_faces()),
    }
