"""
Tests de Validation du Banc d'Audit Continu PropertyAndDifferentialAuditBench.
Garantit la conformité industrielle :
1. Exécution stricte de 1000 cas de tests aléatoires en moins de 2 secondes.
2. Taux de réussite de 100% sur les 4 piliers d'invariants géométriques et physiques.
3. Cadence élevée (> 500 cas/seconde) et latence moyenne microseconde.
4. Exportation conforme des rapports d'audit (JSON & Markdown).
"""

import os
from pathlib import Path
import json
import time
import pytest

from src.core.nexus_kernel.property_and_differential_bench import (
    PropertyAndDifferentialAuditBench,
    AuditBenchReport,
    SubBenchMetric
)


def test_property_and_differential_audit_bench_1000_cases_under_2_seconds(tmp_path: Path) -> None:
    """
    Exigence Maîtresse : Le banc d'audit continu PropertyAndDifferentialAuditBench
    doit être capable d'exécuter 1000 cas aléatoires en moins de 2 secondes (2000 ms).
    """
    bench = PropertyAndDifferentialAuditBench(random_seed=42)

    t_start = time.perf_counter()
    report: AuditBenchReport = bench.run_full_audit(total_cases=1000, target_max_duration_seconds=2.0)
    measured_duration_sec = time.perf_counter() - t_start

    # 1. Vérification des volumes et résultats de tests
    assert report.total_cases == 1000, f"Nombre de cas attendu 1000, obtenu {report.total_cases}"
    assert report.passed_cases == 1000, f"Cas réussis : {report.passed_cases}/1000. Échecs : {report.failed_cases}"
    assert report.failed_cases == 0, f"Présence de cas échoués : {report.failed_cases}"
    assert report.is_audit_passed, "Le rapport d'audit a échoué"

    # 2. Vérification du budget temporel formel (< 2.0 secondes)
    assert report.total_duration_ms < 2000.0, f"Dépassement du temps : {report.total_duration_ms:.2f} ms >= 2000 ms"
    assert measured_duration_sec < 2.0, f"Temps mesuré externe trop long : {measured_duration_sec:.3f} s >= 2.0 s"

    # 3. Vérification de la cadence (> 500 Hz)
    assert report.overall_throughput_hz > 500.0, f"Cadence trop faible : {report.overall_throughput_hz:.1f} Hz"

    # 4. Vérification de l'existence des 4 sous-bancs
    expected_subbenches = [
        "Euler_Poincare_Invariants",
        "Rigid_Isometry_Conservation",
        "FEA_Elastic_Strain_Energy_PSD",
        "Differential_CSG_vs_Quadrature"
    ]
    for sub_name in expected_subbenches:
        assert sub_name in report.sub_metrics, f"Sous-banc manquant : {sub_name}"
        sub_metric: SubBenchMetric = report.sub_metrics[sub_name]
        assert sub_metric.is_passed, f"Sous-banc échoué : {sub_name}"
        assert sub_metric.passed_cases == sub_metric.total_cases
        assert sub_metric.failed_cases == 0

    # 5. Export JSON
    json_path = os.path.join(tmp_path, "audit_bench_report.json")
    bench.export_audit_json(report, json_path)
    assert os.path.exists(json_path)

    with open(json_path, "r", encoding="utf-8") as f:
        loaded_data = json.load(f)
    assert loaded_data["total_cases"] == 1000
    assert loaded_data["is_audit_passed"] is True

    # 6. Génération Markdown
    md_content = bench.generate_markdown_report(report)
    assert "# 🛡️ Rapport d'Audit Continu Property & Differential Fuzzing Bench" in md_content
    assert "✅ VALIDÉ" in md_content
    assert "Euler_Poincare_Invariants" in md_content


def test_subbench_euler_poincare_isolated() -> None:
    """Vérifie le sous-banc Euler-Poincaré de manière isolée."""
    bench = PropertyAndDifferentialAuditBench(random_seed=123)
    metric = bench.run_euler_poincare_subbench(count=100)
    assert metric.is_passed
    assert metric.passed_cases == 100
    assert metric.duration_ms < 50.0  # Ultra-rapide (< 50 ms pour 100 cas)


def test_subbench_rigid_isometry_isolated() -> None:
    """Vérifie le sous-banc d'invariance rigide de manière isolée."""
    bench = PropertyAndDifferentialAuditBench(random_seed=456)
    metric = bench.run_rigid_isometry_subbench(count=100)
    assert metric.is_passed
    assert metric.passed_cases == 100
    assert metric.duration_ms < 500.0


def test_subbench_fea_strain_energy_isolated() -> None:
    """Vérifie le sous-banc FEA strain energy PSD de manière isolée."""
    bench = PropertyAndDifferentialAuditBench(random_seed=789)
    metric = bench.run_fea_strain_energy_subbench(count=100)
    assert metric.is_passed
    assert metric.passed_cases == 100
    assert metric.duration_ms < 500.0


def test_subbench_differential_csg_isolated() -> None:
    """Vérifie le sous-banc de fuzzing différentiel CSG de manière isolée."""
    bench = PropertyAndDifferentialAuditBench(random_seed=101112)
    metric = bench.run_differential_csg_subbench(count=100)
    assert metric.is_passed
    assert metric.passed_cases == 100
    assert metric.duration_ms < 500.0
