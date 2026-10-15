"""
Suite de tests unitaires et d'intégration formels pour l'Orchestrateur
du Quality Gate Hybride et la Matrice de Décision Adaptative.

Conforme aux standards ISO 25010, Clean Architecture et SonarQube Enterprise.
Typage statique strict : strictement zéro Any et zéro object.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Dict, List, Optional, Tuple, Union
import pytest

from scripts.quality_gate_orchestrator import (
    ArchitecturalClassifier,
    ArchitecturalLayer,
    DEFAULT_LAYER_THRESHOLDS,
    FormalDecisionEngine,
    GateStatus,
    HybridQualityGateReport,
    LayerAuditResult,
    LayerThresholds,
    QualityGateOrchestrator,
    VetoCriterion,
    VetoCriterionResult,
)


# ==============================================================================
# 1. Tests des Critères de Veto Absolus (Hard Gates)
# ==============================================================================

def test_veto_sast_triggered() -> None:
    """
    Vérifie qu'une seule violation SAST déclenche immédiatement un veto absolu.
    """
    vetoes = FormalDecisionEngine.evaluate_vetoes(
        total_sast_violations=1,
        circular_cycles_count=0,
        type_completeness_percent=100.0,
        sast_details=["test_file.py:10 - Appel interdit à exec()"]
    )

    sast_res: Optional[VetoCriterionResult] = next(
        (v for v in vetoes if v.criterion == VetoCriterion.ZERO_SAST_VULNERABILITIES), None
    )
    assert sast_res is not None
    assert sast_res.is_vetoed is True
    assert "1 violation(s)" in sast_res.actual_value

    cycles_res: Optional[VetoCriterionResult] = next(
        (v for v in vetoes if v.criterion == VetoCriterion.ZERO_CIRCULAR_DEPENDENCIES), None
    )
    assert cycles_res is not None
    assert cycles_res.is_vetoed is False


def test_veto_cycles_triggered() -> None:
    """
    Vérifie qu'un cycle d'interdépendance circulaire déclenche immédiatement un veto absolu.
    """
    vetoes = FormalDecisionEngine.evaluate_vetoes(
        total_sast_violations=0,
        circular_cycles_count=2,
        type_completeness_percent=100.0
    )

    cycles_res: Optional[VetoCriterionResult] = next(
        (v for v in vetoes if v.criterion == VetoCriterion.ZERO_CIRCULAR_DEPENDENCIES), None
    )
    assert cycles_res is not None
    assert cycles_res.is_vetoed is True
    assert "2 cycle(s)" in cycles_res.actual_value


def test_veto_typing_incompleteness_triggered() -> None:
    """
    Vérifie qu'une régression sous 100% de typage strict déclenche un veto absolu.
    """
    vetoes = FormalDecisionEngine.evaluate_vetoes(
        total_sast_violations=0,
        circular_cycles_count=0,
        type_completeness_percent=98.5
    )

    typing_res: Optional[VetoCriterionResult] = next(
        (v for v in vetoes if v.criterion == VetoCriterion.STRICT_STATIC_TYPING_100), None
    )
    assert typing_res is not None
    assert typing_res.is_vetoed is True
    assert "98.50%" in typing_res.actual_value


def test_veto_all_clean() -> None:
    """
    Vérifie que lorsque toutes les exigences absolues sont satisfaites, aucun veto n'est levé.
    """
    vetoes = FormalDecisionEngine.evaluate_vetoes(
        total_sast_violations=0,
        circular_cycles_count=0,
        type_completeness_percent=100.0
    )
    assert all(not v.is_vetoed for v in vetoes)


# ==============================================================================
# 2. Tests de la Fonction de Score Composite Continue S = sum(w_i * S_i) >= 65%
# ==============================================================================

def test_composite_score_mathematical_weights() -> None:
    """
    Vérifie que la somme des poids w_i est strictement égale à 1.0 (100%).
    """
    total_weights = (
        FormalDecisionEngine.WEIGHT_COVERAGE
        + FormalDecisionEngine.WEIGHT_PASS_RATE
        + FormalDecisionEngine.WEIGHT_MUTATION
        + FormalDecisionEngine.WEIGHT_COMPLEXITY
        + FormalDecisionEngine.WEIGHT_MAINTAINABILITY
        + FormalDecisionEngine.WEIGHT_ARCHITECTURE
    )
    assert abs(total_weights - 1.0) < 1e-9


def test_composite_score_nominal_pass() -> None:
    """
    Vérifie le calcul du score composite nominal au-dessus du seuil de 65.0%.
    """
    score, components = FormalDecisionEngine.calculate_composite_score(
        coverage_percent=85.0,
        test_pass_rate_percent=100.0,
        mutation_score_percent=90.0,
        complexity_compliance_percent=95.0,
        maintainability_index=80.0,
        architecture_compliance_percent=100.0
    )
    # 0.30*85 (25.5) + 0.20*100 (20.0) + 0.15*90 (13.5) + 0.15*95 (14.25) + 0.10*80 (8.0) + 0.10*100 (10.0)
    # Total attendu = 91.25
    expected = 25.5 + 20.0 + 13.5 + 14.25 + 8.0 + 10.0
    assert abs(score - expected) < 1e-4
    assert score >= 65.0
    assert len(components) == 6


def test_composite_score_insufficient_fails() -> None:
    """
    Vérifie qu'un score global inférieur à 65.0% est correctement rejeté.
    """
    score, _ = FormalDecisionEngine.calculate_composite_score(
        coverage_percent=40.0,
        test_pass_rate_percent=50.0,
        mutation_score_percent=30.0,
        complexity_compliance_percent=50.0,
        maintainability_index=40.0,
        architecture_compliance_percent=50.0
    )
    assert score < 65.0


# ==============================================================================
# 3. Tests de la Matrice de Seuils Adaptative par Couche Architecturale
# ==============================================================================

def test_cad_core_adaptive_thresholds() -> None:
    """
    Vérifie les exigences spécifiques du Noyau CAO & Géométrie :
    Complexité <= 18, Instabilité I <= 0.20, Couverture >= 90%.
    """
    core_th = DEFAULT_LAYER_THRESHOLDS[ArchitecturalLayer.CAD_CORE_GEOMETRY]
    assert core_th.max_function_complexity == 18
    assert core_th.max_instability == 0.20
    assert core_th.min_coverage_percent == 90.0
    assert core_th.mutation_exempted is False

    # Cas conforme : Instabilité I = 0.05 <= 0.20, Couverture = 92% >= 90%
    sample_res = LayerAuditResult(
        layer=ArchitecturalLayer.CAD_CORE_GEOMETRY,
        layer_name=core_th.layer_name,
        files_count=45,
        lines_of_code=10000,
        max_cognitive_complexity=16,
        avg_cognitive_complexity=12.0,
        compliant_functions_count=100,
        total_functions_count=100,
        complex_functions_violations=[],
        instability=0.05,
        afferent_coupling=120,
        efferent_coupling=6,
        coverage_percent=92.0,
        mutation_score_percent=95.0,
        mutation_exempted=False,
        sast_violations_count=0,
        sast_violations_details=[],
        type_completeness_percent=100.0,
        status=GateStatus.PASSED,
        status_reasons=[]
    )
    status, reasons = FormalDecisionEngine.evaluate_layer(sample_res, core_th)
    assert status == GateStatus.PASSED

    # Cas violation d'instabilité : I = 0.35 > 0.20
    bad_instability_res = LayerAuditResult(
        layer=ArchitecturalLayer.CAD_CORE_GEOMETRY,
        layer_name=core_th.layer_name,
        files_count=45,
        lines_of_code=10000,
        max_cognitive_complexity=16,
        avg_cognitive_complexity=12.0,
        compliant_functions_count=100,
        total_functions_count=100,
        complex_functions_violations=[],
        instability=0.35,
        afferent_coupling=20,
        efferent_coupling=11,
        coverage_percent=92.0,
        mutation_score_percent=95.0,
        mutation_exempted=False,
        sast_violations_count=0,
        sast_violations_details=[],
        type_completeness_percent=100.0,
        status=GateStatus.PASSED,
        status_reasons=[]
    )
    status_fail, reasons_fail = FormalDecisionEngine.evaluate_layer(bad_instability_res, core_th)
    assert status_fail == GateStatus.FAILED_LAYER_POLICY
    assert any("Instabilité" in r for r in reasons_fail)


def test_numerical_solvers_adaptive_thresholds() -> None:
    """
    Vérifie les exigences spécifiques des Solveurs & Calcul Numérique :
    Complexité <= 25, Mutation >= 90%, Couverture >= 85%.
    """
    solver_th = DEFAULT_LAYER_THRESHOLDS[ArchitecturalLayer.NUMERICAL_SOLVERS]
    assert solver_th.max_function_complexity == 25
    assert solver_th.min_mutation_score == 90.0
    assert solver_th.min_coverage_percent == 85.0
    assert solver_th.mutation_exempted is False

    # Mutation insuffisante (82% < 90%)
    res = LayerAuditResult(
        layer=ArchitecturalLayer.NUMERICAL_SOLVERS,
        layer_name=solver_th.layer_name,
        files_count=24,
        lines_of_code=5000,
        max_cognitive_complexity=24,
        avg_cognitive_complexity=15.0,
        compliant_functions_count=50,
        total_functions_count=50,
        complex_functions_violations=[],
        instability=0.60,
        afferent_coupling=10,
        efferent_coupling=15,
        coverage_percent=86.0,
        mutation_score_percent=82.0,
        mutation_exempted=False,
        sast_violations_count=0,
        sast_violations_details=[],
        type_completeness_percent=100.0,
        status=GateStatus.PASSED,
        status_reasons=[]
    )
    status_strict, reasons_strict = FormalDecisionEngine.evaluate_layer(res, solver_th, strict_mode=True)
    assert status_strict == GateStatus.FAILED_LAYER_POLICY
    assert any("Mutation" in r for r in reasons_strict)


def test_ui_viewport_adaptive_thresholds_and_mutation_exemption() -> None:
    """
    Vérifie les exigences de l'UI & Viewport :
    Complexité <= 15, Couverture >= 65%, et exemption totale de mutation testing.
    """
    ui_th = DEFAULT_LAYER_THRESHOLDS[ArchitecturalLayer.UI_VIEWPORT]
    assert ui_th.max_function_complexity == 15
    assert ui_th.min_coverage_percent == 65.0
    assert ui_th.mutation_exempted is True
    assert ui_th.min_mutation_score is None

    # Mutation à 0%, mais exempté : doit passer sans alerte de mutation
    res = LayerAuditResult(
        layer=ArchitecturalLayer.UI_VIEWPORT,
        layer_name=ui_th.layer_name,
        files_count=33,
        lines_of_code=7000,
        max_cognitive_complexity=14,
        avg_cognitive_complexity=9.0,
        compliant_functions_count=80,
        total_functions_count=80,
        complex_functions_violations=[],
        instability=0.95,
        afferent_coupling=3,
        efferent_coupling=55,
        coverage_percent=70.0,
        mutation_score_percent=0.0,
        mutation_exempted=True,
        sast_violations_count=0,
        sast_violations_details=[],
        type_completeness_percent=100.0,
        status=GateStatus.PASSED,
        status_reasons=[]
    )
    status, reasons = FormalDecisionEngine.evaluate_layer(res, ui_th, strict_mode=True)
    assert status == GateStatus.PASSED
    assert not any("Mutation" in r for r in reasons)


def test_ai_io_connectors_adaptive_thresholds() -> None:
    """
    Vérifie les exigences des Connecteurs IA & I/O :
    Complexité <= 12, Vigilance SAST maximale (0 tolérance), Typage 100%.
    """
    ai_th = DEFAULT_LAYER_THRESHOLDS[ArchitecturalLayer.AI_IO_CONNECTORS]
    assert ai_th.max_function_complexity == 12
    assert ai_th.max_sast_violations == 0
    assert ai_th.min_type_completeness == 100.0

    # Présence d'une violation SAST
    res = LayerAuditResult(
        layer=ArchitecturalLayer.AI_IO_CONNECTORS,
        layer_name=ai_th.layer_name,
        files_count=25,
        lines_of_code=6000,
        max_cognitive_complexity=11,
        avg_cognitive_complexity=8.0,
        compliant_functions_count=60,
        total_functions_count=60,
        complex_functions_violations=[],
        instability=0.80,
        afferent_coupling=15,
        efferent_coupling=60,
        coverage_percent=85.0,
        mutation_score_percent=100.0,
        mutation_exempted=False,
        sast_violations_count=1,
        sast_violations_details=["mcp_stdio.py:50 - Path Traversal"],
        type_completeness_percent=100.0,
        status=GateStatus.PASSED,
        status_reasons=[]
    )
    status, reasons = FormalDecisionEngine.evaluate_layer(res, ai_th)
    assert status == GateStatus.FAILED_LAYER_POLICY
    assert any("SAST" in r for r in reasons)


# ==============================================================================
# 4. Tests de Classification Déterministe des Fichiers
# ==============================================================================

def test_file_classification_layers() -> None:
    """
    Vérifie l'attribution déterministe des modules aux 4 couches architecturales.
    """
    assert ArchitecturalClassifier.classify("src/core/geometry.py") == ArchitecturalLayer.CAD_CORE_GEOMETRY
    assert ArchitecturalClassifier.classify("src/core/sketch.py") == ArchitecturalLayer.CAD_CORE_GEOMETRY
    assert ArchitecturalClassifier.classify("src/sheetmetal/sheet_metal.py") == ArchitecturalLayer.CAD_CORE_GEOMETRY

    assert ArchitecturalClassifier.classify("src/solver/constraints_2d.py") == ArchitecturalLayer.NUMERICAL_SOLVERS
    assert ArchitecturalClassifier.classify("src/fea/fea_engine.py") == ArchitecturalLayer.NUMERICAL_SOLVERS
    assert ArchitecturalClassifier.classify("src/cam/five_axis_cam.py") == ArchitecturalLayer.NUMERICAL_SOLVERS
    assert ArchitecturalClassifier.classify("src/specialized/robot_kinematics.py") == ArchitecturalLayer.NUMERICAL_SOLVERS
    assert ArchitecturalClassifier.classify("src/core/joint_solver.py") == ArchitecturalLayer.NUMERICAL_SOLVERS

    assert ArchitecturalClassifier.classify("src/ui/main_window.py") == ArchitecturalLayer.UI_VIEWPORT
    assert ArchitecturalClassifier.classify("src/viewport/gl_renderer.py") == ArchitecturalLayer.UI_VIEWPORT
    assert ArchitecturalClassifier.classify("src/drawing/techdraw_workbench.py") == ArchitecturalLayer.UI_VIEWPORT

    assert ArchitecturalClassifier.classify("src/ai/cad_ai_bridge.py") == ArchitecturalLayer.AI_IO_CONNECTORS
    assert ArchitecturalClassifier.classify("src/core/serializer.py") == ArchitecturalLayer.AI_IO_CONNECTORS
    assert ArchitecturalClassifier.classify("src/core/step_importer.py") == ArchitecturalLayer.AI_IO_CONNECTORS
    assert ArchitecturalClassifier.classify("src/cli.py") == ArchitecturalLayer.AI_IO_CONNECTORS


# ==============================================================================
# 5. Tests de l'Export JSON Déterministe et de la Sortie Console
# ==============================================================================

def test_json_export_and_schema_determinism() -> None:
    """
    Vérifie la conformité, le versioning et le déterminisme de l'export JSON pour la CI/CD.
    """
    orchestrator = QualityGateOrchestrator(src_dir="src")

    # Création d'un rapport synthétique
    report = orchestrator.run_hybrid_quality_gate(
        custom_coverage={
            ArchitecturalLayer.CAD_CORE_GEOMETRY: 92.0,
            ArchitecturalLayer.NUMERICAL_SOLVERS: 88.0,
            ArchitecturalLayer.UI_VIEWPORT: 70.0,
            ArchitecturalLayer.AI_IO_CONNECTORS: 85.0
        },
        custom_mutation=95.0,
        custom_pass_rate=100.0
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        json_path = os.path.join(tmp_dir, "test_verdict.json")
        json_str = orchestrator.export_json_report(report, json_path)

        assert os.path.exists(json_path)
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["schema_version"] == "2.0.0"
        assert "composite_score" in data
        assert "vetoes" in data
        assert "layers" in data
        assert "summary_metrics" in data
        assert len(data["layers"]) >= 4

        # Vérification du tri alphabétique déterministe des clés JSON
        keys = list(data.keys())
        assert keys == sorted(keys)


def test_console_output_formatting() -> None:
    """
    Vérifie la présence des 3 sections majeures dans la sortie console unifiée.
    """
    orchestrator = QualityGateOrchestrator(src_dir="src")
    report = orchestrator.run_hybrid_quality_gate()
    console_text = orchestrator.format_console_output(report)

    assert "CRITÈRES DE VETO ABSOLUS" in console_text or "CRIT" in console_text
    assert "SCORE COMPOSITE CONTINUE" in console_text or "SCORE COMPOSITE" in console_text
    assert "MATRICE DE DÉCISION ADAPTATIVE" in console_text or "MATRICE" in console_text
    assert "VERDICT FINAL CI/CD" in console_text


def test_exclude_patterns_filters_files() -> None:
    """
    Vérifie que le filtrage par motif d'exclusion retire effectivement les fichiers ciblés.
    """
    orch_all = QualityGateOrchestrator(src_dir="src")
    report_all = orch_all.run_hybrid_quality_gate()

    orch_filtered = QualityGateOrchestrator(src_dir="src", exclude_patterns=["mutation_engine.py"])
    report_filtered = orch_filtered.run_hybrid_quality_gate()

    assert report_filtered.total_files < report_all.total_files


def test_nosec_exemption_in_sast() -> None:
    """
    Vérifie qu'un appel annoté avec # nosec ou # audit-ok n'est pas compté comme violation SAST.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = os.path.join(tmp_dir, "safe_script.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("def run_sandbox() -> None:\n    exec('x = 1')  # nosec: Sandboxed execution\n")

        orch = QualityGateOrchestrator(src_dir=tmp_dir)
        report = orch.run_hybrid_quality_gate()
        assert report.summary_metrics["security_violations"] == 0.0

