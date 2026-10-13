"""
Moteur géométrique volumique 3D haute performance (B-Rep / CSG).
Utilise manifold3d pour garantir des solides manifold (étanches) et des opérations booléennes rapides.
"""

from __future__ import annotations
from typing import List, Tuple, Optional, Sequence
import numpy as np
import manifold3d as m

from src.core.types import Vector3D, Point2D, PlaneType, MeshBuffer, ColorRGBA


class Solid:
    """
    Représente un corps solide 3D étanche (manifold).
    Encapsule le modèle géométrique sous-jacent et fournit les opérations volumiques.
    """

    def __init__(self, internal_manifold: m.Manifold, name: str = "Solid") -> None:
        """Initialise le solide avec une instance Manifold."""
        self._manifold: m.Manifold = internal_manifold
        self.name: str = name
        self.color: ColorRGBA = ColorRGBA(0.72, 0.76, 0.82, 1.0)  # Gris aluminium Fusion 360

    @property
    def manifold(self) -> m.Manifold:
        """Accès à l'instance manifold sous-jacente."""
        return self._manifold

    def is_empty(self) -> bool:
        """Vérifie si le solide ne contient aucun volume."""
        return self._manifold.is_empty()

    def volume(self) -> float:
        """Calcule le volume exact du solide en unités cubiques."""
        if self._manifold.is_empty():
            return 0.0
        return float(self._manifold.volume())

    def bounding_box(self) -> Tuple[Vector3D, Vector3D]:
        """
        Calcule les coordonnées min et max de la boîte englobante (AABB).
        Retourne (min_pt, max_pt).
        """
        if self._manifold.is_empty():
            return (Vector3D(0.0, 0.0, 0.0), Vector3D(0.0, 0.0, 0.0))
        box = self._manifold.bounding_box()
        min_pt = Vector3D(float(box[0]), float(box[1]), float(box[2]))
        max_pt = Vector3D(float(box[3]), float(box[4]), float(box[5]))
        return (min_pt, max_pt)

    def translate(self, offset: Vector3D) -> Solid:
        """Applique une translation au solide."""
        new_manifold = self._manifold.translate([offset.x, offset.y, offset.z])
        res = Solid(new_manifold, self.name)
        res.color = self.color
        return res

    def rotate(self, rx_deg: float, ry_deg: float, rz_deg: float) -> Solid:
        """Applique des rotations en degrés autour des axes X, Y, Z."""
        new_manifold = self._manifold.rotate([rx_deg, ry_deg, rz_deg])
        res = Solid(new_manifold, self.name)
        res.color = self.color
        return res

    def scale(self, factor_x: float, factor_y: float, factor_z: float) -> Solid:
        """Applique une mise à l'échelle non-uniforme au solide."""
        new_manifold = self._manifold.scale([factor_x, factor_y, factor_z])
        res = Solid(new_manifold, self.name)
        res.color = self.color
        return res

    def union(self, other: Solid) -> Solid:
        """Union booléenne : fusionne ce solide avec un autre."""
        res_manifold = self._manifold + other._manifold
        res = Solid(res_manifold, f"{self.name}_Union")
        res.color = self.color
        return res

    def difference(self, other: Solid) -> Solid:
        """Différence booléenne : soustrait un autre solide de ce solide."""
        res_manifold = self._manifold - other._manifold
        res = Solid(res_manifold, f"{self.name}_Cut")
        res.color = self.color
        return res

    def intersection(self, other: Solid) -> Solid:
        """Intersection booléenne : conserve le volume commun."""
        res_manifold = self._manifold ^ other._manifold
        res = Solid(res_manifold, f"{self.name}_Intersect")
        res.color = self.color
        return res

    def to_mesh_buffer(self) -> MeshBuffer:
        """
        Convertit le solide en MeshBuffer optimisé pour le rendu OpenGL.
        Calcule les normales douces et extrait les arêtes nettes (dihedral edges).
        """
        if self._manifold.is_empty():
            return MeshBuffer.empty()

        mesh = self._manifold.to_mesh()
        vert_props = np.array(mesh.vert_properties, dtype=np.float32)
        tri_verts = np.array(mesh.tri_verts, dtype=np.uint32)

        if len(vert_props) == 0 or len(tri_verts) == 0:
            return MeshBuffer.empty()

        # Extraire les coordonnées X, Y, Z
        positions: np.ndarray = vert_props[:, :3]

        # Calculer les normales par face et les normales moyennes par sommet
        normals: np.ndarray = np.zeros_like(positions)
        v0: np.ndarray = positions[tri_verts[:, 0]]
        v1: np.ndarray = positions[tri_verts[:, 1]]
        v2: np.ndarray = positions[tri_verts[:, 2]]

        face_normals: np.ndarray = np.cross(v1 - v0, v2 - v0)
        face_lengths: np.ndarray = np.linalg.norm(face_normals, axis=1, keepdims=True)
        # Éviter la division par zéro
        face_lengths[face_lengths < 1e-9] = 1.0
        face_normals /= face_lengths

        # Accumuler les normales sur les sommets
        np.add.at(normals, tri_verts[:, 0], face_normals)
        np.add.at(normals, tri_verts[:, 1], face_normals)
        np.add.at(normals, tri_verts[:, 2], face_normals)

        vert_lengths: np.ndarray = np.linalg.norm(normals, axis=1, keepdims=True)
        vert_lengths[vert_lengths < 1e-9] = 1.0
        normals /= vert_lengths

        # Extraction des arêtes remarquables (style CAD : arêtes délimitant des faces avec angle marqué)
        edges: np.ndarray = _extract_sharp_edges(tri_verts, face_normals, angle_threshold_deg=20.0)

        buffer = MeshBuffer(
            vertices=positions,
            faces=tri_verts,
            normals=normals,
            edges=edges,
            color=self.color
        )
        return buffer


def make_box(width: float, height: float, depth: float, center: bool = False, name: str = "Box") -> Solid:
    """
    Crée une boîte solide paramétrique.
    - width : dimension selon l'axe X
    - height : dimension selon l'axe Y
    - depth : dimension selon l'axe Z
    - center : centre la boîte sur l'origine si True
    """
    manifold_box = m.Manifold.cube([max(0.001, width), max(0.001, height), max(0.001, depth)], center)
    return Solid(manifold_box, name)


def make_cylinder(radius: float, height: float, segments: int = 36, center: bool = False, name: str = "Cylinder") -> Solid:
    """
    Crée un cylindre solide paramétrique centré le long de l'axe Z.
    - radius : rayon du cylindre
    - height : hauteur du cylindre
    - segments : résolution circulaire
    """
    safe_rad = max(0.001, radius)
    safe_height = max(0.001, height)
    manifold_cyl = m.Manifold.cylinder(safe_height, safe_rad, safe_rad, segments, center)
    return Solid(manifold_cyl, name)


def make_sphere(radius: float, segments: int = 36, name: str = "Sphere") -> Solid:
    """
    Crée une sphère solide paramétrique centrée sur l'origine.
    - radius : rayon de la sphère
    - segments : résolution angulaire
    """
    safe_rad = max(0.001, radius)
    manifold_sph = m.Manifold.sphere(safe_rad, segments)
    return Solid(manifold_sph, name)


def make_cone(radius_bottom: float, radius_top: float, height: float, segments: int = 36, name: str = "Cone") -> Solid:
    """
    Crée un cône ou tronc de cône paramétrique.
    - radius_bottom : rayon inférieur à Z = 0
    - radius_top : rayon supérieur à Z = height
    - height : hauteur totale
    """
    safe_r_bottom = max(0.0, radius_bottom)
    safe_r_top = max(0.0, radius_top)
    safe_height = max(0.001, height)
    manifold_cone = m.Manifold.cylinder(safe_height, safe_r_bottom, safe_r_top, segments, False)
    return Solid(manifold_cone, name)


def extrude_polygon(
    points: Sequence[Point2D],
    height: float,
    plane: PlaneType = PlaneType.XY,
    name: str = "Extrude"
) -> Solid:
    """
    Extrude un contour 2D fermé pour créer un solide 3D.
    - points : liste ordonnée des sommets du polygone 2D
    - height : distance d'extrusion normale au plan
    - plane : plan d'esquisse de référence (XY, XZ ou YZ)
    """
    if len(points) < 3:
        raise ValueError("Un polygone d'extrusion nécessite au moins 3 points.")

    poly_coords: List[List[float]] = [[pt.u, pt.v] for pt in points]
    cs = m.CrossSection([poly_coords])
    safe_height = max(0.001, height)
    solid_manifold = m.Manifold.extrude(cs, safe_height)

    # Réorienter selon le plan choisi
    if plane == PlaneType.XZ:
        # Rotation pour coucher le plan XY sur XZ (90 deg autour de X)
        solid_manifold = solid_manifold.rotate([90.0, 0.0, 0.0])
    elif plane == PlaneType.YZ:
        # Rotation pour coucher le plan XY sur YZ (-90 deg autour de Y)
        solid_manifold = solid_manifold.rotate([0.0, -90.0, 0.0])

    return Solid(solid_manifold, name)


def _extract_sharp_edges(
    tri_verts: np.ndarray,
    face_normals: np.ndarray,
    angle_threshold_deg: float = 20.0
) -> np.ndarray:
    """
    Extrait les arêtes vives du maillage pour l'affichage des lignes de contour CAO.
    Compare l'angle dièdre entre les faces partageant chaque arête.
    """
    # Création d'une table d'arêtes vers les faces associées
    edge_to_faces: dict[Tuple[int, int], List[int]] = {}

    for face_idx, tri in enumerate(tri_verts):
        i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
        edges_in_tri = [
            (min(i0, i1), max(i0, i1)),
            (min(i1, i2), max(i1, i2)),
            (min(i2, i0), max(i2, i0))
        ]
        for edge in edges_in_tri:
            if edge not in edge_to_faces:
                edge_to_faces[edge] = []
            edge_to_faces[edge].append(face_idx)

    sharp_edges: List[Tuple[int, int]] = []
    cos_threshold = float(np.cos(np.radians(angle_threshold_deg)))

    for edge, faces in edge_to_faces.items():
        if len(faces) == 1:
            # Arête frontière (arête nue)
            sharp_edges.append(edge)
        elif len(faces) == 2:
            n0 = face_normals[faces[0]]
            n1 = face_normals[faces[1]]
            dot_val = float(np.dot(n0, n1))
            if dot_val < cos_threshold:
                sharp_edges.append(edge)

    if not sharp_edges:
        return np.zeros((0, 2), dtype=np.uint32)

    return np.array(sharp_edges, dtype=np.uint32)
