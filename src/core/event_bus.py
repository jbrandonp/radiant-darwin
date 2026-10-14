"""
Bus d'Événements Fortement Typé (Event-Driven Lego Architecture).
Permet le découplage absolu entre les sous-systèmes (UI, Moteur 3D, Ateliers, Inspecteur)
selon le patron Publish/Subscribe, garantissant une architecture propre et modulaire.
Strictement typé sans utilisation d'Any.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Type, Callable, Optional, TypeVar


class EventPriority(Enum):
    """Priorité d'exécution des écouteurs d'événements."""
    HIGH = auto()
    NORMAL = auto()
    LOW = auto()


@dataclass(frozen=True)
class CADEvent:
    """Événement de base immuable transitant sur le bus."""
    timestamp: float = 0.0


@dataclass(frozen=True)
class DocumentModifiedEvent(CADEvent):
    """Émis lorsque le document subit une altération (ajout/suppression/rebuild)."""
    document_name: str = ""
    num_bodies: int = 0
    num_features: int = 0


@dataclass(frozen=True)
class FeatureEvaluatedEvent(CADEvent):
    """Émis lors de l'évaluation d'une opération paramétrique."""
    feature_id: str = ""
    feature_name: str = ""
    is_success: bool = True
    error_message: Optional[str] = None


@dataclass(frozen=True)
class SelectionChangedEvent(CADEvent):
    """Émis lors d'un changement de sélection dans la vue 3D ou l'arbre."""
    selected_body_id: Optional[str] = None
    selected_feature_id: Optional[str] = None
    selected_entity_id: Optional[str] = None


@dataclass(frozen=True)
class TimelineRollbackEvent(CADEvent):
    """Émis lorsque le curseur d'historique temporel est déplacé."""
    previous_index: int = -1
    new_index: int = -1
    max_index: int = -1


@dataclass(frozen=True)
class WorkbenchChangedEvent(CADEvent):
    """Émis lors du basculement d'atelier métier (ex: PartDesign -> TechDraw)."""
    old_workbench_id: str = ""
    new_workbench_id: str = ""


T_Event = TypeVar("T_Event", bound=CADEvent)


class CADEventBus:
    """
    Bus d'événements centralisé et typé pour CAD Studio.
    Isole les écouteurs pour qu'une exception dans l'un ne bloque pas les autres.
    """

    def __init__(self) -> None:
        """Initialise le bus avec un dictionnaire d'abonnés vide."""
        self._subscribers: Dict[Type[CADEvent], List[Callable[[CADEvent], None]]] = {}

    def subscribe(
        self,
        event_type: Type[T_Event],
        handler: Callable[[T_Event], None]
    ) -> Callable[[], None]:
        """
        Abonne un gestionnaire à un type d'événement précis.
        Retourne une fonction appelable sans argument pour se désabonner proprement.
        """
        base_key: Type[CADEvent] = event_type
        if base_key not in self._subscribers:
            self._subscribers[base_key] = []

        # Cast sûr pour la liste interne de gestionnaires
        typed_handler: Callable[[CADEvent], None] = handler  # type: ignore[assignment]
        self._subscribers[base_key].append(typed_handler)

        def unsubscribe_token() -> None:
            self.unsubscribe(event_type, handler)

        return unsubscribe_token

    def unsubscribe(
        self,
        event_type: Type[T_Event],
        handler: Callable[[T_Event], None]
    ) -> bool:
        """Désabonne un gestionnaire. Retourne True si trouvé et supprimé."""
        base_key: Type[CADEvent] = event_type
        if base_key in self._subscribers:
            try:
                self._subscribers[base_key].remove(handler)  # type: ignore[arg-type]
                return True
            except ValueError:
                return False
        return False

    def publish(self, event: CADEvent) -> int:
        """
        Diffuse un événement à tous les écouteurs abonnés à son type ou sa classe parente.
        Retourne le nombre total d'écouteurs notifiés.
        """
        notified_count = 0
        event_cls = type(event)

        for sub_cls, handlers in list(self._subscribers.items()):
            if issubclass(event_cls, sub_cls):
                for h in list(handlers):
                    notified_count += 1
                    try:
                        h(event)
                    except Exception as err:
                        print(f"[CADEventBus] Erreur dans le gestionnaire pour {event_cls.__name__} : {err}")

        return notified_count

    def clear(self) -> None:
        """Supprime tous les abonnements du bus."""
        self._subscribers.clear()


# Instance globale partagée prête à l'emploi (Singleton léger)
global_event_bus = CADEventBus()
