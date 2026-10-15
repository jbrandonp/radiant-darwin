"""
Tests unitaires formels pour le Composite Maintainability Index (CMI) ISO/IEC 25010:2023.
Valide :
1. L'indice composite à 5 piliers : Analysabilité (25%), Modularité (20%), Testabilité (25%),
   Sécurité de Typage (15%), et Robustesse (15%).
2. Le découplage strict du terme cyclomatique de McCabe v(G) dans l'équation Microsoft
   sans injection de la complexité cognitive.
3. La fonction de transfert formelle continue T(x) entre l'échelle Microsoft Visual Studio
   (seuil vert >= 20.0) et l'indice standard normalisé ISO 25010 [0, 100].
4. La transparence métrologique et le calcul double (Microsoft VS & ISO CMI).
"""

from __future__ import annotations
import math
import pytest
from typing import Dict, Any

from scripts.industrial_audit_engine import (
    CompositeMaintainabilityCalculator,
    FileAuditReport,
    FunctionQualityMetrics,
    AstQualityAuditor
)


def test_cmi_pillars_weights_and_normalization() -> None:
    """Vérifie que la somme des 5 piliers est rigoureusement égale à 1.0 (100%)."""
    calc = CompositeMaintainabilityCalculator
    w_sum = (
        calc.WEIGHT_ANALYZABILITY +
        calc.WEIGHT_MODULARITY +
        calc.WEIGHT_TESTABILITY +
        calc.WEIGHT_TYPE_SAFETY +
        calc.WEIGHT_ROBUSTNESS
    )
    assert pytest.approx(w_sum, abs=1e-9) == 1.00
    assert calc.WEIGHT_ANALYZABILITY == 0.25
    assert calc.WEIGHT_MODULARITY == 0.20
    assert calc.WEIGHT_TESTABILITY == 0.25
    assert calc.WEIGHT_TYPE_SAFETY == 0.15
    assert calc.WEIGHT_ROBUSTNESS == 0.15


def test_cmi_pillars_marginal_sensitivity() -> None:
    """Vérifie l'impact marginal exact de chaque pilier sur le score global CMI."""
    calc = CompositeMaintainabilityCalculator

    # Référence 100% sur tous les piliers
    base_score, _ = calc.calculate_cmi_pillars(100.0, 100.0, 100.0, 100.0, 100.0)
    assert base_score == 100.0

    # Chute de 10 points sur l'Analysabilité (poids 25%) -> Chute de 2.5 points
    score_ana, _ = calc.calculate_cmi_pillars(90.0, 100.0, 100.0, 100.0, 100.0)
    assert pytest.approx(base_score - score_ana, abs=1e-4) == 2.50

    # Chute de 10 points sur la Modularité (poids 20%) -> Chute de 2.0 points
    score_mod, _ = calc.calculate_cmi_pillars(100.0, 90.0, 100.0, 100.0, 100.0)
    assert pytest.approx(base_score - score_mod, abs=1e-4) == 2.00

    # Chute de 10 points sur la Testabilité (poids 25%) -> Chute de 2.5 points
    score_test, _ = calc.calculate_cmi_pillars(100.0, 100.0, 90.0, 100.0, 100.0)
    assert pytest.approx(base_score - score_test, abs=1e-4) == 2.50

    # Chute de 10 points sur la Sécurité de Typage (poids 15%) -> Chute de 1.5 points
    score_type, _ = calc.calculate_cmi_pillars(100.0, 100.0, 100.0, 90.0, 100.0)
    assert pytest.approx(base_score - score_type, abs=1e-4) == 1.50

    # Chute de 10 points sur la Robustesse (poids 15%) -> Chute de 1.5 points
    score_rob, _ = calc.calculate_cmi_pillars(100.0, 100.0, 100.0, 100.0, 90.0)
    assert pytest.approx(base_score - score_rob, abs=1e-4) == 1.50


def test_cmi_clamping_and_bounds() -> None:
    """Vérifie que les scores CMI sont strictement bornés dans [0, 100]."""
    calc = CompositeMaintainabilityCalculator

    # Cas extrêmes négatifs
    min_score, p_min = calc.calculate_cmi_pillars(-50.0, -100.0, -20.0, -10.0, -99.0)
    assert min_score == 0.0
    assert all(val == 0.0 for val in p_min.values())

    # Cas extrêmes supérieurs à 100
    max_score, p_max = calc.calculate_cmi_pillars(150.0, 200.0, 120.0, 110.0, 300.0)
    assert max_score == 100.0
    assert all(val == 100.0 for val in p_max.values())


def test_mccabe_decoupling_in_microsoft_equation() -> None:
    """
    Vérifie que l'équation Microsoft utilise strictement la complexité cyclomatique
    de McCabe v(G) et ne dépend pas de la complexité cognitive.
    """
    calc = CompositeMaintainabilityCalculator
    loc = 250
    mccabe = 20

    raw_1, vs_1, iso_1 = calc.calculate_microsoft_mi(loc=loc, mccabe=mccabe)

    # La fonction n'accepte que loc et mccabe, garantissant l'absence d'injection cognitive
    assert isinstance(raw_1, float)
    assert isinstance(vs_1, float)
    assert isinstance(iso_1, float)

    # Si McCabe augmente (plus de chemins conditionnels), le score MI Microsoft doit diminuer
    raw_2, vs_2, iso_2 = calc.calculate_microsoft_mi(loc=loc, mccabe=mccabe + 10)
    assert raw_2 < raw_1
    assert vs_2 < vs_1
    assert iso_2 <= iso_1

    # Différence théorique exacte sur raw_mi : -0.23 * delta_G = -0.23 * 10 = -2.30
    assert pytest.approx(raw_1 - raw_2, abs=1e-4) == 2.30


def test_formal_transfer_function_microsoft_to_iso() -> None:
    """
    Vérifie les propriétés mathématiques de la fonction de transfert continue T(x)
    reliant l'échelle Microsoft Visual Studio et l'indice normalisé ISO 25010.
    """
    T = CompositeMaintainabilityCalculator.convert_microsoft_to_iso

    # 1. Valeurs aux bornes et points de transition
    assert T(0.0) == 0.0
    assert T(-10.0) == 0.0
    assert pytest.approx(T(10.0), abs=1e-5) == 50.0   # Fin zone rouge / début zone jaune
    assert pytest.approx(T(20.0), abs=1e-5) == 70.0   # Fin zone jaune / début zone verte (Seuil Microsoft >= 20.0)
    assert pytest.approx(T(40.0), abs=1e-5) == 100.0  # Plafond d'excellence pratique Microsoft
    assert T(50.0) == 100.0
    assert T(100.0) == 100.0

    # 2. Continuité aux frontières x = 10, x = 20, x = 40 (limite gauche = limite droite)
    eps = 1e-6
    # Frontière x = 10
    assert pytest.approx(T(10.0 - eps), abs=1e-4) == 50.0
    assert pytest.approx(T(10.0 + eps), abs=1e-4) == 50.0

    # Frontière x = 20 (Seuil Vert Microsoft Visual Studio)
    assert pytest.approx(T(20.0 - eps), abs=1e-4) == 70.0
    assert pytest.approx(T(20.0 + eps), abs=1e-4) == 70.0

    # Frontière x = 40
    assert pytest.approx(T(40.0 - eps), abs=1e-4) == 100.0
    assert pytest.approx(T(40.0 + eps), abs=1e-4) == 100.0

    # 3. Monotonie stricte
    test_points = [0.0, 5.0, 9.9, 10.0, 15.0, 19.9, 20.0, 25.0, 35.0, 40.0]
    for i in range(len(test_points) - 1):
        x1, x2 = test_points[i], test_points[i + 1]
        assert T(x1) <= T(x2)


def test_iso_grade_and_microsoft_status() -> None:
    """Vérifie la cohérence des labels sémantiques ISO et Microsoft."""
    calc = CompositeMaintainabilityCalculator

    # Statuts Microsoft
    assert "VERT" in calc.get_microsoft_vs_status(25.0)
    assert "VERT" in calc.get_microsoft_vs_status(20.0)
    assert "JAUNE" in calc.get_microsoft_vs_status(19.9)
    assert "JAUNE" in calc.get_microsoft_vs_status(10.0)
    assert "ROUGE" in calc.get_microsoft_vs_status(9.9)
    assert "ROUGE" in calc.get_microsoft_vs_status(0.0)

    # Grades ISO 25010
    assert "GRADE A" in calc.get_iso_grade(95.0)
    assert "GRADE A" in calc.get_iso_grade(85.0)
    assert "GRADE B" in calc.get_iso_grade(80.0)
    assert "GRADE C" in calc.get_iso_grade(70.0)
    assert "GRADE D" in calc.get_iso_grade(55.0)
    assert "GRADE F" in calc.get_iso_grade(40.0)


def test_project_cmi_aggregation() -> None:
    """Vérifie le calcul agrégé global sur un jeu de rapports de fichiers."""
    calc = CompositeMaintainabilityCalculator

    # 2 fichiers modèles
    f1 = FileAuditReport(
        file_path="src/module_a.py",
        lines_of_code=200,
        cognitive_complexity=20,
        cyclomatic_complexity=15,
        maintainability_index=22.5,
        type_completeness_percent=100.0,
        security_violations=[],
        functions=[
            FunctionQualityMetrics("src/module_a.py", "fn1", 10, 5, 4, 30, True),
            FunctionQualityMetrics("src/module_a.py", "fn2", 50, 8, 6, 40, True),
        ],
        afferent_coupling=2,
        efferent_coupling=3,
        instability=0.6,
        microsoft_mi_raw=38.0,
        microsoft_mi_vs=22.5,
        microsoft_mi_iso_converted=73.75,
        cmi_iso_25010=96.0
    )

    f2 = FileAuditReport(
        file_path="src/module_b.py",
        lines_of_code=150,
        cognitive_complexity=10,
        cyclomatic_complexity=8,
        maintainability_index=26.0,
        type_completeness_percent=100.0,
        security_violations=[],
        functions=[
            FunctionQualityMetrics("src/module_b.py", "fn3", 15, 4, 3, 25, True),
        ],
        afferent_coupling=1,
        efferent_coupling=2,
        instability=0.66,
        microsoft_mi_raw=44.0,
        microsoft_mi_vs=26.0,
        microsoft_mi_iso_converted=79.0,
        cmi_iso_25010=98.0
    )

    project_cmi, pillars = calc.compute_project_cmi(
        reports=[f1, f2],
        cycles_count=0,
        coverage_percent=88.0,
        mutation_score=100.0
    )

    assert project_cmi >= 90.0
    assert "analyzability" in pillars
    assert "modularity" in pillars
    assert "testability" in pillars
    assert "type_safety" in pillars
    assert "robustness" in pillars
    assert pillars["type_safety"] == 100.0
    assert pillars["robustness"] == 100.0
    assert pillars["modularity"] == 100.0
