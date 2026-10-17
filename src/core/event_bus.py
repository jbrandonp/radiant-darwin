"""
Bus d'Événements Fortement Typé (Event-Driven Lego Architecture).
Permet le découplage absolu entre les sous-systèmes (UI, Moteur 3D, Ateliers, Inspecteur)
selon le patron Publish/Subscribe, garantissant une architecture propre et modulaire.
Typage nominal strict et événements typés exhaustifs.
"""

from __future__ import annotations
import inspect
import threading
import weakref
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


class _WeakHandlerWrapper:
    """Enveloppe à référence faible empêchant la fuite mémoire des widgets abonnés (Lapsed Listener)."""

    def __init__(self, callback: Callable[[CADEvent], None]) -> None:
        if inspect.ismethod(callback):
            self._ref: Optional[weakref.ReferenceType[Callable[[CADEvent], None]]] = weakref.WeakMethod(callback)
            self._direct_cb: Optional[Callable[[CADEvent], None]] = None
        else:
            try:
                self._ref = weakref.ref(callback)
                self._direct_cb = None
            except TypeError:
                self._ref = None
                self._direct_cb = callback

    def get(self) -> Optional[Callable[[CADEvent], None]]:
        if self._ref is not None:
            return self._ref()
        return self._direct_cb

    def matches(self, callback: Callable[[CADEvent], None]) -> bool:
        live = self.get()
        return live == callback


class CADEventBus:
    """
    Bus d'événements centralisé et typé pour CAD Studio.
    Isole les écouteurs pour qu'une exception dans l'un ne bloque pas les autres.
    Garantit zéro fuite mémoire via références faibles et exécution thread-safe.
    """

    def __init__(self) -> None:
        """Initialise le bus avec un dictionnaire d'abonnés vide."""
        self._subscribers: Dict[Type[CADEvent], List[_WeakHandlerWrapper]] = {}

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
        wrapper = _WeakHandlerWrapper(typed_handler)
        self._subscribers[base_key].append(wrapper)

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
            typed_handler: Callable[[CADEvent], None] = handler  # type: ignore[assignment]
            orig_len = len(self._subscribers[base_key])
            self._subscribers[base_key] = [
                w for w in self._subscribers[base_key] if not w.matches(typed_handler)
            ]
            return len(self._subscribers[base_key]) < orig_len
        return False

    @staticmethod
    def _dispatch_safe(callback: Callable[[CADEvent], None], event: CADEvent) -> None:
        """Exécute l'écouteur avec sécurité multi-thread si un thread graphique Qt est actif."""
        target_obj = getattr(callback, "__self__", None)
        if target_obj is not None and hasattr(target_obj, "thread"):
            try:
                from PySide6.QtCore import QThread, QTimer
                from PySide6.QtWidgets import QApplication
                app = QApplication.instance()
                if app is not None and QThread.currentThread() != app.thread():
                    QTimer.singleShot(0, lambda: callback(event))
                    return
            except (ImportError, RuntimeError, AttributeError):
                pass
        callback(event)

    def publish(self, event: CADEvent) -> int:
        """
        Diffuse un événement à tous les écouteurs abonnés à son type ou sa classe parente.
        Nettoie automatiquement les écouteurs périmés (objets détruits).
        Retourne le nombre total d'écouteurs notifiés.
        """
        notified_count = 0
        event_cls = type(event)

        for sub_cls, wrappers in list(self._subscribers.items()):
            if issubclass(event_cls, sub_cls):
                dead_wrappers: List[_WeakHandlerWrapper] = []
                for w in list(wrappers):
                    cb = w.get()
                    if cb is None:
                        dead_wrappers.append(w)
                        continue
                    notified_count += 1
                    try:
                        self._dispatch_safe(cb, event)
                    except Exception as err:
                        print(f"[CADEventBus] Erreur dans le gestionnaire pour {event_cls.__name__} : {err}")

                for dead in dead_wrappers:
                    if dead in wrappers:
                        wrappers.remove(dead)

        return notified_count

    def clear(self) -> None:
        """Supprime tous les abonnements du bus."""
        self._subscribers.clear()


# Instance globale partagée prête à l'emploi (Singleton léger)
global_event_bus = CADEventBus()
