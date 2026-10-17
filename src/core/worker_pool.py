"""
Shim de rétrocompatibilité pour le gestionnaire de worker pool.
Redirige de manière transparente vers src.system.worker_pool.
"""

from __future__ import annotations
from src.system.worker_pool import (
    CADWorkerPool,
    WorkerPool,
    TPMSWorkerParams,
    TPMSWorkerResult,
    TessellationWorkerParams,
    TessellationWorkerResult,
    FEAWorkerParams,
    FEAWorkerResult,
    dispatch_to_qt_event_loop,
)

__all__ = [
    "CADWorkerPool",
    "WorkerPool",
    "TPMSWorkerParams",
    "TPMSWorkerResult",
    "TessellationWorkerParams",
    "TessellationWorkerResult",
    "FEAWorkerParams",
    "FEAWorkerResult",
    "dispatch_to_qt_event_loop",
]
