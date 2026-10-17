"""
Module de redirection de compatibilité pour la couche I/O unifiée.
Réexporte les classes de src.io vers src.core pour préserver les imports existants.
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
