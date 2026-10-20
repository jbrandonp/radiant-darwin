"""Outil de profilage et d'audit zéro-allocation pour pipelines géométriques (v1.0).

Vérifie l'alignement C-contiguous des tableaux NumPy, l'absence de copies mémoire cachées,
et mesure le delta d'allocation sur le tas via tracemalloc (avec filtrage précis du profileur).
100% typage statique strict (zéro Any, zéro object), complexité cognitive <= 15.
"""

from dataclasses import dataclass
import sys
import tracemalloc
from typing import Final, List
import numpy as np


@dataclass(frozen=True)
class AllocationAuditResult:
    """Résultat quantitatif d'un audit de profilage mémoire."""

    allocated_delta_bytes: int
    is_c_contiguous: bool
    is_zero_allocation: bool


def audit_array_contiguity(arr: np.ndarray) -> bool:
    """Vérifie si un tableau NumPy est contigu en mémoire C (sans saut de stride)."""
    return bool(arr.flags["C_CONTIGUOUS"])


def audit_memory_sharing(source: np.ndarray, derived: np.ndarray) -> bool:
    """Vérifie si deux tableaux partagent le même tampon d'octets sans copie."""
    return bool(np.shares_memory(source, derived))


def benchmark_zero_alloc_transformation(
    vertex_count: int = 100_000,
) -> AllocationAuditResult:
    """Exécute une transformation 3D canonique et audite les allocations mémoires."""
    # Création du tampon initial contigu
    raw_coords: np.ndarray = np.ones((vertex_count, 3), dtype=np.float32)
    # Matrice de rotation 3x3
    rot_matrix: np.ndarray = np.eye(3, dtype=np.float32)

    # Pré-allocation du tampon de sortie (Zéro Allocation dans la boucle)
    out_buffer: np.ndarray = np.empty_like(raw_coords)

    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    # Opération in-place via l'argument 'out' de NumPy
    np.matmul(raw_coords, rot_matrix, out=out_buffer)

    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    # Filtrer le surcoût propre à tracemalloc lui-même
    top_stats = [
        stat
        for stat in snapshot_after.compare_to(snapshot_before, "lineno")
        if "tracemalloc" not in stat.traceback[0].filename and stat.size_diff > 0
    ]
    total_delta: int = sum(stat.size_diff for stat in top_stats)

    c_contig: Final[bool] = audit_array_contiguity(out_buffer)
    zero_alloc: Final[bool] = (total_delta == 0)

    return AllocationAuditResult(
        allocated_delta_bytes=total_delta,
        is_c_contiguous=c_contig,
        is_zero_allocation=zero_alloc,
    )


def main() -> int:
    """Point d'entrée CLI pour le diagnostic zéro-allocation."""
    print("\n================ PROFILER SYSTÈME ZÉRO-ALLOCATION (SOTA 2026) ================")
    print("Test géométrique : Transformation de 100 000 sommets 3D avec tampon pré-alloué")
    result = benchmark_zero_alloc_transformation(100_000)

    print(f"Alignement C-Contiguous : {'OUI' if result.is_c_contiguous else 'NON'}")
    print(f"Octets alloués par l'opération : {result.allocated_delta_bytes} octet(s)")
    print(f"Statut Zéro-Allocation : {'CONFORME (0 octet alloué)' if result.is_zero_allocation else 'VIOLATION'}")

    if not result.is_c_contiguous or not result.is_zero_allocation:
        print("\n[ALERTE] Détection d'allocations cachées dans la boucle critique !")
        return 1

    print("\n[OK] Pipeline 100% conforme aux standards Ronacher/Hashimoto de haute performance.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
