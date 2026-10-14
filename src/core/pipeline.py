"""
Pipeline de Traitement par Assemblage de Briques (Lego Pipeline).
Permet de chaîner des opérations de transformation géométrique sous forme de modules
interchangeables, inspectables étape par étape et réversibles.
Pipeline générique hautement typé avec étapes composables.
"""

from __future__ import annotations
from typing import List, Tuple, Callable, TypeVar, Generic, Optional
from dataclasses import dataclass

from src.core.types import Vector3D, BooleanOperation
from src.core.geometry import Solid
from src.core.interfaces import PipelineStage

T = TypeVar("T")


class LegoPipeline(Generic[T]):
    """
    Chaîne de traitement composable de type LEGO.
    Permet d'emboîter des étapes de calcul les unes après les autres de manière fluide.
    """

    def __init__(self, name: str = "StandardPipeline") -> None:
        """Initialise un pipeline vide."""
        self.name: str = name
        self._stages: List[PipelineStage[T, T]] = []

    def add_stage(self, stage: PipelineStage[T, T]) -> LegoPipeline[T]:
        """Ajoute une brique de traitement à la suite du pipeline (fluent interface)."""
        self._stages.append(stage)
        return self

    def execute(self, initial_data: T) -> T:
        """Exécute séquentiellement toutes les étapes sur la donnée d'entrée."""
        current = initial_data
        for stage in self._stages:
            current = stage.execute(current)
        return current

    def execute_with_history(self, initial_data: T) -> List[Tuple[str, T]]:
        """
        Exécute le pipeline en conservant l'état intermédiaire après chaque brique.
        Retourne la liste ordonnée [(nom_étape, état_résultant)].
        """
        history: List[Tuple[str, T]] = [("Input", initial_data)]
        current = initial_data
        for stage in self._stages:
            current = stage.execute(current)
            history.append((stage.stage_name, current))
        return history

    def stage_count(self) -> int:
        """Retourne le nombre d'étapes dans le pipeline."""
        return len(self._stages)

    def clear(self) -> None:
        """Vide toutes les étapes du pipeline."""
        self._stages.clear()


# =====================================================================
# Briques LEGO de Traitement Géométrique 3D pour Solides (Solid Stages)
# =====================================================================

class TranslateStage(PipelineStage[Solid, Solid]):
    """Brique de translation spatiale d'un solide."""

    def __init__(self, offset: Vector3D, name: str = "Translate") -> None:
        self._offset = offset
        self._name = name

    @property
    def stage_name(self) -> str:
        return f"{self._name}(dx={self._offset.x:.1f}, dy={self._offset.y:.1f}, dz={self._offset.z:.1f})"

    def execute(self, data: Solid) -> Solid:
        return data.translate(self._offset)


class RotateStage(PipelineStage[Solid, Solid]):
    """Brique de rotation 3D d'un solide."""

    def __init__(self, rx_deg: float, ry_deg: float, rz_deg: float, name: str = "Rotate") -> None:
        self._rx = rx_deg
        self._ry = ry_deg
        self._rz = rz_deg
        self._name = name

    @property
    def stage_name(self) -> str:
        return f"{self._name}(rx={self._rx:.1f}, ry={self._ry:.1f}, rz={self._rz:.1f})"

    def execute(self, data: Solid) -> Solid:
        return data.rotate(self._rx, self._ry, self._rz)


class ScaleStage(PipelineStage[Solid, Solid]):
    """Brique de mise à l'échelle non-uniforme."""

    def __init__(self, sx: float, sy: float, sz: float, name: str = "Scale") -> None:
        self._sx = sx
        self._sy = sy
        self._sz = sz
        self._name = name

    @property
    def stage_name(self) -> str:
        return f"{self._name}(sx={self._sx:.2f}, sy={self._sy:.2f}, sz={self._sz:.2f})"

    def execute(self, data: Solid) -> Solid:
        return data.scale(self._sx, self._sy, self._sz)


class BooleanStage(PipelineStage[Solid, Solid]):
    """Brique d'opération booléenne (Union, Différence, Intersection) avec un autre solide."""

    def __init__(self, tool_solid: Solid, operation: BooleanOperation = BooleanOperation.JOIN, name: str = "Boolean") -> None:
        self._tool = tool_solid
        self._op = operation
        self._name = name

    @property
    def stage_name(self) -> str:
        return f"{self._name}_{self._op.value}"

    def execute(self, data: Solid) -> Solid:
        if self._op == BooleanOperation.JOIN:
            return data.union(self._tool)
        elif self._op == BooleanOperation.CUT:
            return data.difference(self._tool)
        elif self._op == BooleanOperation.INTERSECT:
            return data.intersection(self._tool)
        return data


class SimplifyStage(PipelineStage[Solid, Solid]):
    """Brique de simplification et d'optimisation du maillage."""

    def __init__(self, tolerance: float = 0.05, name: str = "Simplify") -> None:
        self._tol = tolerance
        self._name = name

    @property
    def stage_name(self) -> str:
        return f"{self._name}(tol={self._tol:.3f})"

    def execute(self, data: Solid) -> Solid:
        return data.simplify(self._tol)


class InspectorCallbackStage(PipelineStage[Solid, Solid]):
    """Brique d'inspection passive (sonde de métrologie) qui n'altère pas la géométrie."""

    def __init__(self, callback: Callable[[Solid], None], name: str = "Probe") -> None:
        self._cb = callback
        self._name = name

    @property
    def stage_name(self) -> str:
        return self._name

    def execute(self, data: Solid) -> Solid:
        try:
            self._cb(data)
        except Exception as err:
            print(f"[Probe] Erreur métrologie sonde : {err}")
        return data
