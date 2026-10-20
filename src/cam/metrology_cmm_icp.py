"""
Module de métrologie 3D, contrôle CMM et recalage de nuages de points réels (Scan-to-CAD).
Implémente l'algorithme Iterative Closest Point (ICP) par décomposition SVD et
cartographie les écarts d'usinage/tolérancement GD&T par rapport au modèle nominal.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import math
from typing import List, Tuple, Optional, Dict
import numpy as np

from src.core.types import Vector3D


@dataclass
class CMMPointRecord:
    """Mesure ponctuelle issue d'un palpeur MMT ou d'un scanner laser 3D."""
    scanned_point: Vector3D
    nominal_closest_point: Vector3D
    nominal_normal: Vector3D
    signed_deviation_mm: float
    is_in_tolerance: bool


@dataclass
class MetrologyInspectionReport:
    """Rapport métrologique officiel de contrôle géométrique dimensionnel."""
    total_points: int
    in_tolerance_percentage: float
    max_positive_deviation_mm: float # Surépaisseur (matière excédentaire)
    max_negative_deviation_mm: float # Sous-épaisseur (creux / sur-usinage)
    mean_deviation_mm: float
    rms_deviation_mm: float
    rigid_transform_translation: Vector3D
    points: List[CMMPointRecord] = field(default_factory=list)


class IterativeClosestPointAligner:
    """
    Solveur d'alignement rigide optimal (SVD-ICP) recalant un scan physique sur la CAO nominale.
    Estime la matrice de rotation R et le vecteur de translation t minimisant la somme des
    carrés des distances entre le nuage mesuré et la géométrie de référence.
    """

    def __init__(
        self,
        max_iterations: int = 50,
        tolerance_epsilon: float = 1e-6,
        upper_gdt_limit_mm: float = 0.05,
        lower_gdt_limit_mm: float = -0.05
    ) -> None:
        self.max_iterations: int = max_iterations
        self.tolerance_epsilon: float = tolerance_epsilon
        self.upper_limit: float = upper_gdt_limit_mm
        self.lower_limit: float = lower_gdt_limit_mm

    def align_and_inspect(
        self,
        scanned_points: List[Vector3D],
        nominal_points: List[Vector3D],
        nominal_normals: List[Vector3D]
    ) -> MetrologyInspectionReport:
        """
        Exécute la boucle d'optimisation ICP et génère la cartographie des écarts dimensionnels.
        """
        if not scanned_points or not nominal_points:
            return MetrologyInspectionReport(0, 0.0, 0.0, 0.0, 0.0, 0.0, Vector3D(0.0, 0.0, 0.0))

        p_pts = np.array([[p.x, p.y, p.z] for p in scanned_points], dtype=np.float64)
        q_ref = np.array([[q.x, q.y, q.z] for q in nominal_points], dtype=np.float64)
        n_ref = np.array([[n.x, n.y, n.z] for n in nominal_normals], dtype=np.float64)

        current_p = np.copy(p_pts)
        cum_r = np.eye(3, dtype=np.float64)
        cum_t = np.zeros(3, dtype=np.float64)

        prev_error = float("inf")

        for _ in range(self.max_iterations):
            # 1. Correspondance des plus proches voisins (Euclidean Nearest Neighbors)
            closest_indices = self._find_nearest_neighbors(current_p, q_ref)
            matched_q = q_ref[closest_indices]

            # 2. Filtrage robuste des points aberrants (Trimmed ICP pour éliminer brides, étaux et bruits)
            sq_dists = np.sum((current_p - matched_q) ** 2, axis=1)
            inlier_cutoff = float(np.percentile(sq_dists, 85.0))
            inlier_mask = sq_dists <= max(1.0, inlier_cutoff)

            if int(np.sum(inlier_mask)) >= 3:
                r_step, t_step = self._compute_rigid_step(current_p[inlier_mask], matched_q[inlier_mask])
            else:
                r_step, t_step = self._compute_rigid_step(current_p, matched_q)

            # 3. Application de la mise à jour
            current_p = (current_p @ r_step.T) + t_step
            cum_r = r_step @ cum_r
            cum_t = r_step @ cum_t + t_step

            # 4. Évaluation de l'erreur résiduelle quadratique
            diffs = current_p - matched_q
            current_error = float(np.mean(np.sum(diffs ** 2, axis=1)))

            if abs(prev_error - current_error) < self.tolerance_epsilon:
                break
            prev_error = current_error

        # 5. Calcul final des écarts projetés le long des normales nominales
        final_indices = self._find_nearest_neighbors(current_p, q_ref)
        records: List[CMMPointRecord] = []
        deviations: List[float] = []

        in_tol_count = 0
        for i in range(len(scanned_points)):
            p_final = Vector3D(float(current_p[i, 0]), float(current_p[i, 1]), float(current_p[i, 2]))
            idx_nom = final_indices[i]
            q_nom = nominal_points[idx_nom]
            n_nom = nominal_normals[idx_nom].normalized()

            # Écart signé : positif = surépaisseur, négatif = creux
            vec_diff = p_final - q_nom
            signed_dev = vec_diff.dot(n_nom)
            deviations.append(signed_dev)

            is_ok = self.lower_limit <= signed_dev <= self.upper_limit
            if is_ok:
                in_tol_count += 1

            records.append(CMMPointRecord(
                scanned_point=p_final,
                nominal_closest_point=q_nom,
                nominal_normal=n_nom,
                signed_deviation_mm=signed_dev,
                is_in_tolerance=is_ok
            ))

        total_pts = len(scanned_points)
        in_tol_pct = (float(in_tol_count) / float(max(1, total_pts))) * 100.0
        max_pos = max(0.0, max(deviations) if deviations else 0.0)
        max_neg = min(0.0, min(deviations) if deviations else 0.0)
        mean_dev = float(np.mean(deviations)) if deviations else 0.0
        rms_dev = float(np.sqrt(np.mean(np.array(deviations) ** 2))) if deviations else 0.0

        return MetrologyInspectionReport(
            total_points=total_pts,
            in_tolerance_percentage=in_tol_pct,
            max_positive_deviation_mm=max_pos,
            max_negative_deviation_mm=max_neg,
            mean_deviation_mm=mean_dev,
            rms_deviation_mm=rms_dev,
            rigid_transform_translation=Vector3D(float(cum_t[0]), float(cum_t[1]), float(cum_t[2])),
            points=records
        )

    def _find_nearest_neighbors(self, p_arr: np.ndarray, q_arr: np.ndarray) -> np.ndarray:
        """Trouve l'indice du point nominal le plus proche pour chaque point scanné via KD-Tree."""
        try:
            from scipy.spatial import cKDTree
            tree = cKDTree(q_arr)
            _, indices = tree.query(p_arr, k=1)
            return np.asarray(indices, dtype=np.int64)
        except Exception:
            # Fallback par blocs bornés pour éliminer tout risque d'explosion de RAM O(N*M)
            n_p = len(p_arr)
            chunk_size = 2000
            closest = np.zeros(n_p, dtype=np.int64)
            q_norm2 = np.sum(q_arr ** 2, axis=1, keepdims=True).T
            for start in range(0, n_p, chunk_size):
                end = min(start + chunk_size, n_p)
                p_chunk = p_arr[start:end]
                p_norm2 = np.sum(p_chunk ** 2, axis=1, keepdims=True)
                dist_matrix = p_norm2 - 2.0 * (p_chunk @ q_arr.T) + q_norm2
                closest[start:end] = np.argmin(dist_matrix, axis=1)
            return closest

    def _compute_rigid_step(self, p_pts: np.ndarray, q_pts: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Résout le problème de Procruste orthogonal via SVD pour extraire R et t."""
        centroid_p = np.mean(p_pts, axis=0)
        centroid_q = np.mean(q_pts, axis=0)

        p_centered = p_pts - centroid_p
        q_centered = q_pts - centroid_q

        # Matrice de covariance croisée H
        h_cov = p_centered.T @ q_centered

        u_mat, _, vh_mat = np.linalg.svd(h_cov)
        r_mat = vh_mat.T @ u_mat.T

        # Correction de réflexion si det(R) = -1
        if np.linalg.det(r_mat) < 0.0:
            vh_corrected = np.copy(vh_mat)
            vh_corrected[-1, :] *= -1.0
            r_mat = vh_corrected.T @ u_mat.T

        t_vec = centroid_q - (r_mat @ centroid_p)
        return r_mat, t_vec
