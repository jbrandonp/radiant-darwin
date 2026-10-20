"""
Gestionnaire Transactionnel d'Annulation / Rétablissement (Undo/Redo Command Pattern).
Permet de remonter et redescendre l'historique de modélisation pas à pas sans corruption mémoire,
équivalent de la pile de commandes transactionnelle d'Autodesk Fusion 360 et FreeCAD App::Property.
Architecture fortement typée.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional, Callable

from src.core.document import CADDocument
from src.core.feature import Feature
from src.core.sketch import Sketch2D
from src.core.types import Vector3D


class CADCommand(ABC):
    """Commande unitaire réversible modifiant l'état du document CAO."""

    def __init__(self, description: str = "Action CAO") -> None:
        self.description: str = description

    @abstractmethod
    def execute(self, document: CADDocument) -> bool:
        """Exécute la commande sur le document."""
        pass

    @abstractmethod
    def undo(self, document: CADDocument) -> bool:
        """Annule l'effet de la commande sur le document."""
        pass

    def redo(self, document: CADDocument) -> bool:
        """Rétablit l'effet de la commande (par défaut ré-exécute execute)."""
        return self.execute(document)


class AddFeatureCommand(CADCommand):
    """Commande d'ajout d'une nouvelle fonction dans l'arbre historique."""

    def __init__(self, feature: Feature) -> None:
        super().__init__(f"Ajout fonction {feature.name}")
        self.feature: Feature = feature

    def execute(self, document: CADDocument) -> bool:
        document.add_feature(self.feature)
        return True

    def undo(self, document: CADDocument) -> bool:
        document.remove_feature(self.feature.feature_id)
        return True


class RemoveFeatureCommand(CADCommand):
    """Commande de suppression d'une fonction avec sauvegarde pour restauration."""

    def __init__(self, feature_id: str) -> None:
        super().__init__(f"Suppression fonction {feature_id}")
        self.feature_id: str = feature_id
        self._saved_feature: Optional[Feature] = None
        self._saved_index: int = -1

    def execute(self, document: CADDocument) -> bool:
        for idx, feat in enumerate(document.features):
            if feat.feature_id == self.feature_id:
                self._saved_feature = feat
                self._saved_index = idx
                break
        if self._saved_feature is None:
            return False
        document.remove_feature(self.feature_id)
        return True

    def undo(self, document: CADDocument) -> bool:
        if self._saved_feature is not None:
            if self._saved_index >= 0 and self._saved_index <= len(document.features):
                document.features.insert(self._saved_index, self._saved_feature)
            else:
                document.features.append(self._saved_feature)
            document.rebuild()
            return True
        return False


class ModifyParameterCommand(CADCommand):
    """Commande de modification d'un paramètre numérique d'une fonction."""

    def __init__(self, feature_id: str, param_name: str, new_value: float) -> None:
        super().__init__(f"Modification {param_name} de {feature_id}")
        self.feature_id: str = feature_id
        self.param_name: str = param_name
        self.new_value: float = float(new_value)
        self.old_value: Optional[float] = None

    def execute(self, document: CADDocument) -> bool:
        feat = document.get_feature(self.feature_id)
        if feat is None:
            return False
        if self.old_value is None:
            self.old_value = float(feat.parameters.get(self.param_name, 0.0))
        feat.parameters[self.param_name] = self.new_value
        document.invalidate_cache()
        document.rebuild()
        return True

    def undo(self, document: CADDocument) -> bool:
        if self.old_value is None:
            return False
        feat = document.get_feature(self.feature_id)
        if feat is None:
            return False
        feat.parameters[self.param_name] = self.old_value
        document.invalidate_cache()
        document.rebuild()
        return True


class TransformBodyCommand(CADCommand):
    """Commande de transformation spatiale réversible d'un corps solide par translation."""

    def __init__(self, body_id: str, delta_translation: Vector3D) -> None:
        super().__init__(
            f"Déplacement corps {body_id} ({delta_translation.x:+.1f}, {delta_translation.y:+.1f}, {delta_translation.z:+.1f})"
        )
        self.body_id: str = body_id
        self.delta_translation: Vector3D = delta_translation

    def execute(self, document: CADDocument) -> bool:
        """Applique la translation sur le corps solide spécifié."""
        if self.body_id not in document.bodies:
            return False
        solid = document.bodies[self.body_id]
        document.bodies[self.body_id] = solid.translate(self.delta_translation)
        document.notify_listeners()
        return True

    def undo(self, document: CADDocument) -> bool:
        """Annule la translation en appliquant le vecteur inverse."""
        if self.body_id not in document.bodies:
            return False
        solid = document.bodies[self.body_id]
        document.bodies[self.body_id] = solid.translate(self.delta_translation.scale(-1.0))
        document.notify_listeners()
        return True


class UndoRedoManager:
    """
    Pile de commandes transactionnelle avec curseur réversible.
    Empêche les désynchronisations de l'arbre géométrique et garantit l'intégrité du modèle.
    """

    def __init__(self, document: CADDocument, max_history_depth: int = 100) -> None:
        self.document: CADDocument = document
        self.max_depth: int = max_history_depth
        self._history: List[CADCommand] = []
        self._cursor: int = -1  # Pointeur sur la dernière commande exécutée

    @property
    def can_undo(self) -> bool:
        """Indique si une commande peut être annulée."""
        return self._cursor >= 0

    @property
    def can_redo(self) -> bool:
        """Indique si une commande annulée peut être rétablie."""
        return self._cursor + 1 < len(self._history)

    def execute_command(self, command: CADCommand) -> bool:
        """Exécute une nouvelle commande et l'empile en purgeant les branches futures."""
        success = command.execute(self.document)
        if success:
            # Tronquer l'historique futur si on était revenu en arrière
            self._history = self._history[:self._cursor + 1]
            self._history.append(command)
            # Borner la taille de l'historique
            if len(self._history) > self.max_depth:
                self._history.pop(0)
            else:
                self._cursor += 1
        return success

    def undo(self) -> bool:
        """Annule la dernière action effectuée."""
        if not self.can_undo:
            return False
        cmd = self._history[self._cursor]
        success = cmd.undo(self.document)
        if success:
            self._cursor -= 1
        return success

    def redo(self) -> bool:
        """Rétablit l'action précédemment annulée."""
        if not self.can_redo:
            return False
        self._cursor += 1
        cmd = self._history[self._cursor]
        success = cmd.redo(self.document)
        if not success:
            self._cursor -= 1
        return success

    def clear(self) -> None:
        """Vide l'historique de commandes."""
        self._history.clear()
        self._cursor = -1

    def get_history_descriptions(self) -> List[str]:
        """Retourne la liste des intitulés de l'historique pour l'affichage IHM."""
        return [cmd.description for cmd in self._history]
