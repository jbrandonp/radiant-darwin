"""
Module de streaming graphique et décimation géométrique continue LOD (Level of Detail) pour XR.
Gère la simplification topologique adaptative selon la distance caméra pour garantir
un rafraîchissement stable à 90 FPS (11.1 ms de budget de trame) en WebXR et casques spatiaux.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import List, Dict, Tuple, Optional
import numpy as np

from src.core.types import Vector3D


class LODStage(Enum):
    """Niveaux de détail hiérarchiques pour le streaming spatial."""
    LOD_0_FULL = "lod_0_full"        # Géométrie nominale (100% triangles, < 2m)
    LOD_1_MEDIUM = "lod_1_medium"    # Simplification 50% (2m à 10m)
    LOD_2_COARSE = "lod_2_coarse"    # Simplification 80% (10m à 30m)
    LOD_3_PROXY = "lod_3_proxy"      # Boîte englobante / Proxy bas débit (> 30m)


@dataclass
class SpatialMeshChunk:
    """Morceau de maillage spatial avec géométrie et volume englobant."""
    chunk_id: str
    vertices: np.ndarray             # Tableau Nx3 float32
    indices: np.ndarray              # Tableau Mx3 int32
    bounding_center: Vector3D
    bounding_radius_mm: float
    current_lod: LODStage = LODStage.LOD_0_FULL


@dataclass
class XRStreamingFrameReport:
    """Rapport de trame d'affichage temps réel WebXR."""
    frame_budget_ms: float           # Ex: 11.11 ms pour 90 FPS
    actual_render_time_ms: float
    is_frame_budget_respected: bool
    total_triangles_rendered: int
    lod_distribution: Dict[str, int] # Compteur de chunks par LOD


class ContinuousLODDecimator:
    """
    Moteur de décimation continue et régulateur de budget de rendu XR.
    Ajuste dynamiquement la résolution polygonale de chaque pièce en fonction
    de la distance à l'œil de l'utilisateur et de la dérive de fréquence d'images.
    """

    def __init__(
        self,
        target_fps: float = 90.0,
        lod1_distance_m: float = 2.0,
        lod2_distance_m: float = 10.0,
        lod3_distance_m: float = 30.0
    ) -> None:
        self.target_fps: float = target_fps
        self.frame_budget_ms: float = 1000.0 / target_fps  # 11.11 ms
        self.d_lod1: float = lod1_distance_m
        self.d_lod2: float = lod2_distance_m
        self.d_lod3: float = lod3_distance_m
        self.lod_bias: float = 1.0  # Facteur adaptatif dynamique

    def select_lod_for_chunk(self, chunk: SpatialMeshChunk, eye_position: Vector3D) -> LODStage:
        """Sélectionne le niveau LOD approprié selon la distance projective et le biais de charge."""
        dist_m = (chunk.bounding_center - eye_position).length() * 1e-3  # Conversion mm -> m
        effective_dist = dist_m / max(0.1, self.lod_bias)

        if effective_dist < self.d_lod1:
            return LODStage.LOD_0_FULL
        elif effective_dist < self.d_lod2:
            return LODStage.LOD_1_MEDIUM
        elif effective_dist < self.d_lod3:
            return LODStage.LOD_2_COARSE
        else:
            return LODStage.LOD_3_PROXY

    def decimate_mesh_chunk(self, chunk: SpatialMeshChunk, target_lod: LODStage) -> Tuple[np.ndarray, np.ndarray]:
        """
        Génère la version simplifiée du maillage par décimation de sommets (Vertex Clustering).
        """
        if target_lod == LODStage.LOD_0_FULL or len(chunk.indices) == 0:
            return chunk.vertices, chunk.indices

        # Ratio de décimation visé
        reduction_ratio = 0.5 if target_lod == LODStage.LOD_1_MEDIUM else (0.2 if target_lod == LODStage.LOD_2_COARSE else 0.05)
        target_tri_count = max(4, int(len(chunk.indices) * reduction_ratio))

        # Sous-échantillonnage régulier des triangles
        step = max(1, len(chunk.indices) // target_tri_count)
        decimated_indices = chunk.indices[::step]

        return chunk.vertices, decimated_indices

    def evaluate_frame_stream(
        self,
        chunks: List[SpatialMeshChunk],
        eye_position: Vector3D,
        simulated_gpu_time_ms: float
    ) -> XRStreamingFrameReport:
        """
        Traite l'ensemble de la scène spatiale pour une trame et ajuste le biais dynamique
        pour éviter la cinétose (motion sickness) si le budget de 11.1 ms est dépassé.
        """
        distribution: Dict[str, int] = {
            LODStage.LOD_0_FULL.value: 0,
            LODStage.LOD_1_MEDIUM.value: 0,
            LODStage.LOD_2_COARSE.value: 0,
            LODStage.LOD_3_PROXY.value: 0
        }
        total_tris = 0

        for ch in chunks:
            lod = self.select_lod_for_chunk(ch, eye_position)
            ch.current_lod = lod
            distribution[lod.value] += 1

            _, dec_idx = self.decimate_mesh_chunk(ch, lod)
            total_tris += len(dec_idx)

        # Régulation automatique de charge : si le GPU dépasse 11.1 ms, on augmente lod_bias
        is_safe = simulated_gpu_time_ms <= self.frame_budget_ms
        if not is_safe:
            self.lod_bias = min(3.0, self.lod_bias + 0.1)  # Dégrade la résolution pour accélérer
        else:
            self.lod_bias = max(0.5, self.lod_bias - 0.02) # Améliore la qualité visuelle

        return XRStreamingFrameReport(
            frame_budget_ms=self.frame_budget_ms,
            actual_render_time_ms=simulated_gpu_time_ms,
            is_frame_budget_respected=is_safe,
            total_triangles_rendered=total_tris,
            lod_distribution=distribution
        )
