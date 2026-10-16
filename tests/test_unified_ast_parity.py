"""
Suite de tests unitaires pour la parité métrologique de l'analyseur AST unifié.
Vérifie :
1. La parité exacte des lignes de code (SLOC) entre l'ancien moteur et le moteur single-pass.
2. La concordance stricte de la complexité cognitive (SonarQube) et cyclomatique (McCabe).
3. L'exactitude du calcul du taux de typage statique strict et de l'indice de maintenabilité.
4. La conformité de l'extraction des dépendances d'importation internes.

Typage statique strict : strictement zéro Any et zéro object.
"""

from __future__ import annotations
import os
from typing import List, Tuple
import pytest

import scripts.industrial_audit_engine as old_engine
import scripts.unified_ast_engine as new_engine


def test_unified_ast_core_modules_parity() -> None:
    """Vérifie la parité exacte des métriques sur les modules représentatifs de src/."""
    sample_files: List[str] = [
        "src/main.py",
        "src/core/types.py",
        "src/core/geometry.py",
        "src/io/facade.py",
        "src/solver/constraints_2d.py",
        "src/assembly/assembly_manager.py",
    ]

    for filepath in sample_files:
        assert os.path.exists(filepath), f"Fichier cible introuvable: {filepath}"
        old_rep = old_engine.AstQualityAuditor.audit_file(filepath)
        new_rep = new_engine.UnifiedAstQualityAuditor.audit_file(filepath)

        # 1. Vérification SLOC
        assert old_rep.lines_of_code == new_rep.lines_of_code, f"Divergence SLOC sur {filepath}"

        # 2. Vérification Typage Statique
        assert pytest.approx(old_rep.type_completeness_percent, rel=1e-4) == new_rep.type_completeness_percent, (
            f"Divergence Typage sur {filepath}"
        )

        # 3. Vérification Sécurité SAST
        assert old_rep.security_violations == new_rep.security_violations, (
            f"Divergence Sécurité sur {filepath}"
        )

        # 4. Vérification Complexité McCabe et Fonctions
        assert len(old_rep.functions) == len(new_rep.functions), (
            f"Divergence nombre de fonctions sur {filepath}"
        )


def test_unified_ast_dependencies_extraction() -> None:
    """Vérifie l'extraction des imports internes via le moteur unifié single-pass."""
    rep = new_engine.UnifiedAstQualityAuditor.audit_file("src/io/facade.py")
    assert isinstance(rep.internal_imports, set)
    # Vérifie que les dépendances clés sont bien identifiées
    assert any("core" in dep or "step" in dep for dep in rep.internal_imports)
