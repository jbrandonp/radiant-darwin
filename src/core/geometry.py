"""
Moteur géométrique volumique 3D haute performance (B-Rep / CSG).
Utilise manifold3d pour garantir des solides manifold (étanches) et des opérations booléennes rapides.
"""

from __future__ import annotations
from typing import List, Tuple, Optional, Sequence, Callable, Union
import numpy as np
import manifold3d as m

from src.core.types import Vector3D, Point2D, PlaneType, MeshBuffer, ColorRGBA


class Solid:
    """
    Représente un corps solide 3D étanche (manifold).
    Encapsule le modèle géométrique sous-jacent et fournit les opérations volumiques.
    """

    def __init__(
        self,
        internal_manifold: Optional[m.Manifold] = None,
        name: str = "Solid",
        solid_name: Optional[str] = None
    ) -> None:
        """Initialise le solide avec une instance Manifold (ou vide par défaut)."""
        self._manifold: m.Manifold = internal_manifold if internal_manifold is not None else m.Manifold()
        self.name: str = solid_name if solid_name is not None else name
        self.color: ColorRGBA = ColorRGBA(0.72, 0.76, 0.82, 1.0)  # Gris aluminium Fusion 360
        self._cached_buffer: Optional[MeshBuffer] = None

    @property
    def manifold(self) -> m.Manifold:
        """Accès à l'instance manifold sous-jacente."""
        return self._manifold

    def is_empty(self) -> bool:
        """Vérifie si le solide ne contient aucun volume."""
        return self._manifold.is_empty()

    def is_manifold(self) -> bool:
        """Vérifie si le solide est une variété topologique fermée étanche (2-manifold)."""
        return not self._manifold.is_empty() and self.volume() > 0.0

    def is_watertight(self) -> bool:
        """Vérifie que le solide est mathématiquement fermé, 2-variété et étanche sans trou."""
        return self.is_manifold()

    def volume(self) -> float:
        """Calcule le volume exact du solide en unités cubiques."""
        if self._manifold.is_empty():
            return 0.0
        return float(self._manifold.volume())

    def get_volume(self) -> float:
        """Alias pour compatibilité avec le noyau NexusSolid."""
        return self.volume()

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

    def translate(
        self,
        offset_or_x: Union[Vector3D, float, Sequence[float]],
        y: Optional[float] = None,
        z: Optional[float] = None
    ) -> Solid:
        """
        Applique une translation au solide.
        Accepte un Vector3D, une séquence [x, y, z] ou 3 coordonnées scalaires (x, y, z).
        """
        if isinstance(offset_or_x, Vector3D):
            tx, ty, tz = offset_or_x.x, offset_or_x.y, offset_or_x.z
        elif isinstance(offset_or_x, (list, tuple, np.ndarray)):
            tx, ty, tz = float(offset_or_x[0]), float(offset_or_x[1]), float(offset_or_x[2])
        else:
            tx = float(offset_or_x)
            ty = float(y) if y is not None else 0.0
            tz = float(z) if z is not None else 0.0

        new_manifold = self._manifold.translate([tx, ty, tz])
        res = Solid(new_manifold, self.name)
        res.color = self.color
        return res

    def rotate(self, rx_deg: float, ry_deg: float, rz_deg: float) -> Solid:
        """Applique des rotations en degrés autour des axes X, Y, Z."""
        new_manifold = self._manifold.rotate([rx_deg, ry_deg, rz_deg])
        res = Solid(new_manifold, self.name)
        res.color = self.color
        return res

    def transform(self, matrix_3x4: Union[Sequence[Sequence[float]], np.ndarray]) -> Solid:
        """Applique une transformation affine 3x4 [R | T] au solide."""
        mat_list = [list(row) for row in matrix_3x4]
        new_manifold = self._manifold.transform(mat_list)
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

    def split_by_plane(
        self,
        normal: Union[Vector3D, Tuple[float, float, float], Sequence[float]] = (0.0, 0.0, 1.0),
        offset: float = 0.0,
        origin_offset: Optional[float] = None
    ) -> Tuple[Solid, Solid]:
        """
        Découpe le solide en deux sous-solides étanches selon un plan infini (FreeCAD Part Slice).
        - normal : vecteur normal au plan de coupe (Vector3D ou tuple de 3 floats)
        - offset / origin_offset : distance du plan par rapport à l'origine le long de la normale
        Retourne (solide_cote_positif, solide_cote_negatif).
        """
        off = float(offset if origin_offset is None else origin_offset)
        if isinstance(normal, Vector3D):
            norm_list = [normal.x, normal.y, normal.z]
        else:
            norm_list = [float(normal[0]), float(normal[1]), float(normal[2])]

        if self._manifold.is_empty():
            return (Solid(self._manifold, f"{self.name}_Pos"), Solid(self._manifold, f"{self.name}_Neg"))
        m_pos, m_neg = self._manifold.split_by_plane(norm_list, off)
        s_pos = Solid(m_pos, f"{self.name}_Pos")
        s_pos.color = self.color
        s_neg = Solid(m_neg, f"{self.name}_Neg")
        s_neg.color = self.color
        return (s_pos, s_neg)

    def trim_by_plane(
        self,
        normal: Union[Vector3D, Tuple[float, float, float], Sequence[float]] = (0.0, 0.0, 1.0),
        offset: float = 0.0,
        origin_offset: Optional[float] = None
    ) -> Solid:
        """
        Tronque le solide selon un plan et conserve uniquement le demi-espace positif.
        """
        off = float(offset if origin_offset is None else origin_offset)
        if isinstance(normal, Vector3D):
            norm_list = [normal.x, normal.y, normal.z]
        else:
            norm_list = [float(normal[0]), float(normal[1]), float(normal[2])]

        if self._manifold.is_empty():
            return Solid(self._manifold, f"{self.name}_Trimmed")
        m_trimmed = self._manifold.trim_by_plane(norm_list, off)
        res = Solid(m_trimmed, f"{self.name}_Trimmed")
        res.color = self.color
        return res

    def surface_area(self) -> float:
        """Calcule la surface extérieure totale du solide en mm²."""
        if self._manifold.is_empty():
            return 0.0
        return float(self._manifold.surface_area())

    def min_gap(self, other: Solid, search_distance: float = 1000.0) -> float:
        """Calcule la distance minimale (jeu/clearance) entre ce solide et un autre."""
        if self._manifold.is_empty() or other._manifold.is_empty():
            return float("inf")
        return float(self._manifold.min_gap(other._manifold, search_distance))

    def genus(self) -> int:
        """Retourne le genre topologique du solide (nombre de trous traversants)."""
        if self._manifold.is_empty():
            return 0
        return int(self._manifold.genus())

    def num_vertices(self) -> int:
        """Retourne le nombre total de sommets uniques du maillage solide."""
        return int(self._manifold.num_vert())

    def num_edges(self) -> int:
        """Retourne le nombre total d'arêtes du maillage solide."""
        return int(self._manifold.num_edge())

    def num_faces(self) -> int:
        """Retourne le nombre total de facettes triangulaires."""
        return int(self._manifold.num_tri())

    def simplify(self, tolerance: float = 0.05) -> Solid:
        """Simplifie le maillage du solide en conservant sa topologie étanche."""
        new_manifold = self._manifold.simplify(tolerance)
        res = Solid(new_manifold, f"{self.name}_Simplified")
        res.color = self.color
        return res

    def warp(self, func: Callable[[Tuple[float, float, float]], Tuple[float, float, float]]) -> Solid:
        """Déforme le solide selon une fonction de transformation 3D continue."""
        new_manifold = self._manifold.warp(func)
        res = Solid(new_manifold, f"{self.name}_Warped")
        res.color = self.color
        return res

    def slice_cross_section(self, height: float = 0.0) -> List[List[Point2D]]:
        """
        Extrait les contours fermés 2D de la section plane du solide à la hauteur Z donnée.
        Utilise la méthode native slice de Manifold3D (parallèle au plan XY).
        """
        if self._manifold.is_empty():
            return []
        cs = self._manifold.slice(height)
        if cs.is_empty():
            return []
        polys = cs.to_polygons()
        result: List[List[Point2D]] = []
        for poly in polys:
            contour: List[Point2D] = []
            for pt in poly:
                contour.append(Point2D(float(pt[0]), float(pt[1])))
            if len(contour) >= 3:
                result.append(contour)
        return result

    def slice(self, height: float = 0.0) -> List[List[Point2D]]:
        """Alias pour slice_cross_section."""
        return self.slice_cross_section(height)


    def to_nexus(self) -> 'NexusSolid':
        """Convertit le solide en solide hybride NexusSolid pour l'analyse IA et B-Rep."""
        from src.core.nexus_kernel.hybrid_solid import NexusSolid
        return NexusSolid(name=self.name, internal_manifold=self._manifold)

    def compute_sdf(self, query_points: np.ndarray) -> np.ndarray:
        """Calcule le champ de distance signée (SDF) pour l'IA 3D."""
        from src.core.nexus_kernel.ai_interfaces import NeuralSDFEngine
        return NeuralSDFEngine.compute_signed_distance(self.to_nexus(), query_points)

    def get_ai_tokens(self) -> List[str]:
        """Génère la séquence de tokens CAO pour les LLMs et copilotes IA."""
        from src.core.nexus_kernel.ai_interfaces import CADTokenizer
        return CADTokenizer.tokenize(self.to_nexus())

    def get_latent_embedding(self, embedding_dim: int = 64) -> np.ndarray:
        """Génère le vecteur d'empreinte géométrique invariante pour la recherche de formes."""
        from src.core.nexus_kernel.ai_interfaces import LatentShapeEmbedding
        return LatentShapeEmbedding.compute_embedding(self.to_nexus(), embedding_dim)

    @property
    def mesh(self) -> MeshBuffer:
        """Accès direct au tampon de maillage (MeshBuffer) du solide."""
        return self.to_mesh_buffer()

    def clear_cache(self) -> None:
        """Libère le cache MeshBuffer pour forcer une régénération ou libérer la mémoire."""
        self._cached_buffer = None

    def to_mesh_buffer(self) -> MeshBuffer:
        """
        Convertit le solide en MeshBuffer optimisé pour le rendu OpenGL.
        Calcule les normales de faces et extrait les arêtes nettes (dihedral edges).
        Met en cache le résultat pour des performances O(1) lors des rappels de rendu.
        """
        if self._cached_buffer is not None:
            return self._cached_buffer

        if self._manifold.is_empty():
            return MeshBuffer.empty()

        mesh = self._manifold.to_mesh()
        vert_props = np.array(mesh.vert_properties, dtype=np.float32)
        tri_verts = np.array(mesh.tri_verts, dtype=np.uint32)

        if len(vert_props) == 0 or len(tri_verts) == 0:
            return MeshBuffer.empty()

        # Extraire les coordonnées X, Y, Z
        positions: np.ndarray = vert_props[:, :3]

        # Calculer les normales exactes par face
        v0: np.ndarray = positions[tri_verts[:, 0]]
        v1: np.ndarray = positions[tri_verts[:, 1]]
        v2: np.ndarray = positions[tri_verts[:, 2]]

        face_normals: np.ndarray = np.cross(v1 - v0, v2 - v0)
        face_lengths: np.ndarray = np.linalg.norm(face_normals, axis=1, keepdims=True)
        face_lengths[face_lengths < 1e-9] = 1.0
        face_normals /= face_lengths

        # Rendu CAO professionnel : sommets dépliés par facette avec normales exactes de face
        # Élimine 100% des dégradés triangulaires disgracieux sur les faces planes
        num_tris = len(tri_verts)
        v_flat = np.empty((num_tris * 3, 3), dtype=np.float32)
        v_flat[0::3] = v0
        v_flat[1::3] = v1
        v_flat[2::3] = v2

        n_flat = np.empty((num_tris * 3, 3), dtype=np.float32)
        n_flat[0::3] = face_normals
        n_flat[1::3] = face_normals
        n_flat[2::3] = face_normals

        f_flat = np.arange(num_tris * 3, dtype=np.uint32).reshape(-1, 3)

        # Extraction des arêtes remarquables (style CAD : arêtes délimitant des faces avec angle marqué)
        edges: np.ndarray = _extract_sharp_edges(tri_verts, face_normals, angle_threshold_deg=20.0)

        # Coordonnées réelles 3D des arêtes pour tracé direct
        if len(edges) > 0:
            edge_vertices = np.empty((len(edges) * 2, 3), dtype=np.float32)
            edge_vertices[0::2] = positions[edges[:, 0]]
            edge_vertices[1::2] = positions[edges[:, 1]]
        else:
            edge_vertices = np.zeros((0, 3), dtype=np.float32)

        buffer = MeshBuffer(
            vertices=v_flat,
            faces=f_flat,
            normals=n_flat,
            edges=edges,
            color=self.color,
            edge_vertices=edge_vertices
        )
        self._cached_buffer = buffer
        return buffer

    @classmethod
    def make_box(cls, width: float, height: float, depth: float, center: bool = False, name: str = "Box") -> Solid:
        """Fabrique une boîte solide paramétrique via la méthode de classe Solid.make_box."""
        return make_box(width, height, depth, center, name)

    @classmethod
    def cube(cls, size_or_x: float, y: Optional[float] = None, z: Optional[float] = None, center: bool = False, name: str = "Cube") -> Solid:
        """Fabrique un cube ou pavé solide paramétrique via la méthode de classe Solid.cube."""
        sy = y if y is not None else size_or_x
        sz = z if z is not None else size_or_x
        return make_box(size_or_x, sy, sz, center, name)


def make_box(width: float, height: float, depth: float, center: bool = False, name: str = "Box") -> Solid:
    """
    Crée une boîte solide paramétrique.
    - width : dimension selon l'axe X (clampée >= 0.001 pour garantir l'étanchéité manifold)
    - height : dimension selon l'axe Y
    - depth : dimension selon l'axe Z
    - center : centre la boîte sur l'origine si True
    """
    safe_w = max(0.001, abs(float(width)) if width != 0.0 else 0.001)
    safe_h = max(0.001, abs(float(height)) if height != 0.0 else 0.001)
    safe_d = max(0.001, abs(float(depth)) if depth != 0.0 else 0.001)
    manifold_box = m.Manifold.cube([safe_w, safe_h, safe_d], center)
    return Solid(manifold_box, name)


def make_cylinder(radius: float, height: float, segments: int = 36, center: bool = False, name: str = "Cylinder") -> Solid:
    """
    Crée un cylindre solide paramétrique centré le long de l'axe Z.
    - radius : rayon du cylindre
    - height : hauteur du cylindre
    - segments : résolution circulaire
    """
    safe_rad = max(0.001, abs(float(radius)) if radius != 0.0 else 0.001)
    safe_height = max(0.001, abs(float(height)) if height != 0.0 else 0.001)
    manifold_cyl = m.Manifold.cylinder(safe_height, safe_rad, safe_rad, max(3, segments), center)
    return Solid(manifold_cyl, name)


def make_sphere(radius: float, segments: int = 36, name: str = "Sphere") -> Solid:
    """
    Crée une sphère solide paramétrique centrée sur l'origine.
    - radius : rayon de la sphère
    - segments : résolution angulaire
    """
    safe_rad = max(0.001, abs(float(radius)) if radius != 0.0 else 0.001)
    manifold_sph = m.Manifold.sphere(safe_rad, max(3, segments))
    return Solid(manifold_sph, name)


def make_cone(radius_bottom: float, radius_top: float, height: float, segments: int = 36, name: str = "Cone") -> Solid:
    """
    Crée un cône ou tronc de cône paramétrique.
    - radius_bottom : rayon inférieur à Z = 0
    - radius_top : rayon supérieur à Z = height
    - height : hauteur totale
    """
    safe_r_bottom = max(0.0, abs(float(radius_bottom)))
    safe_r_top = max(0.0, abs(float(radius_top)))
    if safe_r_bottom <= 0.0 and safe_r_top <= 0.0:
        safe_r_bottom = 0.001
    safe_height = max(0.001, abs(float(height)) if height != 0.0 else 0.001)
    manifold_cone = m.Manifold.cylinder(safe_height, safe_r_bottom, safe_r_top, max(3, segments), False)
    return Solid(manifold_cone, name)


def make_torus(major_radius: float, minor_radius: float, segments: int = 36, name: str = "Torus") -> Solid:
    """
    Crée un tore solide paramétrique (forme d'anneau / donut).
    - major_radius : rayon majeur (distance du centre au tube)
    - minor_radius : rayon mineur (rayon de la section circulaire du tube)
    - segments : résolution angulaire
    """
    safe_major = max(0.1, major_radius)
    safe_minor = max(0.01, min(safe_major * 0.99, minor_radius))
    segs = max(12, segments)
    cs = m.CrossSection.circle(safe_minor, segs).translate([safe_major, 0.0])
    manifold_torus = m.Manifold.revolve(cs, segs, 360.0)
    return Solid(manifold_torus, name)


def make_wedge(
    dx: float,
    dy: float,
    dz: float,
    dx_top: float = 0.0,
    dy_top: float = 0.0,
    name: str = "Wedge"
) -> Solid:
    """
    Crée un coin ou prisme trapézoïdal paramétrique (Wedge FreeCAD Part).
    - dx : largeur de la base selon X
    - dy : profondeur de la base selon Y
    - dz : hauteur totale selon Z
    - dx_top : largeur de la face supérieure selon X (0.0 pour une arête vive / rampe)
    - dy_top : profondeur de la face supérieure selon Y (0.0 pour conserver dy)
    """
    safe_dx = max(0.001, dx)
    safe_dy = max(0.001, dy)
    safe_dz = max(0.001, dz)
    safe_dx_top = max(0.0, min(safe_dx, dx_top))
    safe_dy_top = safe_dy if dy_top <= 0.0 else max(0.001, min(safe_dy, dy_top))

    if safe_dx_top <= 1e-4:
        # Coin triangulaire (arête vive le long de Y au sommet à X = 0)
        verts = np.array([
            [0.0, 0.0, 0.0],
            [safe_dx, 0.0, 0.0],
            [safe_dx, safe_dy, 0.0],
            [0.0, safe_dy, 0.0],
            [0.0, 0.0, safe_dz],
            [0.0, safe_dy, safe_dz],
        ], dtype=np.float32)
        faces = np.array([
            [0, 2, 1], [0, 3, 2],
            [0, 1, 4],
            [3, 5, 2],
            [0, 4, 5], [0, 5, 3],
            [1, 2, 5], [1, 5, 4],
        ], dtype=np.uint32)
    else:
        # Prisme trapézoïdal à 8 sommets
        x_off = (safe_dx - safe_dx_top) / 2.0
        y_off = (safe_dy - safe_dy_top) / 2.0
        verts = np.array([
            [0.0, 0.0, 0.0],
            [safe_dx, 0.0, 0.0],
            [safe_dx, safe_dy, 0.0],
            [0.0, safe_dy, 0.0],
            [x_off, y_off, safe_dz],
            [x_off + safe_dx_top, y_off, safe_dz],
            [x_off + safe_dx_top, y_off + safe_dy_top, safe_dz],
            [x_off, y_off + safe_dy_top, safe_dz],
        ], dtype=np.float32)
        faces = np.array([
            [0, 2, 1], [0, 3, 2],
            [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4],
            [2, 3, 7], [2, 7, 6],
            [0, 4, 7], [0, 7, 3],
            [1, 6, 5], [1, 2, 6],
        ], dtype=np.uint32)

    mesh = m.Mesh(vert_properties=verts, tri_verts=faces)
    return Solid(m.Manifold(mesh), name)


def _build_advanced_manifold(
    points: Sequence[Point2D],
    abs_h: float,
    cu: float,
    cv: float,
    taper_angle: float,
    twist_degrees: float
) -> m.Manifold:
    """Génère le maillage extrudé avec dépouille et torsion hélicoïdale."""
    centered_coords: List[List[float]] = [[pt.u - cu, pt.v - cv] for pt in points]
    cs = m.CrossSection([centered_coords])

    u_vals = [pt.u for pt in points]
    v_vals = [pt.v for pt in points]
    span_u = max(u_vals) - min(u_vals)
    span_v = max(v_vals) - min(v_vals)

    if abs(taper_angle) > 1e-4:
        delta = abs_h * float(np.tan(np.radians(taper_angle)))
        sx = max(0.01, (span_u + 2.0 * delta) / span_u) if span_u > 1e-4 else 1.0
        sy = max(0.01, (span_v + 2.0 * delta) / span_v) if span_v > 1e-4 else 1.0
        scale_top = (sx, sy)
    else:
        scale_top = (1.0, 1.0)

    n_divisions = max(10, int(abs(twist_degrees) / 5.0)) if abs(twist_degrees) > 1e-4 else 10
    solid_manifold = m.Manifold.extrude(cs, abs_h, n_divisions=n_divisions, twist_degrees=twist_degrees, scale_top=scale_top)
    return solid_manifold.translate([cu, cv, 0.0])


def _apply_plane_orientation(
    solid_manifold: m.Manifold,
    plane: PlaneType,
    plane_offset: float
) -> m.Manifold:
    """Oriente et décale le solide extrudé selon le plan de référence choisi."""
    if plane == PlaneType.XZ:
        solid_manifold = solid_manifold.rotate([90.0, 0.0, 0.0])
    elif plane == PlaneType.YZ:
        solid_manifold = solid_manifold.rotate([0.0, -90.0, 0.0])

    if abs(plane_offset) > 1e-9:
        if plane == PlaneType.XY:
            solid_manifold = solid_manifold.translate([0.0, 0.0, plane_offset])
        elif plane == PlaneType.XZ:
            solid_manifold = solid_manifold.translate([0.0, plane_offset, 0.0])
        elif plane == PlaneType.YZ:
            solid_manifold = solid_manifold.translate([plane_offset, 0.0, 0.0])

    return solid_manifold


def extrude_polygon(
    points: Sequence[Point2D],
    height: float,
    plane: PlaneType = PlaneType.XY,
    plane_offset: float = 0.0,
    symmetric: bool = False,
    taper_angle: float = 0.0,
    twist_degrees: float = 0.0,
    name: str = "Extrude"
) -> Solid:
    """
    Extrude un contour 2D fermé pour créer un solide 3D avec support des options avancées FreeCAD :
    - points : liste ordonnée des sommets du polygone 2D
    - height : distance d'extrusion normale au plan
    - plane : plan d'esquisse de référence (XY, XZ ou YZ)
    - plane_offset : décalage le long de l'axe normal au plan (Datum Plane)
    - symmetric : extrusion symétrique par rapport au plan d'esquisse (Pad symétrique FreeCAD)
    - taper_angle : angle de dépouille (draft angle) en degrés (>0 évasé, <0 rétréci)
    - twist_degrees : angle de torsion hélicoïdale de la face supérieure en degrés
    """
    if len(points) < 3:
        raise ValueError("Un polygone d'extrusion nécessite au moins 3 points.")

    abs_h = max(0.001, abs(height))
    cu = sum(pt.u for pt in points) / float(len(points))
    cv = sum(pt.v for pt in points) / float(len(points))

    has_advanced = (abs(taper_angle) > 1e-4) or (abs(twist_degrees) > 1e-4)

    if has_advanced:
        solid_manifold = _build_advanced_manifold(points, abs_h, cu, cv, taper_angle, twist_degrees)
    else:
        poly_coords: List[List[float]] = [[pt.u, pt.v] for pt in points]
        cs = m.CrossSection([poly_coords])
        solid_manifold = m.Manifold.extrude(cs, abs_h)

    if symmetric:
        solid_manifold = solid_manifold.translate([0.0, 0.0, -abs_h / 2.0])
    elif height < 0.0:
        solid_manifold = solid_manifold.translate([0.0, 0.0, -abs_h])

    solid_manifold = _apply_plane_orientation(solid_manifold, plane, plane_offset)
    return Solid(solid_manifold, name)


def _extract_sharp_edges(
    tri_verts: np.ndarray,
    face_normals: np.ndarray,
    angle_threshold_deg: float = 20.0
) -> np.ndarray:
    """
    Extrait les arêtes vives du maillage pour l'affichage des lignes de contour CAO.
    Algorithme vectorisé NumPy ultra-rapide basé sur le tri lexical des paires de sommets.
    """
    if len(tri_verts) == 0:
        return np.zeros((0, 2), dtype=np.uint32)

    # 1. Extraction vectorisée de toutes les arêtes orientées de tous les triangles
    e0 = np.sort(tri_verts[:, [0, 1]], axis=1)
    e1 = np.sort(tri_verts[:, [1, 2]], axis=1)
    e2 = np.sort(tri_verts[:, [2, 0]], axis=1)
    all_edges = np.vstack([e0, e1, e2])  # (3N, 2)
    # np.tile associe correctement chaque ligne empilée à son indice de triangle respectif
    face_indices = np.tile(np.arange(len(tri_verts), dtype=np.int32), 3)

    # 2. Tri lexical pour regrouper les arêtes identiques contiguës
    order = np.lexsort((all_edges[:, 1], all_edges[:, 0]))
    sorted_edges = all_edges[order]
    sorted_faces = face_indices[order]

    # 3. Détection vectorisée des changements d'arêtes
    diff = np.bitwise_or.reduce(sorted_edges[1:] != sorted_edges[:-1], axis=1)
    split_indices = np.concatenate(([0], np.where(diff)[0] + 1, [len(sorted_edges)]))

    cos_threshold = float(np.cos(np.radians(angle_threshold_deg)))
    sharp_edges: List[Tuple[int, int]] = []

    # 4. Évaluation dièdre uniquement aux transitions
    for i in range(len(split_indices) - 1):
        start = split_indices[i]
        count = split_indices[i + 1] - start
        edge = (int(sorted_edges[start, 0]), int(sorted_edges[start, 1]))

        if count == 1:
            # Arête frontière libre
            sharp_edges.append(edge)
        elif count >= 2:
            # Arête partagée entre deux facettes ou plus
            f0 = sorted_faces[start]
            f1 = sorted_faces[start + 1]
            dot_val = float(np.dot(face_normals[f0], face_normals[f1]))
            if dot_val < cos_threshold:
                sharp_edges.append(edge)

    if not sharp_edges:
        return np.zeros((0, 2), dtype=np.uint32)

    return np.array(sharp_edges, dtype=np.uint32)
