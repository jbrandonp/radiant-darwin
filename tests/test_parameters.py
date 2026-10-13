"""
Tests unitaires pour le moteur d'expressions et la table de paramètres globaux (fx).
Vérifie la robustesse de l'analyseur AST sécurisé et la propagation des dépendances.
"""

import pytest
import math
from src.core.parameters import SafeExpressionEvaluator, ParameterTable, UserParameter


def test_safe_evaluator_basic_arithmetic() -> None:
    """Vérifie l'évaluation des opérations arithmétiques fondamentales."""
    ctx = {"x": 10.0, "y": 2.5}
    assert SafeExpressionEvaluator.evaluate("x + y", ctx) == pytest.approx(12.5)
    assert SafeExpressionEvaluator.evaluate("x - y", ctx) == pytest.approx(7.5)
    assert SafeExpressionEvaluator.evaluate("x * y", ctx) == pytest.approx(25.0)
    assert SafeExpressionEvaluator.evaluate("x / y", ctx) == pytest.approx(4.0)
    assert SafeExpressionEvaluator.evaluate("y ** 2", ctx) == pytest.approx(6.25)
    assert SafeExpressionEvaluator.evaluate("-x", ctx) == pytest.approx(-10.0)
    assert SafeExpressionEvaluator.evaluate("+x", ctx) == pytest.approx(10.0)


def test_safe_evaluator_functions() -> None:
    """Vérifie le support des fonctions mathématiques standard."""
    ctx = {"angle": 90.0, "val": -42.0}
    assert SafeExpressionEvaluator.evaluate("sqrt(16)", {}) == pytest.approx(4.0)
    assert SafeExpressionEvaluator.evaluate("abs(val)", ctx) == pytest.approx(42.0)
    assert SafeExpressionEvaluator.evaluate("min(10, 20)", {}) == pytest.approx(10.0)
    assert SafeExpressionEvaluator.evaluate("max(10, 20)", {}) == pytest.approx(20.0)
    assert SafeExpressionEvaluator.evaluate("sin(angle)", ctx) == pytest.approx(1.0)
    assert SafeExpressionEvaluator.evaluate("cos(0)", {}) == pytest.approx(1.0)
    assert SafeExpressionEvaluator.evaluate("pi", {}) == pytest.approx(math.pi)


def test_safe_evaluator_security_and_errors() -> None:
    """Vérifie que les injections de code et fonctions non autorisées sont bloquées."""
    with pytest.raises(ValueError):
        SafeExpressionEvaluator.evaluate("__import__('os').system('dir')", {})

    with pytest.raises(ValueError):
        SafeExpressionEvaluator.evaluate("open('test.txt')", {})

    with pytest.raises(ValueError):
        SafeExpressionEvaluator.evaluate("inconnue + 1", {})

    with pytest.raises(ValueError):
        SafeExpressionEvaluator.evaluate("'string_not_allowed'", {})


def test_parameter_table_propagation() -> None:
    """Vérifie la mise à jour en cascade des paramètres dépendants."""
    table = ParameterTable()
    table.set_parameter("longueur", "100.0", "mm", "Longueur nominale")
    table.set_parameter("largeur", "longueur / 2", "mm", "Largeur dérivée")
    table.set_parameter("epaisseur", "largeur / 5", "mm", "Épaisseur dérivée")

    assert table.get_value("longueur") == pytest.approx(100.0)
    assert table.get_value("largeur") == pytest.approx(50.0)
    assert table.get_value("epaisseur") == pytest.approx(10.0)

    # Modification de la variable racine
    table.set_parameter("longueur", "200.0")
    assert table.get_value("longueur") == pytest.approx(200.0)
    assert table.get_value("largeur") == pytest.approx(100.0)
    assert table.get_value("epaisseur") == pytest.approx(20.0)


def test_parameter_table_fallback() -> None:
    """Vérifie le comportement de repli sur valeur par défaut."""
    table = ParameterTable()
    assert table.get_value("inexistant", default=12.34) == pytest.approx(12.34)
