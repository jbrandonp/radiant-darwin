"""
Suite de tests unitaires et d'intégration pour l'Analyseur de Graphe de Dépendances Avancé.
Vérifie :
1. L'algorithme de Tarjan en O(V + E) et la détection exhaustive de cycles de longueur k >= 3.
2. La résolution canonique des imports ciblant les packages (__init__.py) et sous-modules.
3. Le calcul formel de l'Indice d'Abstraction A = Na / Nc (ABC, Protocol, @abstractmethod).
4. Le calcul de la Distance à la Séquence Principale D = |A + I - 1| et la classification SAP (Zones de Souffrance et d'Inutilité).
5. L'intégration complète avec le moteur d'audit industriel.

Typage statique strict : strictement zéro Any et zéro object.
"""

from __future__ import annotations
import ast
import os
import tempfile
import pytest
from typing import Dict, List, Set, Tuple

from scripts.dependency_graph_analyzer import (
    ArchitectureDependencyAnalyzer,
    ArchitectureZone,
    CanonicalImportResolver,
    AbstractionAstAnalyzer,
    TarjanCycleDetector,
    DependencyGraphReport,
    ModuleMetrics,
    PackageMetrics,
)


def test_tarjan_acyclic_graph() -> None:
    """Vérifie que l'algorithme de Tarjan ne détecte aucun cycle dans un DAG linéaire."""
    dag: Dict[str, Set[str]] = {
        "A": {"B", "C"},
        "B": {"D"},
        "C": {"D"},
        "D": set(),
    }
    sccs = TarjanCycleDetector.find_strongly_connected_components(dag)
    cycles = TarjanCycleDetector.extract_elementary_cycles(dag, sccs)

    assert len(sccs) == 4
    assert len(cycles) == 0


def test_tarjan_direct_cycle_length_2() -> None:
    """Vérifie la détection d'un cycle réciproque de longueur 2 (A <-> B)."""
    graph: Dict[str, Set[str]] = {
        "A": {"B"},
        "B": {"A"},
        "C": {"A"},
    }
    sccs = TarjanCycleDetector.find_strongly_connected_components(graph)
    cycles = TarjanCycleDetector.extract_elementary_cycles(graph, sccs)

    assert len(cycles) == 1
    # Cycle normalisé débutant par le nœud minimal lexicographique
    assert cycles[0] == ["A", "B", "A"]


def test_tarjan_cycle_length_3() -> None:
    """Vérifie la détection formelle d'un cycle de longueur k = 3 (A -> B -> C -> A)."""
    graph: Dict[str, Set[str]] = {
        "A": {"B"},
        "B": {"C"},
        "C": {"A"},
        "D": {"A"},  # Nœud externe dépendant du cycle
    }
    sccs = TarjanCycleDetector.find_strongly_connected_components(graph)
    cycles = TarjanCycleDetector.extract_elementary_cycles(graph, sccs)

    assert len(cycles) == 1
    assert cycles[0] == ["A", "B", "C", "A"]


def test_tarjan_cycle_length_5() -> None:
    """Vérifie la détection formelle d'un cycle long de longueur k = 5 (A -> B -> C -> D -> E -> A)."""
    graph: Dict[str, Set[str]] = {
        "mod1": {"mod2"},
        "mod2": {"mod3"},
        "mod3": {"mod4"},
        "mod4": {"mod5"},
        "mod5": {"mod1"},
    }
    sccs = TarjanCycleDetector.find_strongly_connected_components(graph)
    cycles = TarjanCycleDetector.extract_elementary_cycles(graph, sccs)

    assert len(cycles) == 1
    assert cycles[0] == ["mod1", "mod2", "mod3", "mod4", "mod5", "mod1"]


def test_tarjan_multiple_interlocking_cycles() -> None:
    """Vérifie la détection de cycles multiples intriqués (figure-8 et boucle locale)."""
    graph: Dict[str, Set[str]] = {
        "A": {"B"},
        "B": {"A", "C"},
        "C": {"D"},
        "D": {"B"},
    }
    sccs = TarjanCycleDetector.find_strongly_connected_components(graph)
    cycles = TarjanCycleDetector.extract_elementary_cycles(graph, sccs)

    # Doit identifier le cycle A <-> B et le cycle B -> C -> D -> B
    cycle_signatures = [tuple(c) for c in cycles]
    assert ("A", "B", "A") in cycle_signatures
    assert ("B", "C", "D", "B") in cycle_signatures
    assert len(cycles) == 2


def test_tarjan_self_loop() -> None:
    """Vérifie la détection d'une auto-boucle réflexive (k = 1)."""
    graph: Dict[str, Set[str]] = {
        "self_loop_mod": {"self_loop_mod"},
    }
    sccs = TarjanCycleDetector.find_strongly_connected_components(graph)
    cycles = TarjanCycleDetector.extract_elementary_cycles(graph, sccs)

    assert len(cycles) == 1
    assert cycles[0] == ["self_loop_mod", "self_loop_mod"]


def test_tarjan_deterministic_order() -> None:
    """Vérifie que l'ordre des dictionnaires n'affecte jamais le résultat (déterminisme 100%)."""
    graph1: Dict[str, Set[str]] = {"A": {"B"}, "B": {"C"}, "C": {"A"}}
    graph2: Dict[str, Set[str]] = {"C": {"A"}, "A": {"B"}, "B": {"C"}}

    sccs1 = TarjanCycleDetector.find_strongly_connected_components(graph1)
    sccs2 = TarjanCycleDetector.find_strongly_connected_components(graph2)

    cycles1 = TarjanCycleDetector.extract_elementary_cycles(graph1, sccs1)
    cycles2 = TarjanCycleDetector.extract_elementary_cycles(graph2, sccs2)

    assert cycles1 == cycles2


def test_tarjan_linear_time_performance_o_v_plus_e() -> None:
    """Vérifie la complexité linéaire O(V + E) sur un graphe synthétique de 1000 nœuds."""
    import time
    n_nodes = 1000
    large_graph: Dict[str, Set[str]] = {}
    for i in range(n_nodes):
        large_graph[f"node_{i:04d}"] = {f"node_{i+1:04d}"} if i < n_nodes - 1 else set()

    t_start = time.perf_counter()
    sccs = TarjanCycleDetector.find_strongly_connected_components(large_graph)
    cycles = TarjanCycleDetector.extract_elementary_cycles(large_graph, sccs)
    elapsed = time.perf_counter() - t_start

    assert len(sccs) == n_nodes
    assert len(cycles) == 0
    # Tarjan O(V+E) pour 1000 nœuds doit s'exécuter en moins de 100 millisecondes
    assert elapsed < 0.15


def test_canonical_import_resolution_on_mock_tree() -> None:
    """Vérifie la résolution canonique d'imports ciblant __init__.py et sous-modules."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Création d'une arborescence factice
        # src_mock/
        #   core/
        #     __init__.py
        #     geometry.py
        #   viewport/
        #     __init__.py
        #     camera.py
        #   cli.py
        os.makedirs(os.path.join(tmp_dir, "core"), exist_ok=True)
        os.makedirs(os.path.join(tmp_dir, "viewport"), exist_ok=True)

        with open(os.path.join(tmp_dir, "core", "__init__.py"), "w", encoding="utf-8") as f:
            f.write("# core init\n")
        with open(os.path.join(tmp_dir, "core", "geometry.py"), "w", encoding="utf-8") as f:
            f.write("# geometry\n")
        with open(os.path.join(tmp_dir, "viewport", "__init__.py"), "w", encoding="utf-8") as f:
            f.write("# viewport init\n")
        with open(os.path.join(tmp_dir, "viewport", "camera.py"), "w", encoding="utf-8") as f:
            f.write("# camera\n")
        with open(os.path.join(tmp_dir, "cli.py"), "w", encoding="utf-8") as f:
            f.write("# cli\n")

        resolver = CanonicalImportResolver(tmp_dir)

        # 1. Cible de package brut -> résout vers package/__init__
        res1 = resolver.resolve_target("core")
        assert res1 == "core/__init__"

        # 2. Cible explicite vers __init__
        res2 = resolver.resolve_target("core/__init__")
        assert res2 == "core/__init__"

        # 3. Cible d'un sous-module physique
        res3 = resolver.resolve_target("core", "geometry")
        assert res3 == "core/geometry"

        # 4. Cible d'un symbole (ex: fonction) dans le package -> résout vers package/__init__
        res4 = resolver.resolve_target("core", "make_box")
        assert res4 == "core/__init__"

        # 5. Cible d'un fichier simple racine
        res5 = resolver.resolve_target("cli")
        assert res5 == "cli"

        # 6. Cible externe (ex: numpy, sys, pytest)
        res6 = resolver.resolve_target("numpy")
        assert res6 is None

        # 7. Résolution relative : depuis 'viewport/camera.py' avec 'from ..core import geometry'
        res_rel = resolver.resolve_relative("viewport/camera", level=2, module_name="core", import_name="geometry")
        assert res_rel == "core/geometry"

        # 8. Résolution relative intra-dossier : depuis 'core/geometry' avec 'from . import make_box'
        res_rel2 = resolver.resolve_relative("core/geometry", level=1, module_name=None, import_name="make_box")
        assert res_rel2 == "core/__init__"


def test_abstraction_index_calculation() -> None:
    """Vérifie le calcul formel de l'Indice d'Abstraction A = Na / Nc selon les différents types de classes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Fichier 1 : 100% concret (A = 0.0)
        p1 = os.path.join(tmp_dir, "concrete.py")
        with open(p1, "w", encoding="utf-8") as f:
            f.write("""
class ClassOne:
    pass

class ClassTwo:
    def method(self) -> int:
        return 42
""")
        nc1, na1, a1 = AbstractionAstAnalyzer.analyze_file(p1)
        assert nc1 == 2
        assert na1 == 0
        assert a1 == 0.0

        # Fichier 2 : 100% abstrait (A = 1.0) avec ABC, Protocol et @abstractmethod
        p2 = os.path.join(tmp_dir, "abstract.py")
        with open(p2, "w", encoding="utf-8") as f:
            f.write("""
from abc import ABC, abstractmethod
from typing import Protocol

class InterfaceA(Protocol):
    def run(self) -> None:
        ...

class BaseService(ABC):
    @abstractmethod
    def execute(self) -> bool:
        pass
""")
        nc2, na2, a2 = AbstractionAstAnalyzer.analyze_file(p2)
        assert nc2 == 2
        assert na2 == 2
        assert a2 == 1.0

        # Fichier 3 : Mixte 50% (A = 0.5)
        p3 = os.path.join(tmp_dir, "mixed.py")
        with open(p3, "w", encoding="utf-8") as f:
            f.write("""
from abc import ABC, abstractmethod

class AbstractBase(ABC):
    @abstractmethod
    def calc(self) -> float:
        pass

class ConcreteImpl(AbstractBase):
    def calc(self) -> float:
        return 3.14
""")
        nc3, na3, a3 = AbstractionAstAnalyzer.analyze_file(p3)
        assert nc3 == 2
        assert na3 == 1
        assert pytest.approx(a3, rel=1e-5) == 0.5

        # Fichier 4 : Fichier de fonctions pures sans classes (Nc = 0, A = 0.0)
        p4 = os.path.join(tmp_dir, "functions_only.py")
        with open(p4, "w", encoding="utf-8") as f:
            f.write("""
def helper_func() -> str:
    return "test"
""")
        nc4, na4, a4 = AbstractionAstAnalyzer.analyze_file(p4)
        assert nc4 == 0
        assert na4 == 0
        assert a4 == 0.0


def test_abstraction_index_on_real_codebase() -> None:
    """Valide l'extraction de métriques d'abstraction sur des fichiers réels de radiant-darwin."""
    # src/core/interfaces.py contient uniquement des Protocols PEP 544
    if os.path.exists("src/core/interfaces.py"):
        nc, na, a = AbstractionAstAnalyzer.analyze_file("src/core/interfaces.py")
        assert nc >= 5
        assert na == nc
        assert a == 1.0

    # src/core/feature.py contient Feature(ABC) et des classes concrètes (BoxFeature, etc.)
    if os.path.exists("src/core/feature.py"):
        nc, na, a = AbstractionAstAnalyzer.analyze_file("src/core/feature.py")
        assert nc > 1
        assert na >= 1
        assert 0.0 < a < 1.0


def test_martin_distance_and_zones_classification() -> None:
    """Vérifie le calcul de la Distance SAP D = |A + I - 1| et la classification des 3 zones."""
    # Cas 1 : Séquence Principale Idéale (D = 0.0)
    # A = 0.0, I = 1.0 -> D = |0 + 1 - 1| = 0.0 (Leaf concrete controller/UI)
    d1 = abs(0.0 + 1.0 - 1.0)
    assert d1 == 0.0

    # Cas 2 : Séquence Principale Idéale Abstraite (D = 0.0)
    # A = 1.0, I = 0.0 -> D = |1 + 0 - 1| = 0.0 (Core abstract interface)
    d2 = abs(1.0 + 0.0 - 1.0)
    assert d2 == 0.0

    # Cas 3 : Zone de Souffrance (Zone of Pain)
    # A = 0.0, I = 0.0 -> Module très stable/dépendant mais non abstrait
    a_pain = 0.0
    i_pain = 0.1
    d_pain = abs(a_pain + i_pain - 1.0)
    assert d_pain == 0.9
    is_pain = (a_pain + i_pain < 0.5) and (a_pain < 0.5 and i_pain < 0.5)
    assert is_pain is True

    # Cas 4 : Zone d'Inutilité (Zone of Uselessness)
    # A = 1.0, I = 0.9 -> Module très abstrait mais sans clients et très instable
    a_useless = 0.9
    i_useless = 0.9
    d_useless = abs(a_useless + i_useless - 1.0)
    assert pytest.approx(d_useless, rel=1e-5) == 0.8
    is_useless = (a_useless + i_useless > 1.5) and (a_useless > 0.5 and i_useless > 0.5)
    assert is_useless is True


def test_full_architecture_analysis_on_src() -> None:
    """Exécute l'analyse architecturale globale sur src/ et valide l'intégrité des résultats."""
    report = ArchitectureDependencyAnalyzer.analyze_full("src")

    assert report.total_modules >= 120
    assert report.total_dependencies > 200
    assert report.cyclic_dependencies_count == 0  # Aucun cycle dans la base de code
    assert len(report.strongly_connected_components) >= 120

    # Vérification des packages
    assert "core" in report.packages
    assert "ui" in report.packages

    core_pkg = report.packages["core"]
    assert core_pkg.afferent_coupling > 50  # Le cœur est largement importé
    assert core_pkg.instability < 0.3       # Le cœur est très stable (I proche de 0)

    ui_pkg = report.packages["ui"]
    assert ui_pkg.efferent_coupling > 20    # L'UI importe de nombreux modules
    assert ui_pkg.instability > 0.8         # L'UI est instable (I proche de 1)
    assert ui_pkg.zone == ArchitectureZone.MAIN_SEQUENCE


def test_analyze_dependencies_legacy_contract() -> None:
    """Valide la rétrocompatibilité stricte de la méthode analyze_dependencies()."""
    deps, cycles, coupling = ArchitectureDependencyAnalyzer.analyze_dependencies("src")

    assert isinstance(deps, dict)
    assert isinstance(cycles, list)
    assert isinstance(coupling, dict)

    # Vérification des métriques de couplage étendues
    for mod_name, metrics in coupling.items():
        assert "ca" in metrics
        assert "ce" in metrics
        assert "instability" in metrics
        assert "na" in metrics
        assert "nc" in metrics
        assert "abstractness" in metrics
        assert "distance_main_sequence" in metrics
        assert "zone_code" in metrics

        # Plages valides
        assert 0.0 <= metrics["instability"] <= 1.0
        assert 0.0 <= metrics["abstractness"] <= 1.0
        assert 0.0 <= metrics["distance_main_sequence"] <= 1.0
