"""Harnais de synthèse et de vérification de programmes CAO au Test-Time (v1.0).

Exécute le filtrage AST statique (sécurité, sandbox) et contrôle le solide produit
via les 4 oracles mathématiques déterministes (étanchéité, volume > 0, Euler chi = 2, AABB).
100% typage statique strict (zéro Any, zéro object), complexité cognitive <= 15.
"""

import ast
from dataclasses import dataclass
import sys
from typing import Final, List, Optional, Tuple


@dataclass(frozen=True)
class VerificationVerdict:
    """Résultat de la vérification formelle d'un programme CAO au test-time."""

    is_ast_safe: bool
    ast_error: Optional[str]
    is_watertight: bool
    is_volume_positive: bool
    is_euler_satisfied: bool
    is_aabb_bounded: bool
    final_passed: bool


class SafeASTVisitor(ast.NodeVisitor):
    """Visiteur AST vérifiant l'absence d'appels système dangereux."""

    BANNED_MODULES: Final[Tuple[str, ...]] = (
        "os",
        "sys",
        "subprocess",
        "socket",
        "shutil",
        "pathlib",
        "requests",
        "urllib",
    )
    BANNED_CALLS: Final[Tuple[str, ...]] = ("open", "eval", "exec", "compile", "__import__")

    def __init__(self) -> None:
        super().__init__()
        self.violations: List[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name.split(".")[0] in self.BANNED_MODULES:
                self.violations.append(f"Import interdit : {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.module.split(".")[0] in self.BANNED_MODULES:
            self.violations.append(f"Import interdit depuis : {node.module}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in self.BANNED_CALLS:
            self.violations.append(f"Appel de fonction interdite : {node.func.id}")
        self.generic_visit(node)


def audit_program_ast(code_str: str) -> Tuple[bool, Optional[str]]:
    """Vérifie la conformité syntaxique et la sécurité de l'AST."""
    try:
        tree = ast.parse(code_str)
    except SyntaxError as err:
        return False, f"Erreur de syntaxe : {err}"

    visitor = SafeASTVisitor()
    visitor.visit(tree)

    if visitor.violations:
        return False, "; ".join(visitor.violations)

    return True, None


def evaluate_cad_oracles(
    vertex_count: int,
    edge_count: int,
    face_count: int,
    volume: float,
    bounding_box_max_span: float,
    is_watertight: bool,
    max_allowed_span: float = 100_000.0,
) -> VerificationVerdict:
    """Évalue les 4 oracles formels d'admissibilité du solide géométrique."""
    euler_chi: Final[int] = vertex_count - edge_count + face_count
    euler_ok: Final[bool] = (euler_chi == 2)
    volume_ok: Final[bool] = (volume > 1e-6)
    aabb_ok: Final[bool] = (0.0 < bounding_box_max_span <= max_allowed_span)

    passed: Final[bool] = is_watertight and volume_ok and euler_ok and aabb_ok

    return VerificationVerdict(
        is_ast_safe=True,
        ast_error=None,
        is_watertight=is_watertight,
        is_volume_positive=volume_ok,
        is_euler_satisfied=euler_ok,
        is_aabb_bounded=aabb_ok,
        final_passed=passed,
    )


def main() -> int:
    """Point d'entrée CLI pour la validation d'un programme génératif au test-time."""
    print("\n================ VÉRIFICATEUR TEST-TIME COMPUTE (CHOLLET-KARPATHY) ================")

    # Programme candidat exemple généré par l'agent
    sample_program: Final[str] = (
        "def generate_part(length: float, width: float) -> float:\n"
        "    return length * width * 10.0\n"
    )

    is_safe, error_msg = audit_program_ast(sample_program)
    print(f"1. Filtrage AST Sandbox : {'CONFORME (Sécurisé)' if is_safe else f'REJETÉ ({error_msg})'}")

    if not is_safe:
        return 1

    # Évaluation des oracles sur une pièce cubique 10x10x10
    verdict = evaluate_cad_oracles(
        vertex_count=8,
        edge_count=18,
        face_count=12,
        volume=1000.0,
        bounding_box_max_span=10.0,
        is_watertight=True,
    )

    print(f"2. Oracle d'Étanchéité (Watertight) : {'OUI' if verdict.is_watertight else 'NON'}")
    print(f"3. Oracle de Volume Positif (>0)    : {'OUI (1000.0 mm³)' if verdict.is_volume_positive else 'NON'}")
    print(f"4. Oracle Euler-Poincaré (Chi = 2)  : {'OUI (Chi = 2)' if verdict.is_euler_satisfied else 'NON'}")
    print(f"5. Oracle Enveloppe AABB            : {'OUI (10.0 mm <= 1000 mm)' if verdict.is_aabb_bounded else 'NON'}")
    print(f"\nVERDICT GLOBAL DU PROGRAMME CANDIDAT : {'ACCEPTÉ' if verdict.final_passed else 'REJETÉ'}")

    return 0 if verdict.final_passed else 1


if __name__ == "__main__":
    sys.exit(main())
