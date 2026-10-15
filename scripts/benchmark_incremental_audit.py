"""
Script de Démonstration et de Benchmark de l'Audit Industriel Déterministe.
Démontre rigoureusement l'accélération du temps d'audit (gain >= 45x)
sur une Pull Request type de 5 fichiers modifiés grâce au cache SHA-256
et à la parallélisation multi-processus.
"""

from __future__ import annotations
import os
import sys
import time
from typing import List, Dict, Tuple

# Injection racine projet
_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.industrial_audit_engine import ProjectIndustrialAuditor, AuditCacheManager


def simulate_pull_request_modification(files_to_touch: List[str]) -> Dict[str, str]:
    """
    Modifie temporairement une liste de fichiers sources en ajoutant un commentaire neutre
    pour simuler des commits réels d'une Pull Request.
    Retourne le contenu original sauvegardé pour restauration parfaite.
    """
    saved_contents: Dict[str, str] = {}
    for filepath in files_to_touch:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8", newline="") as f:
                content = f.read()
            saved_contents[filepath] = content

            # Ajout d'une modification bénigne simulant une PR
            modified = content + f"\n# PR simulated change: {time.time()}\n"
            with open(filepath, "w", encoding="utf-8", newline="") as f:
                f.write(modified)
    return saved_contents


def restore_original_files(saved_contents: Dict[str, str]) -> None:
    """Restaure fidèlement les fichiers originaux après le benchmark."""
    for filepath, original_content in saved_contents.items():
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            f.write(original_content)


def run_benchmark_pr_acceleration() -> Tuple[float, float, float]:
    """
    Exécute le protocole complet de mesure comparative :
    1. Mesure du temps d'audit initial complet à froid (Cold Run sans cache).
    2. Amorçage et validation du cache incrémental SHA-256.
    3. Simulation d'une Pull Request de 5 fichiers modifiés.
    4. Mesure du temps d'audit incrémental (Warm PR Run).
    5. Vérification formelle du facteur d'accélération >= 45x.
    """
    src_dir = os.path.join(_ROOT, "src")
    auditor = ProjectIndustrialAuditor(src_dir=src_dir)

    print("=" * 75)
    print("BANC D'ESSAI COMPARATIF : CACHE INCREMENTAL SHA-256 & PARALLELISATION")
    print("=" * 75)

    # Étape 1 : Audit complet sans cache (Cold Baseline)
    print("\n[ETAPE 1/4] Mesure du temps de référence à froid (Cold Baseline sans cache)...")
    t0_cold = time.perf_counter()
    report_cold = auditor.run_full_enterprise_audit(force_cold=True, verbose=False)
    t_cold = time.perf_counter() - t0_cold
    print(f"  -> Durée Audit à Froid (Cold Baseline) : {t_cold:.3f} s")
    print(f"  -> Fichiers analysés : {int(report_cold['total_files'])}")
    print(f"  -> Cache Hit : {int(report_cold['cache_hits'])}/{int(report_cold['total_files'])} (0%)")

    # Étape 2 : Pré-chauffage du cache
    print("\n[ETAPE 2/4] Pré-chauffage et persistance du cache SHA-256...")
    auditor.run_full_enterprise_audit(force_cold=False, verbose=False)

    # Étape 3 : Simulation d'une Pull Request type (5 fichiers modifiés)
    target_pr_files: List[str] = [
        os.path.join(src_dir, "core", "document.py"),
        os.path.join(src_dir, "core", "geometry.py"),
        os.path.join(src_dir, "core", "sketch.py"),
        os.path.join(src_dir, "core", "serializer.py"),
        os.path.join(src_dir, "ui", "main_window.py"),
    ]
    print(f"\n[ETAPE 3/4] Simulation d'une Pull Request type ({len(target_pr_files)} fichiers modifiés) :")
    for p in target_pr_files:
        print(f"  - {os.path.relpath(p, _ROOT)}")

    saved = simulate_pull_request_modification(target_pr_files)

    try:
        # Étape 4 : Mesure de l'audit incrémental sur la PR
        print("\n[ETAPE 4/4] Mesure de l'audit incrémental haute performance...")
        t0_pr = time.perf_counter()
        report_pr = auditor.run_full_enterprise_audit(force_cold=False, verbose=False)
        t_pr = time.perf_counter() - t0_pr
        print(f"  -> Durée Audit Incrémental PR : {t_pr:.3f} s")
        print(f"  -> Cache Hit : {int(report_pr['cache_hits'])}/{int(report_pr['total_files'])} ({report_pr['cache_hit_ratio_percent']:.1f}%)")

        # Calcul du ratio d'accélération
        speedup_factor = (t_cold / t_pr) if t_pr > 0.0 else 999.0

        print("\n" + "=" * 75)
        print("RESULTATS STATISTIQUES DU BENCHMARK")
        print("=" * 75)
        print(f"  Temps Audit Référence (Cold)    : {t_cold:.3f} secondes")
        print(f"  Temps Audit Incrémental (PR 5f) : {t_pr:.3f} secondes")
        print(f"  FACTEUR D'ACCELERATION REEL     : {speedup_factor:.1f}x plus rapide")
        print(f"  OBJECTIF DU CAHIER DES CHARGES  : >= 45.0x")

        if speedup_factor >= 45.0:
            print(f"  STATUT : [VALIDE] L'accélération ({speedup_factor:.1f}x) dépasse largement l'exigence de 45x.")
        else:
            print(f"  STATUT : [ATTENTION] Accélération mesurée à {speedup_factor:.1f}x (cible: 45x).")
        print("=" * 75 + "\n")

        return t_cold, t_pr, speedup_factor

    finally:
        # Restauration propre de l'arborescence git
        restore_original_files(saved)


if __name__ == "__main__":
    t_cold, t_pr, speedup = run_benchmark_pr_acceleration()
    if speedup < 45.0:
        sys.exit(1)
    sys.exit(0)
