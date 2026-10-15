"""
Validation et benchmark comparatif entre AstQualityAuditor (ancien moteur)
et UnifiedIndustrialAstVisitor (nouveau moteur single-pass).
"""

from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.abspath("."))

import time
import cProfile
import pstats
from typing import Dict, List, Set, Tuple

import scripts.industrial_audit_engine as old_engine
import scripts.unified_ast_engine as new_engine


def validate_parity() -> bool:
    """
    Vérifie la parité exacte de toutes les métriques sur l'ensemble des 129 fichiers de src/.
    """
    print("=" * 70)
    print("TEST DE PARITÉ DÉTERMINISTE DES MÉTRIQUES (129 FICHIERS)")
    print("=" * 70)

    py_files: List[str] = []
    for root, _, files in os.walk("src"):
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))

    mismatches: int = 0
    total_files: int = len(py_files)
    total_functions_checked: int = 0

    for idx, filepath in enumerate(py_files, 1):
        old_rep = old_engine.AstQualityAuditor.audit_file(filepath)
        new_rep = new_engine.UnifiedAstQualityAuditor.audit_file(filepath)

        # 1. Vérification SLOC
        if old_rep.lines_of_code != new_rep.lines_of_code:
            print(f"[{idx}/{total_files}] ÉCHEC SLOC sur {filepath}: old={old_rep.lines_of_code}, new={new_rep.lines_of_code}")
            mismatches += 1

        # 2. Vérification Complexité Cognitive
        if old_rep.cognitive_complexity != new_rep.cognitive_complexity:
            print(f"[{idx}/{total_files}] ÉCHEC Cognitive sur {filepath}: old={old_rep.cognitive_complexity}, new={new_rep.cognitive_complexity}")
            mismatches += 1

        # 3. Vérification Complexité Cyclomatique McCabe
        if old_rep.cyclomatic_complexity != new_rep.cyclomatic_complexity:
            print(f"[{idx}/{total_files}] ÉCHEC McCabe sur {filepath}: old={old_rep.cyclomatic_complexity}, new={new_rep.cyclomatic_complexity}")
            mismatches += 1

        # 4. Vérification Indice de Maintenabilité
        if abs(old_rep.maintainability_index - new_rep.maintainability_index) > 1e-4:
            print(f"[{idx}/{total_files}] ÉCHEC MI sur {filepath}: old={old_rep.maintainability_index:.4f}, new={new_rep.maintainability_index:.4f}")
            mismatches += 1

        # 5. Vérification Typage Statique
        if abs(old_rep.type_completeness_percent - new_rep.type_completeness_percent) > 1e-4:
            print(f"[{idx}/{total_files}] ÉCHEC Typage sur {filepath}: old={old_rep.type_completeness_percent:.2f}%, new={new_rep.type_completeness_percent:.2f}%")
            mismatches += 1

        # 6. Vérification Sécurité SAST
        if old_rep.security_violations != new_rep.security_violations:
            print(f"[{idx}/{total_files}] ÉCHEC Sécurité sur {filepath}: old={old_rep.security_violations}, new={new_rep.security_violations}")
            mismatches += 1

        # 7. Vérification Fonctions individuelles
        if len(old_rep.functions) != len(new_rep.functions):
            print(f"[{idx}/{total_files}] ÉCHEC Nb fonctions sur {filepath}: old={len(old_rep.functions)}, new={len(new_rep.functions)}")
            mismatches += 1
        else:
            old_fn_map = {(fn.name, fn.line_number): fn for fn in old_rep.functions}
            for new_fn in new_rep.functions:
                key = (new_fn.name, new_fn.line_number)
                if key not in old_fn_map:
                    print(f"[{idx}/{total_files}] Fonction manquante {key} dans {filepath}")
                    mismatches += 1
                else:
                    target_fn = old_fn_map[key]
                    total_functions_checked += 1
                    if target_fn.cognitive_complexity != new_fn.cognitive_complexity or target_fn.cyclomatic_complexity != new_fn.cyclomatic_complexity:
                        print(f"[{idx}/{total_files}] ÉCHEC métrique fn {key} dans {filepath}: old=({target_fn.cognitive_complexity}, {target_fn.cyclomatic_complexity}), new=({new_fn.cognitive_complexity}, {new_fn.cyclomatic_complexity})")
                        mismatches += 1

    print(f"Total fichiers vérifiés : {total_files}")
    print(f"Total fonctions vérifiées : {total_functions_checked}")
    print(f"Nombre d'incohérences (mismatches) : {mismatches}")
    if mismatches == 0:
        print(">>> SUCCÈS : PARITÉ RIGOUREUSE 100% ATTEINTE SUR TOUTES LES MÉTRIQUES <<<")
        return True
    else:
        print(">>> ÉCHEC : DES INCOHÉRENCES ONT ÉTÉ DÉTECTÉES <<<")
        return False


def benchmark_acceleration() -> None:
    """
    Mesure le temps d'exécution et le nombre d'appels internes avant et après optimisation.
    """
    print("\n" + "=" * 70)
    print("BENCHMARK D'ACCÉLÉRATION & COMPTAGE DES APPELS INTERNES (cProfile)")
    print("=" * 70)

    py_files: List[str] = []
    for root, _, files in os.walk("src"):
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))

    # --- Ancien moteur ---
    print("\n1. Profilage de l'ancien moteur (Double parsing + walk imbriqués + ast.unparse)...")
    pr_old = cProfile.Profile()
    pr_old.enable()
    t0_old = time.perf_counter()
    for fp in py_files:
        old_engine.AstQualityAuditor.audit_file(fp)
    old_engine.ArchitectureDependencyAnalyzer.analyze_dependencies("src")
    t1_old = time.perf_counter()
    pr_old.disable()
    stats_old = pstats.Stats(pr_old)
    duration_old = t1_old - t0_old

    # --- Nouveau moteur Single-Pass ---
    print("2. Profilage du nouveau moteur (Single-pass unifié + direct AST inspection)...")
    pr_new = cProfile.Profile()
    pr_new.enable()
    t0_new = time.perf_counter()
    all_reports: List[new_engine.FileAuditReport] = []
    all_modules: Set[str] = set()
    graph_deps: Dict[str, Set[str]] = {}

    for fp in py_files:
        rel_p = os.path.relpath(fp, "src").replace("\\", "/").replace(".py", "")
        all_modules.add(rel_p)
        rep = new_engine.UnifiedAstQualityAuditor.audit_file(fp)
        all_reports.append(rep)
        graph_deps[rel_p] = rep.internal_imports

    # Analyse des cycles et du couplage directement depuis le graphe extrait en single-pass
    cycles: List[Tuple[str, str]] = []
    for m1 in graph_deps:
        for m2 in graph_deps[m1]:
            if m2 in graph_deps and m1 in graph_deps[m2] and m1 != m2 and (m2, m1) not in cycles:
                cycles.append((m1, m2))

    ca_counts: Dict[str, int] = {m: 0 for m in all_modules}
    ce_counts: Dict[str, int] = {m: 0 for m in all_modules}
    for src_mod, targets in graph_deps.items():
        ce_counts[src_mod] = len(targets)
        for tgt in targets:
            if tgt in ca_counts:
                ca_counts[tgt] += 1

    t1_new = time.perf_counter()
    pr_new.disable()
    stats_new = pstats.Stats(pr_new)
    duration_new = t1_new - t0_new

    # Résultats comparatifs
    speedup = duration_old / duration_new if duration_new > 0 else 1.0
    calls_reduction = (float(stats_old.total_calls - stats_new.total_calls) / float(stats_old.total_calls)) * 100.0

    print("-" * 70)
    print(f"ANCIEN MOTEUR  : {duration_old:.3f} s  |  Appels internes : {stats_old.total_calls:,}")
    print(f"NOUVEAU MOTEUR : {duration_new:.3f} s  |  Appels internes : {stats_new.total_calls:,}")
    print(f"ACCÉLÉRATION GLOBALE (Speedup) : {speedup:.2f}x plus rapide")
    print(f"RÉDUCTION DES APPELS INTERNES  : -{calls_reduction:.1f}% ({stats_old.total_calls - stats_new.total_calls:,} appels éliminés)")
    print("-" * 70)


if __name__ == "__main__":
    success = validate_parity()
    if success:
        benchmark_acceleration()
