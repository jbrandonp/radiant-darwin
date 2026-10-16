"""
Module d'Analyse Statique de Sécurité (SAST) Déterministe pour Noyau CAO/FAO Industriel 3D.
Conforme aux standards ISO 25010, CWE / SANS Top 25 et OWASP Top 10.
Typage statique strict : strictement zéro Any et zéro object.
100% autonome et sans dépendance externe (uniquement la bibliothèque standard Python).
"""

from __future__ import annotations
import ast
import os
import sys
import re
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Union, Sequence, Callable


class SecuritySeverity(Enum):
    """Niveaux formels de criticité des vulnérabilités de sécurité selon CVSS v3.1."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class SecurityCategory(Enum):
    """Catégories CWE de sécurité ciblées pour les systèmes industriels de CAO/FAO 3D."""
    CODE_INJECTION = "CWE-94: Code Injection"
    COMMAND_INJECTION = "CWE-78: Command Injection"
    UNSAFE_DESERIALIZATION = "CWE-502: Unsafe Deserialization"
    PATH_TRAVERSAL = "CWE-22: Path Traversal / Zip Slip"
    RESOURCE_EXHAUSTION = "CWE-400: Uncontrolled Resource Consumption / Geometric DoS"
    REGEX_DOS = "CWE-1333: Inefficient Regular Expression Complexity / ReDoS"
    NATIVE_MEMORY_HAZARD = "CWE-119: Native Memory Buffer Hazard & Leak"
    UNVALIDATED_NUMERIC = "CWE-682: Incorrect Numeric Calculation / NaN Injection"


@dataclass(frozen=True)
class SecurityFinding:
    """Description formelle et immuable d'une anomalie ou vulnérabilité SAST détectée."""
    rule_id: str
    category: SecurityCategory
    severity: SecuritySeverity
    line_number: int
    column_offset: int
    message: str
    recommendation: str
    code_snippet: str = ""


# ==============================================================================
# Fonctions de Validation et Assainissement à l'Exécution (Runtime Helpers)
# Zéro Any, Zéro object, 100% Bibliothèque Standard
# ==============================================================================

def validate_safe_cadz_path(target_directory: str, member_name: str) -> str:
    """
    Valide et résout de manière sécurisée le chemin d'un fichier extrait d'une archive .cadz.
    Contre formellement les attaques de type Zip Slip via os.path.commonpath.

    :param target_directory: Répertoire de destination de l'extraction.
    :param member_name: Nom du membre d'archive extrait (peut contenir des chemins relatifs).
    :return: Chemin absolu sécurisé et garanti confiné dans target_directory.
    :raises ValueError: Si une tentative d'évasion de répertoire (Zip Slip) est détectée.
    """
    abs_target_dir = os.path.abspath(target_directory)
    # Nettoyage des préfixes obliques et séparateurs absolus
    clean_member = member_name.lstrip("/\\")
    destination_path = os.path.abspath(os.path.join(abs_target_dir, clean_member))

    common = os.path.commonpath([abs_target_dir, destination_path])
    if common != abs_target_dir:
        raise ValueError(
            f"Zip Slip détecté : le membre '{member_name}' tente d'écrire hors de '{abs_target_dir}'."
        )
    return destination_path


def validate_cad_filepath(
    filepath: str,
    allowed_extensions: Tuple[str, ...],
    base_directory: Optional[str] = None
) -> str:
    """
    Valide l'extension et le confinement d'un chemin de fichier pour importateur/exportateur CAD (STL, STEP, DXF).

    :param filepath: Chemin cible fourni par l'utilisateur ou l'API.
    :param allowed_extensions: Tuple des extensions autorisées (ex: ('.stl', '.step', '.stp', '.dxf')).
    :param base_directory: Répertoire racine de confinement optionnel.
    :return: Chemin absolu normalisé et validé.
    :raises ValueError: En cas d'extension non autorisée ou de traversée de répertoire.
    """
    clean_path = filepath.strip()
    lower_path = clean_path.lower()

    # 1. Vérification de l'extension autorisée
    has_valid_ext = any(lower_path.endswith(ext.lower()) for ext in allowed_extensions)
    if not has_valid_ext:
        raise ValueError(
            f"Extension de fichier CAD non autorisée pour '{filepath}'. Extensions admises : {allowed_extensions}"
        )

    abs_path = os.path.abspath(clean_path)

    # 2. Confinement au répertoire de base si spécifié
    if base_directory is not None:
        abs_base = os.path.abspath(base_directory)
        common = os.path.commonpath([abs_base, abs_path])
        if common != abs_base:
            raise ValueError(
                f"Path Traversal CAD détecté : '{filepath}' pointe hors du répertoire de base autorisé '{base_directory}'."
            )

    return abs_path


def analyze_regex_redos_risk(pattern_str: str) -> Tuple[bool, str]:
    """
    Analyse statique déterministe d'un motif d'expression régulière pour détecter
    les risques de ReDoS (Regular Expression Denial of Service) par retour sur trace exponentiel.
    Identifie les quantificateurs imbriqués (ex: (a+)+, (?:[^']*'[^']*')*) et jokers non bornés.

    :param pattern_str: Chaîne de caractères de l'expression régulière.
    :return: Tuple (est_a_risque, explication_detaillee).
    """
    in_char_class = False
    escaped = False
    stack: List[Dict[str, Union[int, bool]]] = []
    i = 0

    while i < len(pattern_str):
        ch = pattern_str[i]
        if escaped:
            escaped = False
            i += 1
            continue
        if ch == "\\":
            escaped = True
            i += 1
            continue
        if in_char_class:
            if ch == "]":
                in_char_class = False
            i += 1
            continue
        if ch == "[":
            in_char_class = True
            i += 1
            continue

        if ch == "(":
            stack.append({"start": i, "has_inner_quantifier": False})
            i += 1
            continue
        elif ch == ")":
            if stack:
                grp_info = stack.pop()
                grp_start_raw = grp_info["start"]
                grp_start = grp_start_raw if isinstance(grp_start_raw, int) else 0
                grp_has_quant_raw = grp_info["has_inner_quantifier"]
                grp_has_quant = bool(grp_has_quant_raw)

                next_i = i + 1
                outer_quantifier = ""
                if next_i < len(pattern_str) and pattern_str[next_i] in ("+", "*"):
                    outer_quantifier = pattern_str[next_i]
                elif next_i < len(pattern_str) and pattern_str[next_i] == "{":
                    close_brace = pattern_str.find("}", next_i)
                    if close_brace != -1:
                        outer_quantifier = pattern_str[next_i:close_brace + 1]

                # Répétition d'un groupe contenant lui-même un quantificateur
                if outer_quantifier and grp_has_quant:
                    snippet = pattern_str[grp_start:i + 1] + outer_quantifier
                    return (
                        True,
                        f"Répétition imbriquée à risque de ReDoS exponentiel : '{snippet}'"
                    )

                if stack and (grp_has_quant or bool(outer_quantifier)):
                    stack[-1]["has_inner_quantifier"] = True
            i += 1
            continue
        elif ch in ("+", "*"):
            if stack:
                stack[-1]["has_inner_quantifier"] = True
            i += 1
            continue
        elif ch == "{":
            close_brace = pattern_str.find("}", i)
            if close_brace != -1:
                if stack:
                    stack[-1]["has_inner_quantifier"] = True
                i = close_brace + 1
                continue
            i += 1
            continue
        i += 1

    return (False, "Pattern conforme (aucun motif ReDoS exponentiel détecté)")


def is_sliver_triangle(
    p0: Tuple[float, float, float],
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float],
    aspect_ratio_threshold: float = 100.0
) -> bool:
    """
    Détermine si un triangle 3D est effilé (sliver triangle) ou dégénéré.
    Calcule le rapport d'aspect rayon circonscrit / rayon inscrit (R / (2*r)).

    :param p0: Coordonnées 3D du premier sommet (x, y, z).
    :param p1: Coordonnées 3D du deuxième sommet (x, y, z).
    :param p2: Coordonnées 3D du troisième sommet (x, y, z).
    :param aspect_ratio_threshold: Seuil au-delà duquel le triangle est considéré comme sliver.
    :return: True si le triangle est effilé ou dégénéré (risque de Geometric DoS), False sinon.
    """
    # Longueurs des arêtes
    d01 = math.sqrt((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2 + (p1[2] - p0[2]) ** 2)
    d12 = math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2 + (p2[2] - p1[2]) ** 2)
    d20 = math.sqrt((p0[0] - p2[0]) ** 2 + (p0[1] - p2[1]) ** 2 + (p0[2] - p2[2]) ** 2)

    s = (d01 + d12 + d20) * 0.5
    heron_val = s * (s - d01) * (s - d12) * (s - d20)

    # Aire nulle ou dégénérescence colinéaire
    if heron_val <= 1e-18:
        return True

    area = math.sqrt(heron_val)
    if area <= 1e-9:
        return True

    # Rayon inscrit r = Aire / demi-périmètre
    r_in = area / s if s > 1e-12 else 0.0
    if r_in <= 1e-12:
        return True

    # Rayon circonscrit R = (a * b * c) / (4 * Aire)
    r_circ = (d01 * d12 * d20) / (4.0 * area)

    # Ratio d'aspect normalisé (1.0 pour un triangle équilatéral, tend vers l'infini pour un sliver)
    aspect_ratio = r_circ / (2.0 * r_in)
    return aspect_ratio > aspect_ratio_threshold


def validate_opengl_draw_elements_bounds(count: int, buffer_element_count: int) -> bool:
    """
    Contrôle l'intégrité mémoire d'un appel glDrawElements.
    Empêche les dépassements de tampons graphiques et les crashes GPU natifs.

    :param count: Nombre d'éléments requis pour le tracé OpenGL.
    :param buffer_element_count: Capacité réelle du tableau d'indices alloué.
    :return: True si l'appel respecte strictement les bornes mémoires allouées, False sinon.
    """
    if count <= 0:
        return False
    if count > buffer_element_count:
        return False
    return True


# ==============================================================================
# Visiteur AST Principal du Scanner SAST
# ==============================================================================

class SecuritySASTVisitor(ast.NodeVisitor):
    """
    Analyseur syntaxique AST déterministe pour la sécurité d'un noyau CAO/FAO 3D.
    Gère la résolution d'alias d'imports, le suivi des sinks dangereux et
    les motifs de vulnérabilités spécifiques aux formats 3D et liaisons natives.
    """

    def __init__(self, filename: str = "<unknown>", source_code: str = "") -> None:
        self.filename: str = filename
        self.source_code: str = source_code
        self.lines: List[str] = source_code.splitlines() if source_code else []
        self.findings: List[SecurityFinding] = []
        self._reported_keys: Set[Tuple[str, int]] = set()

        # Tables de résolution des alias d'importation
        self.module_aliases: Dict[str, str] = {}
        self.function_aliases: Dict[str, Tuple[str, str]] = {}
        self.local_string_vars: Dict[str, str] = {}

        # Contexte syntaxique courant
        self.current_class_name: Optional[str] = None
        self.current_function_name: Optional[str] = None
        self.current_function_node: Optional[Union[ast.FunctionDef, ast.AsyncFunctionDef]] = None

        # Propriétés de sécurité du scope de fonction actif
        self.scope_has_commonpath: bool = False
        self.scope_has_extension_check: bool = False
        self.scope_has_buffer_bounds_check: bool = False
        self.scope_has_epsilon_guard: bool = False
        self.scope_is_cad_importer_exporter: bool = False
        self.scope_is_cadz_context: bool = False

    # --------------------------------------------------------------------------
    # 1. Gestion des contextes de classe et fonction
    # --------------------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        prev_class = self.current_class_name
        self.current_class_name = node.name
        self.generic_visit(node)
        self.current_class_name = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter_function_scope(node)
        self.generic_visit(node)
        self._exit_function_scope()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter_function_scope(node)
        self.generic_visit(node)
        self._exit_function_scope()

    def visit_Assign(self, node: ast.Assign) -> None:
        val_str = self._extract_constant_str(node.value)
        if val_str is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.local_string_vars[target.id] = val_str
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            val_str = self._extract_constant_str(node.value)
            if val_str is not None and isinstance(node.target, ast.Name):
                self.local_string_vars[node.target.id] = val_str
        self.generic_visit(node)

    def _enter_function_scope(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> None:
        """Initialise et pré-analyse le contexte de sécurité de la fonction courante."""
        self.current_function_name = node.name
        self.current_function_node = node
        self.local_string_vars.clear()

        fn_name_lower = node.name.lower()
        class_name = self.current_class_name or ""

        # Identification du contexte d'importateur / exportateur CAD
        cad_keywords = (
            "export_stl", "export_step", "export_dxf", "export_obj", "export_ply",
            "export_iges", "export_gltf", "export_brep", "import_step", "import_stl",
            "import_dxf", "import_iges", "load_step", "load_stl", "load_dxf",
            "save_dxf", "save_step"
        )
        self.scope_is_cad_importer_exporter = (
            any(k in fn_name_lower for k in cad_keywords) or
            any(c_kw in class_name for c_kw in ("Exporter", "Importer"))
        )

        # Identification du contexte d'archives de projet .cadz
        docstring = ast.get_docstring(node) or ""
        self.scope_is_cadz_context = (
            "cadz" in fn_name_lower or
            "cadz" in docstring.lower() or
            any(
                isinstance(c, ast.Constant) and isinstance(c.value, str) and ".cadz" in c.value.lower()
                for c in ast.walk(node)
            )
        )

        # Détection de la présence d'appels de validation formelle (commonpath, is_relative_to)
        self.scope_has_commonpath = any(
            isinstance(call, ast.Call) and (
                (isinstance(call.func, ast.Name) and call.func.id in ("commonpath", "validate_safe_cadz_path", "validate_cad_filepath")) or
                (isinstance(call.func, ast.Attribute) and call.func.attr in ("commonpath", "is_relative_to", "validate_safe_cadz_path"))
            )
            for call in ast.walk(node)
        )

        # Détection de vérification d'extension de fichier
        self.scope_has_extension_check = any(
            isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and (
                call.func.attr.lower() in ("endswith", "endswiths") or
                (isinstance(call.func.value, ast.Attribute) and call.func.value.attr.lower() in ("suffix", "suffixes"))
            )
            for call in ast.walk(node)
        )

        # Détection de garde de bornes de tampons mémoires / GPU
        self.scope_has_buffer_bounds_check = any(
            (isinstance(call, ast.Call) and (
                (isinstance(call.func, ast.Attribute) and call.func.attr in ("is_empty", "empty", "validate_opengl_draw_elements_bounds")) or
                (isinstance(call.func, ast.Name) and call.func.id in ("len", "validate_opengl_draw_elements_bounds"))
            )) or
            isinstance(call, ast.Assert)
            for call in ast.walk(node)
        )

        # Détection de seuil epsilon contre les divisions par zéro
        self.scope_has_epsilon_guard = any(
            isinstance(comp, ast.Compare) and any(
                isinstance(op, (ast.Lt, ast.Gt, ast.LtE, ast.GtE, ast.Eq, ast.NotEq))
                for op in comp.ops
            )
            for comp in ast.walk(node)
        ) or any(
            isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "max"
            for call in ast.walk(node)
        )

    def _exit_function_scope(self) -> None:
        """Restaure l'état syntaxique en quittant une fonction."""
        self.current_function_name = None
        self.current_function_node = None
        self.scope_has_commonpath = False
        self.scope_has_extension_check = False
        self.scope_has_buffer_bounds_check = False
        self.scope_has_epsilon_guard = False
        self.scope_is_cad_importer_exporter = False
        self.scope_is_cadz_context = False

    def _add_finding(
        self,
        rule_id: str,
        category: SecurityCategory,
        severity: SecuritySeverity,
        node: ast.AST,
        message: str,
        recommendation: str
    ) -> None:
        """Enregistre un résultat d'audit unique sans doublon par ligne."""
        lineno = getattr(node, "lineno", 1)
        col_offset = getattr(node, "col_offset", 0)
        key = (rule_id, lineno)

        if key in self._reported_keys:
            return
        self._reported_keys.add(key)

        snippet = ""
        if self.lines and 1 <= lineno <= len(self.lines):
            snippet = self.lines[lineno - 1].strip()

        # Prise en charge des suppressions formelles de sécurité (# nosec, # sast-ignore, # noqa)
        line_comment = snippet.lower()
        prev_comment = (
            self.lines[lineno - 2].strip().lower()
            if (lineno >= 2 and len(self.lines) >= lineno - 1)
            else ""
        )
        if (
            "# nosec" in line_comment
            or "# sast-ignore" in line_comment
            or "# noqa" in line_comment
            or "# nosec" in prev_comment
            or "# sast-ignore" in prev_comment
        ):
            return

        finding = SecurityFinding(
            rule_id=rule_id,
            category=category,
            severity=severity,
            line_number=lineno,
            column_offset=col_offset,
            message=message,
            recommendation=recommendation,
            code_snippet=snippet
        )
        self.findings.append(finding)

    # --------------------------------------------------------------------------
    # 2. Gestion des résolutions d'alias d'import (Anti-contournement)
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
            imported_func = alias.name
            as_name = alias.asname or imported_func
            self.function_aliases[as_name] = (mod_name, imported_func)
        self.generic_visit(node)

    # --------------------------------------------------------------------------
    # 3. Analyse des appels de fonctions et méthodes (Sinks d'injection)
    # --------------------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        resolved_name = self._resolve_callable(node.func)

        # Règle 1 : Injections de code arbitraire (eval, exec, compile)
        self._check_code_injection(node, resolved_name)

        # Règle 2 : Injections de commandes système (os.system, subprocess, etc.)
        self._check_command_injection(node, resolved_name)

        # Règle 3 : Désérialisation dangereuse (pickle, yaml, shelve)
        self._check_unsafe_deserialization(node, resolved_name)

        # Règle 4 : Zip Slip sur archives .cadz
        self._check_zip_slip_and_cadz(node, resolved_name)

        # Règle 5 : Injections de chemin (Path Traversal) dans exportateurs/importateurs STL, STEP, DXF
        self._check_cad_path_traversal(node, resolved_name)

        # Règle 6 : Risques ReDoS géométrique et parsing Regex de STEP
        self._check_regex_redos_and_step(node, resolved_name)

        # Règle 7 : Contrôle de l'intégrité des appels OpenGL natifs
        self._check_native_opengl_hazard(node, resolved_name)

        # Règle 8 : Risques mémoires ctypes et pointeurs bruts
        self._check_ctypes_hazard(node, resolved_name)

        # Règle 9 : Lectures démesurées sans quota
        self._check_geometric_dos_and_io(node, resolved_name)

        self.generic_visit(node)

    # --------------------------------------------------------------------------
    # 4. Analyse des boucles (Geometric DoS et Extractions d'archives manuelles)
    # --------------------------------------------------------------------------

    def visit_While(self, node: ast.While) -> None:
        """Détecte les boucles de raffinement de maillage infinies sans compteur sur triangles slivers."""
        fn_name = (self.current_function_name or "").lower()
        mesh_keywords = ("subdivide", "refine", "remesh", "repair", "tessellate", "triangulate", "sliver")

        if any(k in fn_name for k in mesh_keywords):
            has_iteration_limit = any(
                isinstance(n, ast.Compare) and any(
                    isinstance(name_node, ast.Name) and any(
                        limit_kw in name_node.id.lower()
                        for limit_kw in ("max", "limit", "depth", "count", "iter", "iteration")
                    )
                    for name_node in ast.walk(n)
                )
                for n in ast.walk(node)
            )
            if not has_iteration_limit:
                self._add_finding(
                    rule_id="SEC_GEOMETRIC_UNBOUNDED_SUBDIVISION",
                    category=SecurityCategory.RESOURCE_EXHAUSTION,
                    severity=SecuritySeverity.HIGH,
                    node=node,
                    message=f"Boucle 'while' de modification de maillage sans plafond d'itérations explicite dans '{self.current_function_name}'.",
                    recommendation="Imposer une borne d'itérations maximale (ex: max_iterations=100) pour prévenir le blocage CPU sur triangles effilés."
                )

        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        """Détecte l'extraction manuelle de membres d'archives sans vérification os.path.commonpath."""
        iter_name = ""
        if isinstance(node.iter, ast.Call):
            iter_name = self._resolve_callable(node.iter.func).lower()
        elif isinstance(node.iter, (ast.Name, ast.Attribute)):
            iter_name = self._resolve_callable(node.iter).lower()

        if any(archive_kw in iter_name for archive_kw in ("namelist", "infolist")):
            has_file_write = any(
                isinstance(call, ast.Call) and (
                    (isinstance(call.func, ast.Name) and call.func.id == "open") or
                    (isinstance(call.func, ast.Attribute) and call.func.attr in ("open", "write_bytes", "write_text"))
                )
                for call in ast.walk(node)
            )
            has_commonpath_in_loop = any(
                isinstance(call, ast.Call) and (
                    (isinstance(call.func, ast.Name) and call.func.id == "commonpath") or
                    (isinstance(call.func, ast.Attribute) and call.func.attr == "commonpath")
                )
                for call in ast.walk(node)
            )

            if has_file_write and not has_commonpath_in_loop and not self.scope_has_commonpath:
                self._add_finding(
                    rule_id="SEC_ZIP_SLIP_MANUAL_EXTRACTION",
                    category=SecurityCategory.PATH_TRAVERSAL,
                    severity=SecuritySeverity.HIGH,
                    node=node,
                    message="Extraction manuelle d'archive avec écriture de fichier sans vérification os.path.commonpath().",
                    recommendation="Valider chaque membre d'archive avec os.path.commonpath([dest_dir, target]) == dest_dir avant écriture."
                )

        self.generic_visit(node)

    # --------------------------------------------------------------------------
    # 5. Analyse des opérations arithmétiques (Division par zéro sur triangles slivers)
    # --------------------------------------------------------------------------

    def visit_BinOp(self, node: ast.BinOp) -> None:
        """Détecte les divisions par des normes ou aires sans seuil epsilon de sécurité."""
        if isinstance(node.op, ast.Div):
            denom_name = ""
            if isinstance(node.right, ast.Name):
                denom_name = node.right.id.lower()
            elif isinstance(node.right, ast.Call):
                denom_name = self._resolve_callable(node.right.func).lower()
            elif isinstance(node.right, ast.Attribute):
                denom_name = node.right.attr.lower()

            geometric_denominators = ("norm", "area", "length", "det", "cross", "mag", "magnitude", "height", "denom")
            if any(k in denom_name for k in geometric_denominators):
                if not self.scope_has_epsilon_guard:
                    self._add_finding(
                        rule_id="SEC_GEOMETRIC_SLIVER_DIVISION_BY_ZERO",
                        category=SecurityCategory.UNVALIDATED_NUMERIC,
                        severity=SecuritySeverity.HIGH,
                        node=node,
                        message=f"Division géométrique par '{denom_name}' sans seuil epsilon de sécurité.",
                        recommendation="Ajouter une garde de seuil (ex: if norm > 1e-9 ou max(norm, 1e-9)) pour prévenir la division par zéro sur triangles effilés."
                    )

        self.generic_visit(node)

    # --------------------------------------------------------------------------
    # 6. Méthodes d'inspection spécialisées
    # --------------------------------------------------------------------------

    def _resolve_callable(self, func_node: ast.AST) -> str:
        """Résout un noeud appelable en chaîne canonique 'module.fonction'."""
        if isinstance(func_node, ast.Name):
            func_id = func_node.id
            if func_id in self.function_aliases:
                mod, orig = self.function_aliases[func_id]
                return f"{mod}.{orig}"
            return func_id

        if isinstance(func_node, ast.Attribute):
            attr_name = func_node.attr
            if isinstance(func_node.value, ast.Name):
                target_mod = func_node.value.id
                actual_mod = self.module_aliases.get(target_mod, target_mod)
                return f"{actual_mod}.{attr_name}"
            elif isinstance(func_node.value, ast.Attribute):
                parent = self._resolve_callable(func_node.value)
                return f"{parent}.{attr_name}"
            return attr_name

        return ""

    def _extract_constant_str(self, node: ast.AST) -> Optional[str]:
        """Extrait la valeur textuelle d'un noeud constant ou d'une variable locale connue."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name) and node.id in self.local_string_vars:
            return self.local_string_vars[node.id]
        if isinstance(node, ast.JoinedStr):
            parts: List[str] = []
            for val in node.values:
                part_s = self._extract_constant_str(val)
                if part_s is not None:
                    parts.append(part_s)
            return "".join(parts) if parts else None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left_s = self._extract_constant_str(node.left)
            right_s = self._extract_constant_str(node.right)
            if left_s is not None and right_s is not None:
                return left_s + right_s
        return None

    def _check_code_injection(self, node: ast.Call, resolved: str) -> None:
        """Détecte l'exécution de code Python arbitraire."""
        if resolved in ("eval", "exec", "compile", "builtins.eval", "builtins.exec"):
            self._add_finding(
                rule_id="SEC_CODE_EXEC",
                category=SecurityCategory.CODE_INJECTION,
                severity=SecuritySeverity.CRITICAL,
                node=node,
                message=f"Appel interdit au builtin d'exécution dynamique '{resolved}()'.",
                recommendation="Utiliser un parseur AST mathématique sûr (ex: SafeExpressionEvaluator) sans eval()."
            )

    def _check_command_injection(self, node: ast.Call, resolved: str) -> None:
        """Détecte le spawning de processus système avec risques d'injections shell."""
        if resolved in ("os.system", "os.popen", "os.spawnl", "os.spawnv", "os.spawnle", "os.spawnve", "pty.spawn"):
            self._add_finding(
                rule_id="SEC_SHELL_INJECTION_OS",
                category=SecurityCategory.COMMAND_INJECTION,
                severity=SecuritySeverity.CRITICAL,
                node=node,
                message=f"Exécution directe de commande système via '{resolved}()'.",
                recommendation="Remplacer par subprocess.run() avec une liste d'arguments sans interpréteur shell."
            )

        subprocess_methods = (
            "subprocess.Popen", "subprocess.run", "subprocess.call",
            "subprocess.check_call", "subprocess.check_output"
        )
        if resolved in subprocess_methods:
            for kw in node.keywords:
                if kw.arg == "shell":
                    is_true = isinstance(kw.value, ast.Constant) and kw.value.value is True
                    is_non_literal = not isinstance(kw.value, ast.Constant)
                    if is_true or is_non_literal:
                        self._add_finding(
                            rule_id="SEC_SHELL_INJECTION_SUBPROCESS",
                            category=SecurityCategory.COMMAND_INJECTION,
                            severity=SecuritySeverity.HIGH,
                            node=node,
                            message=f"Invocation de '{resolved}' avec shell=True ou argument shell dynamique.",
                            recommendation="Passer les arguments sous forme de liste explicite [cmd, arg1, arg2] avec shell=False."
                        )

    def _check_unsafe_deserialization(self, node: ast.Call, resolved: str) -> None:
        """Détecte la désérialisation de flux non fiables permettant l'exécution de code."""
        pickle_sinks = (
            "pickle.load", "pickle.loads", "_pickle.load", "_pickle.loads",
            "cPickle.load", "cPickle.loads", "shelve.open", "marshal.load", "marshal.loads"
        )
        if resolved in pickle_sinks:
            self._add_finding(
                rule_id="SEC_UNSAFE_DESERIALIZE_PICKLE",
                category=SecurityCategory.UNSAFE_DESERIALIZATION,
                severity=SecuritySeverity.CRITICAL,
                node=node,
                message=f"Désérialisation non sécurisée détectée via '{resolved}()'.",
                recommendation="Utiliser un schéma JSON strict validé par dataclasses pour les fichiers de projet CAD."
            )

        if resolved == "yaml.load":
            has_safe_loader = False
            for kw in node.keywords:
                if kw.arg == "Loader":
                    loader_name = ast.unparse(kw.value) if hasattr(ast, "unparse") else ""
                    if "SafeLoader" in loader_name or "CSafeLoader" in loader_name:
                        has_safe_loader = True
            if not has_safe_loader and len(node.args) < 2:
                self._add_finding(
                    rule_id="SEC_UNSAFE_DESERIALIZE_YAML",
                    category=SecurityCategory.UNSAFE_DESERIALIZATION,
                    severity=SecuritySeverity.HIGH,
                    node=node,
                    message="Appel à yaml.load() sans Loader=SafeLoader explicite.",
                    recommendation="Remplacer par yaml.safe_load() pour prévenir l'instanciation de classes Python arbitraires."
                )
        elif resolved == "yaml.unsafe_load":
            self._add_finding(
                rule_id="SEC_UNSAFE_DESERIALIZE_YAML_UNSAFE",
                category=SecurityCategory.UNSAFE_DESERIALIZATION,
                severity=SecuritySeverity.CRITICAL,
                node=node,
                message="Appel explicite à yaml.unsafe_load() interdit.",
                recommendation="Remplacer par yaml.safe_load()."
            )

    def _check_zip_slip_and_cadz(self, node: ast.Call, resolved: str) -> None:
        """
        Détecte les vulnérabilités Zip Slip sur l'extraction d'archives,
        avec une surveillance critique pour les archives de projet .cadz.
        """
        attr_name = node.func.attr if isinstance(node.func, ast.Attribute) else ""
        is_extractall = resolved.endswith(".extractall") or attr_name == "extractall"
        is_extract = resolved.endswith(".extract") or attr_name == "extract"

        if is_extractall:
            # Vérifier si un filtre sécurisé data/tar est fourni sous Python 3.12+
            has_safe_filter = False
            for kw in node.keywords:
                if kw.arg == "filter":
                    if isinstance(kw.value, ast.Constant) and kw.value.value in ("data", "tar"):
                        has_safe_filter = True

            if not has_safe_filter and not self.scope_has_commonpath:
                if self.scope_is_cadz_context:
                    self._add_finding(
                        rule_id="SEC_CADZ_ARCHIVE_UNSAFE_EXTRACTION",
                        category=SecurityCategory.PATH_TRAVERSAL,
                        severity=SecuritySeverity.CRITICAL,
                        node=node,
                        message="Extraction d'archive de projet .cadz via extractall() sans validation formelle par os.path.commonpath().",
                        recommendation="Valider chaque membre avec validate_safe_cadz_path() ou vérifier os.path.commonpath([dest, target]) == dest."
                    )
                else:
                    self._add_finding(
                        rule_id="SEC_ZIP_SLIP_EXTRACTALL",
                        category=SecurityCategory.PATH_TRAVERSAL,
                        severity=SecuritySeverity.HIGH,
                        node=node,
                        message=f"Appel direct à '{resolved or attr_name}()' vulnérable aux attaques de type Zip Slip.",
                        recommendation="Valider chaque membre d'archive avec os.path.commonpath ou utiliser le filtre data sous Python 3.12+."
                    )

        elif is_extract:
            if not self.scope_has_commonpath:
                self._add_finding(
                    rule_id="SEC_ZIP_SLIP_EXTRACT",
                    category=SecurityCategory.PATH_TRAVERSAL,
                    severity=SecuritySeverity.HIGH,
                    node=node,
                    message=f"Appel à '{resolved or attr_name}()' sans vérification de confinement par os.path.commonpath.",
                    recommendation="Vérifier la destination de l'extraction avec os.path.commonpath() avant l'appel."
                )

    def _check_cad_path_traversal(self, node: ast.Call, resolved: str) -> None:
        """
        Détecte les injections de chemins (Path Traversal) dans les importateurs et exportateurs STL, STEP et DXF.
        """
        attr_name = node.func.attr if isinstance(node.func, ast.Attribute) else ""

        # Détection de concaténation de chemin non confinée dans un exportateur/importateur CAD
        if resolved in ("os.path.join", "pathlib.Path") and self.scope_is_cad_importer_exporter:
            if not self.scope_has_commonpath:
                self._add_finding(
                    rule_id="SEC_CAD_UNSAFE_PATH_JOIN",
                    category=SecurityCategory.PATH_TRAVERSAL,
                    severity=SecuritySeverity.MEDIUM,
                    node=node,
                    message="Concaténation de chemin dans une routine CAD sans validation de confinement de répertoire.",
                    recommendation="Valider le chemin assemblé avec os.path.commonpath([base_dir, target_path]) == base_dir."
                )

        # Détection des sinks d'écriture ou d'ouverture de fichiers CAD
        is_fs_sink = (
            resolved in ("open", "builtins.open", "os.makedirs", "trimesh.load") or
            attr_name in ("export", "saveas", "save", "write_bytes", "write_text")
        )

        if is_fs_sink and self.scope_is_cad_importer_exporter:
            if not self.scope_has_extension_check:
                self._add_finding(
                    rule_id="SEC_CAD_MISSING_EXTENSION_VALIDATION",
                    category=SecurityCategory.PATH_TRAVERSAL,
                    severity=SecuritySeverity.HIGH,
                    node=node,
                    message=f"Routine d'import/export CAD '{self.current_function_name}' sans vérification d'extension de fichier autorisée.",
                    recommendation="Valider formellement les extensions autorisées (.stl, .step, .stp, .dxf) via endswith() ou validate_cad_filepath()."
                )

            if not self.scope_has_commonpath:
                self._add_finding(
                    rule_id="SEC_CAD_PATH_TRAVERSAL_SINK",
                    category=SecurityCategory.PATH_TRAVERSAL,
                    severity=SecuritySeverity.HIGH,
                    node=node,
                    message=f"Sink de fichier '{resolved or attr_name}' dans un importateur/exportateur CAD sans vérification de confinement de répertoire.",
                    recommendation="Sanitiser les chemins avec os.path.basename() ou confiner la destination avec os.path.commonpath()."
                )

    def _check_regex_redos_and_step(self, node: ast.Call, resolved: str) -> None:
        """
        Détecte les risques de Geometric ReDoS dans le parsing des fichiers STEP ou la CAO 3D.
        """
        regex_funcs = ("re.compile", "re.search", "re.match", "re.split", "re.findall", "re.finditer")
        if resolved in regex_funcs and len(node.args) >= 1:
            pat_str = self._extract_constant_str(node.args[0])
            if pat_str:
                is_risk, reason = analyze_regex_redos_risk(pat_str)
                if is_risk:
                    in_step = (
                        "step" in self.filename.lower() or
                        "step" in (self.current_function_name or "").lower() or
                        "iso-10303" in self.source_code.lower()
                    )
                    sev = SecuritySeverity.CRITICAL if in_step else SecuritySeverity.HIGH
                    self._add_finding(
                        rule_id="SEC_STEP_REDOS_NESTED_QUANTIFIER",
                        category=SecurityCategory.REGEX_DOS,
                        severity=sev,
                        node=node,
                        message=f"Expression régulière vulnérable au déni de service géométrique (Geometric ReDoS) : {reason}",
                        recommendation="Remplacer l'expression régulière par un analyseur linéaire déterministe O(n) sans répétitions imbriquées."
                    )

                # Vérification de re.DOTALL avec joker glouton
                has_dotall = False
                for kw in node.keywords:
                    if kw.arg == "flags":
                        unparsed = ast.unparse(kw.value) if hasattr(ast, "unparse") else ""
                        if "DOTALL" in unparsed or "re.S" in unparsed:
                            has_dotall = True
                if len(node.args) >= 2:
                    unparsed = ast.unparse(node.args[1]) if hasattr(ast, "unparse") else ""
                    if "DOTALL" in unparsed or "re.S" in unparsed:
                        has_dotall = True

                if has_dotall and (".*" in pat_str or ".+" in pat_str) and not (".*?" in pat_str or ".+?" in pat_str):
                    self._add_finding(
                        rule_id="SEC_STEP_REDOS_DOTALL_UNBOUNDED",
                        category=SecurityCategory.REGEX_DOS,
                        severity=SecuritySeverity.HIGH,
                        node=node,
                        message="Regex utilisant re.DOTALL avec joker glouton (.* ou .+) non borné sur du contenu CAD.",
                        recommendation="Utiliser des correspondances bornées ou non-gloutonnes (.*?) avec limite de taille de tampon."
                    )

    def _check_native_opengl_hazard(self, node: ast.Call, resolved: str) -> None:
        """
        Contrôle l'intégrité des appels OpenGL natifs (glDrawElements count vs buffer size, glDrawArrays).
        """
        attr_name = node.func.attr if isinstance(node.func, ast.Attribute) else ""

        if resolved in ("GL.glDrawElements", "OpenGL.GL.glDrawElements") or attr_name == "glDrawElements":
            if len(node.args) >= 2:
                count_arg = node.args[1]
                if isinstance(count_arg, ast.Constant):
                    if isinstance(count_arg.value, int) and count_arg.value <= 0:
                        self._add_finding(
                            rule_id="SEC_OPENGL_INVALID_COUNT",
                            category=SecurityCategory.NATIVE_MEMORY_HAZARD,
                            severity=SecuritySeverity.HIGH,
                            node=node,
                            message=f"glDrawElements appelé avec un nombre d'éléments constant invalide ({count_arg.value}).",
                            recommendation="Le nombre d'éléments count doit être strictement positif."
                        )
                else:
                    if not self.scope_has_buffer_bounds_check:
                        self._add_finding(
                            rule_id="SEC_OPENGL_BUFFER_OVERFLOW",
                            category=SecurityCategory.NATIVE_MEMORY_HAZARD,
                            severity=SecuritySeverity.HIGH,
                            node=node,
                            message="glDrawElements invoqué sans contrôle de validité ni vérification de taille du tampon d'indices.",
                            recommendation="Vérifier formellement que buffer n'est pas vide et que count <= len(indices) avant l'appel."
                        )

        if resolved in ("GL.glDrawArrays", "OpenGL.GL.glDrawArrays") or attr_name == "glDrawArrays":
            if len(node.args) >= 3:
                first_arg = node.args[1]
                count_arg = node.args[2]
                if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, int) and first_arg.value < 0:
                    self._add_finding(
                        rule_id="SEC_OPENGL_INVALID_COUNT",
                        category=SecurityCategory.NATIVE_MEMORY_HAZARD,
                        severity=SecuritySeverity.HIGH,
                        node=node,
                        message=f"glDrawArrays appelé avec un premier indice négatif ({first_arg.value}).",
                        recommendation="L'indice initial doit être supérieur ou égal à zéro."
                    )
                if isinstance(count_arg, ast.Constant) and isinstance(count_arg.value, int) and count_arg.value <= 0:
                    self._add_finding(
                        rule_id="SEC_OPENGL_INVALID_COUNT",
                        category=SecurityCategory.NATIVE_MEMORY_HAZARD,
                        severity=SecuritySeverity.HIGH,
                        node=node,
                        message=f"glDrawArrays appelé avec un nombre d'éléments invalide ({count_arg.value}).",
                        recommendation="Le count de glDrawArrays doit être strictement supérieur à zéro."
                    )

    def _check_ctypes_hazard(self, node: ast.Call, resolved: str) -> None:
        """
        Détecte les manipulations de mémoire brute et de pointeurs ctypes.
        """
        attr_name = node.func.attr if isinstance(node.func, ast.Attribute) else ""

        raw_mem_funcs = (
            "ctypes.memmove", "ctypes.memset", "ctypes.cast",
            "ctypes.string_at", "ctypes.wstring_at"
        )
        if resolved in raw_mem_funcs or (
            attr_name in ("memmove", "memset", "cast", "string_at", "wstring_at") and
            "ctypes" in resolved
        ):
            self._add_finding(
                rule_id="SEC_CTYPES_RAW_MEMORY",
                category=SecurityCategory.NATIVE_MEMORY_HAZARD,
                severity=SecuritySeverity.HIGH,
                node=node,
                message=f"Manipulation directe de mémoire brute via '{resolved or attr_name}'. Risque d'altération de pile/tas.",
                recommendation="Encapsuler dans une classe buffer étanche avec vérification rigoureuse des bornes mémoires allouées."
            )

        if resolved in ("ctypes.c_void_p", "c_void_p") and len(node.args) >= 1:
            arg = node.args[0]
            if isinstance(arg, (ast.Constant, ast.BinOp)):
                self._add_finding(
                    rule_id="SEC_CTYPES_ARBITRARY_ADDRESS",
                    category=SecurityCategory.NATIVE_MEMORY_HAZARD,
                    severity=SecuritySeverity.HIGH,
                    node=node,
                    message="Instanciation d'un pointeur à partir d'une adresse mémoire entière arbitraire.",
                    recommendation="Ne jamais forcer de pointeur brut à partir d'adresses arithmétiques non vérifiées."
                )

    def _check_geometric_dos_and_io(self, node: ast.Call, resolved: str) -> None:
        """Détecte les lectures complètes sans quota."""
        if resolved in ("f.read", "file.read") or (isinstance(node.func, ast.Attribute) and node.func.attr == "read"):
            if len(node.args) == 0:
                self._add_finding(
                    rule_id="SEC_UNBOUNDED_FILE_READ",
                    category=SecurityCategory.RESOURCE_EXHAUSTION,
                    severity=SecuritySeverity.LOW,
                    node=node,
                    message="Lecture complète de fichier via read() sans limite maximale d'octets.",
                    recommendation="Fournir une taille maximale de lecture read(MAX_BYTES) pour contrer les fichiers bombes CAO."
                )


# ==============================================================================
# Fonctions d'Audit et Points d'Entrée
# ==============================================================================

def audit_python_code_security(code_str: str, filename: str = "<string>") -> List[SecurityFinding]:
    """
    Parse et analyse syntaxiquement une chaîne de code source Python.

    :param code_str: Code source Python à inspecter.
    :param filename: Nom logique du fichier analysé.
    :return: Liste ordonnée des anomalies de sécurité identifiées.
    """
    try:
        tree = ast.parse(code_str, filename=filename)
    except SyntaxError as e:
        return [SecurityFinding(
            rule_id="SEC_SYNTAX_ERROR",
            category=SecurityCategory.CODE_INJECTION,
            severity=SecuritySeverity.HIGH,
            line_number=e.lineno or 1,
            column_offset=e.offset or 0,
            message=f"Erreur de syntaxe empêchant l'analyse AST : {e.msg}",
            recommendation="Corriger la syntaxe Python du fichier source."
        )]

    visitor = SecuritySASTVisitor(filename=filename, source_code=code_str)
    visitor.visit(tree)
    return visitor.findings


def audit_python_file_security(filepath: str) -> List[SecurityFinding]:
    """
    Point d'entrée utilitaire pour analyser la sécurité d'un fichier source sur disque.

    :param filepath: Chemin d'accès au fichier Python.
    :return: Liste des anomalies de sécurité identifiées.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        return [SecurityFinding(
            rule_id="SEC_FILE_READ_ERROR",
            category=SecurityCategory.RESOURCE_EXHAUSTION,
            severity=SecuritySeverity.HIGH,
            line_number=1,
            column_offset=0,
            message=f"Impossible de lire le fichier source '{filepath}' : {e}",
            recommendation="Vérifier les permissions d'accès au fichier."
        )]

    return audit_python_code_security(content, filename=filepath)


def audit_directory_security(dirpath: str, recursive: bool = True) -> Dict[str, List[SecurityFinding]]:
    """
    Analyse tous les fichiers Python d'un répertoire donné.

    :param dirpath: Chemin du répertoire racine.
    :param recursive: Parcours récursif des sous-dossiers si True.
    :return: Dictionnaire associant chaque chemin de fichier à sa liste de vulnérabilités.
    """
    results: Dict[str, List[SecurityFinding]] = {}

    if recursive:
        for root, _, files in os.walk(dirpath):
            for file in files:
                if file.endswith(".py"):
                    full_p = os.path.join(root, file)
                    findings = audit_python_file_security(full_p)
                    if findings:
                        results[full_p] = findings
    else:
        for file in os.listdir(dirpath):
            if file.endswith(".py"):
                full_p = os.path.join(dirpath, file)
                findings = audit_python_file_security(full_p)
                if findings:
                    results[full_p] = findings

    return results


def format_security_report(findings_by_file: Dict[str, List[SecurityFinding]]) -> str:
    """
    Formate un rapport d'audit de sécurité complet et lisible pour console ou logs.

    :param findings_by_file: Dictionnaire de résultats par fichier.
    :return: Rapport formaté multi-lignes.
    """
    lines: List[str] = []
    lines.append("=" * 70)
    lines.append("RAPPORT D'AUDIT SAST DE SÉCURITÉ CAO/FAO 3D (ISO 25010 & CWE)")
    lines.append("=" * 70)

    total_files = len(findings_by_file)
    all_findings: List[SecurityFinding] = []
    for f_list in findings_by_file.values():
        all_findings.extend(f_list)

    counts: Dict[str, int] = {
        "CRITICAL": sum(1 for f in all_findings if f.severity == SecuritySeverity.CRITICAL),
        "HIGH": sum(1 for f in all_findings if f.severity == SecuritySeverity.HIGH),
        "MEDIUM": sum(1 for f in all_findings if f.severity == SecuritySeverity.MEDIUM),
        "LOW": sum(1 for f in all_findings if f.severity == SecuritySeverity.LOW),
        "INFO": sum(1 for f in all_findings if f.severity == SecuritySeverity.INFO),
    }

    lines.append(f"Fichiers avec anomalies : {total_files}")
    lines.append(f"Total vulnérabilités   : {len(all_findings)}")
    lines.append(f"  - CRITICAL : {counts['CRITICAL']}")
    lines.append(f"  - HIGH     : {counts['HIGH']}")
    lines.append(f"  - MEDIUM   : {counts['MEDIUM']}")
    lines.append(f"  - LOW      : {counts['LOW']}")
    lines.append(f"  - INFO     : {counts['INFO']}")
    lines.append("-" * 70)

    for filepath, findings in findings_by_file.items():
        lines.append(f"\n[-] {filepath} ({len(findings)} anomalie(s)) :")
        for f in findings:
            lines.append(f"  [{f.severity.value}] {f.rule_id} ({f.category.value}) L.{f.line_number}:")
            lines.append(f"    Message        : {f.message}")
            if f.code_snippet:
                lines.append(f"    Extrait        : {f.code_snippet}")
            lines.append(f"    Recommandation : {f.recommendation}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    """
    Point d'entrée en ligne de commande pour le scanner SAST.

    :param argv: Arguments de la ligne de commande optionnels.
    :return: Code de sortie du processus (0 si conforme, 1 si vulnérabilités critiques/hautes).
    """
    args = argv if argv is not None else sys.argv[1:]
    target_path = args[0] if args else "src"

    if not os.path.exists(target_path):
        print(f"Erreur : le chemin cible '{target_path}' n'existe pas.", file=sys.stderr)
        return 1

    if os.path.isfile(target_path):
        findings = audit_python_file_security(target_path)
        report_data = {target_path: findings} if findings else {}
    else:
        report_data = audit_directory_security(target_path, recursive=True)

    print(format_security_report(report_data))

    # Échec en cas de découverte critique ou haute
    for f_list in report_data.values():
        for f in f_list:
            if f.severity in (SecuritySeverity.CRITICAL, SecuritySeverity.HIGH):
                return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
