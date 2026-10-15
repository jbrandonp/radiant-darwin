"""
Moteur d'Audit AST Unifié Single-Pass Haute Performance (Architecture Déterministe SOTA 2026).
Élimine le double parsing et la surcharge combinatoire des traversées redondantes en fusionnant :
1. Complexité Cognitive SonarSource (Campbell 2018).
2. Complexité Cyclomatique McCabe v(G).
3. Contrôle de typage statique strict (Zéro Any, Zéro object) sans ast.unparse().
4. Analyse statique de sécurité SAST (CWE-94, CWE-78, CWE-502).
5. Extraction instantanée du graphe d'importation et dépendances architecturales.
Typage statique strict : Zéro Any, Zéro object.
"""

from __future__ import annotations
import ast
import hashlib
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union


@dataclass
class FunctionQualityMetrics:
    """
    Métriques formelles calculées pour une fonction ou méthode.
    Enregistre la complexité cognitive, McCabe, la taille et le statut de typage.
    """
    file_path: str
    name: str
    line_number: int
    cognitive_complexity: int
    cyclomatic_complexity: int
    lines_of_code: int
    is_fully_typed: bool
    missing_annotations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Union[str, int, bool, List[str]]]:
        """Convertit l'objet métrique en dictionnaire sérialisable pour le cache."""
        return {
            "file_path": self.file_path,
            "name": self.name,
            "line_number": self.line_number,
            "cognitive_complexity": self.cognitive_complexity,
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "lines_of_code": self.lines_of_code,
            "is_fully_typed": self.is_fully_typed,
            "missing_annotations": list(self.missing_annotations)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Union[str, int, bool, List[str]]]) -> FunctionQualityMetrics:
        """Instancie les métriques depuis un dictionnaire de cache."""
        missing = data.get("missing_annotations", [])
        missing_list: List[str] = [str(item) for item in missing] if isinstance(missing, list) else []
        return cls(
            file_path=str(data["file_path"]),
            name=str(data["name"]),
            line_number=int(data["line_number"]),
            cognitive_complexity=int(data["cognitive_complexity"]),
            cyclomatic_complexity=int(data["cyclomatic_complexity"]),
            lines_of_code=int(data["lines_of_code"]),
            is_fully_typed=bool(data["is_fully_typed"]),
            missing_annotations=missing_list
        )


@dataclass
class FileAuditReport:
    """
    Bilan d'audit d'un fichier source unique généré en une seule passe AST.
    Contient l'ensemble des métriques de qualité, sécurité et dépendances.
    """
    file_path: str
    lines_of_code: int
    cognitive_complexity: int
    cyclomatic_complexity: int
    maintainability_index: float
    type_completeness_percent: float
    security_violations: List[str] = field(default_factory=list)
    functions: List[FunctionQualityMetrics] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    sha256: str = ""
    git_churn: int = 0
    hotspot_index: int = 0
    afferent_coupling: int = 0
    efferent_coupling: int = 0
    instability: float = 0.0

    @property
    def internal_imports(self) -> Set[str]:
        """Vue sous forme d'ensemble des modules importés."""
        return set(self.dependencies)


@dataclass
class _FunctionContext:
    """
    Contexte d'évaluation d'une fonction active sur la pile d'exécution AST.
    Permet le calcul en single-pass de la complexité cognitive et McCabe pour les fonctions imbriquées.
    """
    name: str
    line_number: int
    lines_of_code: int
    is_fully_typed: bool
    missing_annotations: List[str]
    cognitive_complexity: int = 0
    nesting_level: int = 0
    cyclomatic_complexity: int = 1


class UnifiedIndustrialAstVisitor(ast.NodeVisitor):
    """
    Visiteur AST unifié à passe unique (Single-Pass Visitor).
    Traverse l'arbre syntaxique une seule fois pour extraire simultanément :
    - La complexité cognitive globale du fichier et par fonction.
    - La complexité cyclomatique de McCabe globale et par fonction.
    - La conformité stricte du typage (sans sérialisation textuelle ast.unparse).
    - Les vulnérabilités de sécurité SAST (CWE) avec résolution des alias d'import.
    - Les dépendances d'imports internes pour l'analyse de couplage architectural.
    """

    def __init__(self, file_path: str, src_root_prefix: str = "src.") -> None:
        """
        Initialise le visiteur unifié pour un fichier donné.
        :param file_path: Chemin absolu ou relatif du fichier source analysé.
        :param src_root_prefix: Préfixe des modules internes du projet (ex: 'src.').
        """
        self.file_path: str = file_path
        self.src_root_prefix: str = src_root_prefix

        # Complexité cognitive au niveau module
        self.file_cognitive_complexity: int = 0
        self.file_nesting_level: int = 0

        # Pile d'exécution pour les fonctions (gère l'imbrication lexicale)
        self.function_stack: List[_FunctionContext] = []
        self.completed_functions: List[FunctionQualityMetrics] = []

        # Détection de vulnérabilités SAST
        self.security_violations: List[str] = []
        self.module_aliases: Dict[str, str] = {}
        self.function_aliases: Dict[str, Tuple[str, str]] = {}

        # Graphe de dépendances internes (ordre d'apparition préservé)
        self.dependencies: List[str] = []
        self._dependencies_seen: Set[str] = set()

    # --------------------------------------------------------------------------
    # 1. Inspection directe de typage (Zéro ast.unparse, Zéro allocation inutile)
    # --------------------------------------------------------------------------

    def _find_forbidden_type(self, node: Optional[ast.AST]) -> Optional[str]:
        """
        Inspecte récursivement l'arborescence AST d'une annotation de type sans aucune
        sérialisation textuelle ast.unparse(), en ciblant directement ast.Name et ast.Attribute.
        :param node: Nœud AST de l'annotation de type à contrôler.
        :return: Nom du type interdit détecté ('Any' ou 'object'), ou None si conforme.
        """
        if node is None:
            return None

        # Identifiant simple : Any, object
        if isinstance(node, ast.Name):
            identifier = node.id
            if identifier in ("Any", "object"):
                return identifier
            return None

        # Attribut qualifié : typing.Any, builtins.object, mod.Any
        if isinstance(node, ast.Attribute):
            attr_name = node.attr
            if attr_name in ("Any", "object"):
                return attr_name
            return self._find_forbidden_type(node.value)

        # Indexation générique : List[Any], Dict[str, object], Optional[Any]
        if isinstance(node, ast.Subscript):
            forbidden_val = self._find_forbidden_type(node.value)
            if forbidden_val is not None:
                return forbidden_val
            return self._find_forbidden_type(node.slice)

        # Multiples arguments génériques : Tuple[int, Any], Union[A, object]
        if isinstance(node, ast.Tuple):
            for elt in node.elts:
                forbidden_elt = self._find_forbidden_type(elt)
                if forbidden_elt is not None:
                    return forbidden_elt
            return None

        # Union moderne Python 3.10+ via opérateur binaire bitwise : int | Any
        if isinstance(node, ast.BinOp):
            forbidden_left = self._find_forbidden_type(node.left)
            if forbidden_left is not None:
                return forbidden_left
            return self._find_forbidden_type(node.right)

        # Constante littérale (ex: forward references stringifiées 'Any' ou 'object')
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                literal_val = node.value
                if "Any" in literal_val or "object" in literal_val:
                    return literal_val
            return None

        # Liste d'arguments de types (ex: Callable[[int, Any], None])
        if isinstance(node, ast.List):
            for elt in node.elts:
                forbidden_elt = self._find_forbidden_type(elt)
                if forbidden_elt is not None:
                    return forbidden_elt
            return None

        return None

    # --------------------------------------------------------------------------
    # 2. Résolution des appels et alias d'importation
    # --------------------------------------------------------------------------

    def _resolve_callable(self, func_node: ast.AST) -> str:
        """
        Résout un nœud appelable en nom qualifié canonique en tenant compte des alias.
        :param func_node: Nœud AST de la fonction appelée (ast.Name ou ast.Attribute).
        :return: Nom qualifié canonique sous forme de chaîne de caractères.
        """
        if isinstance(func_node, ast.Name):
            func_id = func_node.id
            if func_id in self.function_aliases:
                mod_name, orig_name = self.function_aliases[func_id]
                return f"{mod_name}.{orig_name}"
            return func_id

        if isinstance(func_node, ast.Attribute):
            attr_name = func_node.attr
            if isinstance(func_node.value, ast.Name):
                base_mod = func_node.value.id
                resolved_mod = self.module_aliases.get(base_mod, base_mod)
                return f"{resolved_mod}.{attr_name}"
            if isinstance(func_node.value, ast.Attribute):
                parent_qualname = self._resolve_callable(func_node.value)
                return f"{parent_qualname}.{attr_name}"

        return ""

    def _record_dependency(self, target_module: str) -> None:
        """
        Enregistre de manière unique une dépendance interne du projet.
        :param target_module: Chemin canonique du module cible (ex: 'core/geometry').
        """
        if target_module not in self._dependencies_seen:
            self._dependencies_seen.add(target_module)
            self.dependencies.append(target_module)

    # --------------------------------------------------------------------------
    # 3. Visite des déclarations d'imports (SAST + Dépendances architecturales)
    # --------------------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        """
        Enregistre les alias de modules importés et extrait les dépendances internes du projet.
        :param node: Nœud AST d'importation globale (ex: import os as my_os).
        """
        for alias in node.names:
            mod_name = alias.name
            as_name = alias.asname or mod_name
            self.module_aliases[as_name] = mod_name

            if mod_name.startswith(self.src_root_prefix):
                target_module = mod_name[len(self.src_root_prefix):].replace(".", "/")
                self._record_dependency(target_module)

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """
        Enregistre les alias de fonctions importées et extrait les dépendances internes du projet.
        :param node: Nœud AST d'importation ciblée (ex: from os import system as sys_exec).
        """
        mod_name = node.module or ""
        if mod_name.startswith(self.src_root_prefix):
            target_module = mod_name[len(self.src_root_prefix):].replace(".", "/")
            self._record_dependency(target_module)

        for alias in node.names:
            imported_func = alias.name
            as_name = alias.asname or imported_func
            self.function_aliases[as_name] = (mod_name, imported_func)

        self.generic_visit(node)

    # --------------------------------------------------------------------------
    # 4. Visite des définitions de fonctions (Typage strict + Contexte)
    # --------------------------------------------------------------------------

    def _handle_function_definition(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> None:
        """
        Traite une définition de fonction synchrone ou asynchrone.
        Vérifie la complétude et la rigueur du typage sans ast.unparse(), puis
        pousse un nouveau contexte sur la pile d'analyse avant de visiter le corps.
        :param node: Nœud AST de la fonction (FunctionDef ou AsyncFunctionDef).
        """
        missing_types: List[str] = []

        # Vérification des arguments positionnels et nommés
        all_arguments: List[ast.arg] = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
        for arg in all_arguments:
            if arg.arg in ("self", "cls"):
                continue
            if arg.annotation is None:
                missing_types.append(f"param non typé '{arg.arg}'")
            else:
                forbidden = self._find_forbidden_type(arg.annotation)
                if forbidden is not None:
                    missing_types.append(f"type interdit (Any/object) sur param '{arg.arg}': {forbidden}")

        # Vérification du type de retour
        if node.returns is None and node.name != "__init__":
            missing_types.append("return type manquant")
        elif node.returns is not None:
            forbidden_ret = self._find_forbidden_type(node.returns)
            if forbidden_ret is not None:
                missing_types.append(f"type interdit (Any/object) sur return: {forbidden_ret}")

        is_typed = (len(missing_types) == 0)
        fn_loc = len(node.body)

        context = _FunctionContext(
            name=node.name,
            line_number=node.lineno,
            lines_of_code=fn_loc,
            is_fully_typed=is_typed,
            missing_annotations=missing_types
        )
        self.function_stack.append(context)

        # Traversée du corps de la fonction
        self.generic_visit(node)

        # Dépilement et enregistrement de la métrique finalisée
        popped_context = self.function_stack.pop()
        metric = FunctionQualityMetrics(
            file_path=self.file_path,
            name=popped_context.name,
            line_number=popped_context.line_number,
            cognitive_complexity=popped_context.cognitive_complexity,
            cyclomatic_complexity=popped_context.cyclomatic_complexity,
            lines_of_code=popped_context.lines_of_code,
            is_fully_typed=popped_context.is_fully_typed,
            missing_annotations=popped_context.missing_annotations
        )
        self.completed_functions.append(metric)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Point d'entrée pour les fonctions synchrones."""
        self._handle_function_definition(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Point d'entrée pour les fonctions asynchrones."""
        self._handle_function_definition(node)

    # --------------------------------------------------------------------------
    # 5. Visite des structures de contrôle (Complexité Cognitive & McCabe)
    # --------------------------------------------------------------------------

    def visit_If(self, node: ast.If) -> None:
        """
        Calcule l'incrément de complexité pour une branche conditionnelle if.
        Ajoute 1 + niveau d'imbrication au fichier et à toutes les fonctions englobantes.
        """
        self.file_cognitive_complexity += (1 + self.file_nesting_level)
        self.file_nesting_level += 1

        for fn in self.function_stack:
            fn.cognitive_complexity += (1 + fn.nesting_level)
            fn.cyclomatic_complexity += 1
            fn.nesting_level += 1

        self.generic_visit(node)

        self.file_nesting_level -= 1
        for fn in self.function_stack:
            fn.nesting_level -= 1

    def visit_For(self, node: ast.For) -> None:
        """
        Calcule l'incrément de complexité pour une boucle for.
        """
        self.file_cognitive_complexity += (1 + self.file_nesting_level)
        self.file_nesting_level += 1

        for fn in self.function_stack:
            fn.cognitive_complexity += (1 + fn.nesting_level)
            fn.cyclomatic_complexity += 1
            fn.nesting_level += 1

        self.generic_visit(node)

        self.file_nesting_level -= 1
        for fn in self.function_stack:
            fn.nesting_level -= 1

    def visit_While(self, node: ast.While) -> None:
        """
        Calcule l'incrément de complexité pour une boucle while.
        """
        self.file_cognitive_complexity += (1 + self.file_nesting_level)
        self.file_nesting_level += 1

        for fn in self.function_stack:
            fn.cognitive_complexity += (1 + fn.nesting_level)
            fn.cyclomatic_complexity += 1
            fn.nesting_level += 1

        self.generic_visit(node)

        self.file_nesting_level -= 1
        for fn in self.function_stack:
            fn.nesting_level -= 1

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """
        Calcule l'incrément de complexité pour un gestionnaire d'exception except.
        """
        self.file_cognitive_complexity += (1 + self.file_nesting_level)
        self.file_nesting_level += 1

        for fn in self.function_stack:
            fn.cognitive_complexity += (1 + fn.nesting_level)
            fn.cyclomatic_complexity += 1
            fn.nesting_level += 1

        self.generic_visit(node)

        self.file_nesting_level -= 1
        for fn in self.function_stack:
            fn.nesting_level -= 1

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        """
        Calcule l'incrément pour une séquence d'opérateurs booléens (and, or).
        Ajoute le nombre d'opérations combinées sans pénalité d'imbrication.
        """
        inc_value = max(1, len(node.values) - 1)
        self.file_cognitive_complexity += inc_value

        for fn in self.function_stack:
            fn.cognitive_complexity += inc_value
            fn.cyclomatic_complexity += (len(node.values) - 1)

        self.generic_visit(node)

    # --------------------------------------------------------------------------
    # 6. Visite des appels de fonctions (Analyse Statique de Sécurité SAST)
    # --------------------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        """
        Vérifie en temps réel les appels de fonctions sensibles (SAST).
        Détecte les injections de code, injections shell, désérialisations non fiables.
        :param node: Nœud AST d'appel de fonction ou méthode.
        """
        resolved_name = self._resolve_callable(node.func)

        # Injections de code arbitraire
        if resolved_name in ("eval", "exec", "builtins.eval", "builtins.exec"):
            self.security_violations.append(
                f"Ligne {node.lineno}: Appel interdit au builtin '{resolved_name}'"
            )

        # Injections de commandes système directes
        elif resolved_name in ("os.system", "os.popen", "os.spawnl", "os.spawnv", "os.spawnle", "os.spawnve", "pty.spawn"):
            self.security_violations.append(
                f"Ligne {node.lineno}: Exécution de commande système {resolved_name}()"
            )

        # Subprocess avec interpréteur shell
        elif resolved_name in (
            "subprocess.Popen", "subprocess.run", "subprocess.call",
            "subprocess.check_call", "subprocess.check_output"
        ):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    self.security_violations.append(
                        f"Ligne {node.lineno}: Injection potentielle via subprocess shell=True"
                    )

        # Désérialisation pickle dangereuse
        elif resolved_name in (
            "pickle.load", "pickle.loads", "_pickle.load", "_pickle.loads",
            "cPickle.load", "cPickle.loads", "shelve.open", "marshal.load", "marshal.loads"
        ):
            self.security_violations.append(
                f"Ligne {node.lineno}: Désérialisation non sécurisée détectée via '{resolved_name}()'"
            )

        # YAML unsafe
        elif resolved_name == "yaml.unsafe_load":
            self.security_violations.append(
                f"Ligne {node.lineno}: Appel explicite à yaml.unsafe_load() interdit"
            )

        self.generic_visit(node)


class UnifiedAstQualityAuditor:
    """
    Gestionnaire d'audit de fichier à passe unique (Single-Pass Auditor).
    Orchestre la lecture, le parsing unique et le calcul des indices qualité.
    """

    @classmethod
    def audit_file(cls, filepath: str, sha256_hash: Optional[str] = None) -> FileAuditReport:
        """
        Parse et analyse en profondeur un fichier Python en une seule passe AST.
        :param filepath: Chemin d'accès au fichier source Python.
        :param sha256_hash: Empreinte SHA-256 optionnelle pré-calculée.
        :return: Rapport complet d'audit du fichier (FileAuditReport).
        """
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            code_text = f.read()

        file_sha = sha256_hash or cls.compute_sha256(filepath)
        lines = code_text.splitlines()
        loc = len([l for l in lines if l.strip() and not l.strip().startswith("#")])

        try:
            tree = ast.parse(code_text, filename=filepath)
        except SyntaxError as err:
            return FileAuditReport(
                file_path=filepath,
                lines_of_code=loc,
                cognitive_complexity=999,
                cyclomatic_complexity=999,
                maintainability_index=0.0,
                type_completeness_percent=0.0,
                security_violations=[f"Erreur syntaxe: {err}"],
                sha256=file_sha
            )

        # Exécution unique du visiteur unifié
        visitor = UnifiedIndustrialAstVisitor(filepath)
        visitor.visit(tree)

        # Tri déterministe des fonctions par ordre de ligne d'apparition
        visitor.completed_functions.sort(key=lambda fn: fn.line_number)

        # Calcul du taux de complétude du typage
        total_funcs = len(visitor.completed_functions)
        typed_funcs = sum(1 for fn in visitor.completed_functions if fn.is_fully_typed)
        type_percent = (float(typed_funcs) / float(total_funcs) * 100.0) if total_funcs > 0 else 100.0

        # Calcul de l'Indice de Maintenabilité SEI / Microsoft
        safe_loc = max(1.0, float(loc))
        safe_mccabe = max(1.0, float(visitor.file_cognitive_complexity))
        approx_halstead_vol = safe_loc * 8.0 * math.log2(max(2.0, safe_loc))

        raw_mi = 171.0 - 5.2 * math.log(max(1.0, approx_halstead_vol)) - 0.23 * safe_mccabe - 16.2 * math.log(safe_loc)
        maintainability_index = max(0.0, min(100.0, (raw_mi * 100.0) / 171.0))

        total_cyclomatic = sum(fn.cyclomatic_complexity for fn in visitor.completed_functions)

        return FileAuditReport(
            file_path=filepath,
            lines_of_code=loc,
            cognitive_complexity=visitor.file_cognitive_complexity,
            cyclomatic_complexity=total_cyclomatic,
            maintainability_index=maintainability_index,
            type_completeness_percent=type_percent,
            security_violations=visitor.security_violations,
            functions=visitor.completed_functions,
            dependencies=visitor.dependencies,
            sha256=file_sha
        )

    @classmethod
    def compute_sha256(cls, filepath: str) -> str:
        """
        Calcule de façon streaming le hash SHA-256 d'un fichier source.
        :param filepath: Chemin vers le fichier sur disque.
        :return: Chaîne hexadécimale du SHA-256.
        """
        try:
            hasher = hashlib.sha256()
            with open(filepath, "rb") as fh:
                while chunk := fh.read(65536):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return ""
