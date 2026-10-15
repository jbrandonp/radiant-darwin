"""
Tests unitaires et d'intégration formels pour l'Analyseur Comportementale CodeScene SOTA 2026.
Valide mathématiquement et empiriquement les 4 piliers fondamentaux :
1. Churn Volumétrique réel via 'git log --numstat'.
2. Décroissance temporelle exponentielle par demi-vie (Half-Life Decay avec T_1/2 = 90 jours).
3. Détection du Couplage Temporel Masqué (Hidden Temporal Coupling J >= 0.35 sans import direct).
4. Entropie de Propriété de Shannon (Code Ownership) et diffusion de responsabilité.
"""

from __future__ import annotations

import math
import os
import pytest
from typing import Dict, List, Set, Tuple

from scripts.codescene_analyzer import (
    CodeSceneSOTAAnalyzer,
    BehavioralAnalysisReport,
    FileBehavioralMetrics,
    TemporalCouplingPair,
    CodeOwnershipMetrics,
    AuthorContribution,
)
from scripts.industrial_audit_engine import CodeSceneHotspotAnalyzer


# ==============================================================================
# PILIER 1 : CHURN VOLUMÉTRIQUE RÉEL VIA NUMSTAT
# ==============================================================================

def test_volumetric_churn_numstat_parsing():
    """Vérifie le parsing exact du Churn volumétrique (lignes ajoutées et supprimées)."""
    mock_log = (
        "COMMIT|hash001|1700000000|Alice|alice@example.com\n"
        "100\t20\tsrc/core/geometry.py\n"
        "50\t10\tsrc/core/assembly.py\n"
        "\n"
        "COMMIT|hash002|1700000100|Bob|bob@example.com\n"
        "30\t5\tsrc/core/geometry.py\n"
        "-\t-\tsrc/assets/model.bin\n"
    )

    commits = CodeSceneSOTAAnalyzer.parse_numstat_log(mock_log, src_dir="src")
    assert len(commits) == 2

    # Commit 1
    c1 = commits[0]
    assert c1.author_name == "Alice"
    assert len(c1.files) == 2
    assert c1.files[0].file_path == "src/core/geometry.py"
    assert c1.files[0].lines_added == 100
    assert c1.files[0].lines_deleted == 20

    # Commit 2
    c2 = commits[1]
    assert c2.author_name == "Bob"
    # Le fichier binaire avec '-' doit avoir 0 lignes ajoutées et 0 supprimées
    bin_file = [f for f in c2.files if f.file_path == "src/assets/model.bin"][0]
    assert bin_file.lines_added == 0
    assert bin_file.lines_deleted == 0


def test_git_path_rename_cleaning():
    """Vérifie la normalisation robuste des chemins Git contenant des renommages."""
    assert CodeSceneSOTAAnalyzer.clean_git_path("src/{old => new}/file.py") == "src/new/file.py"
    assert CodeSceneSOTAAnalyzer.clean_git_path("old_module.py => new_module.py") == "new_module.py"
    assert CodeSceneSOTAAnalyzer.clean_git_path("src\\core\\geometry.py") == "src/core/geometry.py"


# ==============================================================================
# PILIER 2 : DÉCROISSANCE TEMPORELLE EXPONENTIELLE PAR DEMI-VIE (90 JOURS)
# ==============================================================================

def test_half_life_decay_exact_values():
    """
    Vérifie les valeurs caractéristiques de la décroissance exponentielle :
    w(t) = 2^(-delta_t / 90.0)
    """
    t_ref = 10000000.0
    day = 86400.0

    # delta_t = 0 jour -> w = 1.0 (100%)
    w_0 = CodeSceneSOTAAnalyzer.calculate_half_life_weight(t_ref, t_ref, half_life_days=90.0)
    assert pytest.approx(w_0, 1e-6) == 1.0

    # delta_t = 90 jours -> w = 0.5 (50%)
    t_90 = t_ref - (90.0 * day)
    w_90 = CodeSceneSOTAAnalyzer.calculate_half_life_weight(t_90, t_ref, half_life_days=90.0)
    assert pytest.approx(w_90, 1e-6) == 0.5

    # delta_t = 180 jours -> w = 0.25 (25%)
    t_180 = t_ref - (180.0 * day)
    w_180 = CodeSceneSOTAAnalyzer.calculate_half_life_weight(t_180, t_ref, half_life_days=90.0)
    assert pytest.approx(w_180, 1e-6) == 0.25

    # delta_t = 270 jours -> w = 0.125 (12.5%)
    t_270 = t_ref - (270.0 * day)
    w_270 = CodeSceneSOTAAnalyzer.calculate_half_life_weight(t_270, t_ref, half_life_days=90.0)
    assert pytest.approx(w_270, 1e-6) == 0.125

    # Date future (horloge décalée) -> bridé à 1.0
    t_future = t_ref + (10.0 * day)
    w_future = CodeSceneSOTAAnalyzer.calculate_half_life_weight(t_future, t_ref, half_life_days=90.0)
    assert w_future == 1.0


def test_decayed_volumetric_churn_accumulation():
    """Vérifie que le Churn accumulé applique la pondération par demi-vie aux modifications."""
    day = 86400.0
    t_ref = 1700000000.0

    # Deux commits sur le même fichier :
    # Commit 1 : aujourd'hui (t_ref) -> 100 lignes modifiées (w = 1.0 -> 100.0)
    # Commit 2 : il y a 90 jours      -> 200 lignes modifiées (w = 0.5 -> 100.0)
    # Total attendu : Brut = 300 lignes, Pondéré (Decayed) = 200.0 lignes
    mock_log = (
        f"COMMIT|c1|{int(t_ref)}|Alice|alice@example.com\n"
        "80\t20\tsrc/core/geometry.py\n"
        "\n"
        f"COMMIT|c2|{int(t_ref - 90 * day)}|Alice|alice@example.com\n"
        "150\t50\tsrc/core/geometry.py\n"
    )

    report = CodeSceneSOTAAnalyzer.analyze_from_log_string(
        raw_log=mock_log,
        src_dir="src",
        reference_timestamp=t_ref,
        half_life_days=90.0
    )

    geo_metrics = report.file_metrics["src/core/geometry.py"]
    assert geo_metrics.raw_volumetric_churn == 300
    assert pytest.approx(geo_metrics.decayed_volumetric_churn, rel=1e-3) == 200.0
    assert geo_metrics.commit_count == 2
    assert pytest.approx(geo_metrics.decayed_commits, rel=1e-3) == 1.5


# ==============================================================================
# PILIER 3 : COUPLAGE TEMPOREL MASQUÉ VIA JACCARD (J >= 0.35 SANS IMPORT)
# ==============================================================================

def test_jaccard_similarity_calculation():
    """
    Vérifie la formule de Jaccard :
    J(A, B) = |A inter B| / |A union B|
    """
    t_ref = 1700000000.0

    # Fichier A modifié dans : c1, c2, c3 (3 commits)
    # Fichier B modifié dans : c1, c2, c4 (3 commits)
    # Commits communs (inter) : c1, c2 (2 commits)
    # Commits totaux (union)  : c1, c2, c3, c4 (4 commits)
    # J = 2 / 4 = 0.50 >= 0.35
    mock_log = (
        f"COMMIT|c1|{int(t_ref)}|Alice|alice@example.com\n"
        "10\t5\tsrc/module_a.py\n"
        "20\t2\tsrc/module_b.py\n"
        "\n"
        f"COMMIT|c2|{int(t_ref)}|Alice|alice@example.com\n"
        "10\t5\tsrc/module_a.py\n"
        "20\t2\tsrc/module_b.py\n"
        "\n"
        f"COMMIT|c3|{int(t_ref)}|Alice|alice@example.com\n"
        "10\t5\tsrc/module_a.py\n"
        "\n"
        f"COMMIT|c4|{int(t_ref)}|Alice|alice@example.com\n"
        "20\t2\tsrc/module_b.py\n"
    )

    report = CodeSceneSOTAAnalyzer.analyze_from_log_string(
        raw_log=mock_log,
        src_dir="src",
        jaccard_threshold=0.35,
        min_shared_commits=2
    )

    assert len(report.all_couplings) == 1
    pair = report.all_couplings[0]
    assert pair.shared_commits == 2
    assert pair.commits_a == 3
    assert pair.commits_b == 3
    assert pytest.approx(pair.jaccard_similarity, 1e-4) == 0.50
    # Comme module_a et module_b n'ont pas d'imports directs réels sur disque, is_hidden doit être True
    assert pair.is_hidden is True
    assert pair in report.hidden_couplings


def test_hidden_temporal_coupling_filter_low_jaccard():
    """Vérifie que les paires ayant un Jaccard < 0.35 sont exclues."""
    t_ref = 1700000000.0
    # Fichier A dans 10 commits, Fichier B dans 10 commits, 2 commits en commun
    # J = 2 / (10 + 10 - 2) = 2 / 18 = 0.111 < 0.35 -> Exclu
    mock_lines: List[str] = []
    # 2 commits partagés
    for idx in range(1, 3):
        mock_lines.append(f"COMMIT|c{idx}|{int(t_ref)}|Alice|a@test.com\n1\t1\tsrc/a.py\n1\t1\tsrc/b.py\n")
    # 8 commits pour A seul
    for idx in range(3, 11):
        mock_lines.append(f"COMMIT|c{idx}|{int(t_ref)}|Alice|a@test.com\n1\t1\tsrc/a.py\n")
    # 8 commits pour B seul
    for idx in range(11, 19):
        mock_lines.append(f"COMMIT|c{idx}|{int(t_ref)}|Alice|a@test.com\n1\t1\tsrc/b.py\n")

    report = CodeSceneSOTAAnalyzer.analyze_from_log_string(
        raw_log="\n".join(mock_lines),
        src_dir="src",
        jaccard_threshold=0.35,
        min_shared_commits=2
    )
    assert len(report.all_couplings) == 0
    assert len(report.hidden_couplings) == 0


# ==============================================================================
# PILIER 4 : ENTROPIE DE PROPRIÉTÉ DE SHANNON (CODE OWNERSHIP)
# ==============================================================================

def test_shannon_entropy_single_author():
    """Un auteur unique (100% ownership) doit produire une entropie nulle (H = 0.00 bits)."""
    contributions = {"Brandon": 500.0}
    h, max_h, norm_h, owner, share = CodeSceneSOTAAnalyzer.calculate_shannon_entropy(contributions)

    assert h == 0.0
    assert norm_h == 0.0
    assert owner == "Brandon"
    assert share == 1.0


def test_shannon_entropy_two_equal_authors():
    """Deux auteurs à 50%/50% doivent produire exactement H = 1.00 bit et norm_h = 1.00."""
    contributions = {"Alice": 250.0, "Bob": 250.0}
    h, max_h, norm_h, owner, share = CodeSceneSOTAAnalyzer.calculate_shannon_entropy(contributions)

    assert pytest.approx(h, 1e-5) == 1.0
    assert pytest.approx(max_h, 1e-5) == 1.0
    assert pytest.approx(norm_h, 1e-5) == 1.0
    assert pytest.approx(share, 1e-5) == 0.5


def test_shannon_entropy_four_equal_authors():
    """Quatre auteurs à parts égales doivent produire H = 2.00 bits (log2(4))."""
    contributions = {"A": 100.0, "B": 100.0, "C": 100.0, "D": 100.0}
    h, max_h, norm_h, owner, share = CodeSceneSOTAAnalyzer.calculate_shannon_entropy(contributions)

    assert pytest.approx(h, 1e-5) == 2.0
    assert pytest.approx(max_h, 1e-5) == 2.0
    assert pytest.approx(norm_h, 1e-5) == 1.0
    assert pytest.approx(share, 1e-5) == 0.25


def test_shannon_entropy_skewed_distribution():
    """Vérifie le calcul avec distribution asymétrique (ex. 90% Alice, 10% Bob)."""
    contributions = {"Alice": 900.0, "Bob": 100.0}
    h, max_h, norm_h, owner, share = CodeSceneSOTAAnalyzer.calculate_shannon_entropy(contributions)

    # H = - (0.9 * log2(0.9) + 0.1 * log2(0.1))
    # 0.9 * (-0.152003) + 0.1 * (-3.321928) = -0.13680 - 0.33219 = -0.46899 -> H = 0.46899 bits
    expected_h = -(0.9 * math.log2(0.9) + 0.1 * math.log2(0.1))
    assert pytest.approx(h, 1e-4) == expected_h
    assert owner == "Alice"
    assert pytest.approx(share, 1e-4) == 0.9
    assert pytest.approx(norm_h, 1e-4) == expected_h / 1.0


def test_hotspot_defect_risk_composite():
    """Vérifie le calcul du Hotspot Index et du risque composite avec entropie."""
    t_ref = 1700000000.0
    mock_log = (
        f"COMMIT|c1|{int(t_ref)}|Alice|alice@example.com\n"
        "100\t0\tsrc/core/complex.py\n"
        "\n"
        f"COMMIT|c2|{int(t_ref)}|Bob|bob@example.com\n"
        "100\t0\tsrc/core/complex.py\n"
    )

    cog_map = {"src/core/complex.py": 50}
    report = CodeSceneSOTAAnalyzer.analyze_from_log_string(
        raw_log=mock_log,
        src_dir="src",
        cognitive_complexities=cog_map,
        reference_timestamp=t_ref
    )

    fm = report.file_metrics["src/core/complex.py"]
    # Churn = 200, Cog = 50 -> HotspotIndex = 10000
    assert fm.raw_volumetric_churn == 200
    assert pytest.approx(fm.hotspot_index, 1e-3) == 10000.0
    # Deux auteurs égaux -> norm_h = 1.0 -> RiskIndex = 10000 * (1.0 + 1.0) = 20000
    assert pytest.approx(fm.hotspot_defect_risk, 1e-3) == 20000.0
    assert fm.ownership is not None
    assert fm.ownership.is_diffused is True


# ==============================================================================
# INTÉGRATION AVEC LE DÉPÔT GIT RÉEL DU PROJET
# ==============================================================================

def test_live_repository_codescene_analysis():
    """Vérifie l'exécution réelle sur le dépôt Git du projet sans régression."""
    report = CodeSceneSOTAAnalyzer.analyze_git_repository(src_dir="src", repo_dir=".")

    assert report.total_commits > 0
    assert report.total_files_analyzed > 0
    assert len(report.file_metrics) > 0
    assert len(report.top_hotspots) > 0

    # Vérification de l'interface de compatibilité CodeSceneHotspotAnalyzer
    churn_dict = CodeSceneHotspotAnalyzer.get_git_churn("src")
    assert isinstance(churn_dict, dict)
    assert len(churn_dict) > 0

    # Au moins un fichier doit avoir un churn volumétrique significatif
    max_churn = max(churn_dict.values())
    assert max_churn > 50

    # Vérification que des couplages masqués sont détectés
    assert len(report.hidden_couplings) > 0
    for c in report.hidden_couplings:
        assert c.jaccard_similarity >= 0.35
        assert c.has_direct_import is False
