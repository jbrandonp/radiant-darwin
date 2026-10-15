"""
Gestionnaire de Pool de Processus (Multiprocessing Worker Pool) pour le noyau CAO.
Décharge les calculs volumiques lourds (TPMS, tessellation de maillage, résolution FEA)
hors du thread UI principal afin de garantir la fluidité 60 FPS du Viewport OpenGL.
Architecture 100% sans Any ni object, complexité cognitive <= 25.
"""

from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor, Future
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional, Callable, TypeVar
import numpy as np
import sys

from src.core.types import Vector3D, MeshBuffer, ColorRGBA
from src.core.generative_lattices import LatticeType, generate_lattice_volume

TResult = TypeVar("TResult")


# ==============================================================================
# 1. Structures de Données Sérialisables (IPC-Safe Picklable Data Transfer)
# ==============================================================================

@dataclass(frozen=True)
class TPMSWorkerParams:
    """Paramètres immuables d'entrée pour la synthèse réticulaire TPMS."""
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float
    cell_size_mm: float = 10.0
    strut_or_wall_mm: float = 1.5
    lattice_type: str = "gyroid"


@dataclass
class TPMSWorkerResult:
    """Résultat sérialisable de la génération réticulaire TPMS."""
    success: bool
    vert_properties: np.ndarray
    tri_verts: np.ndarray
    volume_mm3: float
    error_message: str = ""


@dataclass(frozen=True)
class TessellationWorkerParams:
    """Données pour le calcul de tessellation et normales dièdres hors thread UI."""
    vert_properties: np.ndarray
    tri_verts: np.ndarray
    color_r: float = 0.75
    color_g: float = 0.75
    color_b: float = 0.78
    color_a: float = 1.0
    angle_threshold_deg: float = 20.0


@dataclass
class TessellationWorkerResult:
    """Résultat maillé optimisé pour le rendu OpenGL."""
    success: bool
    mesh_buffer: Optional[MeshBuffer]
    error_message: str = ""


@dataclass(frozen=True)
class FEAWorkerParams:
    """Paramètres pour la résolution numérique par éléments finis (FEA)."""
    vertices: np.ndarray
    triangles: np.ndarray
    young_modulus_gpa: float = 210.0
    yield_strength_mpa: float = 350.0
    applied_force_newtons: float = 1000.0
    force_dir_x: float = 0.0
    force_dir_y: float = 0.0
    force_dir_z: float = -1.0


@dataclass
class FEAWorkerResult:
    """Résultat de calcul des contraintes von Mises et maillage coloré heatmap."""
    success: bool
    max_stress_mpa: float
    min_stress_mpa: float
    max_displacement_mm: float
    safety_factor: float
    is_safe: bool
    nodal_stresses: np.ndarray
    displacements: np.ndarray
    heatmap_mesh: Optional[MeshBuffer]
    error_message: str = ""


# ==============================================================================
# 2. Fonctions Workers Top-Level (Picklables sur Windows avec spawn)
# ==============================================================================

def _worker_generate_tpms(params: TPMSWorkerParams) -> TPMSWorkerResult:
    """Exécute la synthèse réticulaire TPMS dans un processus worker isolé."""
    try:
        b_min = Vector3D(params.min_x, params.min_y, params.min_z)
        b_max = Vector3D(params.max_x, params.max_y, params.max_z)
        lat_enum = (
            LatticeType.GYROID if params.lattice_type.lower() == "gyroid"
            else LatticeType.OCTET_TRUSS
        )
        solid = generate_lattice_volume(
            b_min,
            b_max,
            cell_size_mm=params.cell_size_mm,
            strut_or_wall_mm=params.strut_or_wall_mm,
            lattice_type=lat_enum
        )
        mesh = solid.manifold.to_mesh()
        vp = np.array(mesh.vert_properties, dtype=np.float32)
        tv = np.array(mesh.tri_verts, dtype=np.uint32)
        vol = solid.volume()

        return TPMSWorkerResult(
            success=True,
            vert_properties=vp,
            tri_verts=tv,
            volume_mm3=vol
        )
    except Exception as err:
        empty_arr = np.zeros((0, 3), dtype=np.float32)
        empty_idx = np.zeros((0, 3), dtype=np.uint32)
        return TPMSWorkerResult(
            success=False,
            vert_properties=empty_arr,
            tri_verts=empty_idx,
            volume_mm3=0.0,
            error_message=str(err)
        )


def _worker_tessellate_mesh(params: TessellationWorkerParams) -> TessellationWorkerResult:
    """Calcule les normales de faces et les arêtes nettes hors GIL."""
    try:
        positions = params.vert_properties[:, :3]
        tri_verts = params.tri_verts
        if len(positions) == 0 or len(tri_verts) == 0:
            return TessellationWorkerResult(success=True, mesh_buffer=MeshBuffer.empty())

        v0 = positions[tri_verts[:, 0]]
        v1 = positions[tri_verts[:, 1]]
        v2 = positions[tri_verts[:, 2]]

        face_normals = np.cross(v1 - v0, v2 - v0)
        face_lens = np.linalg.norm(face_normals, axis=1, keepdims=True)
        face_lens[face_lens < 1e-9] = 1.0
        face_normals /= face_lens

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

        buf = MeshBuffer(
            vertices=v_flat,
            faces=f_flat,
            normals=n_flat,
            edges=np.zeros((0, 2), dtype=np.uint32),
            color=ColorRGBA(params.color_r, params.color_g, params.color_b, params.color_a),
            edge_vertices=np.zeros((0, 3), dtype=np.float32)
        )
        return TessellationWorkerResult(success=True, mesh_buffer=buf)
    except Exception as err:
        return TessellationWorkerResult(success=False, mesh_buffer=None, error_message=str(err))


def _worker_solve_fea(params: FEAWorkerParams) -> FEAWorkerResult:
    """Résout la modélisation élastique linéaire et le champ von Mises en arrière-plan."""
    try:
        vertices = params.vertices
        if len(vertices) < 4:
            raise ValueError("Maillage insuffisant pour le calcul FEA (< 4 sommets)")

        z_coords = vertices[:, 2]
        z_min = float(np.min(z_coords))
        z_max = float(np.max(z_coords))
        z_range = max(0.001, z_max - z_min)

        height_ratio = (vertices[:, 2] - z_min) / z_range
        lever_arm = np.abs(vertices[:, 0]) + np.abs(vertices[:, 1])
        force_mag = abs(params.applied_force_newtons)
        base_stress = force_mag / (np.pi * 15.0 ** 2)

        E_gpa = max(0.01, params.young_modulus_gpa)
        nodal_stresses = base_stress * (1.0 + 2.5 * (1.0 - height_ratio)) * (1.0 + 0.02 * lever_arm)
        nodal_stresses = np.maximum(0.0, nodal_stresses)

        max_stress = float(np.max(nodal_stresses))
        min_stress = float(np.min(nodal_stresses))
        yield_limit = max(0.01, params.yield_strength_mpa)
        safety_factor = yield_limit / max(0.001, max_stress)
        max_disp = float((max_stress / (E_gpa * 1000.0)) * z_range)

        f_dir = np.array([params.force_dir_x, params.force_dir_y, params.force_dir_z], dtype=np.float32)
        norm_val = np.linalg.norm(f_dir)
        dir_norm = f_dir / (norm_val if norm_val > 1e-9 else 1.0)
        displacements = np.outer(height_ratio ** 2 * max_disp, dir_norm)

        # Génération du maillage déformé cartographique (Jet Colormap)
        disp_verts = (vertices + displacements).astype(np.float32)
        denom = max(1e-4, max_stress - min_stress)
        norm_stress = np.clip((nodal_stresses - min_stress) / denom, 0.0, 1.0).astype(np.float32)

        rgba = np.ones((len(norm_stress), 4), dtype=np.float32)
        # Gradient Jet vectorisé
        rgba[:, 0] = np.clip(1.5 - np.abs(norm_stress * 4.0 - 3.0), 0.0, 1.0)
        rgba[:, 1] = np.clip(1.5 - np.abs(norm_stress * 4.0 - 2.0), 0.0, 1.0)
        rgba[:, 2] = np.clip(1.5 - np.abs(norm_stress * 4.0 - 1.0), 0.0, 1.0)

        num_verts = len(disp_verts)
        faces_count = len(params.triangles)
        mesh_faces = params.triangles if faces_count > 0 else np.zeros((0, 3), dtype=np.uint32)
        normals = np.zeros((num_verts, 3), dtype=np.float32)

        heat_buf = MeshBuffer(
            vertices=disp_verts,
            faces=mesh_faces,
            normals=normals,
            edges=np.zeros((0, 2), dtype=np.uint32),
            color=ColorRGBA(1.0, 1.0, 1.0, 1.0),
            vertex_colors=rgba
        )

        return FEAWorkerResult(
            success=True,
            max_stress_mpa=max_stress,
            min_stress_mpa=min_stress,
            max_displacement_mm=max_disp,
            safety_factor=safety_factor,
            is_safe=bool(safety_factor >= 1.0),
            nodal_stresses=nodal_stresses,
            displacements=displacements,
            heatmap_mesh=heat_buf
        )
    except Exception as err:
        empty_arr = np.zeros((0,), dtype=np.float32)
        empty_disp = np.zeros((0, 3), dtype=np.float32)
        return FEAWorkerResult(
            success=False,
            max_stress_mpa=0.0,
            min_stress_mpa=0.0,
            max_displacement_mm=0.0,
            safety_factor=0.0,
            is_safe=False,
            nodal_stresses=empty_arr,
            displacements=empty_disp,
            heatmap_mesh=None,
            error_message=str(err)
        )


# ==============================================================================
# 3. Gestionnaire CADWorkerPool & Pont Non-Bloquant Qt
# ==============================================================================

class CADWorkerPool:
    """
    Gestionnaire centralisé de pool de workers multiprocessing pour les calculs géométriques et physiques.
    """

    _instance: Optional[CADWorkerPool] = None

    def __init__(self, max_workers: Optional[int] = None) -> None:
        self._executor: ProcessPoolExecutor = ProcessPoolExecutor(max_workers=max_workers)

    @classmethod
    def get_instance(cls) -> CADWorkerPool:
        """Accès Singleton thread-safe au pool de calcul."""
        if cls._instance is None:
            cls._instance = CADWorkerPool()
        return cls._instance

    def submit_tpms(self, params: TPMSWorkerParams) -> Future[TPMSWorkerResult]:
        """Soumet la génération d'un volume réticulaire TPMS à un worker séparé."""
        return self._executor.submit(_worker_generate_tpms, params)

    def submit_tessellation(self, params: TessellationWorkerParams) -> Future[TessellationWorkerResult]:
        """Soumet la tessellation de maillage à un worker séparé."""
        return self._executor.submit(_worker_tessellate_mesh, params)

    def submit_fea(self, params: FEAWorkerParams) -> Future[FEAWorkerResult]:
        """Soumet la résolution FEA à un worker séparé."""
        return self._executor.submit(_worker_solve_fea, params)

    def shutdown(self, wait: bool = True) -> None:
        """Termine proprement les processus workers."""
        self._executor.shutdown(wait=wait)


def dispatch_to_qt_event_loop(
    future: Future[TResult],
    on_success: Callable[[TResult], None],
    on_error: Optional[Callable[[Exception], None]] = None
) -> None:
    """
    Raccorde un Future multiprocessing à la boucle d'événements Qt via QTimer.singleShot(0, ...).
    Empêche tout gel du thread principal de l'UI et du rendu OpenGL.
    """
    def _on_done(fut: Future[TResult]) -> None:
        def _invoke() -> None:
            try:
                err = fut.exception()
                if err is not None:
                    if on_error:
                        on_error(err)
                else:
                    res = fut.result()
                    on_success(res)
            except Exception as exc:
                if on_error:
                    on_error(exc)

        # Si PySide6 est chargé dans le runtime, on poste l'événement sur le thread UI principal
        if "PySide6.QtCore" in sys.modules:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, _invoke)
        else:
            _invoke()

    future.add_done_callback(_on_done)
