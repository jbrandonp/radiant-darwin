"""
Shim rétrocompatible pour le moteur de mutation in-process (KernelAstMutationEngine).
Le code d'outillage de test et d'analyse a été déplacé dans :
`scripts.tooling.mutation_engine`.
"""
from __future__ import annotations
import sys
from pathlib import Path

# Assurer l'accès au paquet scripts.tooling même si exécuté isolément
_root_dir = str(Path(__file__).resolve().parent.parent.parent)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from scripts.tooling.mutation_engine import (
    MutationFamily,
    MutantStatus,
    GAORTransformer,
    GRORTransformer,
    GTRTransformer,
    GSOLVTransformer,
    BytecodeHotPatcher,
    KernelMutant,
    MutantResult,
    MutationReport,
    KernelMutationRegistry,
    KernelAstMutationEngine,
)

__all__ = [
    "MutationFamily",
    "MutantStatus",
    "GAORTransformer",
    "GRORTransformer",
    "GTRTransformer",
    "GSOLVTransformer",
    "BytecodeHotPatcher",
    "KernelMutant",
    "MutantResult",
    "MutationReport",
    "KernelMutationRegistry",
    "KernelAstMutationEngine",
]
