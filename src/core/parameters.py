"""
Moteur de paramètres utilisateur globaux et évaluateur d'équations mathématiques (fx).
Inspiré de la boîte de dialogue 'Change Parameters' d'Autodesk Fusion 360.
Utilise un parseur AST sécurisé sans aucun appel à eval().
"""

from __future__ import annotations
import ast
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable

_UNIT_RE = re.compile(r'(\b\d+(?:\.\d+)?)\s*(mm|cm|m|inch|deg|rad)\b', re.IGNORECASE)


@dataclass
class UserParameter:
    """Paramètre global défini par une expression ou une constante."""
    name: str
    expression: str
    unit: str = "mm"
    value: float = 0.0
    comment: str = ""


def _safe_pow(a: float, b: float) -> float:
    """Calcul de puissance avec protection contre les dépassements et attaques DoS CPU."""
    if abs(b) > 100.0 or abs(a) > 1e20:
        raise ValueError("Exposant ou base hors limites de sécurité")
    res = a ** b
    if isinstance(res, complex):
        raise ValueError("Résultat complexe non supporté")
    return float(res)


def _safe_div(a: float, b: float) -> float:
    """Division arithmétique protégée contre la division par zéro."""
    if abs(b) < 1e-15:
        raise ValueError("Division par zéro")
    return a / b


def _safe_mod(a: float, b: float) -> float:
    """Modulo arithmétique protégé contre le modulo par zéro."""
    if abs(b) < 1e-15:
        raise ValueError("Modulo par zéro")
    return a % b


def _safe_sqrt(x: float) -> float:
    """Racine carrée protégée contre les valeurs négatives."""
    if x < 0.0:
        raise ValueError("Racine carrée d'un nombre négatif")
    return math.sqrt(x)


class SafeExpressionEvaluator:
    """
    Évaluateur d'expressions mathématiques sécurisé basé sur l'AST Python.
    Empêche toute injection de code arbitraire et supporte les fonctions mathématiques standard.
    """

    ALLOWED_OPERATORS = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: _safe_div,
        ast.Pow: _safe_pow,
        ast.Mod: _safe_mod,
        ast.USub: lambda a: -a,
        ast.UAdd: lambda a: a,
    }

    ALLOWED_FUNCTIONS: Dict[str, Callable[..., float]] = {
        "sqrt": _safe_sqrt,
        "sin": lambda x: math.sin(math.radians(x)),
        "cos": lambda x: math.cos(math.radians(x)),
        "tan": lambda x: math.tan(math.radians(x)),
        "asin": lambda x: math.degrees(math.asin(max(-1.0, min(1.0, x)))),
        "acos": lambda x: math.degrees(math.acos(max(-1.0, min(1.0, x)))),
        "atan": lambda x: math.degrees(math.atan(x)),
        "atan2": lambda y, x: math.degrees(math.atan2(y, x)),
        "floor": lambda x: float(math.floor(x)),
        "ceil": lambda x: float(math.ceil(x)),
        "round": lambda x, n=0: float(round(x, int(n))),
        "exp": lambda x: float(math.exp(min(50.0, x))),
        "log": lambda x: float(math.log(max(1e-15, x))),
        "ln": lambda x: float(math.log(max(1e-15, x))),
        "log10": lambda x: float(math.log10(max(1e-15, x))),
        "abs": abs,
        "min": lambda *args: float(min(args)) if args else 0.0,
        "max": lambda *args: float(max(args)) if args else 0.0,
        "pi": lambda: math.pi,
    }

    @classmethod
    def evaluate(cls, expression_str: str, context: Dict[str, float]) -> float:
        """
        Évalue une expression arithmétique dans le contexte des variables fournies.
        """
        clean_expr = expression_str.strip()
        if not clean_expr:
            return 0.0

        if len(clean_expr) > 500:
            raise ValueError("Expression trop longue (> 500 caractères)")

        # Prétraitement transparent des unités industrielles CAO (ex: '25mm' -> '(25 * mm)')
        clean_expr = _UNIT_RE.sub(r'(\1 * \2)', clean_expr)

        try:
            node = ast.parse(clean_expr, mode='eval')
            return float(cls._eval_node(node.body, context, depth=0))
        except Exception as e:
            raise ValueError(f"Expression invalide '{expression_str}' : {e}")

    @classmethod
    def _eval_node(cls, node: ast.AST, context: Dict[str, float], depth: int = 0) -> float:
        """Parcourt récursivement l'arbre syntaxique pour évaluer l'expression."""
        if depth > 30:
            raise ValueError("Profondeur de récursion maximale dépassée (protection DoS)")

        if isinstance(node, ast.Constant):  # Nombre ou constante (Python 3.8+)
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError(f"Type littéral non autorisé : {node.value}")

        elif isinstance(node, ast.Name):  # Variable du contexte ou constante/unité intégrée
            var_name = node.id
            if var_name in context:
                return float(context[var_name])
            low_name = var_name.lower()
            if low_name == "pi":
                return math.pi
            elif low_name == "e":
                return math.e
            elif low_name == "mm":
                return 1.0
            elif low_name == "cm":
                return 10.0
            elif low_name == "m":
                return 1000.0
            elif low_name == "inch":
                return 25.4
            elif low_name == "deg":
                return 1.0
            elif low_name == "rad":
                return 180.0 / math.pi
            raise ValueError(f"Variable inconnue '{var_name}'")

        elif isinstance(node, ast.UnaryOp):  # Opération unaire (-x, +x)
            op_func = cls.ALLOWED_OPERATORS.get(type(node.op))
            if op_func:
                operand = cls._eval_node(node.operand, context, depth + 1)
                return float(op_func(operand))
            raise ValueError(f"Opérateur unaire non supporté : {type(node.op)}")

        elif isinstance(node, ast.BinOp):  # Opération binaire (a + b, a * b)
            op_func = cls.ALLOWED_OPERATORS.get(type(node.op))
            if op_func:
                left = cls._eval_node(node.left, context, depth + 1)
                right = cls._eval_node(node.right, context, depth + 1)
                return float(op_func(left, right))
            raise ValueError(f"Opérateur binaire non supporté : {type(node.op)}")

        elif isinstance(node, ast.Call):  # Appel de fonction mathématique (sqrt(x))
            func_name = getattr(node.func, 'id', '')
            if func_name in cls.ALLOWED_FUNCTIONS:
                args = [cls._eval_node(arg, context, depth + 1) for arg in node.args]
                return float(cls.ALLOWED_FUNCTIONS[func_name](*args))
            raise ValueError(f"Fonction non autorisée '{func_name}'")

        raise ValueError(f"Nœud syntaxique non pris en charge : {type(node)}")


class ParameterTable:
    """
    Table des paramètres globaux du projet.
    Gère la résolution des dépendances et le recalcul en cascade des variables.
    """

    def __init__(self) -> None:
        """Initialise la table des paramètres."""
        self.parameters: Dict[str, UserParameter] = {}

    def set_parameter(self, name: str, expression: str, unit: str = "mm", comment: str = "") -> float:
        """
        Définit ou modifie un paramètre et réévalue l'ensemble de la table.
        Retourne la valeur calculée.
        """
        param = UserParameter(
            name=name,
            expression=expression,
            unit=unit,
            comment=comment
        )
        self.parameters[name] = param
        self.evaluate_all()
        return self.parameters[name].value

    def get_value(self, name: str, default: float = 0.0) -> float:
        """Récupère la valeur numérique actuelle d'un paramètre."""
        if name in self.parameters:
            return self.parameters[name].value
        return default

    def evaluate_all(self) -> None:
        """
        Évalue toutes les expressions en résolvant l'ordre des dépendances.
        Effectue jusqu'à N passes de propagation.
        """
        context: Dict[str, float] = {}

        # Initialiser avec les valeurs scalaires directes
        for name, p in self.parameters.items():
            try:
                val = float(p.expression)
                context[name] = val
                p.value = val
            except ValueError:
                pass

        # Passes de propagation pour les expressions dépendantes
        max_passes = len(self.parameters) + 2
        for _ in range(max_passes):
            changed = False
            for name, p in self.parameters.items():
                try:
                    new_val = SafeExpressionEvaluator.evaluate(p.expression, context)
                    if abs(context.get(name, 0.0) - new_val) > 1e-9:
                        context[name] = new_val
                        p.value = new_val
                        changed = True
                except Exception:
                    pass
            if not changed:
                break
