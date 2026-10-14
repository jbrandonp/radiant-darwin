"""
Contrats et Protocoles Fondamentaux (Lego Interfaces).
Définit les interfaces formelles (PEP 544 Protocols) assurant une modularité maximale
style 'briques LEGO' : chaque composant s'emboîte de manière totalement découplée.
Strictement typé sans utilisation d'Any.
"""

from __future__ import annotations
from typing import (
    Protocol, runtime_checkable, Dict, List, Tuple, Optional, Sequence,
    Callable, TypeVar
)
import numpy as np

from src.core.types import Vector3D, Point2D, MeshBuffer, FeatureStatus, BooleanOperation


@runtime_checkable
class GeometryProvider(Protocol):
    """Contrat pour tout objet fournissant une géométrie 3D étanche calculable."""

    @property
    def name(self) -> str:
        """Nom identifiant de l'objet géométrique."""
        ...

    def volume(self) -> float:
        """Calcule le volume intérieur en mm³."""
        ...

    def surface_area(self) -> float:
        """Calcule l'aire surfacique extérieure totale en mm²."""
        ...

    def bounding_box(self) -> Tuple[Vector3D, Vector3D]:
        """Retourne la boîte englobante minimale (min_point, max_point)."""
        ...

    def to_mesh_buffer(self) -> MeshBuffer:
        """Convertit l'objet en tampon de maillage pour affichage OpenGL."""
        ...

    def is_empty(self) -> bool:
        """Retourne True si l'objet est vide de matière."""
        ...


@runtime_checkable
class FeatureEvaluator(Protocol):
    """Contrat pour toute opération paramétrique de l'arbre d'historique (Feature)."""

    @property
    def feature_id(self) -> str:
        """Identifiant unique de la fonctionnalité."""
        ...

    @property
    def name(self) -> str:
        """Nom lisible de la fonctionnalité."""
        ...

    @property
    def status(self) -> FeatureStatus:
        """Statut actuel de l'opération (OK, ERROR, OUTDATED, SUPPRESSED)."""
        ...

    @property
    def is_suppressed(self) -> bool:
        """Indique si la fonctionnalité est temporairement désactivée."""
        ...

    def evaluate(
        self,
        existing_bodies: Dict[str, GeometryProvider],
        sketches: Dict[str, object]
    ) -> Dict[str, GeometryProvider]:
        """Évalue l'opération et retourne le dictionnaire mis à jour des corps solides."""
        ...


@runtime_checkable
class ExporterService(Protocol):
    """Contrat pour tout exportateur de fichiers de fabrication (STL, STEP, SVG, DXF, G-Code)."""

    @property
    def format_name(self) -> str:
        """Nom du format supporté (ex: 'STEP', 'SVG', 'G-Code')."""
        ...

    @property
    def file_extension(self) -> str:
        """Extension de fichier associée avec le point (ex: '.step', '.svg')."""
        ...

    def export(self, target: object, filepath: str) -> str:
        """Exporte l'objet cible vers le chemin spécifié et retourne le contenu textuel ou un hash."""
        ...


@runtime_checkable
class WorkbenchModule(Protocol):
    """Contrat d'atelier métier modulaire enfichable (Plug-and-play Workbench)."""

    @property
    def workbench_id(self) -> str:
        """Identifiant unique de l'atelier (ex: 'fea', 'techdraw', 'cam')."""
        ...

    @property
    def title(self) -> str:
        """Titre affiché dans le ruban IHM."""
        ...

    @property
    def icon_name(self) -> str:
        """Nom de l'icône vectorielle associée."""
        ...

    def initialize(self) -> bool:
        """Initialise les ressources et services de l'atelier."""
        ...

    def shutdown(self) -> None:
        """Libère les ressources lors de la fermeture de l'atelier."""
        ...


T_Input = TypeVar("T_Input")
T_Output = TypeVar("T_Output")


@runtime_checkable
class PipelineStage(Protocol[T_Input, T_Output]):
    """Contrat pour une étape de transformation de géométrie ou de données en chaîne."""

    @property
    def stage_name(self) -> str:
        """Nom descriptif de l'étape de traitement."""
        ...

    def execute(self, data: T_Input) -> T_Output:
        """Exécute la transformation sur la donnée d'entrée et produit le résultat."""
        ...
