"""
Tests unitaires de performance et de validation fonctionnelle
pour le gestionnaire de cache incrémental SHA-256 et l'analyseur parallèle.
Garantit l'intégrité déterministe, l'invalidation automatique et le typage strict.
"""

from __future__ import annotations
import os
import tempfile
from typing import Dict, List, Set, Tuple
import pytest

from scripts.industrial_audit_engine import (
    AuditCacheManager,
    AstQualityAuditor,
    FileAuditReport,
    ArchitectureDependencyAnalyzer,
)


def test_sha256_computation_and_consistency() -> None:
    """Vérifie le calcul déterministe et reproductible du hash SHA-256."""
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        f.write("def sample_function() -> int:\n    return 42\n")
        temp_path = f.name

    try:
        hash_1: str = AuditCacheManager.compute_sha256(temp_path)
        hash_2: str = AuditCacheManager.compute_sha256(temp_path)
        assert len(hash_1) == 64
        assert hash_1 == hash_2
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_cache_manager_put_get_and_invalidation() -> None:
    """Vérifie le stockage, la restitution et l'invalidation lors d'une altération de contenu."""
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_manager = AuditCacheManager(cache_dir=temp_dir)
        sample_file = os.path.join(temp_dir, "test_file.py")

        with open(sample_file, "w", encoding="utf-8") as f:
            f.write("def hello() -> str:\n    return 'world'\n")

        sha_initial: str = AuditCacheManager.compute_sha256(sample_file)
        report: FileAuditReport = AstQualityAuditor.audit_file(sample_file, sha256_hash=sha_initial)

        # Enregistrement dans le cache
        cache_manager.put_report(sample_file, report)
        cache_manager.save_cache()

        # Rechargement et vérification
        cache_manager_reloaded = AuditCacheManager(cache_dir=temp_dir)
        retrieved = cache_manager_reloaded.get_cached_report(sample_file, sha_initial)
        assert retrieved is not None
        assert retrieved.sha256 == sha_initial
        assert retrieved.lines_of_code == report.lines_of_code

        # Modification du fichier -> invalidation automatique
        with open(sample_file, "a", encoding="utf-8") as f:
            f.write("# modification supplémentaire\n")

        sha_modified: str = AuditCacheManager.compute_sha256(sample_file)
        assert sha_modified != sha_initial
        invalidated = cache_manager_reloaded.get_cached_report(sample_file, sha_modified)
        assert invalidated is None


def test_architecture_reconstruction_from_cached_reports() -> None:
    """Vérifie que la reconstruction du graphe orienté s'effectue fidèlement en mémoire."""
    rep_a = FileAuditReport(
        file_path="src/module_a.py",
        lines_of_code=20,
        cognitive_complexity=2,
        cyclomatic_complexity=2,
        maintainability_index=85.0,
        type_completeness_percent=100.0,
        security_violations=[],
        dependencies=["module_b"],
        sha256="dummy_sha_a",
        total_classes=1,
        abstract_classes=0,
        abstractness=0.0
    )
    rep_b = FileAuditReport(
        file_path="src/module_b.py",
        lines_of_code=15,
        cognitive_complexity=1,
        cyclomatic_complexity=1,
        maintainability_index=90.0,
        type_completeness_percent=100.0,
        security_violations=[],
        dependencies=[],
        sha256="dummy_sha_b",
        total_classes=1,
        abstract_classes=1,
        abstractness=1.0
    )

    reports: List[FileAuditReport] = [rep_a, rep_b]
    deps, cycles, coupling = ArchitectureDependencyAnalyzer.analyze_from_reports(reports, src_dir="src")

    assert "module_a" in deps
    assert "module_b" in deps["module_a"]
    assert len(cycles) == 0
    assert coupling["module_a"]["ce"] == 1
    assert coupling["module_b"]["ca"] == 1
