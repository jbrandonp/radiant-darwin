"""
Atelier d'Inspection & Métrologie 3D de précision (Inspection / Measure Workbench).
Permet de mesurer les distances 3D, angles, surfaces, volumes, centres de gravité (CoG),
moments d'inertie, jeux/dégagements minimaux (clearance) et détection de collisions/interférences.
Typage métrologique strict et protocoles d'inspection géométrique.
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


@dataclass(frozen=True)
class InertiaTensor:
    """Tenseur d'inertie 3D complet (moments et produits d'inertie) et axes principaux."""
    ixx: float
    iyy: float
    izz: float
    ixy: float
    ixz: float
    iyz: float
    principal_moments: Tuple[float, float, float]
    radius_of_gyration: Tuple[float, float, float]


def compute_inertia_tensor(solid: Solid, density_g_cm3: float = 1.0) -> InertiaTensor:
    """
    Calcule le tenseur d'inertie 3D exact par rapport au centre de gravité du solide.
    Utilise la décomposition tétraédrique vectorisée du théorème de la divergence.
    """
    if solid.is_empty():
        return InertiaTensor(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    mesh = solid.manifold.to_mesh()
    vert_props = np.array(mesh.vert_properties, dtype=np.float64)[:, :3]
    tri_verts = np.array(mesh.tri_verts, dtype=np.int64)

    if len(vert_props) == 0 or len(tri_verts) == 0:
        return InertiaTensor(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    v0 = vert_props[tri_verts[:, 0]]
    v1 = vert_props[tri_verts[:, 1]]
    v2 = vert_props[tri_verts[:, 2]]

    dets = np.einsum("ij,ij->i", np.cross(v0, v1), v2)
    v_tets = dets / 6.0
    total_vol = float(np.sum(v_tets))

    if abs(total_vol) < 1e-9:
        return InertiaTensor(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    if total_vol < 0.0:
        # Normalisation automatique si le maillage d'entrée présente un enroulement inversé
        dets = -dets
        v_tets = -v_tets
        total_vol = -total_vol

    # Intégrales polynomiales de second ordre par rapport à l'origine
    coeff_sq = dets / 60.0
    x2 = np.sum(coeff_sq * (v0[:, 0]**2 + v1[:, 0]**2 + v2[:, 0]**2 + v0[:, 0]*v1[:, 0] + v0[:, 0]*v2[:, 0] + v1[:, 0]*v2[:, 0]))
    y2 = np.sum(coeff_sq * (v0[:, 1]**2 + v1[:, 1]**2 + v2[:, 1]**2 + v0[:, 1]*v1[:, 1] + v0[:, 1]*v2[:, 1] + v1[:, 1]*v2[:, 1]))
    z2 = np.sum(coeff_sq * (v0[:, 2]**2 + v1[:, 2]**2 + v2[:, 2]**2 + v0[:, 2]*v1[:, 2] + v0[:, 2]*v2[:, 2] + v1[:, 2]*v2[:, 2]))

    coeff_prod = dets / 120.0
    xy = np.sum(coeff_prod * (2.0*v0[:, 0]*v0[:, 1] + 2.0*v1[:, 0]*v1[:, 1] + 2.0*v2[:, 0]*v2[:, 1] +
                             v0[:, 0]*v1[:, 1] + v0[:, 1]*v1[:, 0] + v0[:, 0]*v2[:, 1] + v0[:, 1]*v2[:, 0] +
                             v1[:, 0]*v2[:, 1] + v1[:, 1]*v2[:, 0]))
    xz = np.sum(coeff_prod * (2.0*v0[:, 0]*v0[:, 2] + 2.0*v1[:, 0]*v1[:, 2] + 2.0*v2[:, 0]*v2[:, 2] +
                             v0[:, 0]*v1[:, 2] + v0[:, 2]*v1[:, 0] + v0[:, 0]*v2[:, 2] + v0[:, 2]*v2[:, 0] +
                             v1[:, 0]*v2[:, 2] + v1[:, 2]*v2[:, 0]))
    yz = np.sum(coeff_prod * (2.0*v0[:, 1]*v0[:, 2] + 2.0*v1[:, 1]*v1[:, 2] + 2.0*v2[:, 1]*v2[:, 2] +
                             v0[:, 1]*v1[:, 2] + v0[:, 2]*v1[:, 1] + v0[:, 1]*v2[:, 2] + v0[:, 2]*v2[:, 1] +
                             v1[:, 1]*v2[:, 2] + v1[:, 2]*v2[:, 1]))

    # Moments à l'origine (volumiques)
    i_xx_0 = float(y2 + z2)
    i_yy_0 = float(x2 + z2)
    i_zz_0 = float(x2 + y2)
    i_xy_0 = -float(xy)
    i_xz_0 = -float(xz)
    i_yz_0 = -float(yz)

    # Centre de masse
    c_tet = (v0 + v1 + v2) / 4.0
    com = np.sum(v_tets[:, None] * c_tet, axis=0) / total_vol
    cx, cy, cz = float(com[0]), float(com[1]), float(com[2])

    # Théorème de Huygens / axes parallèles pour ramener au centre de gravité
    i_xx_g = float(i_xx_0 - total_vol * (cy**2 + cz**2))
    i_yy_g = float(i_yy_0 - total_vol * (cx**2 + cz**2))
    i_zz_g = float(i_zz_0 - total_vol * (cx**2 + cy**2))
    i_xy_g = float(i_xy_0 + total_vol * cx * cy)
    i_xz_g = float(i_xz_0 + total_vol * cx * cz)
    i_yz_g = float(i_yz_0 + total_vol * cy * cz)

    # Multiplication par la masse volumique (conversion mm³ et g/cm³ -> g.mm²)
    density_factor = density_g_cm3 * 1e-3  # g/mm³
    ixx = i_xx_g * density_factor
    iyy = i_yy_g * density_factor
    izz = i_zz_g * density_factor
    ixy = i_xy_g * density_factor
    ixz = i_xz_g * density_factor
    iyz = i_yz_g * density_factor

    # Matrice d'inertie 3x3 et diagonalisation (moments principaux)
    inertia_matrix = np.array([
        [ixx, ixy, ixz],
        [ixy, iyy, iyz],
        [ixz, iyz, izz]
    ], dtype=np.float64)

    eigenvalues, _ = np.linalg.eigh(inertia_matrix)
    principal = (float(eigenvalues[0]), float(eigenvalues[1]), float(eigenvalues[2]))

    # Rayons de giration rg = sqrt(I / M)
    total_mass = total_vol * density_factor
    if total_mass > 1e-9:
        rg_x = float(np.sqrt(max(0.0, ixx / total_mass)))
        rg_y = float(np.sqrt(max(0.0, iyy / total_mass)))
        rg_z = float(np.sqrt(max(0.0, izz / total_mass)))
    else:
        rg_x, rg_y, rg_z = 0.0, 0.0, 0.0

    return InertiaTensor(
        ixx=ixx,
        iyy=iyy,
        izz=izz,
        ixy=ixy,
        ixz=ixz,
        iyz=iyz,
        principal_moments=principal,
        radius_of_gyration=(rg_x, rg_y, rg_z)
    )


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
) -> Dict[str, Union[str, float, Vector3D, InertiaTensor]]:
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
    inertia = compute_inertia_tensor(solid, density_g_cm3)

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
        "inertia": inertia,
        "genus": float(solid.genus()),
        "vertices_count": float(solid.num_vertices()),
        "faces_count": float(solid.num_faces()),
    }
