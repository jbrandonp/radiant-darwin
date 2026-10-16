"""
Tests unitaires et d'intégration pour le Générateur de Rapport HTML Interactif et Badges SVG.
Vérifie la conformité vectorielle Shields.io, l'intégrité HTML5 autonome (sans CDN)
et la validité des visualisations SVG (CodeScene, Complexité Cognitive, Couplage).
"""

from __future__ import annotations
import os
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from typing import Dict, List, Set, Tuple

from scripts.html_report_generator import (
    ShieldsBadgeGenerator,
    CodeSceneQuadrantSvgGenerator,
    CognitiveDistributionSvgGenerator,
    ArchitectureCouplingSvgGenerator,
    HtmlAuditTableGenerator,
    HtmlAuditReportGenerator,
    GithubStepSummaryGenerator
)
from scripts.industrial_audit_engine import (
    FileAuditReport,
    FunctionQualityMetrics,
    QualityGateVerdict
)

AuditDataTuple = Tuple[List[FileAuditReport], List[FunctionQualityMetrics], Dict[str, Set[str]], Dict[str, Dict[str, float]], QualityGateVerdict]


@pytest.fixture
def dummy_audit_data() -> AuditDataTuple:
    """Jeu de données de test représentatif d'une suite d'audit."""
    fn1 = FunctionQualityMetrics(
        file_path="src/core/geometry.py",
        name="make_box",
        line_number=42,
        cognitive_complexity=4,
        cyclomatic_complexity=2,
        lines_of_code=15,
        is_fully_typed=True
    )
    fn2 = FunctionQualityMetrics(
        file_path="src/cam/toolpath.py",
        name="compute_pocket",
        line_number=88,
        cognitive_complexity=18,
        cyclomatic_complexity=8,
        lines_of_code=50,
        is_fully_typed=True
    )
    all_funcs = [fn1, fn2]

    rep1 = FileAuditReport(
        file_path="src/core/geometry.py",
        lines_of_code=250,
        cognitive_complexity=25,
        cyclomatic_complexity=10,
        maintainability_index=88.5,
        type_completeness_percent=100.0,
        security_violations=[],
        functions=[fn1],
        git_churn=12,
        hotspot_index=300,
        afferent_coupling=15,
        efferent_coupling=2,
        instability=0.12
    )
    rep2 = FileAuditReport(
        file_path="src/cam/toolpath.py",
        lines_of_code=400,
        cognitive_complexity=120,
        cyclomatic_complexity=22,
        maintainability_index=65.0,
        type_completeness_percent=100.0,
        security_violations=[],
        functions=[fn2],
        git_churn=15,
        hotspot_index=1800,
        afferent_coupling=4,
        efferent_coupling=6,
        instability=0.60
    )
    reports = [rep1, rep2]

    deps: Dict[str, Set[str]] = {
        "core/geometry": set(),
        "cam/toolpath": {"core/geometry"}
    }
    coupling: Dict[str, Dict[str, float]] = {
        "core/geometry": {"ca": 15.0, "ce": 2.0, "instability": 0.12},
        "cam/toolpath": {"ca": 4.0, "ce": 6.0, "instability": 0.60}
    }
    qg_verdict = QualityGateVerdict(
        passed=True,
        status_label="PASSED (GREEN - CONFORME INDUSTRIEL)",
        gate_details=[
            ("Strict Static Typing (100% sans Any ni object)", True, "100.0%"),
            ("SAST Security Vulnerabilities (0 violation)", True, "0 violation(s)"),
            ("Architecture Cycles (0 dépendance circulaire)", True, "0 cycle(s)"),
            ("Function Cognitive Complexity Ceiling (<= 25)", True, "0 fonction(s) > 25"),
            ("Test Statement Coverage (>= 80.0%)", True, "85.0%"),
            ("Mutation Testing Score (>= 80.0%)", True, "100.0%")
        ]
    )

    return reports, all_funcs, deps, coupling, qg_verdict


# ==============================================================================
# Tests pour ShieldsBadgeGenerator
# ==============================================================================

def test_shields_badge_text_width_estimation() -> None:
    """Vérifie l'estimation précise de largeur de texte pour différentes chaînes."""
    w_empty = ShieldsBadgeGenerator.estimate_text_width("")
    assert w_empty == 0.0

    w_short = ShieldsBadgeGenerator.estimate_text_width("tests")
    w_long = ShieldsBadgeGenerator.estimate_text_width("maintainability: 94.2/100")
    assert w_short > 0.0
    assert w_long > w_short


def test_shields_badge_svg_xml_validity() -> None:
    """Vérifie que le SVG généré pour un badge est du XML valide et conforme au format Shields.io."""
    svg_str = ShieldsBadgeGenerator.render_badge_svg(
        label="quality gate",
        value="passed",
        value_color="#34d058"
    )

    # Doit être parsable en XML sans erreur
    root = ET.fromstring(svg_str)
    assert root.tag.endswith("svg")
    assert root.attrib["height"] == "20"
    assert "quality gate: passed" in svg_str
    assert "#34d058" in svg_str
    assert "#555" in svg_str


def test_shields_badge_standard_set_generation(tmp_path: Path) -> None:
    """Vérifie la génération complète des 4 badges requis sur disque."""
    badges_dir = str(tmp_path / "badges")
    badges = ShieldsBadgeGenerator.generate_standard_badges(
        output_dir=badges_dir,
        quality_gate_passed=True,
        strict_typing_percent=100.0,
        maintainability_score=94.2,
        test_count=412
    )

    expected_files = ["quality-gate.svg", "strict-typing.svg", "maintainability.svg", "tests.svg"]
    for fname in expected_files:
        assert fname in badges
        fpath = os.path.join(badges_dir, fname)
        assert os.path.isfile(fpath)

        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        root = ET.fromstring(content)
        assert root.tag.endswith("svg")

    assert "passed" in badges["quality-gate.svg"]
    assert "100%" in badges["strict-typing.svg"]
    assert "94.2/100" in badges["maintainability.svg"]
    assert "412 passed" in badges["tests.svg"]


# ==============================================================================
# Tests pour les Visualisations SVG Interactives
# ==============================================================================

def test_codescene_quadrant_svg_generation(dummy_audit_data: AuditDataTuple) -> None:
    """Vérifie la structure et les éléments du quadrant CodeScene."""
    reports, _, _, _, _ = dummy_audit_data
    svg = CodeSceneQuadrantSvgGenerator.generate_svg(reports)

    # Vérification XML
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert "ZONE ROUGE : HOTSPOTS CRITIQUES" in svg
    assert "ZONE SAINE OPTIMALE" in svg
    assert "hotspot-bubble" in svg
    assert 'data-file="src/cam/toolpath.py"' in svg


def test_cognitive_distribution_svg_generation(dummy_audit_data: AuditDataTuple) -> None:
    """Vérifie le graphique de distribution de la complexité cognitive."""
    reports, all_funcs, _, _, _ = dummy_audit_data
    svg = CognitiveDistributionSvgGenerator.generate_svg(reports, all_funcs)

    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert "Triviale [0 - 5]" in svg
    assert "Critique [> 25]" in svg
    assert "tier-bar-group" in svg


def test_architecture_coupling_svg_generation(dummy_audit_data: AuditDataTuple) -> None:
    """Vérifie le graphe de couplage architectural en SVG."""
    _, _, deps, coupling, _ = dummy_audit_data
    svg = ArchitectureCouplingSvgGenerator.generate_svg(deps, coupling)

    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert "arch-node" in svg
    assert "SOCLE FONDAMENTAL NOYAU KERNEL" in svg
    assert "marker id=\"arch-arrow\"" in svg


# ==============================================================================
# Tests pour le Tableau Interactif et le Rapport HTML Global
# ==============================================================================

def test_html_audit_table_generation(dummy_audit_data: AuditDataTuple) -> None:
    """Vérifie les composants du tableau d'audit dynamique."""
    reports, _, _, _, _ = dummy_audit_data
    tbl_html = HtmlAuditTableGenerator.generate_table_html(reports)

    assert "fileTableSearch" in tbl_html
    assert "filter-pill" in tbl_html
    assert "auditedFilesTable" in tbl_html
    assert "geometry.py" in tbl_html
    assert "toolpath.py" in tbl_html
    assert "btnPrevPage" in tbl_html
    assert "btnNextPage" in tbl_html


def test_html_audit_report_end_to_end(dummy_audit_data: AuditDataTuple, tmp_path: Path) -> None:
    """Vérifie la génération complète de docs/audit_report.html sans dépendance externe bloquante."""
    reports, all_funcs, deps, coupling, qg_verdict = dummy_audit_data
    html_path = str(tmp_path / "docs" / "audit_report.html")
    badges_dir = str(tmp_path / "docs" / "badges")

    mutations = {
        "Assembly Solver": (True, "AOR"),
        "Ray Picking": (True, "ROR")
    }
    summary_metrics: Dict[str, float] = {
        "total_files": 2.0,
        "total_lines_of_code": 650.0,
        "total_cognitive_complexity": 145.0,
        "avg_cognitive_complexity_per_file": 72.5,
        "avg_maintainability_index": 76.7,
        "type_completeness_percent": 100.0,
        "security_violations": 0.0,
        "circular_dependencies": 0.0,
        "mutation_score_percent": 100.0,
        "critical_functions_over_25": 0.0
    }

    report_content = HtmlAuditReportGenerator.generate_all(
        reports=reports,
        all_functions=all_funcs,
        deps=deps,
        cycles=[],
        coupling=coupling,
        mutations=mutations,
        qg_verdict=qg_verdict,
        summary_metrics=summary_metrics,
        output_html_path=html_path,
        badges_dir=badges_dir
    )

    assert os.path.isfile(html_path)
    assert "<!DOCTYPE html>" in report_content
    assert "CAD Studio (Radiant-Darwin)" in report_content
    assert "PASSED (GREEN - CONFORME INDUSTRIEL)" in report_content

    # Vérification stricte : Zéro dépendance CDN externe bloquante
    assert "<script src=" not in report_content.lower()
    assert "<link rel=\"stylesheet\" href=\"http" not in report_content.lower()
    assert "cdn." not in report_content.lower()
    assert "fonts.googleapis.com" not in report_content.lower()


def test_github_step_summary_injection(dummy_audit_data: AuditDataTuple, tmp_path: Path) -> None:
    """Vérifie l'écriture et l'injection dans $GITHUB_STEP_SUMMARY."""
    reports, _, _, _, qg_verdict = dummy_audit_data
    summary_md_path = str(tmp_path / "docs" / "audit_summary.md")
    step_summary_file = str(tmp_path / "github_step_summary.md")

    mutations = {"Solver": (True, "AOR")}
    summary_metrics: Dict[str, float] = {
        "total_files": 2.0,
        "total_lines_of_code": 650.0,
        "total_cognitive_complexity": 145.0,
        "avg_cognitive_complexity_per_file": 72.5,
        "type_completeness_percent": 100.0,
        "security_violations": 0.0,
        "circular_dependencies": 0.0,
        "mutation_score_percent": 100.0
    }

    md = GithubStepSummaryGenerator.export(
        summary_metrics=summary_metrics,
        qg_verdict=qg_verdict,
        reports=reports,
        mutations=mutations,
        output_md_path=summary_md_path,
        github_step_summary_file=step_summary_file
    )

    assert os.path.isfile(summary_md_path)
    assert os.path.isfile(step_summary_file)

    with open(step_summary_file, "r", encoding="utf-8") as f:
        step_content = f.read()

    assert "# 🛡️ CAD Studio (Radiant-Darwin) — Industrial Quality Gate Report" in step_content
    assert "PASSED (GREEN - CONFORME INDUSTRIEL)" in step_content
    assert "100.0%" in step_content
