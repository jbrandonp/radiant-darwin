"""
Suite de tests unitaires pour le Calculateur de Complexité Cognitive SonarSource (G. Ann Campbell).
Vérifie la conformité formelle et mathématique stricte selon la spécification officielle SonarQube 2026 :
1. Exemples canoniques du livre blanc SonarSource (G. Ann Campbell, 2017-2023).
2. Élimination de la surtaxe quadratique des chaînes de 'elif' (comportement linéaire O(n)).
3. Séquences d'opérateurs booléens (and/or) : +1 par séquence identique, +1 par transition d'opérateur.
4. Support complet des expressions ternaires (IfExp).
5. Support du pattern matching Python 3.10+ (ast.Match, ast.match_case, guards).
6. Support des compréhensions (ListComp, DictComp, SetComp, GeneratorExp).
7. Support des boucles asynchrones (AsyncFor).
8. Détection de la récursion directe (+1 fondamental par méthode récursive).
"""

import ast
import pytest
from typing import Optional, Union
from scripts.industrial_audit_engine import SonarCognitiveComplexityVisitor


def compute_complexity(source_code: str, func_name: Optional[str] = None) -> int:
    """
    Fonction helper pour évaluer la complexité cognitive d'un bloc de code source Python.
    Si le code source définit une fonction et qu'aucun nom n'est fourni, la fonction est ciblée automatiquement.
    """
    tree: ast.AST = ast.parse(source_code.strip())
    # Si le module contient une seule fonction, on évalue la fonction directement
    if isinstance(tree, ast.Module) and len(tree.body) == 1 and isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        target_fn: Union[ast.FunctionDef, ast.AsyncFunctionDef] = tree.body[0]
        return SonarCognitiveComplexityVisitor.calculate_for_function(target_fn)
    return SonarCognitiveComplexityVisitor.calculate(tree, func_name=func_name)


# ==============================================================================
# 1. EXEMPLES OFFICIELS DU LIVRE BLANC SONARSOURCE (G. Ann Campbell)
# ==============================================================================

class TestSonarSourceWhitePaperOfficialExamples:
    """Valide les exemples de référence décrits dans le livre blanc officiel SonarSource."""

    def test_white_paper_page10_get_words_switch_case(self) -> None:
        """
        Livre Blanc SonarSource - Page 10 :
        getWords(int number) - La structure switch et l'ensemble de ses clauses case
        n'engendre qu'un seul incrément structurel (+1), contrairement à la complexité cyclomatique (+4).
        """
        code = """
def get_words(number: int) -> str:
    match number:
        case 1:
            return "one"
        case 2:
            return "a couple"
        case 3:
            return "a few"
        case _:
            return "lots"
"""
        assert compute_complexity(code) == 1

    def test_white_paper_page10_sum_of_primes(self) -> None:
        """
        Livre Blanc SonarSource - Page 10 :
        sumOfPrimes(int max) - Boucles for imbriquées et condition if :
        - for externe : +1 (nesting 0)
        - for interne : +2 (nesting 1)
        - if interne  : +3 (nesting 2)
        Total = 6 en Python (les breaks/continues sans label ne sont pas surtaxés).
        """
        code = """
def sum_of_primes(max_val: int) -> int:
    total: int = 0
    for i in range(1, max_val + 1):  # +1
        for j in range(2, i):        # +2 (nesting = 1)
            if i % j == 0:           # +3 (nesting = 2)
                break
        total += i
    return total
"""
        assert compute_complexity(code) == 6

    def test_white_paper_page9_nesting_and_catch(self) -> None:
        """
        Livre Blanc SonarSource - Page 9 :
        Nesting structurel et gestion des exceptions :
        - try : +0 (non comptabilisé)
        - if condition1 : +1 (nesting 0)
        - for loop      : +2 (nesting 1)
        - while loop    : +3 (nesting 2)
        - catch clause  : +1 (nesting 0)
        - if condition2 : +2 (nesting 1)
        Total = 1 + 2 + 3 + 1 + 2 = 9.
        """
        code = """
def my_method() -> None:
    try:
        if condition1:                  # +1
            for i in range(10):         # +2 (nesting = 1)
                while condition2:       # +3 (nesting = 2)
                    pass
    except (ValueError, TypeError):     # +1 (nesting = 0, peu importe le nombre de types)
        if condition2:                  # +2 (nesting = 1)
            pass
"""
        assert compute_complexity(code) == 9

    def test_white_paper_page7_boolean_sequence_single_operator(self) -> None:
        """
        Livre Blanc SonarSource - Page 7 :
        Une séquence d'opérateurs identiques (a and b and c and d) ne compte que pour 1 point.
        """
        code_and = "res = a and b and c and d"
        code_or = "res = a or b or c or d"
        assert compute_complexity(code_and) == 1
        assert compute_complexity(code_or) == 1

    def test_white_paper_page8_boolean_mixed_operators(self) -> None:
        """
        Livre Blanc SonarSource - Page 8 :
        if (a && b && c || d || e && f) :
        - if          : +1
        - && sequence : +1
        - || transition : +1
        - && transition : +1
        Total = 4.
        """
        code = """
if (a and b and c or d or e and f):
    pass
"""
        assert compute_complexity(code) == 4

    def test_white_paper_page8_boolean_negated_nested_sequence(self) -> None:
        """
        Livre Blanc SonarSource - Page 8 :
        if (a && !(b && c)) :
        - if                 : +1
        - && externe         : +1
        - && interne dans not: +1
        Total = 3.
        """
        code = """
if (a and not (b and c)):
    pass
"""
        assert compute_complexity(code) == 3

    def test_white_paper_page15_decorator_pure(self) -> None:
        """
        Livre Blanc SonarSource - Annexe A (Page 15) :
        Exception décorateur Python pur (ne contient qu'une fonction imbriquée et un return) :
        Le niveau de nesting n'est pas incrémenté (+0 nesting).
        - if condition : +1 (nesting = 0)
        Total = 1.
        """
        code = """
def a_decorator(a: int, b: str):
    def inner(func):
        if condition:          # +1 (nesting = 0 grâce à l'exception décorateur)
            print(b)
        func()
    return inner
"""
        assert compute_complexity(code) == 1

    def test_white_paper_page15_decorator_not_pure(self) -> None:
        """
        Livre Blanc SonarSource - Annexe A (Page 15) :
        Fonction non pure décoratrice (présence de my_var = a * b avant la fonction imbriquée) :
        La fonction imbriquée incrémente le niveau de nesting (+1 nesting).
        - if condition : +2 (1 structure + 1 nesting)
        Total = 2.
        """
        code = """
def not_a_decorator(a: int, b: str):
    my_var: int = a * 2
    def inner(func):
        if condition:          # +2 (1 structure + 1 nesting)
            print(b)
        func()
    return inner
"""
        assert compute_complexity(code) == 2

    def test_white_paper_page15_decorator_generator(self) -> None:
        """
        Livre Blanc SonarSource - Annexe A (Page 15) :
        Générateur de décorateur avec double imbrication pure :
        Toutes deux éligibles à l'exception -> nesting = 0.
        Total = 1.
        """
        code = """
def decorator_generator(a: int):
    def generator(func):
        def decorator(func):
            if condition:        # +1 (nesting = 0)
                print(a)
            return func()
        return decorator
    return generator
"""
        assert compute_complexity(code) == 1

    def test_white_paper_appendix_c_java_symbol(self) -> None:
        """
        Livre Blanc SonarSource - Annexe C (Page 17) :
        Exemple de référence 'overriddenSymbolFrom' extrait de SonarJava :
        - if isUnknown()           : +1
        - for overrideSymbol       : +1
        - if isKind && !isStatic   : +2 (nesting 1) + 1 (logical seq) = +3
        - if canOverride           : +3 (nesting 2)
        - if overriding == null    : +4 (nesting 3)
        - if !unknownFound         : +5 (nesting 4)
        - elif overriding          : +1 (hybrid increment sur elif)
        - if unknownFound          : +1 (nesting 0)
        Total = 1 + 1 + 3 + 3 + 4 + 5 + 1 + 1 = 19.
        """
        code = """
def overridden_symbol_from(class_type):
    if class_type.is_unknown():                                         # +1
        return None
    unknown_found: bool = False
    symbols = class_type.get_symbols()
    for override_symbol in symbols:                                     # +1
        if override_symbol.is_mth and not override_symbol.is_static:    # +2 (nesting 1) + 1 (&& seq)
            if can_override(override_symbol):                           # +3 (nesting 2)
                overriding = check_overriding(override_symbol)
                if overriding is None:                                  # +4 (nesting 3)
                    if not unknown_found:                               # +5 (nesting 4)
                        unknown_found = True
                elif overriding:                                        # +1 (hybrid increment)
                    return override_symbol
    if unknown_found:                                                   # +1
        return None
    return None
"""
        assert compute_complexity(code) == 19

    def test_white_paper_appendix_c_to_regexp(self) -> None:
        """
        Livre Blanc SonarSource - Annexe C (Page 19) :
        Exemple de référence 'toRegexp' extrait de WildcardPattern (SonarQube) :
        - ternary if (starts / starts) : +1 (ternary) + 1 (or seq) = +2
        - while loop                   : +1 (nesting 0)
        - if special chars             : +2 (nesting 1)
        - elif ch == '*'               : +1 (hybrid)
        - if i + 1 < len && ch == '*'  : +3 (nesting 2) + 1 (&& seq) = +4
        - if i + 2 < len && isSlash    : +4 (nesting 3) + 1 (&& seq) = +5
        - else                         : +1 (hybrid)
        - else                         : +1 (hybrid)
        - elif ch == '?'               : +1 (hybrid)
        - elif isSlash(ch)             : +1 (hybrid)
        - else                         : +1 (hybrid)
        Total = 2 + 1 + 2 + 1 + 4 + 5 + 1 + 1 + 1 + 1 + 1 = 20.
        """
        code = """
def to_regexp(ant_pattern: str, directory_separator: str) -> str:
    escaped: str = "\\\\" + directory_separator
    i: int = 1 if (ant_pattern.startswith("/") or ant_pattern.startswith("\\\\")) else 0 # +1 (ternary) + 1 (or)
    while i < len(ant_pattern):                                       # +1
        ch: str = ant_pattern[i]
        if ch in SPECIAL_CHARS:                                        # +2 (nesting 1)
            sb.append("\\\\").append(ch)
        elif ch == "*":                                                # +1 (hybrid increment)
            if i + 1 < len(ant_pattern) and ant_pattern[i+1] == "*":  # +3 (nesting 2) + 1 (&&)
                if i + 2 < len(ant_pattern) and is_slash(ant_pattern[i+2]): # +4 (nesting 3) + 1 (&&)
                    sb.append("(?:.*" + escaped + "|)")
                    i += 2
                else:                                                  # +1 (hybrid increment)
                    sb.append(".*")
                    i += 1
            else:                                                      # +1 (hybrid increment)
                sb.append("[^" + escaped + "]*?")
        elif ch == "?":                                                # +1 (hybrid increment)
            sb.append("[^" + escaped + "]")
        elif is_slash(ch):                                             # +1 (hybrid increment)
            sb.append(escaped)
        else:                                                          # +1 (hybrid increment)
            sb.append(ch)
        i += 1
    return "".join(sb)
"""
        assert compute_complexity(code) == 20


# ==============================================================================
# 2. CORRECTION DE LA SURTAXE QUADRATIQUE DES CHAÎNES ELIF
# ==============================================================================

class TestQuadraticSurchargeElifFix:
    """Valide la stricte linéarité O(n) des chaînes d'elif et le maintien du nesting d'origine."""

    def test_flat_elif_chain_is_strictly_linear(self) -> None:
        """
        Pour N clauses elif à nesting 0, la complexité doit être 1 (if) + N (elifs).
        Avec l'ancien bug quadratique, cela produisait sum(1..N+1) = O(N^2).
        """
        # 1 if + 4 elifs + 1 else = 6 points
        code_5_branches = """
def dispatch_status(code: int) -> str:
    if code == 200:
        return "OK"
    elif code == 201:
        return "Created"
    elif code == 400:
        return "Bad Request"
    elif code == 404:
        return "Not Found"
    elif code == 500:
        return "Internal Error"
    else:
        return "Unknown"
"""
        assert compute_complexity(code_5_branches) == 6

        # 1 if + 10 elifs = 11 points (avec bug quadratique, ce serait 66 !)
        code_10_elifs = """
def large_dispatcher(x: int) -> int:
    if x == 0: return 0
    elif x == 1: return 1
    elif x == 2: return 2
    elif x == 3: return 3
    elif x == 4: return 4
    elif x == 5: return 5
    elif x == 6: return 6
    elif x == 7: return 7
    elif x == 8: return 8
    elif x == 9: return 9
    elif x == 10: return 10
"""
        assert compute_complexity(code_10_elifs) == 11

    def test_nested_elif_chain_preserves_origin_nesting(self) -> None:
        """
        Chaîne elif imbriquée dans une boucle for (nesting d'origine = 1) :
        - for : +1 (nesting 0)
        - if  : +2 (1 + nesting 1)
        - elif: +1 (hybrid increment, nesting de la chaîne maintenu)
        - elif: +1
        - else: +1
        Total = 1 + 2 + 1 + 1 + 1 = 6.
        """
        code = """
def process_items(items):
    for item in items:         # +1 (nesting 0)
        if item.type == 'A':   # +2 (nesting 1)
            handle_a(item)
        elif item.type == 'B': # +1 (hybrid increment)
            handle_b(item)
        elif item.type == 'C': # +1 (hybrid increment)
            handle_c(item)
        else:                  # +1 (hybrid increment)
            handle_other(item)
"""
        assert compute_complexity(code) == 6

    def test_nested_structures_inside_elifs_get_proper_nesting(self) -> None:
        """
        Vérifie qu'un if imbriqué DANS un bloc elif reçoit origin_nesting + 1 :
        - for loop   : +1 (nesting 0)
        - if         : +2 (nesting 1)
        - elif       : +1 (hybrid increment)
          - if inner : +3 (1 structure + nesting 2)
        - else       : +1 (hybrid increment)
        Total = 1 + 2 + 1 + 3 + 1 = 8.
        """
        code = """
for item in items:         # +1 (nesting 0)
    if item > 10:          # +2 (nesting 1)
        pass
    elif item > 5:         # +1 (hybrid increment)
        if item == 7:      # +3 (nesting = origin 1 + 1 = 2)
            pass
    else:                  # +1 (hybrid increment)
        pass
"""
        assert compute_complexity(code) == 8


# ==============================================================================
# 3. RÈGLE OFFICIELLE DES SÉQUENCES BOOLÉENNES (AND / OR)
# ==============================================================================

class TestBooleanSequencesAndTransitions:
    """Vérifie l'application rigoureuse des séquences booléennes et transitions d'opérateurs."""

    def test_single_operator_chain(self) -> None:
        """Chaîne d'opérateurs identiques = 1 point."""
        assert compute_complexity("x = a and b and c and d and e") == 1
        assert compute_complexity("x = a or b or c or d or e") == 1

    def test_single_transition_and_to_or(self) -> None:
        """Transition de and vers or = 2 points."""
        # a and b (seq 1) or c (transition vers or -> seq 2)
        assert compute_complexity("x = a and b or c") == 2

    def test_single_transition_or_to_and(self) -> None:
        """Transition de or vers and = 2 points."""
        assert compute_complexity("x = a or b and c") == 2

    def test_multiple_transitions(self) -> None:
        """Transitions alternées : and -> or -> and -> or = 4 points."""
        assert compute_complexity("x = a and b or c and d or e") == 4

    def test_parenthesized_boolean_groups(self) -> None:
        """Groupements parenthésés : (a and b) or (c and d) = 3 points (and -> or -> and)."""
        assert compute_complexity("x = (a and b) or (c and d)") == 3

    def test_boolean_sequences_in_control_structures(self) -> None:
        """Séquences booléennes dans des structures de contrôle if et while."""
        code_if = """
if (a and b and c and d):
    pass
"""
        # if = +1, sequence and = +1 -> total = 2
        assert compute_complexity(code_if) == 2

        code_while = """
while (a or b and c):
    pass
"""
        # while = +1, or -> and = +2 -> total = 3
        assert compute_complexity(code_while) == 3

    def test_boolean_in_assignments_returns_and_calls(self) -> None:
        """Les séquences booléennes sont comptabilisées partout dans le code."""
        code_return = "return a and b or c"
        assert compute_complexity(code_return) == 2

        code_call = "foo(a and b and c, d or e)"
        # premier arg = 1, deuxième arg = 1 -> total = 2
        assert compute_complexity(code_call) == 2


# ==============================================================================
# 4. PATTERN MATCHING PYTHON 3.10+ (MATCH / MATCH_CASE ET GUARDS)
# ==============================================================================

class TestPython310PatternMatching:
    """Valide l'évaluation de complexité cognitive sur le structural pattern matching."""

    def test_match_without_guards(self) -> None:
        """Un match avec plusieurs cas sans guard n'ajoute que +1 (structure de sélection)."""
        code = """
def match_color(color: str) -> str:
    match color:
        case "red":
            return "#FF0000"
        case "green":
            return "#00FF00"
        case "blue":
            return "#0000FF"
        case _:
            return "#000000"
"""
        assert compute_complexity(code) == 1

    def test_match_with_guard(self) -> None:
        """
        Un cas avec un guard (if condition) est un branchement conditionnel :
        - match : +1 (nesting 0)
        - guard : +2 (1 structure + nesting 1)
        Total = 3.
        """
        code = """
def match_number(val: int) -> str:
    match val:
        case n if n > 100:     # +1 match, +2 guard (nesting 1)
            return "large"
        case n if n > 0:       # +2 guard (nesting 1)
            return "positive"
        case _:
            return "non-positive"
"""
        # match (+1), guard 1 (+2), guard 2 (+2) = 5
        assert compute_complexity(code) == 5

    def test_match_with_boolean_guard(self) -> None:
        """Guard contenant une séquence logique booléenne."""
        code = """
match val:
    case (x, y) if x > 0 and y > 0: # match: +1, guard: +2, and seq: +1 -> 4
        return True
    case _:
        return False
"""
        assert compute_complexity(code) == 4

    def test_nested_match(self) -> None:
        """Match imbriqué dans un autre match : outer = +1, inner = +2 (nesting 1). Total = 3."""
        code = """
match outer_val:
    case 1:
        match inner_val:       # +2 (nesting = 1)
            case "a":
                pass
    case _:
        pass
"""
        assert compute_complexity(code) == 3


# ==============================================================================
# 5. EXPRESSIONS TERNAIRES (IFEXP)
# ==============================================================================

class TestTernaryExpressionsIfExp:
    """Valide les expressions ternaires (IfExp)."""

    def test_standalone_ifexp(self) -> None:
        """Expression ternaire au niveau racine : +1."""
        assert compute_complexity("x = 10 if condition else 20") == 1

    def test_ifexp_with_boolean_test(self) -> None:
        """Expression ternaire avec condition booléenne : 1 (ternary) + 1 (and) = 2."""
        assert compute_complexity("x = 10 if (a and b) else 20") == 2

    def test_nested_ifexp_in_loop(self) -> None:
        """Expression ternaire imbriquée dans une boucle for : 1 (for) + 2 (ternary nesting 1) = 3."""
        code = """
for item in items:
    val = item if item > 0 else 0
"""
        assert compute_complexity(code) == 3

    def test_chained_ternaries(self) -> None:
        """Expressions ternaires chaînées : a if c1 else (b if c2 else d) = 1 + 2 = 3."""
        assert compute_complexity("x = 1 if c1 else (2 if c2 else 3)") == 3


# ==============================================================================
# 6. COMPRÉHENSIONS (LISTCOMP, DICTCOMP, SETCOMP, GENERATOREXP)
# ==============================================================================

class TestComprehensions:
    """Valide le calcul de complexité des compréhensions de données."""

    def test_simple_listcomp(self) -> None:
        """Compréhension de liste simple sans filtre : +1 (boucle génératrice)."""
        assert compute_complexity("res = [x * 2 for x in numbers]") == 1

    def test_listcomp_with_if_filter(self) -> None:
        """Compréhension avec filtre conditionnel : 1 (générateur) + 2 (filtre if imbriqué) = 3."""
        assert compute_complexity("res = [x for x in numbers if x > 0]") == 3

    def test_listcomp_with_boolean_filter(self) -> None:
        """Compréhension avec filtre et condition booléenne : 1 (for) + 2 (if) + 1 (and seq) = 4."""
        assert compute_complexity("res = [x for x in numbers if x > 0 and x < 100]") == 4

    def test_multi_generator_listcomp(self) -> None:
        """Compréhension avec double boucle génératrice : 1 (1er for) + 2 (2ème for imbriqué) = 3."""
        assert compute_complexity("res = [x for row in matrix for x in row]") == 3

    def test_dict_set_generator_expressions(self) -> None:
        """Vérifie DictComp, SetComp et GeneratorExp avec filtre if."""
        dict_comp = "d = {k: v for k, v in pairs if k is not None}"
        set_comp = "s = {x for x in items if x % 2 == 0}"
        gen_exp = "g = (x for x in items if x > 0)"

        assert compute_complexity(dict_comp) == 3
        assert compute_complexity(set_comp) == 3
        assert compute_complexity(gen_exp) == 3


# ==============================================================================
# 7. BOUCLES ASYNCHRONES (ASYNCFOR)
# ==============================================================================

class TestAsyncForLoops:
    """Valide les boucles for asynchrones (AsyncFor)."""

    def test_async_for_standalone(self) -> None:
        """Boucle async for simple : +1."""
        code = """
async def stream_data():
    async for item in async_iterator():
        process(item)
"""
        assert compute_complexity(code) == 1

    def test_async_for_nested_in_async_for(self) -> None:
        """Boucles async for imbriquées : 1 + 2 = 3."""
        code = """
async def nested_stream():
    async for chunk in source():       # +1 (nesting 0)
        async for byte in chunk:       # +2 (nesting 1)
            consume(byte)
"""
        assert compute_complexity(code) == 3

    def test_async_for_with_else(self) -> None:
        """Boucle async for avec clause alternative else : 1 (async for) + 1 (else) = 2."""
        code = """
async def stream_with_else():
    async for item in async_iterator():
        if item.is_target:
            break
    else:
        log_missing()
"""
        # async for (+1), if (+2), else (+1) = 4
        assert compute_complexity(code) == 4


# ==============================================================================
# 8. RÉCURSION DIRECTE (INCÉMENT FONDAMENTAL +1)
# ==============================================================================

class TestDirectRecursion:
    """Valide l'attribution d'un incrément fondamental unique (+1) pour la récursion directe."""

    def test_factorial_direct_recursion(self) -> None:
        """
        Fonction récursive directe (factorielle) :
        - if n <= 1       : +1 (nesting 0)
        - récursion direct: +1 fondamental
        Total = 2.
        """
        code = """
def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)
"""
        assert compute_complexity(code) == 2

    def test_fibonacci_multiple_recursive_calls_counted_once(self) -> None:
        """
        Fonction de Fibonacci avec multiples appels récursifs dans la même fonction :
        L'incrément de récursion (+1) ne doit être comptabilisé qu'une seule fois.
        - if n <= 1       : +1 (nesting 0)
        - récursion direct: +1 fondamental (unique)
        Total = 2.
        """
        code = """
def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
"""
        assert compute_complexity(code) == 2

    def test_method_self_recursion(self) -> None:
        """Méthode de classe s'appelant via self.method_name(...)."""
        code = """
class Solver:
    def binary_search(self, arr, target, low, high):
        if low > high:
            return -1
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] > target:
            return self.binary_search(arr, target, low, mid - 1)
        else:
            return self.binary_search(arr, target, mid + 1, high)
"""
        # Dans Solver :
        # if low > high : +1
        # if arr[mid] == target : +1
        # elif arr[mid] > target : +1
        # else : +1
        # self.binary_search recursion : +1
        # Total = 5
        tree = ast.parse(code)
        method_node = tree.body[0].body[0]  # binary_search
        assert SonarCognitiveComplexityVisitor.calculate_for_function(method_node) == 5

    def test_non_recursive_function_no_bonus(self) -> None:
        """Une fonction appelant une autre fonction ne reçoit aucun incrément de récursion."""
        code = """
def compute_area(r: float) -> float:
    if r < 0:
        return 0.0
    return math.pi * helper_square(r)
"""
        assert compute_complexity(code) == 1
