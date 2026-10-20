"""
Atelier Quincaillerie Mécanique & Visserie Standard (FreeCAD Fasteners Workbench Parity).
Fournit la fonctionnalité Feature de visserie pour la timeline CAO et réexporte
les générateurs géométriques depuis le catalogue unifié src.catalog.fasteners.
"""

from __future__ import annotations
from typing import Dict, Optional, Union

from src.core.types import BooleanOperation, FeatureStatus
from src.core.geometry import Solid
from src.core.feature import Feature, _apply_boolean_operation
from src.core.sketch import Sketch2D

from src.catalog.fasteners import (
    MetricFastenerSpec,
    ISO_METRIC_TABLE,
    _FASTENER_CACHE,
    clear_fastener_cache,
    create_hex_bolt,
    create_socket_head_cap_screw,
    create_hex_nut,
    create_washer,
)

__all__ = [
    "MetricFastenerSpec",
    "ISO_METRIC_TABLE",
    "_FASTENER_CACHE",
    "clear_fastener_cache",
    "create_hex_bolt",
    "create_socket_head_cap_screw",
    "create_hex_nut",
    "create_washer",
    "FastenerFeature",
]


class FastenerFeature(Feature):
    """
    Fonctionnalité paramétrique de visserie et boulonnerie normalisée.
    Insère des vis, écrous et rondelles directement dans la Timeline CAO.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Fastener",
        fastener_type: str = "hex_bolt",
        standard_size: str = "M6",
        length: float = 30.0,
        operation: BooleanOperation = BooleanOperation.NEW_BODY,
        target_body_id: Optional[str] = None,
        has_washer: bool = False,
        thread_size: Optional[str] = None,
        threaded: bool = True
    ) -> None:
        super().__init__(feature_id, name)
        self.fastener_type = "socket_screw" if fastener_type in ("socket_cap", "socket_screw") else fastener_type
        self.standard_size = thread_size if thread_size is not None else standard_size
        self.has_washer = has_washer
        self.threaded = threaded
        self.parameters = {
            "length": float(length),
            "has_washer": 1.0 if has_washer else 0.0,
            "threaded": 1.0 if threaded else 0.0
        }
        self.operation = operation
        self.target_body_id = target_body_id
        self.body_id = f"body_{feature_id}"

    def get_parameters(self) -> Dict[str, Union[float, str, bool]]:
        """Retourne les paramètres de la quincaillerie."""
        return {
            "length": self.parameters.get("length", 30.0),
            "thread_size": self.standard_size,
            "standard_size": self.standard_size,
            "fastener_type": self.fastener_type,
            "has_washer": self.has_washer,
            "threaded": self.threaded
        }

    def _apply_single_param(self, name: str, val: Union[float, str, bool]) -> None:
        """Assigne un paramètre individuel typé à la quincaillerie."""
        if name == "length" and isinstance(val, (int, float)):
            self.parameters["length"] = float(val)
        elif name in ("thread_size", "standard_size") and isinstance(val, str):
            self.standard_size = val
        elif name == "fastener_type" and isinstance(val, str):
            self.fastener_type = "socket_screw" if val in ("socket_cap", "socket_screw") else val
        elif name == "has_washer" and isinstance(val, bool):
            self.has_washer = val
            self.parameters["has_washer"] = 1.0 if val else 0.0
        elif name == "threaded" and isinstance(val, bool):
            self.threaded = val
            self.parameters["threaded"] = 1.0 if val else 0.0

    def set_parameters(self, new_params: Dict[str, Union[float, str, bool]]) -> None:
        """Met à jour les paramètres de la quincaillerie."""
        for name, val in new_params.items():
            self._apply_single_param(name, val)
        self.status = FeatureStatus.OUTDATED

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Génère la pièce de quincaillerie selon les normes industrielles."""
        l_val = self.parameters.get("length", 30.0)
        solid: Solid

        if self.fastener_type == "socket_screw":
            solid = create_socket_head_cap_screw(self.standard_size, l_val, self.name, threaded=self.threaded)
        elif self.fastener_type == "hex_nut":
            solid = create_hex_nut(self.standard_size, self.name, threaded=self.threaded)
        elif self.fastener_type == "washer":
            solid = create_washer(self.standard_size, self.name)
        else:
            solid = create_hex_bolt(self.standard_size, l_val, self.name, threaded=self.threaded)

        if self.has_washer and self.fastener_type in ("hex_bolt", "socket_screw"):
            washer_solid = create_washer(self.standard_size, f"{self.name}_Rondelle")
            solid = solid.union(washer_solid)

        self.status = FeatureStatus.OK
        return _apply_boolean_operation(existing_bodies, solid, self.operation, self.body_id, self.target_body_id)
