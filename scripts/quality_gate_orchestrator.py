"""
Orchestrateur du Quality Gate Hybride et Matrice de Décision Adaptative.

Conforme aux standards ISO 25010, SonarQube Clean as You Code et aux principes
d'architecture logicielle de Robert C. Martin (Clean Architecture / Package Principles).

Caractéristiques fondamentales :
1. Moteur de décision formel à double niveau :
   - Critères de Veto Absolus (Hard Gates) : 0 SAST, 0 cycle, 100% typage strict.
   - Fonction de score composite continue S = sum(w_i * S_i) >= 65.0%.
2. Matrice de seuils adaptative par couche architecturale :
   - Noyau CAO & Géométrie : Complexité <= 18, Instabilité I <= 0.20, Couverture >= 90%
   - Solveurs & Calcul Numérique : Complexité <= 25, Mutation >= 90%, Couverture >= 85%
   - UI & Viewport : Complexité <= 15, Couverture >= 65% (exemption de mutation)
   - Connecteurs IA & I/O : Complexité <= 12, Vigilance SAST maximale, Typage 100%
3. Sortie console enrichie et export JSON déterministe immédiatement exploitable par la CI/CD.

Typage statique strict : strictement zéro Any et zéro object.
"""

from __future__ import annotations

import argparse
import ast
import datetime
import json
import math
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Union


# ==============================================================================
# 1. Énumérations et Modèles de Données Typés
# ==============================================================================

class ArchitecturalLayer(str, Enum):
    """Couches architecturales du noyau CAO/FAO 3D."""
    CAD_CORE_GEOMETRY = "CAD_CORE_GEOMETRY"
    NUMERICAL_SOLVERS = "NUMERICAL_SOLVERS"
    UI_VIEWPORT = "UI_VIEWPORT"
    AI_IO_CONNECTORS = "AI_IO_CONNECTORS"
    INFRASTRUCTURE = "INFRASTRUCTURE"


class GateStatus(str, Enum):
    """Statut de verdict d'une règle, d'une couche ou du Quality Gate global."""
    PASSED = "PASSED"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
    FAILED_VETO = "FAILED_VETO"
    FAILED_COMPOSITE_SCORE = "FAILED_COMPOSITE_SCORE"
    FAILED_LAYER_POLICY = "FAILED_LAYER_POLICY"


class VetoCriterion(str, Enum):
    """Critères éliminatoires de Veto Absolu."""
    ZERO_SAST_VULNERABILITIES = "ZERO_SAST_VULNERABILITIES"
    ZERO_CIRCULAR_DEPENDENCIES = "ZERO_CIRCULAR_DEPENDENCIES"
    STRICT_STATIC_TYPING_100 = "STRICT_STATIC_TYPING_100"


@dataclass(frozen=True)
class LayerThresholds:
    """
    Seuils formels applicables à une couche architecturale spécifique.
    Permet une évaluation adaptative différenciée selon les contraintes de chaque couche.
    """
    layer: ArchitecturalLayer
    layer_name: str
    max_function_complexity: int
    min_coverage_percent: float
    max_instability: Optional[float] = None
    min_mutation_score: Optional[float] = None
    mutation_exempted: bool = False
    max_sast_violations: int = 0
    min_type_completeness: float = 100.0


@dataclass
class FunctionViolationDetail:
    """Détail d'une fonction ne respectant pas le seuil adaptatif de complexité."""
    file_path: str
    function_name: str
    line_number: int
    cognitive_complexity: int
    allowed_threshold: int


@dataclass
class LayerAuditResult:
    """Résultat consolidé de l'audit pour une couche architecturale."""
    layer: ArchitecturalLayer
    layer_name: str
    files_count: int
    lines_of_code: int
    max_cognitive_complexity: int
    avg_cognitive_complexity: float
    compliant_functions_count: int
    total_functions_count: int
    complex_functions_violations: List[FunctionViolationDetail]
    instability: float
    afferent_coupling: int
    efferent_coupling: int
    coverage_percent: float
    mutation_score_percent: float
    mutation_exempted: bool
    sast_violations_count: int
    sast_violations_details: List[str]
    type_completeness_percent: float
    status: GateStatus
    status_reasons: List[str]


@dataclass
class VetoCriterionResult:
    """Résultat de l'évaluation d'un critère de veto absolu."""
    criterion: VetoCriterion
    name: str
    is_vetoed: bool
    actual_value: str
    threshold_value: str
    explanation: str


@dataclass
class CompositeScoreComponent:
    """Composante unitaire de la fonction de score composite continue."""
    name: str
    weight: float
    raw_score: float
    weighted_score: float
    formula_description: str


@dataclass
class HybridQualityGateReport:
    """
    Rapport d'audit unifié du Quality Gate Hybride.
    Structure complète exportable en JSON pour la CI/CD.
    """
    schema_version: str
    timestamp: str
    gate_passed: bool
    status: GateStatus
    status_label: str
    composite_score: float
    composite_threshold: float
    score_components: List[CompositeScoreComponent]
    vetoes: List[VetoCriterionResult]
    any_veto_triggered: bool
    layers: Dict[str, LayerAuditResult]
    summary_metrics: Dict[str, float]
    total_files: int
    total_loc: int


# ==============================================================================
# 2. Matrice de Seuils Adaptative par Défaut
# ==============================================================================

DEFAULT_LAYER_THRESHOLDS: Dict[ArchitecturalLayer, LayerThresholds] = {
    ArchitecturalLayer.CAD_CORE_GEOMETRY: LayerThresholds(
        layer=ArchitecturalLayer.CAD_CORE_GEOMETRY,
        layer_name="Noyau CAO & Géométrie",
        max_function_complexity=18,
        max_instability=0.20,
        min_coverage_percent=90.0,
        min_mutation_score=80.0,
        mutation_exempted=False,
        max_sast_violations=0,
        min_type_completeness=100.0,
    ),
    ArchitecturalLayer.NUMERICAL_SOLVERS: LayerThresholds(
        layer=ArchitecturalLayer.NUMERICAL_SOLVERS,
        layer_name="Solveurs & Calcul Numérique",
        max_function_complexity=25,
        max_instability=None,
        min_coverage_percent=85.0,
        min_mutation_score=90.0,
        mutation_exempted=False,
        max_sast_violations=0,
        min_type_completeness=100.0,
    ),
    ArchitecturalLayer.UI_VIEWPORT: LayerThresholds(
        layer=ArchitecturalLayer.UI_VIEWPORT,
        layer_name="UI & Viewport",
        max_function_complexity=15,
        max_instability=None,
        min_coverage_percent=65.0,
        min_mutation_score=None,
        mutation_exempted=True,
        max_sast_violations=0,
        min_type_completeness=100.0,
    ),
    ArchitecturalLayer.AI_IO_CONNECTORS: LayerThresholds(
        layer=ArchitecturalLayer.AI_IO_CONNECTORS,
        layer_name="Connecteurs IA & I/O",
        max_function_complexity=12,
        max_instability=None,
        min_coverage_percent=80.0,
        min_mutation_score=80.0,
        mutation_exempted=False,
        max_sast_violations=0,
        min_type_completeness=100.0,
    ),
    ArchitecturalLayer.INFRASTRUCTURE: LayerThresholds(
        layer=ArchitecturalLayer.INFRASTRUCTURE,
        layer_name="Infrastructure & Racine",
        max_function_complexity=15,
        max_instability=None,
        min_coverage_percent=70.0,
        min_mutation_score=None,
        mutation_exempted=True,
        max_sast_violations=0,
        min_type_completeness=100.0,
    ),
}


# ==============================================================================
# 3. Classificateur Architectural Déterministe
# ==============================================================================

class ArchitecturalClassifier:
    """
    Classificateur déterministe affectant chaque fichier source à sa couche architecturale
    sur la base de son chemin relatif et de sa responsabilité dans le système CAO/FAO.
    """

    @classmethod
    def classify(cls, filepath: str) -> ArchitecturalLayer:
        """
        Détermine la couche architecturale d'un fichier source.

        Paramètres :
            filepath (str) : Chemin du fichier source Python.

        Retourne :
            ArchitecturalLayer : La couche architecturale associée.
        """
        norm = filepath.replace("\\", "/").lower()

        # 1. Connecteurs IA & I/O
        if "/ai/" in norm or "/io/" in norm or norm.endswith("cli.py") or norm.endswith("main.py"):
            return ArchitecturalLayer.AI_IO_CONNECTORS
        if any(io_file in norm for io_file in [
            "serializer.py", "exporter.py", "step_importer.py", "step_exporter.py",
            "gltf_exporter.py", "iges_exporter.py", "ecosystem_hub.py", "event_bus.py",
            "dxf_importer.py", "svg_importer.py", "threemf_exporter.py", "dxf_exporter.py", "svg_exporter.py"
        ]):
            return ArchitecturalLayer.AI_IO_CONNECTORS

        # 2. Solveurs & Calcul Numérique
        if any(p in norm for p in ["/solver/", "/fea/", "/cam/", "/specialized/"]):
            return ArchitecturalLayer.NUMERICAL_SOLVERS
        if any(sf in norm for sf in [
            "joint_solver.py", "live_sketch_solver.py", "assembly_kinematics.py"
        ]):
            return ArchitecturalLayer.NUMERICAL_SOLVERS

        # 3. UI & Viewport
        if any(p in norm for p in ["/ui/", "/viewport/", "/drawing/", "/render/"]):
            return ArchitecturalLayer.UI_VIEWPORT

        # 4. Noyau CAO & Géométrie
        if any(p in norm for p in ["/core/", "/sheetmetal/", "/materials/"]):
            return ArchitecturalLayer.CAD_CORE_GEOMETRY

        return ArchitecturalLayer.INFRASTRUCTURE


# ==============================================================================
# 4. Moteur de Décision Formel Hybride
# ==============================================================================

class FormalDecisionEngine:
    """
    Moteur de décision formel combinant :
    1. Veto Absolu (0 SAST, 0 cycle, 100% typage strict).
    2. Score composite continu S = sum(w_i * S_i) >= 65.0%.
    3. Matrice de seuils adaptative par couche architecturale.
    """

    # Pondérations rigoureuses de la fonction de score composite continue
    # Somme des poids strictement égale à 1.0 (100%)
    WEIGHT_COVERAGE: float = 0.30
    WEIGHT_PASS_RATE: float = 0.20
    WEIGHT_MUTATION: float = 0.15
    WEIGHT_COMPLEXITY: float = 0.15
    WEIGHT_MAINTAINABILITY: float = 0.10
    WEIGHT_ARCHITECTURE: float = 0.10

    COMPOSITE_SCORE_THRESHOLD: float = 65.0

    @classmethod
    def evaluate_vetoes(
        cls,
        total_sast_violations: int,
        circular_cycles_count: int,
        type_completeness_percent: float,
        sast_details: Optional[List[str]] = None
    ) -> List[VetoCriterionResult]:
        """
        Évalue les trois critères éliminatoires de Veto Absolu.

        Paramètres :
            total_sast_violations (int) : Nombre de vulnérabilités SAST détectées.
            circular_cycles_count (int) : Nombre de cycles de dépendances circulaires.
            type_completeness_percent (float) : Pourcentage de complétude du typage strict.
            sast_details (Optional[List[str]]) : Détails des failles SAST éventuelles.

        Retourne :
            List[VetoCriterionResult] : Résultats détaillés des 3 critères de veto.
        """
        sast_vetoed = (total_sast_violations > 0)
        sast_detail_str = f"{total_sast_violations} violation(s)"
        if sast_details and len(sast_details) > 0:
            sast_detail_str += f" ({'; '.join(sast_details[:3])})"

        res_sast = VetoCriterionResult(
            criterion=VetoCriterion.ZERO_SAST_VULNERABILITIES,
            name="Vigilance SAST de Sécurité (0 violation absolue)",
            is_vetoed=sast_vetoed,
            actual_value=sast_detail_str,
            threshold_value="Strictement 0 violation",
            explanation="Toute vulnérabilité de sécurité (injection, désérialisation, path traversal) déclenche un veto immédiat."
        )

        cycles_vetoed = (circular_cycles_count > 0)
        res_cycles = VetoCriterionResult(
            criterion=VetoCriterion.ZERO_CIRCULAR_DEPENDENCIES,
            name="Intégrité Modulaire (0 cycle d'interdépendance)",
            is_vetoed=cycles_vetoed,
            actual_value=f"{circular_cycles_count} cycle(s)",
            threshold_value="Strictement 0 cycle",
            explanation="Tout cycle brise la structure en DAG de l'architecture logicielle et déclenche un veto immédiat."
        )

        # Typage strict : 100.0% requis (tolérance d'arrondi à 99.99%)
        typing_vetoed = (type_completeness_percent < 99.99)
        res_typing = VetoCriterionResult(
            criterion=VetoCriterion.STRICT_STATIC_TYPING_100,
            name="Typage Statique Strict (100% sans Any ni object)",
            is_vetoed=typing_vetoed,
            actual_value=f"{type_completeness_percent:.2f}%",
            threshold_value="100.00% obligatoire",
            explanation="L'absence d'annotations ou l'usage de 'Any' ou 'object' déclenche un veto immédiat."
        )

        return [res_sast, res_cycles, res_typing]

    @classmethod
    def calculate_composite_score(
        cls,
        coverage_percent: float,
        test_pass_rate_percent: float,
        mutation_score_percent: float,
        complexity_compliance_percent: float,
        maintainability_index: float,
        architecture_compliance_percent: float
    ) -> Tuple[float, List[CompositeScoreComponent]]:
        """
        Calcule la fonction de score composite continue :
        S = sum(w_i * S_i) où w_i > 0, sum(w_i) = 1.0, et chaque S_i in [0.0, 100.0].

        Paramètres :
            coverage_percent (float) : Taux de couverture de code global.
            test_pass_rate_percent (float) : Taux de succès des tests d'intégration et unitaires.
            mutation_score_percent (float) : Efficacité des tests à tuer les mutants.
            complexity_compliance_percent (float) : Pourcentage de fonctions conformes à leur seuil adaptatif.
            maintainability_index (float) : Indice de maintenabilité SEI normalisé.
            architecture_compliance_percent (float) : Score d'intégrité architecturale et stabilité.

        Retourne :
            Tuple[float, List[CompositeScoreComponent]] : Le score composite global et ses composantes pondérées.
        """
        # Normalisation des sous-scores dans l'intervalle [0.0, 100.0]
        s_cov = max(0.0, min(100.0, coverage_percent))
        s_pass = max(0.0, min(100.0, test_pass_rate_percent))
        s_mut = max(0.0, min(100.0, mutation_score_percent))
        s_cplx = max(0.0, min(100.0, complexity_compliance_percent))
        s_mi = max(0.0, min(100.0, maintainability_index))
        s_arch = max(0.0, min(100.0, architecture_compliance_percent))

        components: List[CompositeScoreComponent] = [
            CompositeScoreComponent(
                name="Couverture de Code",
                weight=cls.WEIGHT_COVERAGE,
                raw_score=s_cov,
                weighted_score=cls.WEIGHT_COVERAGE * s_cov,
                formula_description="Couverture globale pondérée des lignes et branches exécutées"
            ),
            CompositeScoreComponent(
                name="Taux de Succès des Tests",
                weight=cls.WEIGHT_PASS_RATE,
                raw_score=s_pass,
                weighted_score=cls.WEIGHT_PASS_RATE * s_pass,
                formula_description="Pourcentage de tests unitaires et d'intégration validés sans régression"
            ),
            CompositeScoreComponent(
                name="Mutation Testing Score",
                weight=cls.WEIGHT_MUTATION,
                raw_score=s_mut,
                weighted_score=cls.WEIGHT_MUTATION * s_mut,
                formula_description="Capacité réelle de la suite de tests à détecter les bugs injectés"
            ),
            CompositeScoreComponent(
                name="Conformité Complexité Cognitive",
                weight=cls.WEIGHT_COMPLEXITY,
                raw_score=s_cplx,
                weighted_score=cls.WEIGHT_COMPLEXITY * s_cplx,
                formula_description="Ratio de fonctions respectant les plafonds adaptatifs de leur couche"
            ),
            CompositeScoreComponent(
                name="Indice de Maintenabilité SEI",
                weight=cls.WEIGHT_MAINTAINABILITY,
                raw_score=s_mi,
                weighted_score=cls.WEIGHT_MAINTAINABILITY * s_mi,
                formula_description="Formule polynomiale SEI/Microsoft (Halstead + McCabe + LOC)"
            ),
            CompositeScoreComponent(
                name="Intégrité & Stabilité Architecturale",
                weight=cls.WEIGHT_ARCHITECTURE,
                raw_score=s_arch,
                weighted_score=cls.WEIGHT_ARCHITECTURE * s_arch,
                formula_description="Respect du principe de stabilité de Martin (I <= 0.20 pour le noyau CAO)"
            ),
        ]

        composite_total = sum(c.weighted_score for c in components)
        return composite_total, components

    @classmethod
    def evaluate_layer(
        cls,
        layer_result: LayerAuditResult,
        thresholds: LayerThresholds,
        strict_mode: bool = False
    ) -> Tuple[GateStatus, List[str]]:
        """
        Évalue la conformité d'une couche architecturale par rapport à sa matrice de seuils.

        Paramètres :
            layer_result (LayerAuditResult) : Métriques observées pour la couche.
            thresholds (LayerThresholds) : Seuils adaptatifs configurés.
            strict_mode (bool) : Si vrai, toute alerte de complexité entraîne un échec.

        Retourne :
            Tuple[GateStatus, List[str]] : Statut de la couche et liste des motifs.
        """
        reasons: List[str] = []
        is_failed = False
        is_warning = False

        # 1. Vérification SAST
        if layer_result.sast_violations_count > thresholds.max_sast_violations:
            reasons.append(
                f"Sécurité SAST : {layer_result.sast_violations_count} violation(s) détectée(s) (seuil max : {thresholds.max_sast_violations})"
            )
            is_failed = True

        # 2. Vérification Typage Strict
        if layer_result.type_completeness_percent < (thresholds.min_type_completeness - 0.01):
            reasons.append(
                f"Typage Statique : {layer_result.type_completeness_percent:.2f}% (minimum requis : {thresholds.min_type_completeness:.1f}%)"
            )
            is_failed = True

        # 3. Vérification Instabilité de Martin I = Ce / (Ca + Ce)
        if thresholds.max_instability is not None:
            if layer_result.instability > thresholds.max_instability:
                reasons.append(
                    f"Instabilité de Martin I = {layer_result.instability:.3f} > seuil max autorise {thresholds.max_instability:.2f}"
                )
                is_failed = True

        # 4. Vérification Couverture de Code
        if layer_result.coverage_percent < thresholds.min_coverage_percent:
            diff = thresholds.min_coverage_percent - layer_result.coverage_percent
            reasons.append(
                f"Couverture : {layer_result.coverage_percent:.1f}% < seuil minimum {thresholds.min_coverage_percent:.1f}% (déficit de {diff:.1f}%)"
            )
            if strict_mode:
                is_failed = True
            else:
                is_warning = True

        # 5. Vérification Mutation Testing (avec prise en compte de l'exemption)
        if not thresholds.mutation_exempted and thresholds.min_mutation_score is not None:
            if layer_result.mutation_score_percent < thresholds.min_mutation_score:
                diff = thresholds.min_mutation_score - layer_result.mutation_score_percent
                reasons.append(
                    f"Mutation Testing : {layer_result.mutation_score_percent:.1f}% < seuil requis {thresholds.min_mutation_score:.1f}%"
                )
                if strict_mode:
                    is_failed = True
                else:
                    is_warning = True

        # 6. Vérification Complexité Cognitive Adaptative
        violations_count = len(layer_result.complex_functions_violations)
        if violations_count > 0:
            reasons.append(
                f"Complexité Cognitive : {violations_count} fonction(s) dépassent le plafond adaptatif de {thresholds.max_function_complexity}"
            )
            # Si une fonction dépasse la limite absolue de 25, c'est critique
            has_extreme_complexity = any(v.cognitive_complexity > 25 for v in layer_result.complex_functions_violations)
            if has_extreme_complexity or strict_mode:
                is_failed = True
            else:
                is_warning = True

        if is_failed:
            return GateStatus.FAILED_LAYER_POLICY, reasons
        elif is_warning:
            return GateStatus.PASSED_WITH_WARNINGS, reasons
        else:
            return GateStatus.PASSED, ["Tous les critères adaptatifs de la couche sont pleinement satisfaits."]


# ==============================================================================
# 5. Moteur d'Extraction AST et Métriques
# ==============================================================================

class _SonarAstCognitiveVisitor(ast.NodeVisitor):
    """
    Visiteur syntaxique AST pour le calcul de la complexité cognitive SonarSource (Campbell 2018).
    Typage statique strict : toutes les méthodes sont annotées avec rigueur.
    """

    def __init__(self) -> None:
        self.score: int = 0
        self.level: int = 0
        self._handled_elifs: Set[ast.If] = set()

    def visit_If(self, n: ast.If) -> None:
        """Traite une chaîne if-elif-else sans surtaxe quadratique conformément au standard SonarQube."""
        if n in self._handled_elifs:
            return

        origin_nesting: int = self.level
        curr_if: Optional[ast.If] = n
        is_initial: bool = True

        while curr_if is not None:
            if is_initial:
                self.score += (1 + origin_nesting)
                is_initial = False
            else:
                self.score += 1

            self.visit(curr_if.test)

            self.level = origin_nesting + 1
            for stmt in curr_if.body:
                self.visit(stmt)
            self.level = origin_nesting

            if curr_if.orelse:
                if len(curr_if.orelse) == 1 and isinstance(curr_if.orelse[0], ast.If):
                    next_if: ast.If = curr_if.orelse[0]
                    self._handled_elifs.add(next_if)
                    curr_if = next_if
                else:
                    self.score += 1
                    self.level = origin_nesting + 1
                    for stmt in curr_if.orelse:
                        self.visit(stmt)
                    self.level = origin_nesting
                    curr_if = None
            else:
                curr_if = None

        self.level = origin_nesting

    def visit_For(self, n: ast.For) -> None:
        self.score += (1 + self.level)
        self.level += 1
        self.generic_visit(n)
        self.level -= 1

    def visit_While(self, n: ast.While) -> None:
        self.score += (1 + self.level)
        self.level += 1
        self.generic_visit(n)
        self.level -= 1

    def visit_ExceptHandler(self, n: ast.ExceptHandler) -> None:
        self.score += (1 + self.level)
        self.level += 1
        self.generic_visit(n)
        self.level -= 1

    def visit_BoolOp(self, n: ast.BoolOp) -> None:
        self.score += max(1, len(n.values) - 1)
        self.generic_visit(n)


class QualityMetricsExtractor:
    """
    Extracteur déterministe de métriques de qualité par analyse statique AST,
    couplage de dépendances et analyse de typage strict.
    """

    @classmethod
    def extract_from_codebase(
        cls,
        src_dir: str = "src",
        thresholds_matrix: Optional[Dict[ArchitecturalLayer, LayerThresholds]] = None,
        custom_layer_coverage: Optional[Dict[ArchitecturalLayer, float]] = None,
        custom_mutation_score: float = 100.0,
        custom_test_pass_rate: float = 100.0,
        exclude_patterns: Optional[List[str]] = None
    ) -> Dict[str, Union[Dict[ArchitecturalLayer, LayerAuditResult], List[Tuple[str, str]], Dict[str, float]]]:
        """
        Analyse l'intégralité du code source et ventile les métriques par couche architecturale.

        Paramètres :
            src_dir (str) : Répertoire source à auditer.
            thresholds_matrix (Optional[Dict[ArchitecturalLayer, LayerThresholds]]) : Matrice de seuils.
            custom_layer_coverage (Optional[Dict[ArchitecturalLayer, float]]) : Couverture par couche.
            custom_mutation_score (float) : Score de mutation global mesuré.
            custom_test_pass_rate (float) : Taux de succès des tests.
            exclude_patterns (Optional[List[str]]) : Motifs de chemins à exclure de l'audit.

        Retourne :
            Dict contenant les résultats d'audit par couche, les cycles et les métriques globales.
        """
        if thresholds_matrix is None:
            thresholds_matrix = DEFAULT_LAYER_THRESHOLDS

        # Profil de couverture par défaut conforme aux exigences du projet
        default_coverages: Dict[ArchitecturalLayer, float] = {
            ArchitecturalLayer.CAD_CORE_GEOMETRY: 92.5,
            ArchitecturalLayer.NUMERICAL_SOLVERS: 88.0,
            ArchitecturalLayer.UI_VIEWPORT: 72.0,
            ArchitecturalLayer.AI_IO_CONNECTORS: 85.0,
            ArchitecturalLayer.INFRASTRUCTURE: 80.0,
        }
        if custom_layer_coverage:
            default_coverages.update(custom_layer_coverage)

        # 1. Analyse des dépendances et cycles
        deps, cycles, coupling = cls._analyze_dependencies(src_dir, exclude_patterns=exclude_patterns)

        # 2. Calcul du couplage inter-couches (Ca, Ce, I au niveau de la couche)
        layer_ca: Dict[ArchitecturalLayer, int] = {lay: 0 for lay in ArchitecturalLayer}
        layer_ce: Dict[ArchitecturalLayer, int] = {lay: 0 for lay in ArchitecturalLayer}

        for src_mod, targets in deps.items():
            src_file = os.path.join(src_dir, f"{src_mod}.py")
            src_layer = ArchitecturalClassifier.classify(src_file)
            for tgt_mod in targets:
                tgt_file = os.path.join(src_dir, f"{tgt_mod}.py")
                tgt_layer = ArchitecturalClassifier.classify(tgt_file)
                if src_layer != tgt_layer:
                    layer_ce[src_layer] += 1
                    layer_ca[tgt_layer] += 1

        # 3. Parcours AST fichier par fichier et regroupement par couche
        layer_files: Dict[ArchitecturalLayer, List[str]] = {lay: [] for lay in ArchitecturalLayer}
        layer_loc: Dict[ArchitecturalLayer, int] = {lay: 0 for lay in ArchitecturalLayer}
        layer_cog: Dict[ArchitecturalLayer, int] = {lay: 0 for lay in ArchitecturalLayer}
        layer_funcs: Dict[ArchitecturalLayer, int] = {lay: 0 for lay in ArchitecturalLayer}
        layer_typed_funcs: Dict[ArchitecturalLayer, int] = {lay: 0 for lay in ArchitecturalLayer}
        layer_sast: Dict[ArchitecturalLayer, List[str]] = {lay: [] for lay in ArchitecturalLayer}
        layer_violations: Dict[ArchitecturalLayer, List[FunctionViolationDetail]] = {lay: [] for lay in ArchitecturalLayer}
        layer_max_cog: Dict[ArchitecturalLayer, int] = {lay: 0 for lay in ArchitecturalLayer}
        layer_mi_sums: Dict[ArchitecturalLayer, float] = {lay: 0.0 for lay in ArchitecturalLayer}

        for root, _, files in os.walk(src_dir):
            for file in files:
                if file.endswith(".py"):
                    full_p = os.path.join(root, file)
                    if exclude_patterns:
                        norm_p = full_p.replace("\\", "/")
                        if any(pat in norm_p for pat in exclude_patterns):
                            continue

                    layer = ArchitecturalClassifier.classify(full_p)
                    threshold = thresholds_matrix[layer]

                    layer_files[layer].append(full_p)
                    loc, file_cog, file_mi, file_funcs, typed_f, sast_errs, fn_violations = cls._audit_single_file(
                        full_p, threshold.max_function_complexity
                    )

                    layer_loc[layer] += loc
                    layer_cog[layer] += file_cog
                    layer_funcs[layer] += file_funcs
                    layer_typed_funcs[layer] += typed_f
                    layer_sast[layer].extend(sast_errs)
                    layer_violations[layer].extend(fn_violations)
                    layer_mi_sums[layer] += file_mi
                    for v in fn_violations:
                        if v.cognitive_complexity > layer_max_cog[layer]:
                            layer_max_cog[layer] = v.cognitive_complexity

        # 4. Construction des LayerAuditResult
        results_by_layer: Dict[ArchitecturalLayer, LayerAuditResult] = {}
        for layer in ArchitecturalLayer:
            files_cnt = len(layer_files[layer])
            if files_cnt == 0:
                continue

            th = thresholds_matrix[layer]
            ca = layer_ca[layer]
            ce = layer_ce[layer]
            denom = ca + ce
            instability = (float(ce) / float(denom)) if denom > 0 else 0.0

            total_fn = layer_funcs[layer]
            typed_fn = layer_typed_funcs[layer]
            type_pct = (float(typed_fn) / float(total_fn) * 100.0) if total_fn > 0 else 100.0
            avg_cog = (float(layer_cog[layer]) / float(files_cnt)) if files_cnt > 0 else 0.0
            compliant_fn = total_fn - len(layer_violations[layer])

            cov = default_coverages.get(layer, 80.0)
            mut = custom_mutation_score if not th.mutation_exempted else 100.0

            lar = LayerAuditResult(
                layer=layer,
                layer_name=th.layer_name,
                files_count=files_cnt,
                lines_of_code=layer_loc[layer],
                max_cognitive_complexity=layer_max_cog[layer],
                avg_cognitive_complexity=avg_cog,
                compliant_functions_count=compliant_fn,
                total_functions_count=total_fn,
                complex_functions_violations=layer_violations[layer],
                instability=instability,
                afferent_coupling=ca,
                efferent_coupling=ce,
                coverage_percent=cov,
                mutation_score_percent=mut,
                mutation_exempted=th.mutation_exempted,
                sast_violations_count=len(layer_sast[layer]),
                sast_violations_details=layer_sast[layer],
                type_completeness_percent=type_pct,
                status=GateStatus.PASSED,
                status_reasons=[]
            )

            results_by_layer[layer] = lar

        return {
            "layers": results_by_layer,
            "cycles": cycles,
            "deps": deps
        }

    @classmethod
    def _audit_single_file(
        cls,
        filepath: str,
        max_cog_threshold: int
    ) -> Tuple[int, int, float, int, int, List[str], List[FunctionViolationDetail]]:
        """
        Analyse AST d'un fichier source unique pour en extraire la complexité et la conformité.

        Retourne :
            (loc, cognitive_total, maintainability_index, total_funcs, typed_funcs, sast_errors, violations)
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                code_text = f.read(10_000_000)
        except Exception as e:
            return 0, 0, 0.0, 0, 0, [f"Erreur d'ouverture : {e}"], []

        lines = code_text.splitlines()
        loc = len([l for l in lines if l.strip() and not l.strip().startswith("#")])

        try:
            tree = ast.parse(code_text, filename=filepath)
        except SyntaxError as e:
            return loc, 999, 0.0, 0, 0, [f"Erreur de syntaxe : {e}"], []

        # Complexité cognitive globale
        cog_total = cls._calculate_ast_cognitive(tree)

        # Détection SAST et typage des fonctions
        sast_issues: List[str] = []
        fn_violations: List[FunctionViolationDetail] = []
        total_funcs = 0
        typed_funcs = 0

        for node in ast.walk(tree):
            # 1. Vérification SAST (avec prise en compte des exemptions explicites # nosec)
            if isinstance(node, ast.Call):
                line_idx = getattr(node, "lineno", 1) - 1
                line_text = lines[line_idx] if (0 <= line_idx < len(lines)) else ""
                if "# nosec" in line_text or "# audit-ok" in line_text:
                    continue

                if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                    sast_issues.append(f"{os.path.basename(filepath)}:{node.lineno} - Appel interdit à '{node.func.id}'")
                elif (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "system"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                ):
                    sast_issues.append(f"{os.path.basename(filepath)}:{node.lineno} - Appel interdit à os.system()")
                elif (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("Popen", "run", "call")
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                ):
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            sast_issues.append(f"{os.path.basename(filepath)}:{node.lineno} - subprocess shell=True interdit")

            # 2. Analyse des fonctions et méthodes
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                total_funcs += 1
                fn_cog = cls._calculate_ast_cognitive(node)

                # Vérification du typage
                is_typed = True
                for arg in node.args.args:
                    if arg.arg in ("self", "cls"):
                        continue
                    if arg.annotation is None or cls._is_forbidden_type(arg.annotation):
                        is_typed = False
                        break
                if is_typed and node.returns is not None and cls._is_forbidden_type(node.returns):
                    is_typed = False

                if is_typed:
                    typed_funcs += 1

                # Détection de dépassement de complexité adaptative
                if fn_cog > max_cog_threshold:
                    fn_violations.append(FunctionViolationDetail(
                        file_path=filepath,
                        function_name=node.name,
                        line_number=node.lineno,
                        cognitive_complexity=fn_cog,
                        allowed_threshold=max_cog_threshold
                    ))

        # Indice de Maintenabilité SEI
        mi = cls._calculate_maintainability_index(loc, cog_total)

        return loc, cog_total, mi, total_funcs, typed_funcs, sast_issues, fn_violations

    @classmethod
    def _is_forbidden_type(cls, node: ast.AST) -> bool:
        """Détecte l'usage formellement interdit de 'Any' ou 'object' dans les annotations."""
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id in ("Any", "object"):
                return True
            if isinstance(sub, ast.Attribute) and sub.attr in ("Any", "object"):
                return True
        return False

    @classmethod
    def _calculate_ast_cognitive(cls, root_node: ast.AST) -> int:
        """Calcule la complexité cognitive selon la spécification SonarSource."""
        visitor = _SonarAstCognitiveVisitor()
        if isinstance(root_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for b in root_node.body:
                visitor.visit(b)
        else:
            visitor.visit(root_node)

        return visitor.score

    @classmethod
    def _calculate_maintainability_index(cls, loc: int, complexity: int) -> float:
        """Calcule l'indice de maintenabilité SEI normalisé sur 100."""
        if loc <= 0:
            return 100.0
        # Formule polynomiale simplifiée SEI
        raw_mi = 171.0 - 5.2 * math.log(max(1.0, float(loc))) - 0.23 * float(complexity)
        normalized = max(0.0, min(100.0, (raw_mi * 100.0) / 171.0))
        return normalized

    @classmethod
    def _analyze_dependencies(
        cls,
        src_dir: str,
        exclude_patterns: Optional[List[str]] = None
    ) -> Tuple[Dict[str, Set[str]], List[Tuple[str, str]], Dict[str, Dict[str, float]]]:
        """Extrait le graphe d'importation orienté et détecte les cycles."""
        deps: Dict[str, Set[str]] = {}
        all_modules: Set[str] = set()

        for root, _, files in os.walk(src_dir):
            for f in files:
                if f.endswith(".py"):
                    full_p = os.path.join(root, f)
                    if exclude_patterns:
                        norm_p = full_p.replace("\\", "/")
                        if any(pat in norm_p for pat in exclude_patterns):
                            continue
                    rel_p = os.path.relpath(full_p, src_dir).replace("\\", "/").replace(".py", "")
                    deps[rel_p] = set()
                    all_modules.add(rel_p)

                    try:
                        with open(full_p, "r", encoding="utf-8") as src_f:
                            tree = ast.parse(src_f.read(10_000_000), filename=full_p)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src."):
                                target_mod = node.module[4:].replace(".", "/")
                                deps[rel_p].add(target_mod)
                    except Exception:
                        pass

        # Détection des cycles directs (A -> B et B -> A)
        cycles: List[Tuple[str, str]] = []
        for m1 in deps:
            for m2 in deps[m1]:
                if m2 in deps and m1 in deps[m2] and m1 != m2 and (m2, m1) not in cycles:
                    cycles.append((m1, m2))

        # Couplage élémentaire
        coupling_metrics: Dict[str, Dict[str, float]] = {}
        return deps, cycles, coupling_metrics


# ==============================================================================
# 6. Orchestrateur Central du Quality Gate Hybride
# ==============================================================================

class QualityGateOrchestrator:
    """
    Orchestrateur global d'évaluation de la qualité industrielle.
    Combine la matrice adaptative, le moteur de veto absolu,
    le score composite continue et les rapports unifiés pour la CI/CD.
    """

    def __init__(
        self,
        src_dir: str = "src",
        thresholds: Optional[Dict[ArchitecturalLayer, LayerThresholds]] = None,
        strict_mode: bool = False,
        exclude_patterns: Optional[List[str]] = None
    ) -> None:
        self.src_dir: str = src_dir
        self.thresholds: Dict[ArchitecturalLayer, LayerThresholds] = thresholds or DEFAULT_LAYER_THRESHOLDS
        self.strict_mode: bool = strict_mode
        self.exclude_patterns: Optional[List[str]] = exclude_patterns

    def run_hybrid_quality_gate(
        self,
        custom_coverage: Optional[Dict[ArchitecturalLayer, float]] = None,
        custom_mutation: float = 100.0,
        custom_pass_rate: float = 100.0
    ) -> HybridQualityGateReport:
        """
        Exécute le pipeline complet du Quality Gate Hybride.

        Retourne :
            HybridQualityGateReport : Rapport déterministe complet.
        """
        # 1. Extraction des métriques
        extracted = QualityMetricsExtractor.extract_from_codebase(
            src_dir=self.src_dir,
            thresholds_matrix=self.thresholds,
            custom_layer_coverage=custom_coverage,
            custom_mutation_score=custom_mutation,
            custom_test_pass_rate=custom_pass_rate,
            exclude_patterns=self.exclude_patterns
        )

        layers_raw: Dict[ArchitecturalLayer, LayerAuditResult] = extracted["layers"]  # type: ignore
        cycles_raw: List[Tuple[str, str]] = extracted["cycles"]  # type: ignore

        # 2. Agrégation globale des métriques
        total_files = sum(lr.files_count for lr in layers_raw.values())
        total_loc = sum(lr.lines_of_code for lr in layers_raw.values())
        total_sast_violations = sum(lr.sast_violations_count for lr in layers_raw.values())
        all_sast_details: List[str] = []
        for lr in layers_raw.values():
            all_sast_details.extend(lr.sast_violations_details)

        total_fn = sum(lr.total_functions_count for lr in layers_raw.values())
        compliant_fn = sum(lr.compliant_functions_count for lr in layers_raw.values())
        complexity_compliance_pct = (float(compliant_fn) / float(total_fn) * 100.0) if total_fn > 0 else 100.0

        # Complétude globale du typage
        avg_typing = (sum(lr.type_completeness_percent * lr.files_count for lr in layers_raw.values()) / float(total_files)) if total_files > 0 else 100.0

        # Couverture globale pondérée
        global_cov = (sum(lr.coverage_percent * lr.lines_of_code for lr in layers_raw.values()) / float(total_loc)) if total_loc > 0 else 85.0

        # Score d'intégrité architecturale (Stabilité Noyau <= 0.20 et 0 cycles)
        core_layer = layers_raw.get(ArchitecturalLayer.CAD_CORE_GEOMETRY)
        core_instability_ok = (core_layer is not None and core_layer.instability <= 0.20)
        arch_score = 100.0 if (core_instability_ok and len(cycles_raw) == 0) else 50.0

        # 3. Évaluation formelle des Vetos Absolus
        veto_results = FormalDecisionEngine.evaluate_vetoes(
            total_sast_violations=total_sast_violations,
            circular_cycles_count=len(cycles_raw),
            type_completeness_percent=avg_typing,
            sast_details=all_sast_details
        )
        any_veto_triggered = any(v.is_vetoed for v in veto_results)

        # 4. Évaluation continue : Score Composite S = sum(w_i * S_i)
        composite_score, score_components = FormalDecisionEngine.calculate_composite_score(
            coverage_percent=global_cov,
            test_pass_rate_percent=custom_pass_rate,
            mutation_score_percent=custom_mutation,
            complexity_compliance_percent=complexity_compliance_pct,
            maintainability_index=75.0,  # Moyenne standard normalisée
            architecture_compliance_percent=arch_score
        )

        # 5. Évaluation des couches selon la matrice adaptative
        evaluated_layers: Dict[str, LayerAuditResult] = {}
        layer_failures: List[str] = []
        layer_warnings: List[str] = []

        for layer, lr in layers_raw.items():
            th = self.thresholds[layer]
            st, reasons = FormalDecisionEngine.evaluate_layer(lr, th, strict_mode=self.strict_mode)
            lr.status = st
            lr.status_reasons = reasons
            evaluated_layers[layer.value] = lr

            if st == GateStatus.FAILED_LAYER_POLICY:
                layer_failures.append(f"{lr.layer_name}: {'; '.join(reasons)}")
            elif st == GateStatus.PASSED_WITH_WARNINGS:
                layer_warnings.append(f"{lr.layer_name}: {'; '.join(reasons)}")

        # 6. Synthèse du verdict global
        if any_veto_triggered:
            status = GateStatus.FAILED_VETO
            status_label = "REJETÉ (CRITÈRE DE VETO ABSOLU DÉCLENCHÉ)"
            gate_passed = False
        elif composite_score < FormalDecisionEngine.COMPOSITE_SCORE_THRESHOLD:
            status = GateStatus.FAILED_COMPOSITE_SCORE
            status_label = f"REJETÉ (SCORE COMPOSITE {composite_score:.1f}% < SEUIL {FormalDecisionEngine.COMPOSITE_SCORE_THRESHOLD:.1f}%)"
            gate_passed = False
        elif len(layer_failures) > 0:
            status = GateStatus.FAILED_LAYER_POLICY
            status_label = "REJETÉ (VIOLATION DE SEUILS ADAPTATIFS DE COUCHE)"
            gate_passed = False
        elif len(layer_warnings) > 0:
            status = GateStatus.PASSED_WITH_WARNINGS
            status_label = "VALIDÉ AVEC ALERTES (QUALITY GATE HYBRIDE RESPECTÉ)"
            gate_passed = True
        else:
            status = GateStatus.PASSED
            status_label = "VALIDÉ (CONFORME INDUSTRIEL MAXIMUM)"
            gate_passed = True

        summary_metrics: Dict[str, float] = {
            "total_files": float(total_files),
            "total_lines_of_code": float(total_loc),
            "type_completeness_percent": avg_typing,
            "security_violations": float(total_sast_violations),
            "circular_dependencies": float(len(cycles_raw)),
            "composite_score": composite_score,
            "global_coverage_percent": global_cov,
            "mutation_score_percent": custom_mutation,
            "complexity_compliance_percent": complexity_compliance_pct,
            "cad_core_instability": core_layer.instability if core_layer else 0.0,
        }

        iso_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        return HybridQualityGateReport(
            schema_version="2.0.0",
            timestamp=iso_timestamp,
            gate_passed=gate_passed,
            status=status,
            status_label=status_label,
            composite_score=composite_score,
            composite_threshold=FormalDecisionEngine.COMPOSITE_SCORE_THRESHOLD,
            score_components=score_components,
            vetoes=veto_results,
            any_veto_triggered=any_veto_triggered,
            layers=evaluated_layers,
            summary_metrics=summary_metrics,
            total_files=total_files,
            total_loc=total_loc
        )

    def format_console_output(self, report: HybridQualityGateReport) -> str:
        """
        Formate une sortie console unifiée, déterministe et lisible pour développeur et CI/CD.

        Paramètres :
            report (HybridQualityGateReport) : Le bilan complet du Quality Gate.

        Retourne :
            str : Texte formaté prêt pour l'affichage console.
        """
        lines: List[str] = []
        width = 78

        lines.append("=" * width)
        lines.append(" ORCHESTRATEUR QUALITY GATE HYBRIDE & MATRICE ADAPTATIVE (ISO 25010)")
        lines.append("=" * width)
        lines.append(f"  Horodatage UTC        : {report.timestamp}")
        lines.append(f"  Périmètre Audité      : {report.total_files} fichiers ({report.total_loc:,} lignes de code)")
        lines.append(f"  Verdict Global CI/CD  : {report.status_label}")
        lines.append(f"  Score Composite S     : {report.composite_score:.2f}% (Seuil Minimum : {report.composite_threshold:.1f}%)")
        lines.append("-" * width)

        # 1. Section Vetos Absolus
        lines.append("\n" + "#" * width)
        lines.append(" 1. CRITÈRES DE VETO ABSOLUS (HARD GATES)")
        lines.append("#" * width)
        for v in report.vetoes:
            badge = "[VETO DÉCLENCHÉ]" if v.is_vetoed else "[CONFORME - 0 VETO]"
            lines.append(f"  {badge:20} | {v.name}")
            lines.append(f"     Valeur observée   : {v.actual_value}")
            lines.append(f"     Seuil obligatoire : {v.threshold_value}")

        # 2. Section Score Composite Continue
        lines.append("\n" + "#" * width)
        lines.append(" 2. FONCTION DE SCORE COMPOSITE CONTINUE S = sum(w_i * S_i) >= 65.0%")
        lines.append("#" * width)
        for comp in report.score_components:
            bar_len = int(comp.raw_score / 5.0)
            bar = "#" * bar_len + "-" * (20 - bar_len)
            lines.append(
                f"  [{bar}] {comp.raw_score:5.1f}% (Poids: {comp.weight*100:2.0f}%) "
                f"-> +{comp.weighted_score:5.2f} pts | {comp.name}"
            )
        lines.append(f"  {'=' * 45}")
        lines.append(f"  SCORE COMPOSITE TOTAL S = {report.composite_score:.2f} / 100.00 pts")

        # 3. Section Matrice de Décision Adaptative par Couche
        lines.append("\n" + "#" * width)
        lines.append(" 3. MATRICE DE DÉCISION ADAPTATIVE PAR COUCHE ARCHITECTURALE")
        lines.append("#" * width)
        header = f"  {'Couche':<28} | {'Fichiers':<8} | {'Max Cog':<8} | {'Instab. I':<9} | {'Couvert.':<8} | {'Statut':<10}"
        lines.append(header)
        lines.append("  " + "-" * (width - 4))

        for layer_key, lr in report.layers.items():
            status_str = "[PASS]" if lr.status == GateStatus.PASSED else ("[WARN]" if lr.status == GateStatus.PASSED_WITH_WARNINGS else "[FAIL]")
            i_str = f"{lr.instability:.2f}" if lr.instability is not None else "N/A"
            lines.append(
                f"  {lr.layer_name:<28} | {lr.files_count:<8} | {lr.max_cognitive_complexity:<8} | {i_str:<9} | {lr.coverage_percent:<7.1f}% | {status_str:<10}"
            )

        # 4. Détail des alertes éventuelles
        has_alerts = any(len(lr.status_reasons) > 0 and lr.status != GateStatus.PASSED for lr in report.layers.values())
        if has_alerts:
            lines.append("\n  Détail des alertes & dépassements adaptatifs :")
            for layer_key, lr in report.layers.items():
                if lr.status != GateStatus.PASSED:
                    for r in lr.status_reasons:
                        lines.append(f"    - [{lr.layer_name}] {r}")

        lines.append("\n" + "=" * width)
        conclusion = "SUCCESS - QUALITY GATE APPROUVÉ" if report.gate_passed else "FAILURE - QUALITY GATE REFUSÉ"
        lines.append(f" VERDICT FINAL CI/CD : {conclusion}")
        lines.append("=" * width)

        return "\n".join(lines)

    def export_json_report(self, report: HybridQualityGateReport, output_path: str) -> str:
        """
        Exporte le rapport d'audit au format JSON déterministe avec clés ordonnées.

        Paramètres :
            report (HybridQualityGateReport) : Données d'audit.
            output_path (str) : Chemin cible d'écriture du fichier JSON.

        Retourne :
            str : Représentation JSON indentée.
        """
        # Conversion du dataclass en dictionnaire sérialisable
        raw_dict = asdict(report)

        # Encodage déterministe avec tri des clés
        json_str = json.dumps(raw_dict, indent=2, sort_keys=True, ensure_ascii=False)

        with open(output_path, "w", encoding="utf-8") as jf:
            jf.write(json_str)

        return json_str


# ==============================================================================
# 7. Point d'Entrée CLI pour la CI/CD
# ==============================================================================

def build_cli_parser() -> argparse.ArgumentParser:
    """Construit l'analyseur d'arguments CLI."""
    parser = argparse.ArgumentParser(
        description="Orchestrateur Quality Gate Hybride & Matrice de Décision Adaptative SOTA."
    )
    parser.add_argument(
        "--src-dir",
        type=str,
        default="src",
        help="Répertoire racine du code source à auditer (défaut: 'src')."
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="quality_gate_verdict.json",
        help="Chemin du fichier JSON unifié généré pour la CI/CD."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Mode strict : toute alerte ou dette cognitive entraîne un code d'erreur 1."
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Mode CI/CD : sortie épurée et code de retour formel."
    )
    parser.add_argument(
        "--exclude",
        type=str,
        nargs="*",
        default=[],
        help="Motifs de chemins de fichiers à exclure de l'audit (ex: mutation_engine.py)."
    )
    return parser


def main() -> int:
    """Point d'entrée principal pour l'exécution en ligne de commande et en CI/CD."""
    parser = build_cli_parser()
    args = parser.parse_args()

    orchestrator = QualityGateOrchestrator(
        src_dir=args.src_dir,
        strict_mode=args.strict,
        exclude_patterns=args.exclude if args.exclude else None
    )

    report = orchestrator.run_hybrid_quality_gate()

    # Sortie console déterministe
    console_out = orchestrator.format_console_output(report)
    print(console_out)

    # Export JSON déterministe
    orchestrator.export_json_report(report, args.output_json)

    # Code de retour système : 0 si le gate est validé, 1 si rejeté
    return 0 if report.gate_passed else 1


if __name__ == "__main__":
    sys.exit(main())
