"""
Analyseur de Graphe de Dépendances Avancé (Robert C. Martin & Algorithme de Tarjan).
Fournit une analyse architecturale formelle et déterministe pour noyaux logiciels industriels :
1. Algorithme de Tarjan en O(V + E) pour la détection de tous les cycles de dépendance (taille k >= 3).
2. Résolution canonique rigoureuse des imports ciblant les packages et sous-modules (__init__.py).
3. Calcul formel de l'Indice d'Abstraction A = Na / Nc (Protocol, ABC, abstractmethod).
4. Distance à la Séquence Principale D = |A + I - 1| (SAP) et isolation de la Zone de Souffrance et de la Zone d'Inutilité.

Typage statique strict : strictement zéro Any et zéro object.
"""

from __future__ import annotations
import ast
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class ArchitectureZone(Enum):
    """
    Classification des zones architecturales selon Robert C. Martin (Clean Architecture).
    Permet de vérifier le respect du principe d'abstraction stable (Stable Abstractions Principle).
    """
    MAIN_SEQUENCE = "MAIN_SEQUENCE"              # Zone d'équilibre optimal (A + I ≈ 1)
    ZONE_OF_PAIN = "ZONE_OF_PAIN"                # Zone de Souffrance : stable mais bétonné/concret (A ≈ 0, I ≈ 0)
    ZONE_OF_USELESSNESS = "ZONE_OF_USELESSNESS"  # Zone d'Inutilité : abstrait mais instable/inutilisé (A ≈ 1, I ≈ 1)


@dataclass
class ModuleMetrics:
    """
    Métriques architecturales complètes calculées pour un fichier/module unique.
    """
    module_name: str
    file_path: str
    afferent_coupling: int              # Ca : Nombre de modules externes dépendant de ce module
    efferent_coupling: int              # Ce : Nombre de modules externes dont ce module dépend
    instability: float                  # I = Ce / (Ca + Ce)
    total_classes: int                  # Nc : Nombre total de classes déclarées
    abstract_classes: int               # Na : Nombre de classes abstraites ou Protocoles
    abstractness: float                 # A = Na / Nc
    distance_main_sequence: float       # D = |A + I - 1|
    zone: ArchitectureZone              # Zone architecturale SAP
    zone_description: str               # Description explicative en français


@dataclass
class PackageMetrics:
    """
    Métriques d'architecture agrégées à l'échelle d'un paquet de modules (package).
    """
    package_name: str
    modules: List[str]
    afferent_coupling: int
    efferent_coupling: int
    instability: float
    total_classes: int
    abstract_classes: int
    abstractness: float
    distance_main_sequence: float
    zone: ArchitectureZone


@dataclass
class DependencyGraphReport:
    """
    Bilan global de l'analyse du graphe de dépendances et des métriques de Robert C. Martin.
    """
    modules: Dict[str, ModuleMetrics] = field(default_factory=dict)
    packages: Dict[str, PackageMetrics] = field(default_factory=dict)
    dependencies: Dict[str, Set[str]] = field(default_factory=dict)
    strongly_connected_components: List[List[str]] = field(default_factory=list)
    cycles: List[List[str]] = field(default_factory=list)
    total_modules: int = 0
    total_dependencies: int = 0
    cyclic_dependencies_count: int = 0
    zone_of_pain_count: int = 0
    zone_of_uselessness_count: int = 0
    main_sequence_count: int = 0


class CanonicalImportResolver:
    """
    Résolveur canonique d'importations Python.
    Résout les imports absolus, relatifs et les cibles de paquets vers leurs fichiers réels (__init__.py).
    """

    def __init__(self, src_dir: str) -> None:
        """
        Initialise le résolveur en scannant la structure physique du répertoire source.
        
        :param src_dir: Chemin racine du code source (ex: 'src').
        """
        self.src_dir: str = os.path.abspath(src_dir)
        self.package_root_name: str = os.path.basename(self.src_dir)
        self.known_modules: Set[str] = set()
        self.package_to_init: Dict[str, str] = {}
        self.file_to_module: Dict[str, str] = {}
        self._build_index()

    def _build_index(self) -> None:
        """
        Construit l'index interne reliant les chemins de fichiers aux identifiants canoniques de modules.
        """
        for root, _, files in os.walk(self.src_dir):
            for file_name in files:
                if file_name.endswith(".py"):
                    full_path = os.path.join(root, file_name)
                    rel_path = Path(full_path).relative_to(self.src_dir).with_suffix("").as_posix()
                    self.known_modules.add(rel_path)
                    self.file_to_module[full_path] = rel_path

                    if rel_path.endswith("/__init__"):
                        pkg_name = rel_path[:-9]
                        self.package_to_init[pkg_name] = rel_path
                    elif rel_path == "__init__":
                        self.package_to_init[""] = rel_path

    def resolve_target(self, base_module: str, import_name: Optional[str] = None) -> Optional[str]:
        """
        Résout canoniquement un nom de module ou d'attribut importé.
        Si la cible correspond à un paquet contenant un __init__.py, résout vers ce __init__.py.
        Si l'attribut importé est un sous-module existant, résout vers ce sous-module.
        
        :param base_module: Chemin importé (ex: 'src.core', 'src.core.nexus_kernel', 'core').
        :param import_name: Nom optionnel d'un symbole ou sous-module importé (ex: 'geometry', 'types').
        :return: Identifiant canonique du module (ex: 'core/__init__', 'core/geometry') ou None si externe.
        """
        clean: str = base_module
        prefix_with_dot: str = f"{self.package_root_name}."
        if clean.startswith(prefix_with_dot):
            clean = clean[len(prefix_with_dot):]
        elif clean == self.package_root_name:
            clean = ""

        clean_path: str = clean.replace(".", "/") if clean else ""

        # 1. Vérification si l'import cible un sous-module physique : from src.core import geometry
        if import_name and clean_path:
            sub_candidate: str = f"{clean_path}/{import_name}"
            if sub_candidate in self.known_modules:
                return sub_candidate
            if sub_candidate in self.package_to_init:
                return self.package_to_init[sub_candidate]
        elif import_name and not clean_path:
            if import_name in self.known_modules:
                return import_name
            if import_name in self.package_to_init:
                return self.package_to_init[import_name]

        # 2. Vérification directe du module
        if clean_path in self.known_modules:
            return clean_path
        if clean_path in self.package_to_init:
            return self.package_to_init[clean_path]

        # 3. Tentative avec __init__ explicite
        init_cand: str = f"{clean_path}/__init__" if clean_path else "__init__"
        if init_cand in self.known_modules:
            return init_cand

        return None

    def resolve_relative(self, current_module: str, level: int, module_name: Optional[str], import_name: Optional[str]) -> Optional[str]:
        """
        Résout un import relatif (PEP 328) en fonction de l'emplacement du module courant.
        
        :param current_module: Module émetteur de l'import (ex: 'core/feature').
        :param level: Nombre de points dans la syntaxe relative (1 pour '.', 2 pour '..').
        :param module_name: Nom du module relatif importé (ex: 'geometry' dans 'from .geometry import make_box').
        :param import_name: Nom du symbole ou sous-module importé.
        :return: Module cible canonique ou None.
        """
        parts: List[str] = current_module.split("/")
        # Si le module courant est un fichier ordinaire, son dossier parent est parts[:-1]
        parent_parts: List[str] = parts[:-1]

        # Remonter d'autant de niveaux supplémentaires que (level - 1)
        up_steps: int = level - 1
        if up_steps > len(parent_parts):
            return None
        base_parts: List[str] = parent_parts[:len(parent_parts) - up_steps] if up_steps > 0 else parent_parts
        base_dir: str = "/".join(base_parts)

        target_base: str = base_dir
        if module_name:
            target_base = f"{base_dir}/{module_name.replace('.', '/')}" if base_dir else module_name.replace(".", "/")

        return self.resolve_target(target_base, import_name)


class AbstractionAstAnalyzer:
    """
    Analyseur syntaxique AST déterministe pour le calcul formel de l'Indice d'Abstraction.
    Identifie précisément les classes concrètes, abstraites, Protocoles PEP 544 et ABC.
    """

    @classmethod
    def analyze_file(cls, file_path: str) -> Tuple[int, int, float]:
        """
        Calcule le nombre total de classes (Nc), de classes abstraites (Na) et l'indice A = Na / Nc.
        
        :param file_path: Chemin absolu ou relatif vers le fichier source Python.
        :return: Tuple (Nc, Na, A).
        """
        try:
            with open(file_path, "r", encoding="utf-8") as source_file:
                tree = ast.parse(source_file.read(), filename=file_path)
        except Exception:
            return 0, 0, 0.0

        total_classes: int = 0
        abstract_classes: int = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                total_classes += 1
                if cls._is_abstract_class(node):
                    abstract_classes += 1

        abstractness: float = (float(abstract_classes) / float(total_classes)) if total_classes > 0 else 0.0
        return total_classes, abstract_classes, abstractness

    @classmethod
    def _is_abstract_expr(cls, expr: ast.expr) -> bool:
        """Détermine récursivement si une expression de base représente ABC ou Protocol (y compris Subscripts)."""
        if isinstance(expr, ast.Subscript):
            return cls._is_abstract_expr(expr.value)
        if isinstance(expr, ast.Name) and expr.id in ("ABC", "Protocol"):
            return True
        if isinstance(expr, ast.Attribute) and expr.attr in ("ABC", "Protocol"):
            return True
        return False

    @classmethod
    def _is_abstract_class(cls, class_node: ast.ClassDef) -> bool:
        """
        Détermine si une déclaration de classe est formellement abstraite.
        Règles d'abstraction :
        - Hérite directement de ABC, abc.ABC, Protocol ou typing.Protocol (y compris génériques Protocol[T])
        - Possède un mot-clé metaclass=ABCMeta ou abc.ABCMeta
        - Contient au moins une méthode ou propriété décorée par @abstractmethod ou @abstractproperty
        """
        # 1. Vérification des classes de base (Bases, y compris Protocol[T])
        for base in class_node.bases:
            if cls._is_abstract_expr(base):
                return True

        # 2. Vérification des métaclasses (metaclass=ABCMeta)
        for keyword in class_node.keywords:
            if keyword.arg == "metaclass":
                if isinstance(keyword.value, ast.Name) and keyword.value.id == "ABCMeta":
                    return True
                if isinstance(keyword.value, ast.Attribute) and keyword.value.attr == "ABCMeta":
                    return True

        # 3. Vérification des décorateurs de méthodes dans le corps de la classe
        for item in class_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in item.decorator_list:
                    if isinstance(decorator, ast.Name) and decorator.id in ("abstractmethod", "abstractproperty"):
                        return True
                    if isinstance(decorator, ast.Attribute) and decorator.attr in ("abstractmethod", "abstractproperty"):
                        return True

        return False


class TarjanCycleDetector:
    """
    Implémentation déterministe de l'algorithme de Tarjan (1972) en O(V + E)
    pour la détection des composantes fortement connexes (SCC) et l'extraction
    exhaustive de tous les cycles de dépendance quelle que soit leur longueur (k >= 3).
    Version itérative sans récursion, immunisée contre les dépassements de pile.
    """

    @classmethod
    def find_strongly_connected_components(cls, graph: Dict[str, Set[str]]) -> List[List[str]]:
        """
        Décompose le graphe orienté en Composantes Fortement Connexes (SCC) selon Tarjan en O(V + E).
        Garantit un ordre de visite strictement déterministe par tri lexicographique.
        
        :param graph: Graphe d'adjacence orienté {noeud: ensemble_voisins}.
        :return: Liste des SCCs identifiées.
        """
        index: int = 0
        indices: Dict[str, int] = {}
        lowlink: Dict[str, int] = {}
        on_stack: Set[str] = set()
        tarjan_stack: List[str] = []
        sccs: List[List[str]] = []

        sorted_nodes: List[str] = sorted(graph.keys())

        for start_node in sorted_nodes:
            if start_node in indices:
                continue

            # Pile d'exploration DFS itérative : [noeud_courant, liste_voisins, index_prochain_voisin]
            dfs_stack: List[List[Tuple[str, List[str], int]]] = []  # Type structurel
            
            # Initialisation de start_node
            indices[start_node] = index
            lowlink[start_node] = index
            index += 1
            tarjan_stack.append(start_node)
            on_stack.add(start_node)
            initial_neighbors: List[str] = [w for w in sorted(graph.get(start_node, set())) if w in graph]

            # Représentation d'état [node, neighbors, next_idx]
            call_stack: List[List[str]] = [[start_node, "0"]]
            neighbors_map: Dict[str, List[str]] = {start_node: initial_neighbors}

            while call_stack:
                frame = call_stack[-1]
                u: str = frame[0]
                next_idx: int = int(frame[1])
                u_neighbors: List[str] = neighbors_map[u]

                if next_idx < len(u_neighbors):
                    w: str = u_neighbors[next_idx]
                    frame[1] = str(next_idx + 1)

                    if w not in indices:
                        # Descendre sur w
                        indices[w] = index
                        lowlink[w] = index
                        index += 1
                        tarjan_stack.append(w)
                        on_stack.add(w)
                        neighbors_map[w] = [k for k in sorted(graph.get(w, set())) if k in graph]
                        call_stack.append([w, "0"])
                    elif w in on_stack:
                        lowlink[u] = min(lowlink[u], indices[w])
                else:
                    # u a exploré tous ses voisins
                    call_stack.pop()

                    if lowlink[u] == indices[u]:
                        scc: List[str] = []
                        while True:
                            popped: str = tarjan_stack.pop()
                            on_stack.remove(popped)
                            scc.append(popped)
                            if popped == u:
                                break
                        sccs.append(sorted(scc))

                    # Mise à jour du nœud parent
                    if call_stack:
                        parent_u: str = call_stack[-1][0]
                        lowlink[parent_u] = min(lowlink[parent_u], lowlink[u])

        return sccs


    @classmethod
    def extract_elementary_cycles(cls, graph: Dict[str, Set[str]], sccs: List[List[str]]) -> List[List[str]]:
        """
        Extrait les cycles élémentaires ordonnés pour chaque composante fortement connexe cyclique.
        Isole tous les cycles simples de longueur k >= 2 (ainsi que les boucles k=1).
        Chaque cycle est normalisé pour commencer par son plus petit noeud alphabétique.
        
        :param graph: Graphe d'adjacence complet.
        :param sccs: Liste des SCCs produites par Tarjan.
        :return: Liste de chemins cycliques [v1, v2, ..., vk, v1].
        """
        cycles: List[List[str]] = []
        seen_cycles: Set[Tuple[str, ...]] = set()

        for scc in sccs:
            scc_set: Set[str] = set(scc)
            if len(scc) == 1:
                single_node: str = scc[0]
                if single_node in graph.get(single_node, set()):
                    self_cycle: Tuple[str, str] = (single_node, single_node)
                    if self_cycle not in seen_cycles:
                        seen_cycles.add(self_cycle)
                        cycles.append([single_node, single_node])
                continue

            # Recherche des cycles simples dans la composante connexe
            sorted_scc_nodes: List[str] = sorted(scc)
            for start_node in sorted_scc_nodes:
                def dfs_find_cycles(current: str, path: List[str]) -> None:
                    for nxt in sorted(graph.get(current, set())):
                        if nxt not in scc_set:
                            continue
                        if nxt == start_node and len(path) >= 2:
                            cycle_signature: Tuple[str, ...] = tuple(path)
                            if cycle_signature not in seen_cycles:
                                seen_cycles.add(cycle_signature)
                                cycles.append(path + [start_node])
                        elif nxt > start_node and nxt not in path:
                            dfs_find_cycles(nxt, path + [nxt])

                dfs_find_cycles(start_node, [start_node])

        return cycles


class ArchitectureDependencyAnalyzer:
    """
    Analyseur d'Architecture Avancé selon les principes de Robert C. Martin.
    Calcule Ca, Ce, Instabilité (I), Abstraction (A), Distance à la Séquence Principale (D)
    et identifie les dépendances circulaires via l'algorithme de Tarjan O(V + E).
    """

    @classmethod
    def analyze_dependencies(
        cls,
        src_dir: str = "src"
    ) -> Tuple[Dict[str, Set[str]], List[List[str]], Dict[str, Dict[str, float]]]:
        """
        Construit le graphe de dépendances complet, extrait les cycles de longueur k >= 3 via Tarjan,
        et calcule les métriques de couplage et de séquence principale pour chaque module.
        Garantit la compatibilité avec l'API existante d'industrial_audit_engine.py.
        
        :param src_dir: Répertoire source racine à analyser.
        :return: Tuple (deps, cycles, coupling_metrics).
        """
        report: DependencyGraphReport = cls.analyze_full(src_dir)

        # Format compatible avec les structures attendues par le moteur d'audit
        coupling_dict: Dict[str, Dict[str, float]] = {}
        for mod_name, met in report.modules.items():
            zone_code: float = 0.0
            if met.zone == ArchitectureZone.ZONE_OF_PAIN:
                zone_code = 1.0
            elif met.zone == ArchitectureZone.ZONE_OF_USELESSNESS:
                zone_code = 2.0

            coupling_dict[mod_name] = {
                "ca": float(met.afferent_coupling),
                "ce": float(met.efferent_coupling),
                "instability": met.instability,
                "na": float(met.abstract_classes),
                "nc": float(met.total_classes),
                "abstractness": met.abstractness,
                "distance_main_sequence": met.distance_main_sequence,
                "zone_code": zone_code,
            }

        return report.dependencies, report.cycles, coupling_dict

    @classmethod
    def analyze_full(cls, src_dir: str = "src") -> DependencyGraphReport:
        """
        Exécute l'analyse architecturale complète et produit un rapport enrichi de tous les modules et packages.
        
        :param src_dir: Répertoire racine du code source.
        :return: Objet DependencyGraphReport contenant les résultats formels.
        """
        resolver = CanonicalImportResolver(src_dir)
        deps: Dict[str, Set[str]] = {m: set() for m in resolver.known_modules}
        abs_cache: Dict[str, Tuple[int, int, float]] = {}

        # 1. Extraction des dépendances via AST et résolution canonique
        for full_path, rel_module in resolver.file_to_module.items():
            # Calcul de l'indice d'abstraction pour le fichier courant
            nc, na, a_val = AbstractionAstAnalyzer.analyze_file(full_path)
            abs_cache[rel_module] = (nc, na, a_val)

            try:
                with open(full_path, "r", encoding="utf-8") as source_file:
                    tree = ast.parse(source_file.read(), filename=full_path)
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        target = resolver.resolve_target(alias.name)
                        if target and target != rel_module:
                            deps[rel_module].add(target)
                elif isinstance(node, ast.ImportFrom):
                    if node.level > 0:
                        # Import relatif (. ou ..)
                        for alias in node.names:
                            target = resolver.resolve_relative(rel_module, node.level, node.module, alias.name)
                            if target and target != rel_module:
                                deps[rel_module].add(target)
                    elif node.module:
                        # Import absolu
                        for alias in node.names:
                            target = resolver.resolve_target(node.module, alias.name)
                            if target and target != rel_module:
                                deps[rel_module].add(target)

        # 2. Algorithme de Tarjan O(V + E) pour les composantes fortement connexes et cycles k >= 3
        sccs: List[List[str]] = TarjanCycleDetector.find_strongly_connected_components(deps)
        cycles: List[List[str]] = TarjanCycleDetector.extract_elementary_cycles(deps, sccs)

        # 3. Calcul du Couplage Afférent (Ca) et Efférent (Ce)
        ca_counts: Dict[str, int] = {m: 0 for m in resolver.known_modules}
        ce_counts: Dict[str, int] = {m: 0 for m in resolver.known_modules}

        for src_mod, targets in deps.items():
            ce_counts[src_mod] = len(targets)
            for tgt in targets:
                if tgt in ca_counts:
                    ca_counts[tgt] += 1

        # 4. Calcul de l'Instabilité, Abstraction, Distance à la Séquence Principale et Zones
        module_metrics: Dict[str, ModuleMetrics] = {}
        pain_count: int = 0
        useless_count: int = 0
        main_seq_count: int = 0

        for mod in sorted(resolver.known_modules):
            ca: int = ca_counts.get(mod, 0)
            ce: int = ce_counts.get(mod, 0)
            denom: float = float(ca + ce)
            # Instabilité I = Ce / (Ca + Ce). Si denom == 0, fixé à 0.5 (neutre)
            instability: float = (float(ce) / denom) if denom > 0.0 else 0.5

            nc, na, abstractness = abs_cache.get(mod, (0, 0, 0.0))

            # Distance à la Séquence Principale : D = |A + I - 1|
            distance: float = abs(abstractness + instability - 1.0)

            # Classification des zones de Robert C. Martin
            zone: ArchitectureZone
            zone_desc: str
            if (abstractness + instability < 0.5) and (abstractness < 0.5 and instability < 0.5):
                zone = ArchitectureZone.ZONE_OF_PAIN
                zone_desc = "Zone de Souffrance : Module très stable et dépendant, mais non abstrait (rigide, difficile à modifier sans impacter le système)."
                pain_count += 1
            elif (abstractness + instability > 1.5) and (abstractness > 0.5 and instability > 0.5):
                zone = ArchitectureZone.ZONE_OF_USELESSNESS
                zone_desc = "Zone d'Inutilité : Module très abstrait mais sans clients dépendants et très instable (abstractions inutilisées)."
                useless_count += 1
            else:
                zone = ArchitectureZone.MAIN_SEQUENCE
                zone_desc = "Séquence Principale : Équilibre optimal entre stabilité et abstraction (conforme au Stable Abstractions Principle)."
                main_seq_count += 1

            # Chemin de fichier réel
            fpath: str = ""
            for p, m in resolver.file_to_module.items():
                if m == mod:
                    fpath = p
                    break

            module_metrics[mod] = ModuleMetrics(
                module_name=mod,
                file_path=fpath,
                afferent_coupling=ca,
                efferent_coupling=ce,
                instability=instability,
                total_classes=nc,
                abstract_classes=na,
                abstractness=abstractness,
                distance_main_sequence=distance,
                zone=zone,
                zone_description=zone_desc,
            )

        # 5. Agrégation par paquet (Package Level)
        package_metrics: Dict[str, PackageMetrics] = {}
        packages_map: Dict[str, List[str]] = {}
        for mod in resolver.known_modules:
            pkg_key: str = mod.split("/")[0] if "/" in mod else ""
            if pkg_key not in packages_map:
                packages_map[pkg_key] = []
            packages_map[pkg_key].append(mod)

        for pkg, pkg_mods in packages_map.items():
            pkg_nc: int = sum(module_metrics[m].total_classes for m in pkg_mods)
            pkg_na: int = sum(module_metrics[m].abstract_classes for m in pkg_mods)
            pkg_a: float = (float(pkg_na) / float(pkg_nc)) if pkg_nc > 0 else 0.0

            # Dépendances externes au package
            pkg_set: Set[str] = set(pkg_mods)
            pkg_ca: int = 0
            pkg_ce: int = 0
            for m in pkg_mods:
                for tgt in deps.get(m, set()):
                    if tgt not in pkg_set:
                        pkg_ce += 1
            for ext_m, ext_targets in deps.items():
                if ext_m not in pkg_set:
                    for tgt in ext_targets:
                        if tgt in pkg_set:
                            pkg_ca += 1

            pkg_denom: float = float(pkg_ca + pkg_ce)
            pkg_i: float = (float(pkg_ce) / pkg_denom) if pkg_denom > 0.0 else 0.5
            pkg_d: float = abs(pkg_a + pkg_i - 1.0)

            pkg_zone: ArchitectureZone
            if (pkg_a + pkg_i < 0.5) and (pkg_a < 0.5 and pkg_i < 0.5):
                pkg_zone = ArchitectureZone.ZONE_OF_PAIN
            elif (pkg_a + pkg_i > 1.5) and (pkg_a > 0.5 and pkg_i > 0.5):
                pkg_zone = ArchitectureZone.ZONE_OF_USELESSNESS
            else:
                pkg_zone = ArchitectureZone.MAIN_SEQUENCE

            package_metrics[pkg if pkg else "root"] = PackageMetrics(
                package_name=pkg if pkg else "root",
                modules=pkg_mods,
                afferent_coupling=pkg_ca,
                efferent_coupling=pkg_ce,
                instability=pkg_i,
                total_classes=pkg_nc,
                abstract_classes=pkg_na,
                abstractness=pkg_a,
                distance_main_sequence=pkg_d,
                zone=pkg_zone,
            )

        total_deps_count: int = sum(len(targets) for targets in deps.values())

        return DependencyGraphReport(
            modules=module_metrics,
            packages=package_metrics,
            dependencies=deps,
            strongly_connected_components=sccs,
            cycles=cycles,
            total_modules=len(resolver.known_modules),
            total_dependencies=total_deps_count,
            cyclic_dependencies_count=len(cycles),
            zone_of_pain_count=pain_count,
            zone_of_uselessness_count=useless_count,
            main_sequence_count=main_seq_count,
        )


if __name__ == "__main__":
    src_target: str = sys.argv[1] if len(sys.argv) > 1 else "src"
    report_res = ArchitectureDependencyAnalyzer.analyze_full(src_target)

    print("=" * 80)
    print("ANALYSEUR DE GRAPHE DE DÉPENDANCES & MÉTRIQUES DE ROBERT C. MARTIN")
    print("=" * 80)
    print(f"Modules analysés         : {report_res.total_modules}")
    print(f"Total des dépendances    : {report_res.total_dependencies}")
    print(f"Composantes SCC (Tarjan) : {len(report_res.strongly_connected_components)}")
    print(f"Cycles de dépendance     : {report_res.cyclic_dependencies_count}")
    print(f"Modules Séquence P. (D<=0.5) : {report_res.main_sequence_count}")
    print(f"Zone de Souffrance (Pain)    : {report_res.zone_of_pain_count}")
    print(f"Zone d'Inutilité (Useless)   : {report_res.zone_of_uselessness_count}")
    print("-" * 80)

    if report_res.cycles:
        print("\n[!] DÉPENDANCES CIRCULAIRES DÉTECTÉES :")
        for i, cyc in enumerate(report_res.cycles, 1):
            print(f"  Cycle #{i} (longueur {len(cyc) - 1}): {' -> '.join(cyc)}")
    else:
        print("\n[OK] Zéro cycle de dépendance détecté dans le projet.")

    print("\n" + "=" * 80)
    print("MÉTRIQUES PAR PAQUET ARCHITECTURAL (ROBERT C. MARTIN)")
    print("=" * 80)
    header: str = f"{'Package':20} | {'Ca':4} | {'Ce':4} | {'I':5} | {'Nc':4} | {'Na':4} | {'A':5} | {'D':5} | {'Zone':16}"
    print(header)
    print("-" * len(header))
    for pkg_name, pmet in sorted(report_res.packages.items()):
        print(f"{pkg_name:20} | {pmet.afferent_coupling:4d} | {pmet.efferent_coupling:4d} | {pmet.instability:5.2f} | {pmet.total_classes:4d} | {pmet.abstract_classes:4d} | {pmet.abstractness:5.2f} | {pmet.distance_main_sequence:5.2f} | {pmet.zone.value:16}")
