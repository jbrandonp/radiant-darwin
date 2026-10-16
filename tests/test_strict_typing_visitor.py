"""
Tests unitaires complets pour le Système de Typage Statique Inviolable SOTA (Basedpyright & Mypy Strict).
scripts/strict_typing_visitor.py

Vérifie formellement :
1. Résolution exhaustive des alias d'importation (from typing import Any as T) et modules (import typing as t).
2. Résolution transitive des alias locaux (MyType = Any, ComplexType = Dict[str, Any]) avec protection anti-boucles.
3. Détection et interdiction de tous les conteneurs génériques bruts (Bare Generics : List, Dict, Callable, etc.).
4. Inspection exhaustive des arguments (posonlyargs, args, kwonlyargs, varargs *args, kwargs **kwargs).
5. Typage de retour obligatoire sur toutes les fonctions, y compris __init__ -> None.
6. Validation de la correction de la signature de l'invoker dans src/ai/cad_script_engine.py:389.
"""

from __future__ import annotations
import os
import sys
import pytest

from scripts.strict_typing_visitor import (
    StrictTypingViolationType,
    StrictTypingViolation,
    StrictTypingVisitor,
    audit_strict_typing_code,
    audit_strict_typing_file,
    format_strict_typing_report,
)


# ==============================================================================
# 1. Tests de résolution des alias d'importation (Any, object, Bare Generics)
# ==============================================================================

def test_import_alias_any_direct_and_renamed() -> None:
    """Vérifie que 'from typing import Any as T' et 'import typing as t' sont interceptés."""
    code = """
from typing import Any as T
import typing as t
from typing_extensions import Any as ExtAny

def func_1(x: T) -> None:
    pass

def func_2(x: t.Any) -> None:
    pass

def func_3(x: ExtAny) -> None:
    pass
"""
    violations = audit_strict_typing_code(code, filename="test_alias_any.py")
    assert len(violations) == 3
    for v in violations:
        assert v.violation_type == StrictTypingViolationType.FORBIDDEN_ANY


def test_import_alias_object_forbidden() -> None:
    """Vérifie que 'object' est interdit même via alias d'import ou builtins.object."""
    code = """
from builtins import object as RawObject
import builtins

def bad_1(x: RawObject) -> None:
    pass

def bad_2(x: builtins.object) -> None:
    pass

def bad_3(x: object) -> None:
    pass
"""
    violations = audit_strict_typing_code(code, filename="test_alias_object.py")
    assert len(violations) == 3
    for v in violations:
        assert v.violation_type == StrictTypingViolationType.FORBIDDEN_OBJECT


def test_import_alias_bare_generics() -> None:
    """Vérifie que les conteneurs génériques bruts renommés à l'import sont interceptés."""
    code = """
from typing import List as L, Dict as D, Callable as C

def f1(x: L) -> None:
    pass

def f2(x: D) -> None:
    pass

def f3(x: C) -> None:
    pass
"""
    violations = audit_strict_typing_code(code, filename="test_alias_bare.py")
    assert len(violations) == 3
    for v in violations:
        assert v.violation_type == StrictTypingViolationType.BARE_GENERIC


# ==============================================================================
# 2. Tests de résolution transitive des alias locaux
# ==============================================================================

def test_local_alias_transitive_any_resolution() -> None:
    """Vérifie la résolution transitive d'alias locaux en chaîne vers Any."""
    code = """
from typing import Any as T

AliasLevel1 = T
AliasLevel2 = AliasLevel1
AliasLevel3 = AliasLevel2

def bad_deep_alias(param: AliasLevel3) -> None:
    pass
"""
    violations = audit_strict_typing_code(code, filename="test_transitive_any.py")
    assert len(violations) == 1
    assert violations[0].violation_type == StrictTypingViolationType.FORBIDDEN_ANY
    assert "AliasLevel3" in violations[0].target_name or "param" in violations[0].target_name


def test_local_alias_parameterized_container_with_any() -> None:
    """Vérifie qu'un alias de type composé contenant Any est intercepté."""
    code = """
from typing import Dict, List, Any as MyAny

NestedType = Dict[str, List[MyAny]]

def bad_container(data: NestedType) -> None:
    pass
"""
    violations = audit_strict_typing_code(code, filename="test_nested_alias.py")
    assert len(violations) == 1
    assert violations[0].violation_type == StrictTypingViolationType.FORBIDDEN_ANY


def test_local_alias_bare_generic_resolution() -> None:
    """Vérifie qu'un alias local pointant vers un Bare Generic est détecté."""
    code = """
from typing import List, Callable

MyListAlias = List
MyCallAlias = Callable

def bad_alias_usage(a: MyListAlias, b: MyCallAlias) -> None:
    pass
"""
    violations = audit_strict_typing_code(code, filename="test_bare_alias.py")
    assert len(violations) == 2
    for v in violations:
        assert v.violation_type == StrictTypingViolationType.BARE_GENERIC


def test_local_alias_cycle_protection() -> None:
    """Vérifie que des alias cycliques ne provoquent pas de boucle infinie."""
    code = """
CycleA = CycleB
CycleB = CycleA

def func_cycle(x: CycleA) -> None:
    pass
"""
    # Ne doit pas lever RecursionError
    violations = audit_strict_typing_code(code, filename="test_cycle.py")
    assert isinstance(violations, list)


# ==============================================================================
# 3. Tests des conteneurs génériques bruts (Bare Generics)
# ==============================================================================

def test_bare_generics_all_standard_types() -> None:
    """Vérifie le rejet de List, Dict, Set, Tuple, Callable bruts sans arguments."""
    code = """
from typing import List, Dict, Set, Tuple, Callable

def f(
    a: List,
    b: Dict,
    c: Set,
    d: Tuple,
    e: Callable
) -> None:
    pass
"""
    violations = audit_strict_typing_code(code, filename="test_all_bare.py")
    assert len(violations) == 5
    for v in violations:
        assert v.violation_type == StrictTypingViolationType.BARE_GENERIC


def test_parameterized_generics_valid() -> None:
    """Vérifie que les conteneurs formellement paramétrés sont acceptés sans violation."""
    code = """
from typing import List, Dict, Set, Tuple, Callable

def f_valid(
    a: List[str],
    b: Dict[str, float],
    c: Set[int],
    d: Tuple[int, str],
    e: Callable[[int, str], bool],
    f: Callable[..., None]
) -> List[int]:
    return [1, 2, 3]
"""
    violations = audit_strict_typing_code(code, filename="test_param_ok.py")
    assert len(violations) == 0


def test_nested_bare_generic_inside_container() -> None:
    """Vérifie la détection d'un conteneur brut imbriqué dans un autre conteneur."""
    code = """
from typing import List, Dict, Callable

def f_nested(
    a: List[Dict],
    b: Dict[str, Callable]
) -> None:
    pass
"""
    violations = audit_strict_typing_code(code, filename="test_nested_bare.py")
    assert len(violations) == 2
    for v in violations:
        assert v.violation_type == StrictTypingViolationType.BARE_GENERIC


# ==============================================================================
# 4. Tests des variables annotées (AnnAssign) et cas de cad_script_engine:389
# ==============================================================================

def test_variable_ann_assign_bare_callable_violation() -> None:
    """Vérifie que 'invoker: Callable = ...' est intercepté comme BARE_GENERIC."""
    code = """
from typing import Callable

def run_exec():
    invoker: Callable = getattr(__builtins__, "exec")
    return invoker
"""
    violations = audit_strict_typing_code(code, filename="test_ann_bare.py")
    # 1 return manquant sur run_exec + 1 Bare Generic sur invoker
    types = [v.violation_type for v in violations]
    assert StrictTypingViolationType.BARE_GENERIC in types
    assert StrictTypingViolationType.MISSING_RETURN_ANNOTATION in types


def test_variable_ann_assign_formally_typed_callable() -> None:
    """Vérifie que l'invoker formellement typé sans Any ne produit aucune violation."""
    code = """
import types
from typing import Callable, Dict

SafeContextVal = Dict[str, str]

def run_exec() -> None:
    invoker: Callable[[types.CodeType, Dict[str, SafeContextVal]], None] = (
        getattr(__builtins__, "exec") if hasattr(__builtins__, "exec") else __builtins__["exec"]
    )
"""
    violations = audit_strict_typing_code(code, filename="test_ann_formal.py")
    assert len(violations) == 0


def test_variable_ann_assign_forbidden_any() -> None:
    """Vérifie qu'une variable annotée avec Any est interceptée."""
    code = """
from typing import Any

def test_func() -> None:
    temp: Any = 42
"""
    violations = audit_strict_typing_code(code, filename="test_ann_any.py")
    assert len(violations) == 1
    assert violations[0].violation_type == StrictTypingViolationType.FORBIDDEN_ANY


# ==============================================================================
# 5. Tests d'inspection exhaustive des arguments
# ==============================================================================

def test_missing_posonly_arg_annotation() -> None:
    """Vérifie la détection d'annotation manquante sur les arguments positionnels purs (avant '/')."""
    code = """
def posonly_fn(x, /, y: int) -> None:
    pass
"""
    violations = audit_strict_typing_code(code, filename="test_posonly.py")
    assert len(violations) == 1
    assert violations[0].violation_type == StrictTypingViolationType.MISSING_PARAM_ANNOTATION
    assert "x" in violations[0].target_name


def test_missing_kwonly_arg_annotation() -> None:
    """Vérifie la détection d'annotation manquante sur les arguments mot-clé purs (après '*')."""
    code = """
def kwonly_fn(x: int, *, mode) -> None:
    pass
"""
    violations = audit_strict_typing_code(code, filename="test_kwonly.py")
    assert len(violations) == 1
    assert violations[0].violation_type == StrictTypingViolationType.MISSING_PARAM_ANNOTATION
    assert "mode" in violations[0].target_name


def test_missing_vararg_and_kwarg_annotation() -> None:
    """Vérifie que *args et **kwargs sans types sont interceptés."""
    code = """
def variadic_fn(*args, **kwargs) -> None:
    pass
"""
    violations = audit_strict_typing_code(code, filename="test_variadic.py")
    assert len(violations) == 2
    v_types = {v.violation_type for v in violations}
    assert StrictTypingViolationType.MISSING_VARARG_ANNOTATION in v_types
    assert StrictTypingViolationType.MISSING_KWARG_ANNOTATION in v_types


def test_fully_typed_complex_signature() -> None:
    """Vérifie qu'une signature complexe totalement typée passe sans anomalie."""
    code = """
def complete_signature(
    pos_val: int,
    /,
    std_val: str,
    *args: float,
    kw_val: bool = True,
    **kwargs: str
) -> None:
    pass
"""
    violations = audit_strict_typing_code(code, filename="test_complete_sig.py")
    assert len(violations) == 0


def test_class_method_receivers_self_and_cls() -> None:
    """Vérifie que 'self' et 'cls' sont ignorés pour les méthodes de classes, mais typés pour @staticmethod."""
    code = """
class MyCADService:
    def __init__(self, name: str) -> None:
        self.name = name

    def compute(self, factor: float) -> float:
        return factor * 2.0

    @classmethod
    def create_default(cls, label: str) -> MyCADService:
        return cls(label)

    @staticmethod
    def pure_calc(x: float, y: float) -> float:
        return x + y
"""
    violations = audit_strict_typing_code(code, filename="test_class_methods.py")
    assert len(violations) == 0


def test_staticmethod_untyped_receiver_reported() -> None:
    """Vérifie qu'un argument nommé 'self' dans une @staticmethod est obligatoirement typé."""
    code = """
class Utility:
    @staticmethod
    def untyped_static(self) -> None:
        pass
"""
    violations = audit_strict_typing_code(code, filename="test_static_untyped.py")
    assert len(violations) == 1
    assert violations[0].violation_type == StrictTypingViolationType.MISSING_PARAM_ANNOTATION


# ==============================================================================
# 6. Tests du typage de retour (y compris __init__ -> None)
# ==============================================================================

def test_missing_init_return_annotation() -> None:
    """Vérifie que __init__ sans '-> None' est formellement rejeté."""
    code = """
class Engine:
    def __init__(self, rpm: int):
        self.rpm = rpm
"""
    violations = audit_strict_typing_code(code, filename="test_init_ret.py")
    assert len(violations) == 1
    assert violations[0].violation_type == StrictTypingViolationType.MISSING_RETURN_ANNOTATION
    assert "__init__" in violations[0].target_name


def test_missing_function_return_annotation() -> None:
    """Vérifie qu'une fonction ordinaire sans type de retour est formellement rejetée."""
    code = """
def calculate(a: int, b: int):
    return a + b
"""
    violations = audit_strict_typing_code(code, filename="test_fn_ret.py")
    assert len(violations) == 1
    assert violations[0].violation_type == StrictTypingViolationType.MISSING_RETURN_ANNOTATION


def test_return_forbidden_types_any_and_object() -> None:
    """Vérifie qu'un type de retour '-> Any' ou '-> object' est rejeté."""
    code = """
from typing import Any

def ret_any() -> Any:
    return 1

def ret_obj() -> object:
    return "hello"
"""
    violations = audit_strict_typing_code(code, filename="test_ret_forbidden.py")
    assert len(violations) == 2
    types = {v.violation_type for v in violations}
    assert StrictTypingViolationType.FORBIDDEN_ANY in types
    assert StrictTypingViolationType.FORBIDDEN_OBJECT in types


# ==============================================================================
# 7. Tests modernes : Forward References, Union PEP 604 et Literal
# ==============================================================================

def test_forward_references_clean_and_forbidden() -> None:
    """Vérifie l'inspection des chaînes d'annotations Forward References."""
    code_clean = """
def process(doc: 'CADDocument') -> 'List[str]':
    return []
"""
    violations_clean = audit_strict_typing_code(code_clean, filename="test_fwd_clean.py")
    assert len(violations_clean) == 0

    code_dirty = """
def process_bad(doc: 'Any') -> None:
    pass
"""
    violations_dirty = audit_strict_typing_code(code_dirty, filename="test_fwd_dirty.py")
    assert len(violations_dirty) == 1
    assert violations_dirty[0].violation_type == StrictTypingViolationType.FORBIDDEN_ANY


def test_pep604_union_syntax() -> None:
    """Vérifie la syntaxe PEP 604 'int | str' et la détection de 'int | Any'."""
    code_ok = """
def union_ok(x: int | str | None) -> None:
    pass
"""
    assert len(audit_strict_typing_code(code_ok, filename="test_pep604_ok.py")) == 0

    code_bad = """
from typing import Any

def union_bad(x: int | Any) -> None:
    pass
"""
    violations = audit_strict_typing_code(code_bad, filename="test_pep604_bad.py")
    assert len(violations) == 1
    assert violations[0].violation_type == StrictTypingViolationType.FORBIDDEN_ANY


def test_literal_values_allowed() -> None:
    """Vérifie que les chaînes et entiers dans Literal[...] ne sont pas pris pour des types."""
    code_literal = """
from typing import Literal

def set_mode(mode: Literal['SOLID', 'WIREFRAME', 'POINTS']) -> None:
    pass
"""
    violations = audit_strict_typing_code(code_literal, filename="test_literal.py")
    assert len(violations) == 0


# ==============================================================================
# 8. Test de validation réelle sur src/ai/cad_script_engine.py
# ==============================================================================

def test_cad_script_engine_zero_strict_typing_violations() -> None:
    """
    Vérifie que le fichier src/ai/cad_script_engine.py ne présente STRICTEMENT AUCUNE
    violation après correction formelle de la ligne 389 et de SafeContextVal.
    """
    target_file = "src/ai/cad_script_engine.py"
    assert os.path.exists(target_file), f"Fichier cible introuvable : {target_file}"

    violations = audit_strict_typing_file(target_file)
    if violations:
        report = format_strict_typing_report(violations)
        pytest.fail(f"Violations de typage strict trouvées dans {target_file} :\n{report}")
    assert len(violations) == 0


def test_format_strict_typing_report_output() -> None:
    """Vérifie le formatage textuel du rapport de typage strict."""
    empty_report = format_strict_typing_report([])
    assert "Zéro violation" in empty_report

    sample_violations = [
        StrictTypingViolation(
            violation_type=StrictTypingViolationType.BARE_GENERIC,
            line_number=42,
            column_offset=10,
            target_name="invoker",
            message="Conteneur brut",
            recommendation="Paramétrer",
            file_path="sample.py"
        )
    ]
    formatted = format_strict_typing_report(sample_violations)
    assert "BARE_GENERIC" in formatted
    assert "sample.py:42:10" in formatted
    assert "invoker" in formatted
