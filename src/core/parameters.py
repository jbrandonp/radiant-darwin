"""
Moteur de paramètres utilisateur globaux et évaluateur d'équations mathématiques (fx).
Inspiré de la boîte de dialogue 'Change Parameters' d'Autodesk Fusion 360.
Utilise un parseur AST sécurisé sans aucun appel à eval().
"""

from __future__ import annotations
import ast
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable


@dataclass
class UserParameter:
    """Paramètre global défini par une expression ou une constante."""
    name: str
    expression: str
    unit: str = "mm"
    value: float = 0.0
    comment: str = ""


class SafeExpressionEvaluator:
    """
    Évaluateur d'expressions mathématiques sécurisé basé sur l'AST Python.
    Empêche toute injection de code arbitraire et supporte les fonctions mathématiques standard.
    """

    ALLOWED_OPERATORS = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.Pow: lambda a, b: a ** b,
        ast.Mod: lambda a, b: a % b,
        ast.USub: lambda a: -a,
        ast.UAdd: lambda a: a,
    }

    ALLOWED_FUNCTIONS: Dict[str, Callable[..., float]] = {
        "sqrt": math.sqrt,
        "sin": lambda x: math.sin(math.radians(x)),
        "cos": lambda x: math.cos(math.radians(x)),
        "tan": lambda x: math.tan(math.radians(x)),
        "abs": abs,
        "min": min,
        "max": max,
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

        try:
            node = ast.parse(clean_expr, mode='eval')
            return float(cls._eval_node(node.body, context))
        except Exception as e:
            raise ValueError(f"Expression invalide '{expression_str}' : {e}")

    @classmethod
    def _eval_node(cls, node: ast.AST, context: Dict[str, float]) -> float:
        """Parcourt récursivement l'arbre syntaxique pour évaluer l'expression."""
        if isinstance(node, ast.Constant):  # Nombre ou constante (Python 3.8+)
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError(f"Type littéral non autorisé : {node.value}")

        elif isinstance(node, ast.Name):  # Variable du contexte
            var_name = node.id
            if var_name in context:
                return float(context[var_name])
            elif var_name.lower() == "pi":
                return math.pi
            raise ValueError(f"Variable inconnue '{var_name}'")

        elif isinstance(node, ast.UnaryOp):  # Opération unaire (-x, +x)
            op_func = cls.ALLOWED_OPERATORS.get(type(node.op))
            if op_func:
                operand = cls._eval_node(node.operand, context)
                return float(op_func(operand))
            raise ValueError(f"Opérateur unaire non supporté : {type(node.op)}")

        elif isinstance(node, ast.BinOp):  # Opération binaire (a + b, a * b)
            op_func = cls.ALLOWED_OPERATORS.get(type(node.op))
            if op_func:
                left = cls._eval_node(node.left, context)
                right = cls._eval_node(node.right, context)
                return float(op_func(left, right))
            raise ValueError(f"Opérateur binaire non supporté : {type(node.op)}")

        elif isinstance(node, ast.Call):  # Appel de fonction mathématique (sqrt(x))
            func_name = getattr(node.func, 'id', '')
            if func_name in cls.ALLOWED_FUNCTIONS:
                args = [cls._eval_node(arg, context) for arg in node.args]
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
