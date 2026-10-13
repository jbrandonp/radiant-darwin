"""
Document de CAO paramétrique principal.
Gère l'arbre d'historique (Timeline), les esquisses, les corps 3D,
le rollback temporel et le recalcul automatique des fonctionnalités.
"""

from __future__ import annotations
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field

from src.core.geometry import Solid
from src.core.sketch import Sketch2D
from src.core.feature import Feature
from src.core.types import MeshBuffer


class CADDocument:
    """
    Conteneur central d'un projet CAO.
    Représente le modèle paramétrique complet avec son historique temporel.
    """

    def __init__(self, name: str = "Untitled Document") -> None:
        """Initialise un nouveau document vide."""
        self.name: str = name
        self.sketches: Dict[str, Sketch2D] = {}
        self.features: List[Feature] = []
        self.bodies: Dict[str, Solid] = {}
        # Curseur de retour dans le temps (Rollback) : -1 signifie tout évaluer
        self.rollback_index: int = -1
        self._counter: int = 0
        self._on_change_callbacks: List[Callable[[], None]] = []

    def register_change_listener(self, callback: Callable[[], None]) -> None:
        """Enregistre un écouteur appelé à chaque modification du modèle."""
        self._on_change_callbacks.append(callback)

    def _notify_change(self) -> None:
        """Notifie tous les écouteurs qu'une mise à jour a eu lieu."""
        for cb in self._on_change_callbacks:
            try:
                cb()
            except Exception as e:
                print(f"Erreur callback document : {e}")

    def add_sketch(self, sketch: Sketch2D) -> None:
        """Ajoute une esquisse au document."""
        self.sketches[sketch.sketch_id] = sketch
        self._notify_change()

    def get_sketch(self, sketch_id: str) -> Optional[Sketch2D]:
        """Récupère une esquisse par son identifiant."""
        return self.sketches.get(sketch_id)

    def add_feature(self, feature: Feature) -> None:
        """Ajoute une nouvelle fonctionnalité à la fin de l'arbre d'historique et recalcule."""
        self.features.append(feature)
        self.rollback_index = len(self.features) - 1
        self.rebuild()

    def remove_feature(self, feature_id: str) -> None:
        """Supprime une fonctionnalité de l'historique et recalcule le modèle."""
        self.features = [f for f in self.features if f.feature_id != feature_id]
        if self.rollback_index >= len(self.features):
            self.rollback_index = len(self.features) - 1
        self.rebuild()

    def set_rollback_index(self, index: int) -> None:
        """
        Déplace le curseur de rollback de l'historique (comme la barre en bas de Fusion 360).
        Évalue uniquement les fonctionnalités jusqu'à cet index.
        """
        clamped_idx = max(-1, min(index, len(self.features) - 1))
        self.rollback_index = clamped_idx
        self.rebuild()

    def rebuild(self) -> None:
        """
        Recalcule séquentiellement l'intégralité du modèle 3D
        depuis la première feature jusqu'à l'index de rollback actuel.
        """
        current_bodies: Dict[str, Solid] = {}
        max_idx = len(self.features) - 1 if self.rollback_index == -1 else self.rollback_index

        for idx, feat in enumerate(self.features):
            if idx > max_idx:
                break
            if feat.is_suppressed:
                continue

            try:
                current_bodies = feat.evaluate(current_bodies, self.sketches)
            except Exception as err:
                print(f"Erreur lors de l'évaluation de la feature {feat.name} ({feat.feature_id}) : {err}")

        self.bodies = current_bodies
        self._notify_change()

    def get_all_mesh_buffers(self) -> List[MeshBuffer]:
        """Convertit tous les corps solides visibles en tampons maillés pour OpenGL."""
        buffers: List[MeshBuffer] = []
        for body in self.bodies.values():
            buf = body.to_mesh_buffer()
            if not buf.is_empty():
                buffers.append(buf)
        return buffers

    def get_active_body_ids(self) -> List[str]:
        """Retourne la liste des identifiants des corps 3D actuellement existants."""
        return list(self.bodies.keys())
