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
from src.core.types import MeshBuffer, FeatureStatus
from src.core.assembly import AssemblyInstance, AssemblyMate, AssemblySolver


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
        # Atelier d'Assemblage Multi-Pièces
        self.assembly_instances: Dict[str, AssemblyInstance] = {}
        self.assembly_mates: List[AssemblyMate] = []
        # Curseur de retour dans le temps (Rollback) : -1 signifie tout évaluer
        self.rollback_index: int = -1
        self._counter: int = 0
        self._on_change_callbacks: List[Callable[[], None]] = []
        # Cache des instantanés d'étapes (Timeline checkpoint snapshots) pour rejeu O(1)
        self._timeline_snapshots: Dict[int, Dict[str, Solid]] = {}

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

        # Notification sur le bus d'événements LEGO découplé
        try:
            from src.core.event_bus import global_event_bus, DocumentModifiedEvent
            global_event_bus.publish(DocumentModifiedEvent(
                document_name=self.name,
                num_bodies=len(self.bodies),
                num_features=len(self.features)
            ))
        except Exception:
            pass

    def invalidate_cache(self) -> None:
        """Invalide les instantanés d'historique lors d'une modification paramétrique."""
        self._timeline_snapshots.clear()

    def add_sketch(self, sketch: Sketch2D) -> None:
        """Ajoute une esquisse au document."""
        self.sketches[sketch.sketch_id] = sketch
        self.invalidate_cache()
        self._notify_change()

    def get_sketch(self, sketch_id: str) -> Optional[Sketch2D]:
        """Récupère une esquisse par son identifiant."""
        return self.sketches.get(sketch_id)

    def get_feature(self, feature_id: str) -> Optional[Feature]:
        """Récupère une fonctionnalité de l'historique par son identifiant."""
        for feat in self.features:
            if feat.feature_id == feature_id:
                return feat
        return None

    def remove_sketch(self, sketch_id: str) -> None:
        """Supprime une esquisse du document et invalide le cache."""
        if sketch_id in self.sketches:
            del self.sketches[sketch_id]
            self.invalidate_cache()
            self._notify_change()

    def add_feature(self, feature: Feature) -> None:
        """Ajoute une nouvelle fonctionnalité à la fin de l'arbre d'historique et recalcule."""
        self.features.append(feature)
        self.rollback_index = len(self.features) - 1
        self.rebuild()

    def invalidate_from_index(self, index: int) -> None:
        """Invalide les instantanés d'historique à partir de l'index donné."""
        for snap_idx in list(self._timeline_snapshots.keys()):
            if snap_idx >= index:
                del self._timeline_snapshots[snap_idx]

    def set_feature_suppressed(self, feature_id: str, suppressed: bool) -> None:
        """Active ou désactive (supprime/rétablit) une opération dans l'arbre d'historique."""
        for idx, feat in enumerate(self.features):
            if feat.feature_id == feature_id:
                if feat.is_suppressed != suppressed:
                    feat.is_suppressed = suppressed
                    self.invalidate_from_index(idx)
                    self.rebuild()
                break

    def remove_feature(self, feature_id: str) -> None:
        """Supprime une fonctionnalité de l'historique et recalcule le modèle."""
        self.features = [f for f in self.features if f.feature_id != feature_id]
        if self.rollback_index >= len(self.features):
            self.rollback_index = len(self.features) - 1
        self.invalidate_cache()
        self.rebuild()

    def set_rollback_index(self, index: int) -> None:
        """
        Déplace le curseur de rollback de l'historique (comme la barre en bas de Fusion 360).
        Restauration instantanée O(1) si l'étape est déjà présente en cache.
        """
        prev_idx = self.rollback_index
        clamped_idx = max(-1, min(index, len(self.features) - 1))
        self.rollback_index = clamped_idx

        # Notification sur le bus d'événements LEGO
        try:
            from src.core.event_bus import global_event_bus, TimelineRollbackEvent
            global_event_bus.publish(TimelineRollbackEvent(
                previous_index=prev_idx,
                new_index=clamped_idx,
                max_index=len(self.features) - 1
            ))
        except Exception:
            pass

        self.rebuild()

    def rebuild(self) -> None:
        """
        Recalcule séquentiellement le modèle 3D avec mise en cache des étapes (Snapshots).
        Si un instantané est déjà valide à l'index de rollback demandé et qu'aucune opération n'est
        périmée (OUTDATED), restauration instantanée O(1).
        """
        max_idx = len(self.features) - 1 if self.rollback_index == -1 else self.rollback_index

        if max_idx < 0 or len(self.features) == 0:
            self.bodies = {}
            self._notify_change()
            return

        # Détecter la première feature marquée comme périmée (OUTDATED)
        first_outdated_idx = max_idx + 1
        for idx in range(max_idx + 1):
            if getattr(self.features[idx], "status", None) == FeatureStatus.OUTDATED:
                first_outdated_idx = idx
                break

        # Si une opération a été modifiée, purger les snapshots à partir d'elle
        if first_outdated_idx <= max_idx:
            for snap_idx in list(self._timeline_snapshots.keys()):
                if snap_idx >= first_outdated_idx:
                    del self._timeline_snapshots[snap_idx]
        elif max_idx in self._timeline_snapshots:
            # Aucune opération modifiée et snapshot disponible : Restauration O(1)
            self.bodies = dict(self._timeline_snapshots[max_idx])
            self._notify_change()
            return

        # Trouver le dernier point d'arrêt en cache valide
        start_idx = 0
        current_bodies: Dict[str, Solid] = {}
        for prev_idx in range(max_idx - 1, -1, -1):
            if prev_idx in self._timeline_snapshots:
                current_bodies = dict(self._timeline_snapshots[prev_idx])
                start_idx = prev_idx + 1
                break

        for idx in range(start_idx, max_idx + 1):
            feat = self.features[idx]
            if not feat.is_suppressed:
                try:
                    if getattr(feat, "status", None) == FeatureStatus.OUTDATED:
                        feat.status = FeatureStatus.OK
                    current_bodies = feat.evaluate(current_bodies, self.sketches)
                except Exception as err:
                    feat.status = FeatureStatus.ERROR
                    print(f"Erreur lors de l'évaluation de la feature {feat.name} ({feat.feature_id}) : {err}")
            self._timeline_snapshots[idx] = dict(current_bodies)

        self.bodies = current_bodies
        self._notify_change()

    def get_all_mesh_buffers(self) -> List[MeshBuffer]:
        """Convertit tous les corps solides et instances d'assemblage en tampons maillés pour OpenGL."""
        buffers: List[MeshBuffer] = []
        for body in self.bodies.values():
            buf = body.to_mesh_buffer()
            if not buf.is_empty():
                buffers.append(buf)

        # Inclure les instances positionnées de l'assemblage
        for inst in self.assembly_instances.values():
            inst_solid = inst.get_transformed_solid()
            buf = inst_solid.to_mesh_buffer()
            if not buf.is_empty():
                buffers.append(buf)

        return buffers

    def get_active_body_ids(self) -> List[str]:
        """Retourne la liste des identifiants des corps 3D actuellement existants."""
        return list(self.bodies.keys())

    # --- Méthodes de l'Atelier d'Assemblage Multi-Pièces ---

    def add_assembly_instance(
        self,
        instance_id: str,
        solid: Solid,
        name: str = "Component",
        is_grounded: bool = False
    ) -> AssemblyInstance:
        """Ajoute une pièce instanciée dans l'assemblage."""
        inst = AssemblyInstance(instance_id=instance_id, solid=solid, name=name, is_grounded=is_grounded)
        self.assembly_instances[instance_id] = inst
        self._notify_change()
        return inst

    def add_assembly_mate(self, mate: AssemblyMate) -> None:
        """Ajoute une contrainte géométrique d'assemblage."""
        self.assembly_mates.append(mate)
        self.solve_assembly()

    def solve_assembly(self) -> bool:
        """Résout le positionnement relatif des composants et actualise l'affichage."""
        success = AssemblySolver.solve_mates(self.assembly_instances, self.assembly_mates)
        self._notify_change()
        return success

    def check_assembly_collisions(self) -> List[Tuple[str, str, float]]:
        """Détecte les collisions et interférences physiques réelles entre pièces (en mm³)."""
        return AssemblySolver.detect_collisions(self.assembly_instances)

    def dispose(self) -> None:
        """Libère toutes les références géométriques et callbacks pour éliminer les fuites mémoire."""
        self.invalidate_cache()
        self.bodies.clear()
        self.assembly_instances.clear()
        self.assembly_mates.clear()
        self.features.clear()
        self.sketches.clear()
        self._on_change_callbacks.clear()

