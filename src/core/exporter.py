"""
Module d'exportation de fichiers 3D pour la fabrication et l'impression 3D (STL, OBJ, PLY).
Permet d'exporter les corps solides modélisés vers les trancheurs (Cura, Bambu Lab, Prusa).
"""

from __future__ import annotations
from typing import List, Dict, Optional
import os
import numpy as np
import trimesh

from src.core.geometry import Solid
from src.core.types import MeshBuffer


class CADExporter:
    """Exportateur multi-format pour les modèles de CAO 3D."""

    @staticmethod
    def export_stl(bodies: Dict[str, Solid], filepath: str, binary: bool = True) -> bool:
        """
        Exporte les corps solides au format STL pour l'impression 3D.
        - filepath : chemin du fichier de destination (.stl)
        - binary : encodage binaire compact si True, sinon ASCII lisible.
        """
        if not filepath.lower().endswith(".stl"):
            return False
        abs_path = os.path.abspath(filepath)
        os.path.commonpath([abs_path, abs_path])

        meshes = CADExporter._combine_solids_to_trimesh(bodies)
        if meshes is None:
            return False

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        meshes.export(abs_path, file_type="stl_ascii" if not binary else "stl")
        return True

    @staticmethod
    def export_obj(bodies: Dict[str, Solid], filepath: str) -> bool:
        """
        Exporte les corps solides au format Wavefront OBJ.
        Conserve les sommets, faces et normales lissées.
        """
        if not filepath.lower().endswith(".obj"):
            return False
        abs_path = os.path.abspath(filepath)
        os.path.commonpath([abs_path, abs_path])

        meshes = CADExporter._combine_solids_to_trimesh(bodies)
        if meshes is None:
            return False

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        meshes.export(abs_path, file_type="obj")
        return True

    @staticmethod
    def export_ply(bodies: Dict[str, Solid], filepath: str) -> bool:
        """Exporte les corps solides au format Stanford PLY."""
        if not filepath.lower().endswith(".ply"):
            return False
        abs_path = os.path.abspath(filepath)
        os.path.commonpath([abs_path, abs_path])

        meshes = CADExporter._combine_solids_to_trimesh(bodies)
        if meshes is None:
            return False

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        meshes.export(abs_path, file_type="ply")
        return True

    @staticmethod
    def export_step(bodies: Dict[str, Solid], filepath: str) -> bool:
        """Exporte les corps solides au format standard d'échange STEP (ISO 10303-21 AP203)."""
        from src.core.step_exporter import STEPExporter
        return STEPExporter.export_multiple_solids(bodies, filepath)

    @staticmethod
    def export_3mf(bodies: Dict[str, Solid], filepath: str) -> bool:
        """Exporte les corps solides au format de fabrication additive 3MF (ISO/IEC 25422)."""
        from src.core.threemf_exporter import ThreeMFExporter
        return ThreeMFExporter.export_to_file(filepath, solids=bodies)

    @staticmethod
    def _combine_solids_to_trimesh(bodies: Dict[str, Solid]) -> Optional[trimesh.Trimesh]:
        """Combine tous les solides du dictionnaire en une seule structure trimesh."""
        sub_meshes: List[trimesh.Trimesh] = []

        for body in bodies.values():
            if body.is_empty():
                continue
            buf = body.to_mesh_buffer()
            if buf.is_empty():
                continue

            tm = trimesh.Trimesh(
                vertices=buf.vertices,
                faces=buf.faces,
                vertex_normals=buf.normals,
                process=False
            )
            sub_meshes.append(tm)

        if not sub_meshes:
            return None

        if len(sub_meshes) == 1:
            return sub_meshes[0]

        combined = trimesh.util.concatenate(sub_meshes)
        return combined
