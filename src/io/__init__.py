"""
Package I/O universel pour CAD Studio.
Fournit une façade unifiée (IOManager) pour l'import et l'export multi-format
(STEP, IGES, DXF, SVG, 3MF, STL, OBJ, PLY, GLTF).
"""

from src.io.io_manager import (
    FileFormat,
    ImportResult,
    ExportResult,
    IOManager,
)

__all__ = [
    "FileFormat",
    "ImportResult",
    "ExportResult",
    "IOManager",
]
