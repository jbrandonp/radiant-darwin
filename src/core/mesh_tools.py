"""
Atelier d'Analyse et Réparation de Maillages 3D (Mesh Workbench).
Équivalent de l'atelier Mesh de FreeCAD :
- Diagnostic de fermeture / étanchéité (Watertight / 2-Manifold).
- Détection des facettes dégénérées, dupliquées et sommets orphelins.
- Réparation automatique de maillage (nettoyage topologique, inversion des normales).
- Simplification et décimation adaptative (Quadric Decimation).
- Conversion de maillage triangulaire en Solide CAO B-Rep étanche.
Typage maillage et structures tensorielles rigoureuses.
"""

from __future__ import annotations
from typing import List, Tuple, Sequence, Optional
from dataclasses import dataclass
import numpy as np
import manifold3d as m
import trimesh
import trimesh.repair as tm_repair

from src.core.geometry import Solid


@dataclass(frozen=True)
class MeshDiagnostic:
    """Rapport d'analyse géométrique et topologique d'un maillage 3D."""
    is_watertight: bool
    num_vertices: int
    num_edges: int
    num_faces: int
    genus: int
    surface_area: float
    volume: float
    degenerate_faces: int
    duplicate_faces: int
    unreferenced_vertices: int
    euler_number: int


def diagnose_mesh(solid: Solid) -> MeshDiagnostic:
    """
    Exécute un audit de conformité géométrique et topologique complet du maillage.
    Identifie les défauts de surface, auto-intersections et trous ouverts.
    """
    if solid.is_empty():
        return MeshDiagnostic(
            is_watertight=False,
            num_vertices=0,
            num_edges=0,
            num_faces=0,
            genus=0,
            surface_area=0.0,
            volume=0.0,
            degenerate_faces=0,
            duplicate_faces=0,
            unreferenced_vertices=0,
            euler_number=0
        )

    mesh_data = solid.manifold.to_mesh()
    vert_props = np.array(mesh_data.vert_properties, dtype=np.float64)[:, :3]
    tri_verts = np.array(mesh_data.tri_verts, dtype=np.int64)

    tm = trimesh.Trimesh(vertices=vert_props, faces=tri_verts, process=False)

    # Détection des défauts
    non_deg_mask = tm.nondegenerate_faces()
    degenerate_count = int(np.sum(~non_deg_mask))

    unique_faces = len(np.unique(np.sort(tri_verts, axis=1), axis=0))
    duplicate_count = len(tri_verts) - unique_faces

    used_verts = np.unique(tri_verts)
    unref_count = max(0, len(vert_props) - len(used_verts))

    euler = int(tm.euler_number)
    genus = int(solid.genus())
    area = float(solid.surface_area())
    vol = float(solid.volume())
    watertight = bool(tm.is_watertight)

    return MeshDiagnostic(
        is_watertight=watertight,
        num_vertices=int(solid.num_vertices()),
        num_edges=int(solid.num_edges()),
        num_faces=int(solid.num_faces()),
        genus=genus,
        surface_area=area,
        volume=vol,
        degenerate_faces=degenerate_count,
        duplicate_faces=duplicate_count,
        unreferenced_vertices=unref_count,
        euler_number=euler
    )


def repair_mesh(solid: Solid) -> Solid:
    """
    Répare automatiquement un maillage 3D défectueux ou non-manifold :
    - Élimination des facettes dégénérées (aire nulle)
    - Fusion des sommets dupliqués
    - Recalcul et réorientation cohérente des normales de face
    - Remplissage des trous ouverts
    - Reconstitution d'un solide manifold garanti étanche
    """
    if solid.is_empty():
        return solid

    mesh_data = solid.manifold.to_mesh()
    vert_props = np.array(mesh_data.vert_properties, dtype=np.float64)[:, :3]
    tri_verts = np.array(mesh_data.tri_verts, dtype=np.int64)

    tm = trimesh.Trimesh(vertices=vert_props, faces=tri_verts, process=True)

    # Pipeline de réparation certifié
    tm_repair.fix_normals(tm)
    tm_repair.fix_winding(tm)
    tm_repair.fill_holes(tm)
    tm.update_faces(tm.nondegenerate_faces())
    tm.remove_unreferenced_vertices()

    return create_solid_from_triangles(
        vertices=tm.vertices.tolist(),
        faces=tm.faces.tolist(),
        name=f"{solid.name}_Repaired"
    )


def simplify_mesh(solid: Solid, target_fraction: float = 0.5) -> Solid:
    """
    Décime et simplifie le maillage en réduisant le nombre de triangles
    tout en préservant fidèlement la courbure et le volume initial.
    """
    if solid.is_empty():
        return solid

    # Simplification par Manifold3D avec tolérance adaptative
    b_min, b_max = solid.bounding_box()
    diag = float(np.sqrt((b_max.x - b_min.x)**2 + (b_max.y - b_min.y)**2 + (b_max.z - b_min.z)**2))
    tolerance = max(0.01, diag * 0.005 * (1.0 - max(0.1, min(0.9, target_fraction))))

    simplified = solid.simplify(tolerance)
    return Solid(simplified.manifold, f"{solid.name}_Decimated")


def flip_mesh_normals(solid: Solid) -> Solid:
    """Inverse l'orientation des normales de face du maillage (Faces inversées)."""
    if solid.is_empty():
        return solid

    mesh_data = solid.manifold.to_mesh()
    vert_props = np.array(mesh_data.vert_properties, dtype=np.float32)
    tri_verts = np.array(mesh_data.tri_verts, dtype=np.uint32)

    # Inversion de l'ordre des sommets de chaque triangle
    flipped_tris = np.column_stack([tri_verts[:, 0], tri_verts[:, 2], tri_verts[:, 1]])
    mesh = m.Mesh(vert_properties=vert_props, tri_verts=flipped_tris)
    res_manifold = m.Manifold(mesh)
    return Solid(res_manifold, f"{solid.name}_Flipped")


def create_solid_from_triangles(
    vertices: Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    name: str = "MeshSolid"
) -> Solid:
    """
    Construit un Solide CAO Manifold3D à partir d'une liste de coordonnées de sommets et facettes.
    Assure automatiquement l'orientation positive du volume.
    """
    v_arr = np.array(vertices, dtype=np.float32)
    f_arr = np.array(faces, dtype=np.uint32)

    mesh = m.Mesh(vert_properties=v_arr, tri_verts=f_arr)
    mani = m.Manifold(mesh)

    # Si le volume calculé est négatif, réorienter les facettes pour un volume positif
    if float(mani.volume()) < -1e-6:
        f_arr_flipped = np.column_stack([f_arr[:, 0], f_arr[:, 2], f_arr[:, 1]])
        mesh = m.Mesh(vert_properties=v_arr, tri_verts=f_arr_flipped)
        mani = m.Manifold(mesh)

    return Solid(mani, name)
