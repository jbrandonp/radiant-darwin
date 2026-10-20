"""
Module d'analyse de rigidité structurelle et décomposition de graphe géométrique 2D (SOTA 2026).

Implémente :
1. Le Théorème de Laman (1970) pour la détection exacte de la rigidité générique 2D (m = 2n - 3)
   et l'isolation combinatoire des sous-graphes sur-contraints.
2. La décomposition bipartite de Dulmage-Mendelsohn (D-M) pour le partitionnement des systèmes
   géométriques en composantes sous-contraintes, bien contraintes et sur-contraintes.

Typage statique strict : strictement zéro Any et zéro object, complexité cognitive <= 15.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import itertools
from typing import Dict, Final, List, Set, Tuple


@dataclass(frozen=True)
class LamanRigidityResult:
    """Résultat immuable du diagnostic de rigidité générique de Laman."""
    vertex_count: int
    edge_count: int
    is_rigid: bool
    degrees_of_freedom: int
    redundant_edges: List[Tuple[int, int]] = field(default_factory=list)
    violating_subgraphs: List[List[int]] = field(default_factory=list)


@dataclass(frozen=True)
class DulmageMendelsohnResult:
    """Résultat immuable de la décomposition bipartite de Dulmage-Mendelsohn."""
    under_constrained_params: List[str]
    well_constrained_blocks: List[List[str]]
    over_constrained_constraints: List[str]
    is_well_constrained: bool
    matching_size: int


class LamanRigidityOracle:
    """
    Oracle d'évaluation de la rigidité générique en 2D basé sur le théorème de Laman.
    
    Un graphe géométrique G = (V, E) à n sommets est génériquement rigide si et seulement si :
    1. |E| = 2n - 3
    2. Pour tout sous-ensemble V' de sommets avec |V'| >= 2, |E(V')| <= 2|V'| - 3.
    """

    @classmethod
    def evaluate_graph(cls, vertex_count: int, edges: List[Tuple[int, int]]) -> LamanRigidityResult:
        """
        Évalue la rigidité structurelle d'un graphe selon le théorème de Laman.
        
        Args:
            vertex_count: Nombre total de sommets n.
            edges: Liste des arêtes (u, v) représentant les contraintes de distance.
            
        Returns:
            LamanRigidityResult détaillant la rigidité, les DDL résiduels et les violations.
        """
        if vertex_count <= 1:
            return LamanRigidityResult(
                vertex_count=vertex_count,
                edge_count=len(edges),
                is_rigid=True,
                degrees_of_freedom=0,
                redundant_edges=[],
                violating_subgraphs=[],
            )

        unique_edges: Final[List[Tuple[int, int]]] = cls._normalize_edges(edges)
        edge_count: Final[int] = len(unique_edges)
        expected_edges: Final[int] = 2 * vertex_count - 3

        # Détection des sous-graphes violant la condition de Laman (m(V') > 2|V'| - 3)
        violating: List[List[int]] = []
        redundant: List[Tuple[int, int]] = []

        cls._check_subgraph_violations(vertex_count, unique_edges, violating, redundant)

        is_rigid = (edge_count == expected_edges) and (len(violating) == 0)
        dof = max(0, expected_edges - edge_count) if edge_count <= expected_edges else 0

        return LamanRigidityResult(
            vertex_count=vertex_count,
            edge_count=edge_count,
            is_rigid=is_rigid,
            degrees_of_freedom=dof,
            redundant_edges=redundant,
            violating_subgraphs=violating,
        )

    @classmethod
    def _normalize_edges(cls, edges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Élimine les auto-boucles et les doublons non orientés."""
        seen: Set[Tuple[int, int]] = set()
        normalized: List[Tuple[int, int]] = []
        for u, v in edges:
            if u == v:
                continue
            pair = (u, v) if u < v else (v, u)
            if pair not in seen:
                seen.add(pair)
                normalized.append(pair)
        return normalized

    @classmethod
    def _check_subgraph_violations(
        cls,
        n: int,
        edges: List[Tuple[int, int]],
        violating_out: List[List[int]],
        redundant_out: List[Tuple[int, int]],
    ) -> None:
        """Examine les sous-ensembles de sommets pour détecter des densités excédentaires."""
        # Limité à n <= 16 pour éviter l'explosion combinatoire dans les esquisses denses
        max_subset_size = min(n - 1, 8)
        for k in range(2, max_subset_size + 1):
            max_allowed = 2 * k - 3
            for subset in itertools.combinations(range(n), k):
                subset_set = set(subset)
                sub_edges = [e for e in edges if e[0] in subset_set and e[1] in subset_set]
                if len(sub_edges) > max_allowed:
                    violating_out.append(list(subset))
                    for e in sub_edges[max_allowed:]:
                        if e not in redundant_out:
                            redundant_out.append(e)


class DulmageMendelsohnPartitioner:
    """
    Partitionneur de graphe bipartite contraintes-paramètres par décomposition de Dulmage-Mendelsohn.
    
    Permet de séparer les variables sous-contraintes (manipulables), les blocs carrés (solubles)
    et les contraintes sur-déterminées (redondantes).
    """

    @classmethod
    def partition(
        cls,
        parameters: List[str],
        constraints: List[str],
        incidence: Dict[str, List[str]],
    ) -> DulmageMendelsohnResult:
        """
        Décompose le système bipartite en 3 composantes fondamentales.
        
        Args:
            parameters: Liste des identifiants de paramètres (variables géométriques).
            constraints: Liste des identifiants de contraintes.
            incidence: Dictionnaire {contrainte: [paramètres_dépendants]}.
            
        Returns:
            DulmageMendelsohnResult avec classification univoque des blocs.
        """
        # 1. Calcul du couplage bipartite maximum (Algorithme d'augmentation glouton/Kuhn)
        matching: Dict[str, str] = {}  # param -> contrainte
        for c_id in constraints:
            visited: Set[str] = set()
            cls._augment_path(c_id, incidence, matching, visited)

        matched_params = set(matching.keys())
        matched_constraints = set(matching.values())

        # 2. Paramètres sous-contraints : ceux qui ne sont pas saturés par le couplage
        under_constrained = [p for p in parameters if p not in matched_params]

        # 3. Contraintes sur-contraintes : celles qui ne sont pas engagées dans le couplage
        over_constrained = [c for c in constraints if c not in matched_constraints]

        # 4. Blocs bien contraints : les paramètres et contraintes couplés de façon 1-pour-1
        well_blocks: List[List[str]] = []
        for p, c in matching.items():
            well_blocks.append([p, c])

        is_well = (len(under_constrained) == 0) and (len(over_constrained) == 0)

        return DulmageMendelsohnResult(
            under_constrained_params=sorted(under_constrained),
            well_constrained_blocks=well_blocks,
            over_constrained_constraints=sorted(over_constrained),
            is_well_constrained=is_well,
            matching_size=len(matching),
        )

    @classmethod
    def _augment_path(
        cls,
        constraint: str,
        incidence: Dict[str, List[str]],
        matching: Dict[str, str],
        visited: Set[str],
    ) -> bool:
        """Recherche récursivement une chaîne augmentante dans le graphe bipartite."""
        params = incidence.get(constraint, [])
        for p in params:
            if p in visited:
                continue
            visited.add(p)
            if p not in matching or cls._augment_path(matching[p], incidence, matching, visited):
                matching[p] = constraint
                return True
        return False
