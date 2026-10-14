"""
Moteur de Résolution du Problème de Nommage Topologique (TNP Mitigation Engine).
Inspiré de l'algorithme RealThunder (FreeCAD 1.0) et des systèmes de nommage invariants de CATIA V5.
Génère une empreinte géométrique (Geometric Fingerprint) multi-facteurs pour chaque face et arête,
permettant aux opérations aval de retrouver leur cible même si la géométrie amont est modifiée ou scindée.
Strictement typé sans utilisation d'Any.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple, Optional, Sequence
import numpy as np

from src.core.types import Vector3D, MeshBuffer
from src.core.geometry import Solid


class TNPSurfaceKind(Enum):
    """Nature géométrique de la surface pour l'appariement invariant."""
    PLANE = "plane"
    CYLINDER = "cylinder"
    SPHERE = "sphere"
    FREEFORM = "freeform"


@dataclass
class GeometricFingerprint:
    """
    Empreinte géométrique invariante d'une entité topologique (Face ou Arête).
    Résiste aux renumérotations d'indices de facettes lors des recalculs paramétriques.
    """
    surface_kind: TNPSurfaceKind
    normal: Tuple[float, float, float]       # Vecteur normal moyen normalisé
    centroid: Tuple[float, float, float]     # Centre de gravité (barycentre surfacique)
    area: float                              # Aire surfacique totale
    bbox_min: Tuple[float, float, float]     # Boîte englobante AABB
    bbox_max: Tuple[float, float, float]
    generating_feature_id: str = ""          # Identifiant de la fonction génératrice (ex. 'f_pad')
    ancestry_tag: str = ""                   # Balise de lignée historique


@dataclass
class TrackedFace:
    """Face topologique suivie dans l'historique du modèle."""
    face_id: str
    fingerprint: GeometricFingerprint
    triangle_indices: List[int] = field(default_factory=list)
    split_from: Optional[str] = None         # Si la face résulte d'une découpe (scission)


class TNPMitigationManager:
    """
    Gestionnaire central du nommage topologique persistant.
    Assure la correspondance des faces et arêtes entre deux recalculs de l'arbre historique.
    """

    def __init__(self) -> None:
        # Cache des empreintes par version de solide : Dict[nom_solide, Dict[face_id, TrackedFace]]
        self._history_registry: Dict[str, Dict[str, TrackedFace]] = {}

    @staticmethod
    def compute_fingerprint(
        vertices: np.ndarray,
        tri_indices: Sequence[int],
        normals: np.ndarray,
        feature_id: str = "",
        tag: str = ""
    ) -> GeometricFingerprint:
        """Calcule l'empreinte géométrique exacte pour un groupe de triangles contigus."""
        if len(tri_indices) == 0:
            return GeometricFingerprint(
                surface_kind=TNPSurfaceKind.PLANE,
                normal=(0.0, 0.0, 1.0),
                centroid=(0.0, 0.0, 0.0),
                area=0.0,
                bbox_min=(0.0, 0.0, 0.0),
                bbox_max=(0.0, 0.0, 0.0),
                generating_feature_id=feature_id,
                ancestry_tag=tag
            )

        total_area = 0.0
        weighted_centroid = np.zeros(3, dtype=np.float64)
        avg_normal = np.zeros(3, dtype=np.float64)

        all_pts: List[np.ndarray] = []
        for tri_idx in tri_indices:
            v0 = vertices[tri_idx * 3].astype(np.float64)
            v1 = vertices[tri_idx * 3 + 1].astype(np.float64)
            v2 = vertices[tri_idx * 3 + 2].astype(np.float64)
            all_pts.extend([v0, v1, v2])

            cross_prod = np.cross(v1 - v0, v2 - v0)
            area_tri = 0.5 * float(np.linalg.norm(cross_prod))
            if area_tri > 1e-9:
                tri_normal = cross_prod / (2.0 * area_tri)
                avg_normal += tri_normal * area_tri
                c_tri = (v0 + v1 + v2) / 3.0
                weighted_centroid += c_tri * area_tri
                total_area += area_tri

        if total_area > 1e-9:
            centroid_pt = weighted_centroid / total_area
            norm_len = float(np.linalg.norm(avg_normal))
            final_norm = avg_normal / norm_len if norm_len > 1e-9 else np.array([0.0, 0.0, 1.0])
        else:
            centroid_pt = np.zeros(3, dtype=np.float64)
            final_norm = np.array([0.0, 0.0, 1.0], dtype=np.float64)

        pts_arr = np.array(all_pts)
        b_min = np.min(pts_arr, axis=0) if len(pts_arr) > 0 else np.zeros(3)
        b_max = np.max(pts_arr, axis=0) if len(pts_arr) > 0 else np.zeros(3)

        return GeometricFingerprint(
            surface_kind=TNPSurfaceKind.PLANE,
            normal=(float(final_norm[0]), float(final_norm[1]), float(final_norm[2])),
            centroid=(float(centroid_pt[0]), float(centroid_pt[1]), float(centroid_pt[2])),
            area=float(total_area),
            bbox_min=(float(b_min[0]), float(b_min[1]), float(b_min[2])),
            bbox_max=(float(b_max[0]), float(b_max[1]), float(b_max[2])),
            generating_feature_id=feature_id,
            ancestry_tag=tag
        )

    @classmethod
    def extract_faces(cls, solid: Solid, feature_id: str = "") -> List[TrackedFace]:
        """
        Décompose un solide en faces topologiques cohérentes par regroupement de normales coplanaires.
        """
        if solid.is_empty():
            return []

        buf = solid.to_mesh_buffer()
        if buf.is_empty():
            return []

        num_tris = len(buf.faces)
        normals = buf.normals
        vertices = buf.vertices

        # Regrouper les triangles coplanaires (même orientation de normale à 5 degrés près)
        visited = [False] * num_tris
        faces: List[TrackedFace] = []

        for i in range(num_tris):
            if visited[i]:
                continue

            ref_norm = normals[i * 3]
            group: List[int] = [i]
            visited[i] = True

            for j in range(i + 1, num_tris):
                if visited[j]:
                    continue
                cand_norm = normals[j * 3]
                dot = float(np.dot(ref_norm, cand_norm))
                if dot > 0.996:  # Moins de 5 degrés d'écart
                    # Vérifier que les triangles sont dans le même plan (offset similaire)
                    d_ref = float(np.dot(ref_norm, vertices[i * 3]))
                    d_cand = float(np.dot(ref_norm, vertices[j * 3]))
                    if abs(d_ref - d_cand) < 0.5:
                        visited[j] = True
                        group.append(j)

            face_idx = len(faces)
            fp = cls.compute_fingerprint(vertices, group, normals, feature_id=feature_id, tag=f"face_{face_idx}")
            faces.append(TrackedFace(
                face_id=f"Face_{face_idx}",
                fingerprint=fp,
                triangle_indices=group
            ))

        return faces

    @staticmethod
    def calculate_similarity(fp1: GeometricFingerprint, fp2: GeometricFingerprint) -> float:
        """
        Calcule la métrique de similarité géométrique multi-facteurs entre deux empreintes :
        Score = w_norm * Cos(theta) + w_cent * Proximité(centroid) + w_area * Ratio(aire)
        """
        # 1. Alignement des normales (poids 0.40)
        n1 = np.array(fp1.normal, dtype=np.float64)
        n2 = np.array(fp2.normal, dtype=np.float64)
        dot_n = max(0.0, float(np.dot(n1, n2)))
        w_norm = 0.40 * dot_n

        # 2. Proximité des centroïdes (poids 0.35)
        c1 = np.array(fp1.centroid, dtype=np.float64)
        c2 = np.array(fp2.centroid, dtype=np.float64)
        dist = float(np.linalg.norm(c1 - c2))
        w_cent = 0.35 * float(np.exp(-dist / 30.0))  # Échelle caractéristique 30 mm

        # 3. Ratio des aires (poids 0.15)
        a1, a2 = max(1e-4, fp1.area), max(1e-4, fp2.area)
        w_area = 0.15 * (min(a1, a2) / max(a1, a2))

        # 4. Fonction génératrice identique (poids 0.10)
        w_feat = 0.10 if (fp1.generating_feature_id and fp1.generating_feature_id == fp2.generating_feature_id) else 0.05

        return w_norm + w_cent + w_area + w_feat

    def match_face_across_rebuild(
        self,
        target_fingerprint: GeometricFingerprint,
        current_faces: Sequence[TrackedFace],
        acceptance_threshold: float = 0.60
    ) -> Optional[TrackedFace]:
        """
        Retrouve la face cible après recalcul de l'arbre, même si les index ont changé.
        Retourne la meilleure correspondance si le score dépasse le seuil de tolérance.
        """
        best_score = 0.0
        best_face: Optional[TrackedFace] = None

        for face in current_faces:
            score = self.calculate_similarity(target_fingerprint, face.fingerprint)
            if score > best_score:
                best_score = score
                best_face = face

        if best_score >= acceptance_threshold and best_face is not None:
            return best_face
        return None
