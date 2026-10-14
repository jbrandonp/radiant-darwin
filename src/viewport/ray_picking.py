"""
Système de sélection interactive 3D (Ray-Casting Picking) pour le Viewport CAO.
Permet d'attraper directement les faces, arêtes et sommets avec le curseur de la souris,
sans nécessiter la saisie manuelle d'identifiants textuels.
Architecture fortement typée.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple, Optional
import numpy as np

from src.core.types import Vector3D, MeshBuffer
from src.core.geometry import Solid
from src.viewport.camera import CADCamera


class PickedEntityType(Enum):
    """Types d'entités géométriques sélectionnables par lancer de rayon."""
    NONE = "none"
    FACE = "face"
    EDGE = "edge"
    VERTEX = "vertex"
    BODY = "body"


@dataclass
class Ray3D:
    """Rayon géométrique 3D défini par une origine et une direction unitaire."""
    origin: Vector3D
    direction: Vector3D

    def point_at(self, t: float) -> Vector3D:
        """Calcule la position 3D le long du rayon à la distance t."""
        return self.origin.add(self.direction.scale(t))


@dataclass
class PickResult:
    """Résultat détaillé d'un lancer de rayon sur la scène 3D."""
    entity_type: PickedEntityType = PickedEntityType.NONE
    hit_point: Vector3D = field(default_factory=lambda: Vector3D(0.0, 0.0, 0.0))
    distance: float = float("inf")
    normal: Vector3D = field(default_factory=lambda: Vector3D(0.0, 0.0, 1.0))
    face_index: int = -1
    face_id: str = ""
    edge_index: int = -1
    edge_id: str = ""
    body_id: str = ""

    @property
    def has_hit(self) -> bool:
        """Vérifie si une entité géométrique a été interceptée."""
        return self.entity_type != PickedEntityType.NONE and self.distance < float("inf")


class RayPicker:
    """
    Moteur de détection d'intersection rayon-géométrie pour la sélection CAO.
    Implémente l'algorithme de Möller-Trumbore pour les facettes et la distance minimale
    segment-rayon pour la sélection précise des arêtes.
    """

    @staticmethod
    def intersect_triangle(
        ray: Ray3D,
        v0: np.ndarray,
        v1: np.ndarray,
        v2: np.ndarray
    ) -> Optional[Tuple[float, float, float]]:
        """
        Algorithme de Möller-Trumbore pour l'intersection rayon-triangle.
        Retourne (distance_t, barycentrique_u, barycentrique_v) ou None si pas d'impact.
        """
        orig = np.array([ray.origin.x, ray.origin.y, ray.origin.z], dtype=np.float64)
        dir_vec = np.array([ray.direction.x, ray.direction.y, ray.direction.z], dtype=np.float64)

        edge1 = v1 - v0
        edge2 = v2 - v0
        pvec = np.cross(dir_vec, edge2)
        det = float(np.dot(edge1, pvec))

        if abs(det) < 1e-9:
            return None  # Rayon parallèle au triangle

        inv_det = 1.0 / det
        tvec = orig - v0
        u = float(np.dot(tvec, pvec)) * inv_det
        if u < -1e-4 or u > 1.0001:
            return None

        qvec = np.cross(tvec, edge1)
        v = float(np.dot(dir_vec, qvec)) * inv_det
        if v < -1e-4 or (u + v) > 1.0001:
            return None

        t = float(np.dot(edge2, qvec)) * inv_det
        if t < 1e-4:
            return None  # Impact derrière l'origine du rayon

        return (t, u, v)

    @staticmethod
    def distance_ray_to_segment(
        ray: Ray3D,
        p0: np.ndarray,
        p1: np.ndarray
    ) -> Tuple[float, float, Vector3D]:
        """
        Calcule la distance euclidienne minimale entre un rayon 3D et un segment de droite [p0, p1].
        Retourne (distance_minimale, t_rayon, point_le_plus_proche_sur_segment).
        """
        ro = np.array([ray.origin.x, ray.origin.y, ray.origin.z], dtype=np.float64)
        rd = np.array([ray.direction.x, ray.direction.y, ray.direction.z], dtype=np.float64)

        seg_dir = p1 - p0
        seg_len = float(np.linalg.norm(seg_dir))
        if seg_len < 1e-9:
            diff = ro - p0
            t_r = max(0.0, float(np.dot(-diff, rd)))
            closest_ray = ro + t_r * rd
            dist = float(np.linalg.norm(closest_ray - p0))
            return (dist, t_r, Vector3D(float(p0[0]), float(p0[1]), float(p0[2])))

        s_dir = seg_dir / seg_len
        w0 = ro - p0
        a = float(np.dot(rd, rd))
        b = float(np.dot(rd, s_dir))
        c = float(np.dot(s_dir, s_dir))
        d = float(np.dot(rd, w0))
        e = float(np.dot(s_dir, w0))

        denom = a * c - b * b
        if abs(denom) < 1e-9:
            # Rayon et segment parallèles
            s_param = 0.0
            t_param = max(0.0, e / b if abs(b) > 1e-9 else 0.0)
        else:
            t_param = (b * e - c * d) / denom
            s_param = (a * e - b * d) / denom

        # Borner le paramètre s sur la longueur du segment
        s_clamped = max(0.0, min(seg_len, s_param))
        closest_seg = p0 + s_clamped * s_dir

        t_clamped = max(0.0, float(np.dot(closest_seg - ro, rd)))
        closest_ray = ro + t_clamped * rd

        dist = float(np.linalg.norm(closest_ray - closest_seg))
        pt_3d = Vector3D(float(closest_seg[0]), float(closest_seg[1]), float(closest_seg[2]))
        return (dist, t_clamped, pt_3d)

    @classmethod
    def pick_face(
        cls,
        ray: Ray3D,
        mesh_buffer: MeshBuffer,
        body_id: str = ""
    ) -> Optional[PickResult]:
        """Détecte la première facette 3D traversée par le rayon."""
        if mesh_buffer.is_empty():
            return None

        verts = mesh_buffer.vertices
        faces = mesh_buffer.faces
        normals = mesh_buffer.normals

        best_t = float("inf")
        best_face_idx = -1
        best_hit_pt = Vector3D(0.0, 0.0, 0.0)
        best_norm = Vector3D(0.0, 0.0, 1.0)

        for f_idx in range(len(faces)):
            i0, i1, i2 = int(faces[f_idx, 0]), int(faces[f_idx, 1]), int(faces[f_idx, 2])
            hit = cls.intersect_triangle(ray, verts[i0], verts[i1], verts[i2])
            if hit is not None:
                t_val, _, _ = hit
                if t_val < best_t:
                    best_t = t_val
                    best_face_idx = f_idx
                    best_hit_pt = ray.point_at(t_val)
                    n = normals[i0]
                    best_norm = Vector3D(float(n[0]), float(n[1]), float(n[2])).normalized()

        if best_face_idx >= 0:
            return PickResult(
                entity_type=PickedEntityType.FACE,
                hit_point=best_hit_pt,
                distance=best_t,
                normal=best_norm,
                face_index=best_face_idx,
                face_id=f"Face_{best_face_idx}",
                body_id=body_id
            )
        return None

    @classmethod
    def pick_edge(
        cls,
        ray: Ray3D,
        mesh_buffer: MeshBuffer,
        max_tolerance: float = 2.0,
        body_id: str = ""
    ) -> Optional[PickResult]:
        """Détecte l'arête remarquable la plus proche du rayon."""
        edges = mesh_buffer.edges
        if len(edges) == 0:
            return None

        ev = mesh_buffer.edge_vertices
        has_ev = ev is not None and len(ev) >= 2 * len(edges)
        verts = mesh_buffer.vertices

        best_dist = float("inf")
        best_edge_idx = -1
        best_t_ray = float("inf")
        best_pt = Vector3D(0.0, 0.0, 0.0)

        for k in range(len(edges)):
            if has_ev and ev is not None:
                p0 = ev[2 * k]
                p1 = ev[2 * k + 1]
            else:
                p0 = verts[int(edges[k, 0])]
                p1 = verts[int(edges[k, 1])]

            dist, t_ray, pt_closest = cls.distance_ray_to_segment(ray, p0, p1)
            if dist < max_tolerance and dist < best_dist:
                best_dist = dist
                best_edge_idx = k
                best_t_ray = t_ray
                best_pt = pt_closest

        if best_edge_idx >= 0:
            return PickResult(
                entity_type=PickedEntityType.EDGE,
                hit_point=best_pt,
                distance=best_t_ray,
                normal=Vector3D(0.0, 0.0, 1.0),
                edge_index=best_edge_idx,
                edge_id=f"Edge_{best_edge_idx}",
                body_id=body_id
            )
        return None

    @classmethod
    def pick_entity(
        cls,
        ray: Ray3D,
        solid: Solid,
        body_id: str = "",
        edge_tolerance: float = 2.0
    ) -> PickResult:
        """
        Sélectionne l'entité géométrique sous le rayon (priorité à l'arête si très proche, sinon face).
        """
        if solid.is_empty():
            return PickResult()

        buf = solid.to_mesh_buffer()
        if buf.is_empty():
            return PickResult()

        # 1. Tester d'abord si une arête est sous le curseur
        edge_hit = cls.pick_edge(ray, buf, max_tolerance=edge_tolerance, body_id=body_id)
        face_hit = cls.pick_face(ray, buf, body_id=body_id)

        # Si une arête est touchée et n'est pas occluse par une face située bien devant
        if edge_hit is not None:
            if face_hit is None or edge_hit.distance <= face_hit.distance + 2.0:
                return edge_hit

        if face_hit is not None:
            return face_hit

        return PickResult()

    @classmethod
    def pick_from_screen(
        cls,
        screen_x: float,
        screen_y: float,
        viewport_width: int,
        viewport_height: int,
        camera: CADCamera,
        bodies: Dict[str, Solid],
        edge_tolerance: float = 2.0
    ) -> PickResult:
        """
        Sélectionne directement un composant ou une sous-entité depuis les coordonnées pixels de l'écran.
        """
        ray_origin, ray_dir = camera.unproject_ray(screen_x, screen_y, viewport_width, viewport_height)
        ray = Ray3D(origin=ray_origin, direction=ray_dir)

        best_result = PickResult()
        for b_id, solid in bodies.items():
            res = cls.pick_entity(ray, solid, body_id=b_id, edge_tolerance=edge_tolerance)
            if res.has_hit and res.distance < best_result.distance:
                best_result = res

        return best_result
