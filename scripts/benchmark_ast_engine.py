"""
Banc de mesure et benchmark comparatif d'accélération :
Ancien Moteur Multi-Pass (ast.walk + SonarVisitor récursif + ast.unparse)
vs
Nouveau Moteur Single-Pass Unifié (UnifiedIndustrialAstVisitor).
Typage strict : zéro Any, zéro object.
"""

from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.abspath("."))

import ast
import time
import cProfile
import pstats
from typing import Dict, List, Set, Tuple

import scripts.unified_ast_engine as uae


# Implémentation isolée de l'ancien moteur pour une comparaison déterministe rigoureuse
class LegacySonarCognitiveVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.complexity: int = 0
        self.nesting_level: int = 0

    def visit_If(self, node: ast.If) -> None:
        self.complexity += (1 + self.nesting_level)
        self.nesting_level += 1
        self.generic_visit(node)
        self.nesting_level -= 1

    def visit_For(self, node: ast.For) -> None:
        self.complexity += (1 + self.nesting_level)
        self.nesting_level += 1
        self.generic_visit(node)
        self.nesting_level -= 1

    def visit_While(self, node: ast.While) -> None:
        self.complexity += (1 + self.nesting_level)
        self.nesting_level += 1
        self.generic_visit(node)
        self.nesting_level -= 1

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.complexity += (1 + self.nesting_level)
        self.nesting_level += 1
        self.generic_visit(node)
        self.nesting_level -= 1

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.complexity += max(1, len(node.values) - 1)
        self.generic_visit(node)


def legacy_audit_file(filepath: str) -> Tuple[int, int, int, List[str]]:
    """Ancienne logique d'audit multi-pass avec ast.walk et ast.unparse()."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        code = f.read()

    tree = ast.parse(code, filename=filepath)

    # Passe 1 : Complexité cognitive globale
    cog_visitor = LegacySonarCognitiveVisitor()
    cog_visitor.visit(tree)
    total_cognitive = cog_visitor.complexity

    # Passe 2 : ast.walk global + fn_cog récursif + ast.walk par fonction + ast.unparse
    total_mccabe = 0
    fn_count = 0
    dependencies: List[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src."):
            dependencies.append(node.module[4:].replace(".", "/"))

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_count += 1
            fn_cog = LegacySonarCognitiveVisitor()
            for child in node.body:
                fn_cog.visit(child)

            mccabe = 1
            for sub in ast.walk(node):
                if isinstance(sub, (ast.If, ast.For, ast.While, ast.ExceptHandler)):
                    mccabe += 1
                elif isinstance(sub, ast.BoolOp):
                    mccabe += len(sub.values) - 1
            total_mccabe += mccabe

            # ast.unparse sur les annotations
            for arg in node.args.args:
                if arg.annotation is not None:
                    _ = ast.unparse(arg.annotation)
            if node.returns is not None:
                _ = ast.unparse(node.returns)

    return total_cognitive, total_mccabe, fn_count, dependencies


def single_pass_audit_file(filepath: str) -> Tuple[int, int, int, List[str]]:
    """Nouvelle logique d'audit single-pass via UnifiedIndustrialAstVisitor."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        code = f.read()

    tree = ast.parse(code, filename=filepath)
    visitor = uae.UnifiedIndustrialAstVisitor(filepath)
    visitor.visit(tree)

    total_mccabe = sum(fn.cyclomatic_complexity for fn in visitor.completed_functions)
    return (
        visitor.file_cognitive_complexity,
        total_mccabe,
        len(visitor.completed_functions),
        visitor.dependencies
    )


def run_benchmark() -> None:
    """
    Exécute le protocole de benchmark rigoureux sur un échantillon représentatif de fichiers.
    """
    # Échantillon représentatif de fichiers couvrant chaque sous-domaine de src/
    sample_files: List[str] = [
        "src/core/document.py",
        "src/core/sketch.py",
        "src/core/geometry.py",
        "src/core/operations_advanced.py",
        "src/core/serializer.py",
        "src/core/step_importer.py",
        "src/solver/constraints_2d.py",
        "src/ui/main_window.py",
        "src/viewport/gl_renderer.py",
        "src/fea/fea_solver.py",
        "src/cam/five_axis_cam.py",
        "src/drawing/drawing_generator.py"
    ]

    # Vérification de l'existence des fichiers
    valid_sample: List[str] = [f for f in sample_files if os.path.exists(f)]
    print("=" * 80)
    print("BENCHMARK COMPARATIF : ANCIEN MOTEUR MULTI-PASS vs UNIFIED INDUSTRIAL AST VISITOR")
    print("=" * 80)
    print(f"Échantillon de test : {len(valid_sample)} fichiers représentatifs critiques de src/\n")

    # 1. Vérification de la parité stricte sur l'échantillon
    print("1. VÉRIFICATION DE LA PARITÉ DES RÉSULTATS...")
    for f in valid_sample:
        c1, m1, n1, d1 = legacy_audit_file(f)
        c2, m2, n2, d2 = single_pass_audit_file(f)
        assert c1 == c2, f"Échec Cognitive sur {f}: {c1} != {c2}"
        assert m1 == m2, f"Échec McCabe sur {f}: {m1} != {m2}"
        assert n1 == n2, f"Échec Nombre fonctions sur {f}: {n1} != {n2}"
        assert set(d1) == set(d2), f"Échec Dépendances sur {f}"
        print(f"  [PARITÉ OK] {f:38} | Cog={c1:3d} | McCabe={m1:3d} | Fonctions={n1:2d}")
    print(">>> PARITÉ 100% CONFIRMÉE SUR L'ÉCHANTILLON <<<\n")

    # 2. Mesure du temps d'exécution (10 itérations)
    iterations: int = 10
    print(f"2. MESURE DU TEMPS D'EXÉCUTION ({iterations} ITÉRATIONS EN BOUCLE)...")

    # Ancien moteur
    t0 = time.perf_counter()
    for _ in range(iterations):
        for f in valid_sample:
            _ = legacy_audit_file(f)
    t1 = time.perf_counter()
    duration_legacy = (t1 - t0)

    # Nouveau moteur
    t0 = time.perf_counter()
    for _ in range(iterations):
        for f in valid_sample:
            _ = single_pass_audit_file(f)
    t1 = time.perf_counter()
    duration_single_pass = (t1 - t0)

    speedup = duration_legacy / duration_single_pass if duration_single_pass > 0 else 1.0

    print(f"  - Ancien Moteur Multi-Pass : {duration_legacy:.4f} s (Moyenne : {duration_legacy / iterations * 1000.0:.2f} ms)")
    print(f"  - Unified Single-Pass      : {duration_single_pass:.4f} s (Moyenne : {duration_single_pass / iterations * 1000.0:.2f} ms)")
    print(f"  >>> FACTEUR D'ACCÉLÉRATION (SPEEDUP) : {speedup:.2f}x PLUS RAPIDE <<<\n")

    # 3. Mesure du volume d'appels internes avec cProfile
    print("3. MESURE DES APPELS INTERNES VIA CPROFILE (1 ITÉRATION)...")
    pr_old = cProfile.Profile()
    pr_old.enable()
    for f in valid_sample:
        _ = legacy_audit_file(f)
    pr_old.disable()
    stats_old = pstats.Stats(pr_old)

    pr_new = cProfile.Profile()
    pr_new.enable()
    for f in valid_sample:
        _ = single_pass_audit_file(f)
    pr_new.disable()
    stats_new = pstats.Stats(pr_new)

    calls_old = stats_old.total_calls
    calls_new = stats_new.total_calls
    calls_eliminated = calls_old - calls_new
    calls_pct = (float(calls_eliminated) / float(calls_old)) * 100.0

    print(f"  - Appels internes Ancien Moteur : {calls_old:,}")
    print(f"  - Appels internes Unified Visitor: {calls_new:,}")
    print(f"  - Appels éliminés               : {calls_eliminated:,} appels ({calls_pct:.1f}% d'appels supprimés)")
    print("=" * 80)


if __name__ == "__main__":
    run_benchmark()
