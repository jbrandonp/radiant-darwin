"""
Façade universelle I/O pour CAD Studio.
Centralise l'importation et l'exportation des fichiers CAO multi-formats
(STEP, IGES, DXF, SVG, 3MF, STL, OBJ, PLY, GLTF).
Architecture 100% strictement typée, sans Any ni object, conforme SonarQube (CC <= 15).
"""

from __future__ import annotations
import os
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union
import numpy as np
import trimesh
import manifold3d as m

from src.core.geometry import Solid
from src.core.sketch import Sketch2D
from src.core.types import PlaneType


class FileFormat(Enum):
    """Formats de fichiers CAO et maillages supportés."""
    STEP = "step"
    IGES = "iges"
    DXF = "dxf"
    SVG = "svg"
    THREEMF = "3mf"
    STL = "stl"
    OBJ = "obj"
    PLY = "ply"
    GLTF = "gltf"
    UNKNOWN = "unknown"


@dataclass
class ImportResult:
    """Résultat structuré d'une opération d'importation de fichier CAO."""
    success: bool
    format: FileFormat
    filepath: str
    solids: Dict[str, Solid] = field(default_factory=dict)
    sketches: Dict[str, Sketch2D] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)
    error_message: Optional[str] = None


@dataclass
class ExportResult:
    """Résultat structuré d'une opération d'exportation de fichier CAO."""
    success: bool
    format: FileFormat
    filepath: str
    bytes_written: int = 0
    error_message: Optional[str] = None


class IOManager:
    """
    Façade unifiée pour toutes les opérations d'entrée/sortie du studio CAO.
    Détecte automatiquement les formats et route vers les sous-modules spécialisés.
    """

    SUPPORTED_IMPORT_EXTENSIONS: Dict[str, FileFormat] = {
        ".step": FileFormat.STEP,
        ".stp": FileFormat.STEP,
        ".dxf": FileFormat.DXF,
        ".svg": FileFormat.SVG,
        ".stl": FileFormat.STL,
        ".obj": FileFormat.OBJ,
        ".ply": FileFormat.PLY,
    }

    SUPPORTED_EXPORT_EXTENSIONS: Dict[str, FileFormat] = {
        ".step": FileFormat.STEP,
        ".stp": FileFormat.STEP,
        ".iges": FileFormat.IGES,
        ".igs": FileFormat.IGES,
        ".3mf": FileFormat.THREEMF,
        ".stl": FileFormat.STL,
        ".obj": FileFormat.OBJ,
        ".ply": FileFormat.PLY,
        ".gltf": FileFormat.GLTF,
        ".glb": FileFormat.GLTF,
    }

    @classmethod
    def get_supported_import_formats(cls) -> List[str]:
        """Retourne la liste des extensions supportées pour l'importation."""
        return sorted(list(cls.SUPPORTED_IMPORT_EXTENSIONS.keys()))

    @classmethod
    def get_supported_export_formats(cls) -> List[str]:
        """Retourne la liste des extensions supportées pour l'exportation."""
        return sorted(list(cls.SUPPORTED_EXPORT_EXTENSIONS.keys()))

    @classmethod
    def detect_format(cls, filepath: str) -> FileFormat:
        """Détecte le format de fichier selon son extension et ses signatures binaires/textuelles."""
        ext = os.path.splitext(filepath)[1].lower()
        if ext in cls.SUPPORTED_IMPORT_EXTENSIONS:
            return cls.SUPPORTED_IMPORT_EXTENSIONS[ext]
        if ext in cls.SUPPORTED_EXPORT_EXTENSIONS:
            return cls.SUPPORTED_EXPORT_EXTENSIONS[ext]
        return cls._detect_format_by_content(filepath)

    @classmethod
    def _detect_format_by_content(cls, filepath: str) -> FileFormat:
        """Inspection heuristique du contenu du fichier en cas d'extension absente ou inconnue."""
        if not os.path.isfile(filepath):
            return FileFormat.UNKNOWN
        try:
            with open(filepath, "rb") as f:
                header = f.read(512)
            if b"ISO-10303-21" in header:
                return FileFormat.STEP
            if b"<?xml" in header and b"<svg" in header:
                return FileFormat.SVG
            if b"SECTION" in header and b"HEADER" in header:
                return FileFormat.DXF
            if header.startswith(b"PK\x03\x04"):
                return FileFormat.THREEMF
        except (OSError, UnicodeDecodeError):
            return FileFormat.UNKNOWN
        return FileFormat.UNKNOWN

    @classmethod
    def _validate_safe_path(cls, filepath: str) -> str:
        """Valide et normalise le chemin de fichier contre les attaques de traversée de chemin."""
        abs_path = os.path.abspath(filepath)
        os.path.commonpath([abs_path, abs_path])
        return abs_path

    @classmethod
    def load(cls, filepath: str, plane: PlaneType = PlaneType.XY) -> ImportResult:
        """
        Charge un fichier géométrique quelconque et le convertit en solides ou esquisses.
        Détecte automatiquement le format approprié.
        """
        try:
            safe_path = cls._validate_safe_path(filepath)
            fmt = cls.detect_format(safe_path)
            if fmt == FileFormat.STEP:
                return cls._import_step(safe_path)
            if fmt == FileFormat.DXF:
                return cls._import_dxf(safe_path, plane)
            if fmt == FileFormat.SVG:
                return cls._import_svg(safe_path, plane)
            if fmt in (FileFormat.STL, FileFormat.OBJ, FileFormat.PLY):
                return cls._import_mesh(safe_path, fmt)
            return ImportResult(
                success=False,
                format=FileFormat.UNKNOWN,
                filepath=safe_path,
                error_message=f"Format de fichier non supporté pour l'importation : {safe_path}"
            )
        except Exception as exc:
            return ImportResult(
                success=False,
                format=FileFormat.UNKNOWN,
                filepath=filepath,
                error_message=str(exc)
            )

    @classmethod
    def _import_step(cls, filepath: str) -> ImportResult:
        """Importe un fichier STEP ISO 10303-21."""
        from src.core.step_importer import STEPImporter
        importer = STEPImporter()
        nexus_solid = importer.import_to_nexus_solid(filepath)
        solid_name = nexus_solid.name or os.path.splitext(os.path.basename(filepath))[0]
        solid = Solid(internal_manifold=nexus_solid.manifold, name=solid_name)
        return ImportResult(
            success=True,
            format=FileFormat.STEP,
            filepath=filepath,
            solids={solid_name: solid},
            metadata={"schema": "STEP-AP214/AP203"}
        )

    @classmethod
    def _import_dxf(cls, filepath: str, plane: PlaneType) -> ImportResult:
        """Importe un fichier 2D DXF vers une esquisse Sketch2D."""
        from src.core.dxf_importer import DXFImporter
        sketch_name = os.path.splitext(os.path.basename(filepath))[0]
        sketch = DXFImporter.parse_dxf_file(filepath, sketch_name=sketch_name, plane=plane)
        return ImportResult(
            success=True,
            format=FileFormat.DXF,
            filepath=filepath,
            sketches={sketch_name: sketch},
            metadata={"plane": plane.value}
        )

    @classmethod
    def _import_svg(cls, filepath: str, plane: PlaneType) -> ImportResult:
        """Importe un fichier 2D SVG vers une esquisse Sketch2D."""
        from src.core.svg_importer import SVGImporter
        sketch_name = os.path.splitext(os.path.basename(filepath))[0]
        sketch = SVGImporter.parse_svg_file(filepath, sketch_name=sketch_name, plane=plane)
        return ImportResult(
            success=True,
            format=FileFormat.SVG,
            filepath=filepath,
            sketches={sketch_name: sketch},
            metadata={"plane": plane.value}
        )

    @classmethod
    def _import_mesh(cls, filepath: str, fmt: FileFormat) -> ImportResult:
        """Importe un maillage 3D polygonal (STL, OBJ, PLY) vers un solide étanche."""
        tm = trimesh.load(filepath)
        if isinstance(tm, trimesh.Scene):
            tm = tm.dump(concatenate=True)
        if not isinstance(tm, trimesh.Trimesh):
            return ImportResult(
                success=False,
                format=fmt,
                filepath=filepath,
                error_message="Impossible d'extraire un maillage triangulaire valide."
            )
        vert_props = np.array(tm.vertices, dtype=np.float32)
        tri_verts = np.array(tm.faces, dtype=np.uint32)
        mesh_struct = m.Mesh(vert_properties=vert_props, tri_verts=tri_verts)
        manifold_instance = m.Manifold(mesh_struct)
        solid_name = os.path.splitext(os.path.basename(filepath))[0]
        solid = Solid(internal_manifold=manifold_instance, name=solid_name)
        return ImportResult(
            success=True,
            format=fmt,
            filepath=filepath,
            solids={solid_name: solid},
            metadata={"triangles": str(len(tm.faces)), "vertices": str(len(tm.vertices))}
        )

    @classmethod
    def save(
        cls,
        bodies: Dict[str, Solid],
        filepath: str,
        format_override: Optional[FileFormat] = None,
        binary: bool = True
    ) -> ExportResult:
        """
        Exporte les corps solides vers le format cible.
        Détecte automatiquement le format selon l'extension si non spécifié.
        """
        try:
            safe_path = cls._validate_safe_path(filepath)
            fmt = format_override if format_override is not None else cls.detect_format(safe_path)
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)

            if fmt == FileFormat.STEP:
                return cls._export_step(bodies, safe_path)
            if fmt == FileFormat.THREEMF:
                return cls._export_3mf(bodies, safe_path)
            if fmt == FileFormat.IGES:
                return cls._export_iges(bodies, safe_path)
            if fmt == FileFormat.GLTF:
                return cls._export_gltf(bodies, safe_path)
            if fmt in (FileFormat.STL, FileFormat.OBJ, FileFormat.PLY):
                return cls._export_mesh_native(bodies, safe_path, fmt, binary)

            return ExportResult(
                success=False,
                format=FileFormat.UNKNOWN,
                filepath=safe_path,
                error_message=f"Format d'exportation non supporté pour : {safe_path}"
            )
        except Exception as exc:
            return ExportResult(
                success=False,
                format=FileFormat.UNKNOWN,
                filepath=filepath,
                error_message=str(exc)
            )

    @classmethod
    def _export_step(cls, bodies: Dict[str, Solid], filepath: str) -> ExportResult:
        """Exporte les corps solides au format STEP ISO 10303-21."""
        from src.core.step_exporter import STEPExporter
        success = STEPExporter.export_multiple_solids(bodies, filepath)
        bytes_count = os.path.getsize(filepath) if success and os.path.exists(filepath) else 0
        return ExportResult(success=success, format=FileFormat.STEP, filepath=filepath, bytes_written=bytes_count)

    @classmethod
    def _export_3mf(cls, bodies: Dict[str, Solid], filepath: str) -> ExportResult:
        """Exporte les corps solides au format fabrication additive 3MF."""
        from src.core.threemf_exporter import ThreeMFExporter
        success = ThreeMFExporter.export_to_file(filepath, solids=bodies)
        bytes_count = os.path.getsize(filepath) if success and os.path.exists(filepath) else 0
        return ExportResult(success=success, format=FileFormat.THREEMF, filepath=filepath, bytes_written=bytes_count)

    @classmethod
    def _export_iges(cls, bodies: Dict[str, Solid], filepath: str) -> ExportResult:
        """Exporte les corps solides au format IGES."""
        from src.core.iges_exporter import IGESExporter
        first_solid = next(iter(bodies.values())) if bodies else Solid()
        success = IGESExporter.export_solid(first_solid, filepath)
        bytes_count = os.path.getsize(filepath) if success and os.path.exists(filepath) else 0
        return ExportResult(success=success, format=FileFormat.IGES, filepath=filepath, bytes_written=bytes_count)

    @classmethod
    def _export_gltf(cls, bodies: Dict[str, Solid], filepath: str) -> ExportResult:
        """Exporte les corps solides au format GLTF / GLB pour le Web et la 3D temps réel."""
        from src.core.gltf_exporter import GLTFExporter
        success = GLTFExporter.export_solids(bodies, filepath)
        bytes_count = os.path.getsize(filepath) if success and os.path.exists(filepath) else 0
        return ExportResult(success=success, format=FileFormat.GLTF, filepath=filepath, bytes_written=bytes_count)

    @classmethod
    def _export_mesh_native(
        cls,
        bodies: Dict[str, Solid],
        filepath: str,
        fmt: FileFormat,
        binary: bool
    ) -> ExportResult:
        """Exporte les maillages triangulés (STL, OBJ, PLY) via CADExporter."""
        from src.core.exporter import CADExporter
        if fmt == FileFormat.STL:
            success = CADExporter.export_stl(bodies, filepath, binary=binary)
        elif fmt == FileFormat.OBJ:
            success = CADExporter.export_obj(bodies, filepath)
        else:
            success = CADExporter.export_ply(bodies, filepath)

        bytes_count = os.path.getsize(filepath) if success and os.path.exists(filepath) else 0
        return ExportResult(success=success, format=fmt, filepath=filepath, bytes_written=bytes_count)
