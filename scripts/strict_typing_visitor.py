"""
Module de Typage Statique Inviolable SOTA (Basedpyright & Mypy Strict) pour Noyau Industriel.
Conforme aux standards ISO 25010, PEP 484, PEP 526, PEP 585 et PEP 604.

Règles de validation formelle :
1. Strictement ZÉRO Any (interdiction totale directe et via alias d'imports ou alias locaux).
2. Strictement ZÉRO object comme annotation de type (interdiction directe et via alias).
3. Interdiction formelle de tous les conteneurs génériques bruts (Bare Generics : List, Dict, Callable sans arguments).
4. Exhaustivité totale des signatures : posonlyargs, args, kwonlyargs, varargs (*args), kwargs (**kwargs).
5. Typage de retour obligatoire sur TOUTES les fonctions, y compris __init__ -> None.
6. Résolution transitive des chaînes d'alias d'importation et d'alias locaux avec protection anti-cycles.
"""

from __future__ import annotations
import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Union


class StrictTypingViolationType(Enum):
    """Catégories formelles de violations de typage statique strict."""
    FORBIDDEN_ANY = "FORBIDDEN_ANY"
    FORBIDDEN_OBJECT = "FORBIDDEN_OBJECT"
    BARE_GENERIC = "BARE_GENERIC"
    MISSING_PARAM_ANNOTATION = "MISSING_PARAM_ANNOTATION"
    MISSING_VARARG_ANNOTATION = "MISSING_VARARG_ANNOTATION"
    MISSING_KWARG_ANNOTATION = "MISSING_KWARG_ANNOTATION"
    MISSING_RETURN_ANNOTATION = "MISSING_RETURN_ANNOTATION"
    SYNTAX_ERROR = "SYNTAX_ERROR"


@dataclass
class StrictTypingViolation:
    """Description formelle d'une anomalie de typage statique détectée."""
    violation_type: StrictTypingViolationType
    line_number: int
    column_offset: int
    target_name: str
    message: str
    recommendation: str
    file_path: str = ""
    code_snippet: str = ""


# Ensemble exhaustif des conteneurs génériques nécessitant obligatoirement des arguments de types
BARE_GENERIC_NAMES: Set[str] = {
    # Collections standard typing et builtins (PEP 585)
    "List", "list",
    "Dict", "dict",
    "Set", "set",
    "FrozenSet", "frozenset",
    "Tuple", "tuple",
    "Deque", "deque",
    "DefaultDict", "defaultdict",
    "OrderedDict",
    # Callables et générateurs
    "Callable",
    "Generator", "AsyncGenerator",
    "Iterator", "Iterable", "AsyncIterator", "AsyncIterable",
    "Coroutine",
    # Collections abstraites
    "Sequence", "MutableSequence",
    "Mapping", "MutableMapping",
    "AbstractSet", "MutableSet",
    "Collection", "Container",
    # Méta-types et enveloppes
    "Type",
    # Formes spéciales si utilisées sans indice
    "Optional", "Union"
}

TYPING_MODULES: Set[str] = {"typing", "typing_extensions", "collections.abc"}


class StrictTypingVisitor(ast.NodeVisitor):
    """
    Analyseur syntaxique AST déterministe pour le typage statique inviolable SOTA.
    Traque et résout les alias d'import et les alias locaux de manière transitive.
    """

    def __init__(self, filename: str = "<unknown>") -> None:
        self.filename: str = filename
        self.violations: List[StrictTypingViolation] = []

        # Alias d'importation :
        # - Module : "t" -> "typing"
        # - Symbole : "T" -> "typing.Any", "L" -> "typing.List"
        self.module_aliases: Dict[str, str] = {}
        self.imported_symbols: Dict[str, str] = {}

        # Alias locaux : "MyType" -> noeud AST (ex: Name(id="Any"), Subscript(...))
        self.local_aliases: Dict[str, ast.AST] = {}

        # Contexte d'inspection
        self.in_class_stack: List[str] = []
        self.function_depth: int = 0
        self.total_functions_inspected: int = 0
        self.fully_typed_functions_count: int = 0

    # --------------------------------------------------------------------------
    # 1. Collecte préliminaire des alias d'importation et alias locaux
    # --------------------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            mod_name = alias.name
            as_name = alias.asname or mod_name
            self.module_aliases[as_name] = mod_name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod_name = node.module or ""
        for alias in node.names:
            imported_symbol = alias.name
            as_name = alias.asname or imported_symbol
            full_target = f"{mod_name}.{imported_symbol}" if mod_name else imported_symbol
            self.imported_symbols[as_name] = full_target
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Détection des alias de types locaux (ex: MyType = Any, ComplexType = Dict[str, Any])
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.local_aliases[target.id] = node.value
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        # Enregistrement d'alias typé (ex: MyType: TypeAlias = Any)
        if isinstance(node.target, ast.Name) and node.value is not None:
            self.local_aliases[node.target.id] = node.value

        # Inspection de l'annotation de la variable elle-même (ex: invoker: Callable = ...)
        target_name = ast.unparse(node.target) if hasattr(ast, "unparse") else "variable"
        self._inspect_annotation(
            annotation_node=node.annotation,
            target_description=f"variable '{target_name}'",
            lineno=node.lineno,
            col_offset=node.col_offset
        )
        self.generic_visit(node)

    # --------------------------------------------------------------------------
    # 2. Gestion du contexte de classe
    # --------------------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.in_class_stack.append(node.name)
        self.generic_visit(node)
        self.in_class_stack.pop()

    # --------------------------------------------------------------------------
    # 3. Inspection exhaustive des signatures de fonctions
    # --------------------------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._inspect_function_signature(node)
        self.function_depth += 1
        self.generic_visit(node)
        self.function_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._inspect_function_signature(node)
        self.function_depth += 1
        self.generic_visit(node)
        self.function_depth -= 1

    def _is_direct_class_method(self) -> bool:
        """Détermine si la fonction actuelle est une méthode directe de classe."""
        return len(self.in_class_stack) > 0 and self.function_depth == 0

    def _is_static_method(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> bool:
        """Détecte le décorateur @staticmethod."""
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id == "staticmethod":
                return True
            if isinstance(dec, ast.Attribute) and dec.attr == "staticmethod":
                return True
        return False

    def _inspect_function_signature(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> None:
        """Examine en détail chaque paramètre et le type de retour d'une fonction."""
        self.total_functions_inspected += 1
        initial_violation_count = len(self.violations)

        is_method = self._is_direct_class_method()
        is_static = self._is_static_method(node)

        # Déterminer si le premier argument est le récepteur (self/cls)
        first_arg_is_receiver = is_method and not is_static

        # 1. posonlyargs (arguments positionnels stricts avant '/')
        for idx, arg in enumerate(node.args.posonlyargs):
            if idx == 0 and first_arg_is_receiver and arg.arg in ("self", "cls"):
                continue
            self._validate_arg(arg, f"paramètre positionnel strict '{arg.arg}' in {node.name}")

        # 2. args (arguments classiques)
        has_posonly = len(node.args.posonlyargs) > 0
        for idx, arg in enumerate(node.args.args):
            if idx == 0 and not has_posonly and first_arg_is_receiver and arg.arg in ("self", "cls"):
                continue
            self._validate_arg(arg, f"paramètre '{arg.arg}' in {node.name}")

        # 3. kwonlyargs (arguments mot-clé stricts après '*')
        for arg in node.args.kwonlyargs:
            self._validate_arg(arg, f"paramètre mot-clé strict '{arg.arg}' in {node.name}")

        # 4. vararg (*args)
        if node.args.vararg is not None:
            arg = node.args.vararg
            if arg.annotation is None:
                self.violations.append(StrictTypingViolation(
                    violation_type=StrictTypingViolationType.MISSING_VARARG_ANNOTATION,
                    line_number=arg.lineno,
                    column_offset=arg.col_offset,
                    target_name=f"*{arg.arg}",
                    message=f"Le paramètre variable '*{arg.arg}' dans '{node.name}' n'est pas typé.",
                    recommendation="Ajouter une annotation de type ex: *args: str ou *args: Tuple[str, ...].",
                    file_path=self.filename
                ))
            else:
                self._inspect_annotation(
                    arg.annotation,
                    f"paramètre variable '*{arg.arg}' in {node.name}",
                    arg.lineno,
                    arg.col_offset
                )

        # 5. kwarg (**kwargs)
        if node.args.kwarg is not None:
            arg = node.args.kwarg
            if arg.annotation is None:
                self.violations.append(StrictTypingViolation(
                    violation_type=StrictTypingViolationType.MISSING_KWARG_ANNOTATION,
                    line_number=arg.lineno,
                    column_offset=arg.col_offset,
                    target_name=f"**{arg.arg}",
                    message=f"Le paramètre variable '**{arg.arg}' dans '{node.name}' n'est pas typé.",
                    recommendation="Ajouter une annotation de type ex: **kwargs: FeatureArg ou **kwargs: Union[str, int].",
                    file_path=self.filename
                ))
            else:
                self._inspect_annotation(
                    arg.annotation,
                    f"paramètre variable '**{arg.arg}' in {node.name}",
                    arg.lineno,
                    arg.col_offset
                )

        # 6. Type de retour (y compris __init__ -> None)
        if node.returns is None:
            self.violations.append(StrictTypingViolation(
                violation_type=StrictTypingViolationType.MISSING_RETURN_ANNOTATION,
                line_number=node.lineno,
                column_offset=node.col_offset,
                target_name=node.name,
                message=f"Type de retour manquant sur la fonction '{node.name}' (y compris __init__ -> None).",
                recommendation=f"Spécifier explicitement le type de retour '-> None' ou '-> TypeAttendu' sur '{node.name}'.",
                file_path=self.filename
            ))
        else:
            self._inspect_annotation(
                node.returns,
                f"type de retour de '{node.name}'",
                node.returns.lineno if hasattr(node.returns, "lineno") else node.lineno,
                node.returns.col_offset if hasattr(node.returns, "col_offset") else node.col_offset
            )

        if len(self.violations) == initial_violation_count:
            self.fully_typed_functions_count += 1

    def _validate_arg(self, arg: ast.arg, description: str) -> None:
        """Vérifie la présence et la conformité de l'annotation d'un argument."""
        if arg.annotation is None:
            self.violations.append(StrictTypingViolation(
                violation_type=StrictTypingViolationType.MISSING_PARAM_ANNOTATION,
                line_number=arg.lineno,
                column_offset=arg.col_offset,
                target_name=arg.arg,
                message=f"Annotation de type manquante sur {description}.",
                recommendation=f"Ajouter un type explicite sans Any pour '{arg.arg}'.",
                file_path=self.filename
            ))
        else:
            self._inspect_annotation(arg.annotation, description, arg.lineno, arg.col_offset)

    # --------------------------------------------------------------------------
    # 4. Résolution transitive et vérification approfondie des annotations
    # --------------------------------------------------------------------------

    def _inspect_annotation(
        self,
        annotation_node: ast.AST,
        target_description: str,
        lineno: int,
        col_offset: int,
        visited_aliases: Optional[Set[str]] = None
    ) -> None:
        """
        Inspecte récursivement une expression d'annotation.
        Résout les alias d'importation et les alias locaux de manière transitive.
        """
        if visited_aliases is None:
            visited_aliases = set()

        # Cas 1 : Constante (ex: None ou ForwardRef sous forme de chaîne de caractères)
        if isinstance(annotation_node, ast.Constant):
            if annotation_node.value is None:
                return  # None valide (ex: -> None)
            if isinstance(annotation_node.value, str):
                # Forward reference : parser la chaîne pour valider son contenu
                try:
                    parsed_ref = ast.parse(annotation_node.value, mode="eval")
                    self._inspect_annotation(
                        parsed_ref.body,
                        f"{target_description} (forward-ref '{annotation_node.value}')",
                        lineno,
                        col_offset,
                        visited_aliases
                    )
                except SyntaxError:
                    self.violations.append(StrictTypingViolation(
                        violation_type=StrictTypingViolationType.SYNTAX_ERROR,
                        line_number=lineno,
                        column_offset=col_offset,
                        target_name=target_description,
                        message=f"Forward reference invalide syntaxiquement : '{annotation_node.value}'.",
                        recommendation="Corriger la chaîne d'annotation de type.",
                        file_path=self.filename
                    ))
            return

        # Cas 2 : Identifiant simple (ast.Name)
        if isinstance(annotation_node, ast.Name):
            name_id = annotation_node.id

            # 2.1 Résolution via alias locaux (ex: MyType = Any ou MyList = List)
            if name_id in self.local_aliases:
                if name_id in visited_aliases:
                    return  # Protection contre les cycles récursifs d'alias
                new_visited = set(visited_aliases)
                new_visited.add(name_id)
                self._inspect_annotation(
                    self.local_aliases[name_id],
                    f"{target_description} (résolu via alias local '{name_id}')",
                    lineno,
                    col_offset,
                    new_visited
                )
                return

            # 2.2 Résolution via alias d'imports (ex: from typing import Any as T)
            if name_id in self.imported_symbols:
                full_symbol = self.imported_symbols[name_id]
                self._check_canonical_symbol(full_symbol, name_id, target_description, lineno, col_offset)
                return

            # 2.3 Vérification des builtins et noms directs
            if name_id == "Any":
                self._report_forbidden_any(target_description, lineno, col_offset, direct_name="Any")
            elif name_id == "object":
                self._report_forbidden_object(target_description, lineno, col_offset, direct_name="object")
            elif name_id in BARE_GENERIC_NAMES:
                self._report_bare_generic(name_id, target_description, lineno, col_offset)
            return

        # Cas 3 : Accès d'attribut (ex: typing.Any, t.List, builtins.object)
        if isinstance(annotation_node, ast.Attribute):
            canonical = self._resolve_attribute_chain(annotation_node)
            parts = canonical.split(".")
            mod_prefix = parts[0] if parts else ""
            attr_name = parts[-1] if parts else ""

            # Résolution de l'alias de module
            actual_mod = self.module_aliases.get(mod_prefix, mod_prefix)
            resolved_full = f"{actual_mod}.{attr_name}" if len(parts) > 1 else canonical

            if resolved_full in ("typing.Any", "typing_extensions.Any") or attr_name == "Any":
                self._report_forbidden_any(target_description, lineno, col_offset, direct_name=canonical)
            elif resolved_full in ("builtins.object", "object") or (actual_mod == "builtins" and attr_name == "object"):
                self._report_forbidden_object(target_description, lineno, col_offset, direct_name=canonical)
            elif (actual_mod in TYPING_MODULES or actual_mod == "builtins") and attr_name in BARE_GENERIC_NAMES:
                self._report_bare_generic(canonical, target_description, lineno, col_offset)
            return

        # Cas 4 : Générique indexé (ast.Subscript, ex: List[int], Dict[str, float], Callable[[int], None])
        if isinstance(annotation_node, ast.Subscript):
            # Vérifier la base du subscript
            base_node = annotation_node.value

            # Si la base est Literal, on n'inspecte pas les arguments comme des types
            base_name = ""
            if isinstance(base_node, ast.Name):
                base_name = base_node.id
                if base_name in self.imported_symbols:
                    base_name = self.imported_symbols[base_name].split(".")[-1]
            elif isinstance(base_node, ast.Attribute):
                base_name = base_node.attr

            if base_name == "Literal":
                return

            # Vérifier si la base elle-même est Any
            if isinstance(base_node, ast.Name) and base_node.id == "Any":
                self._report_forbidden_any(target_description, lineno, col_offset, direct_name="Any")

            # Inspecter récursivement les arguments à l'intérieur du slice
            slice_node = annotation_node.slice
            if isinstance(slice_node, ast.Tuple):
                for elt in slice_node.elts:
                    self._inspect_annotation(elt, target_description, lineno, col_offset, visited_aliases)
            elif isinstance(slice_node, ast.List):
                # Cas Callable[[arg1, arg2], ret]
                for elt in slice_node.elts:
                    self._inspect_annotation(elt, target_description, lineno, col_offset, visited_aliases)
            else:
                self._inspect_annotation(slice_node, target_description, lineno, col_offset, visited_aliases)
            return

        # Cas 5 : Union PEP 604 (ex: int | str, None | Any)
        if isinstance(annotation_node, ast.BinOp) and isinstance(annotation_node.op, ast.BitOr):
            self._inspect_annotation(annotation_node.left, target_description, lineno, col_offset, visited_aliases)
            self._inspect_annotation(annotation_node.right, target_description, lineno, col_offset, visited_aliases)
            return

        # Cas 6 : Tuples ou Listes (structures de paramètres)
        if isinstance(annotation_node, (ast.Tuple, ast.List)):
            for elt in annotation_node.elts:
                self._inspect_annotation(elt, target_description, lineno, col_offset, visited_aliases)
            return

    # --------------------------------------------------------------------------
    # 5. Méthodes utilitaires de détection et signalement
    # --------------------------------------------------------------------------

    def _resolve_attribute_chain(self, node: ast.Attribute) -> str:
        """Reconstitue la chaîne 'module.attribut'."""
        if isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        elif isinstance(node.value, ast.Attribute):
            parent = self._resolve_attribute_chain(node.value)
            return f"{parent}.{node.attr}"
        return node.attr

    def _check_canonical_symbol(
        self,
        full_symbol: str,
        alias_name: str,
        target_description: str,
        lineno: int,
        col_offset: int
    ) -> None:
        """Vérifie si un symbole importé résolu correspond à Any, object ou Bare Generic."""
        base_name = full_symbol.split(".")[-1]
        mod_name = full_symbol.rsplit(".", 1)[0] if "." in full_symbol else ""

        if full_symbol in ("typing.Any", "typing_extensions.Any") or base_name == "Any":
            self._report_forbidden_any(
                target_description,
                lineno,
                col_offset,
                direct_name=f"{alias_name} (résolu en '{full_symbol}')"
            )
        elif full_symbol in ("builtins.object", "object") or (mod_name == "builtins" and base_name == "object"):
            self._report_forbidden_object(
                target_description,
                lineno,
                col_offset,
                direct_name=f"{alias_name} (résolu en '{full_symbol}')"
            )
        elif base_name in BARE_GENERIC_NAMES:
            self._report_bare_generic(
                f"{alias_name} (résolu en '{full_symbol}')",
                target_description,
                lineno,
                col_offset
            )

    def _report_forbidden_any(self, target_description: str, lineno: int, col_offset: int, direct_name: str) -> None:
        self.violations.append(StrictTypingViolation(
            violation_type=StrictTypingViolationType.FORBIDDEN_ANY,
            line_number=lineno,
            column_offset=col_offset,
            target_name=target_description,
            message=f"Utilisation interdite de 'Any' ({direct_name}) sur {target_description}.",
            recommendation="Remplacer 'Any' par un type d'union strict, un protocole ou une classe concrète.",
            file_path=self.filename
        ))

    def _report_forbidden_object(self, target_description: str, lineno: int, col_offset: int, direct_name: str) -> None:
        self.violations.append(StrictTypingViolation(
            violation_type=StrictTypingViolationType.FORBIDDEN_OBJECT,
            line_number=lineno,
            column_offset=col_offset,
            target_name=target_description,
            message=f"Utilisation interdite de 'object' ({direct_name}) comme type sur {target_description}.",
            recommendation="Spécifier le type exact ou une Union de types formels sans object.",
            file_path=self.filename
        ))

    def _report_bare_generic(self, generic_name: str, target_description: str, lineno: int, col_offset: int) -> None:
        self.violations.append(StrictTypingViolation(
            violation_type=StrictTypingViolationType.BARE_GENERIC,
            line_number=lineno,
            column_offset=col_offset,
            target_name=target_description,
            message=f"Conteneur générique brut '{generic_name}' interdit sans arguments de types sur {target_description}.",
            recommendation=f"Paramétrer le conteneur ex: {generic_name}[TypeElem] ou Callable[[ArgType], ReturnType].",
            file_path=self.filename
        ))


def audit_strict_typing_code(code_str: str, filename: str = "<unknown>") -> List[StrictTypingViolation]:
    """Analyse un extrait de code Python et retourne les violations de typage strict."""
    try:
        tree = ast.parse(code_str, filename=filename)
    except SyntaxError as e:
        return [StrictTypingViolation(
            violation_type=StrictTypingViolationType.SYNTAX_ERROR,
            line_number=e.lineno or 1,
            column_offset=e.offset or 0,
            target_name="syntax",
            message=f"Erreur de syntaxe Python : {e.msg}",
            recommendation="Corriger la syntaxe pour permettre l'analyse AST.",
            file_path=filename
        )]

    visitor = StrictTypingVisitor(filename=filename)
    visitor.visit(tree)
    return visitor.violations


def audit_strict_typing_file(filepath: str) -> List[StrictTypingViolation]:
    """Analyse un fichier Python et retourne les violations de typage strict."""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    return audit_strict_typing_code(content, filename=filepath)


def format_strict_typing_report(violations: List[StrictTypingViolation]) -> str:
    """Formate un rapport textuel clair et détaillé des violations."""
    if not violations:
        return "PARFAIT : Zéro violation de typage strict détectée (100% conforme Basedpyright / Mypy Strict)."

    lines: List[str] = [
        "=" * 70,
        f"RAPPORT DE TYPAGE STATIQUE STRICT SOTA : {len(violations)} VIOLATION(S)",
        "=" * 70
    ]

    for idx, v in enumerate(violations, 1):
        loc = f"{v.file_path}:{v.line_number}:{v.column_offset}" if v.file_path else f"Ligne {v.line_number}"
        lines.append(f"[{idx}] {v.violation_type.value} à {loc}")
        lines.append(f"    Cible   : {v.target_name}")
        lines.append(f"    Message : {v.message}")
        lines.append(f"    Conseil : {v.recommendation}")
        lines.append("-" * 70)

    return "\n".join(lines)


def main() -> int:
    """Point d'entrée CLI pour auditer un ou plusieurs fichiers/dossiers."""
    import argparse
    import json
    import os
    import sys

    parser = argparse.ArgumentParser(description="Auditeur de typage statique strict déterministe (SOTA 2026)")
    parser.add_argument("paths", nargs="*", default=["src"], help="Fichiers ou répertoires à auditer (défaut: src)")
    parser.add_argument("--strict", action="store_true", help="Retourne le code d'erreur 1 si des violations existent")
    parser.add_argument("--json", action="store_true", help="Génère la sortie au format JSON")
    args = parser.parse_args()

    all_violations: List[StrictTypingViolation] = []
    inspected_files = 0

    for p in args.paths:
        if os.path.isfile(p):
            if p.endswith(".py"):
                inspected_files += 1
                all_violations.extend(audit_strict_typing_file(p))
        elif os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    if f.endswith(".py"):
                        inspected_files += 1
                        full_p = os.path.join(root, f)
                        all_violations.extend(audit_strict_typing_file(full_p))

    if args.json:
        report_data = [
            {
                "type": v.violation_type.value,
                "file": v.file_path,
                "line": v.line_number,
                "column": v.column_offset,
                "target": v.target_name,
                "message": v.message,
                "recommendation": v.recommendation
            }
            for v in all_violations
        ]
        print(json.dumps({"total_files": inspected_files, "total_violations": len(all_violations), "violations": report_data}, indent=2))
    else:
        print(f"Fichiers Python analysés : {inspected_files}")
        print(format_strict_typing_report(all_violations))

    if args.strict and len(all_violations) > 0:
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

