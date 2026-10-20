"""
Document de CAO paramétrique principal.
Gère l'arbre d'historique (Timeline), les esquisses, les corps 3D,
le rollback temporel et le recalcul automatique des fonctionnalités.
"""

from __future__ import annotations
import threading
from contextlib import contextmanager
from typing import List, Dict, Optional, Callable, Tuple, Iterator
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
    Sécurisé pour l'accès multithread via un verrou réentrant transactionnel.
    """

    def __init__(self, name: str = "Untitled Document") -> None:
        """Initialise un nouveau document vide."""
        self.name: str = name
        self._lock: threading.RLock = threading.RLock()
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
        self._on_error_callbacks: List[Callable[[str, Feature], None]] = []
        self.last_error: Optional[str] = None
        self.build_errors: List[str] = []
        # Cache des instantanés d'étapes (Timeline checkpoint snapshots) pour rejeu O(1)
        self._timeline_snapshots: Dict[int, Dict[str, Solid]] = {}
        self.body_materials: Dict[str, str] = {}
        self._bus_connected: bool = True

    @contextmanager
    def read_transaction(self) -> Iterator[CADDocument]:
        """Verrouille le document en lecture pour les threads d'arrière-plan ou l'UI."""
        with self._lock:
            yield self

    @contextmanager
    def write_transaction(self) -> Iterator[CADDocument]:
        """Verrouille le document en écriture pour les modifications atomiques."""
        with self._lock:
            yield self

    def lock(self) -> None:
        """Acquiert le verrou réentrant du document."""
        self._lock.acquire()

    def unlock(self) -> None:
        """Libère le verrou réentrant du document."""
        self._lock.release()

    def register_change_listener(self, callback: Callable[[], None]) -> None:
        """Enregistre un écouteur appelé à chaque modification du modèle."""
        self._on_change_callbacks.append(callback)

    def register_error_listener(self, callback: Callable[[str, Feature], None]) -> None:
        """Enregistre un écouteur notifié lors d'une erreur d'évaluation de feature."""
        self._on_error_callbacks.append(callback)

    def register_error_callback(self, callback: Callable[[str, Feature], None]) -> None:
        """Alias public pour register_error_listener."""
        self.register_error_listener(callback)

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
        except (ImportError, AttributeError, RuntimeError):
            self._bus_connected = False

    def notify_listeners(self) -> None:
        """Alias public pour notifier tous les écouteurs de changements."""
        self._notify_change()

    def _notify_error(self, message: str, feature: Feature) -> None:
        """Notifie les écouteurs et le bus global d'une erreur d'évaluation géométrique."""
        for cb in self._on_error_callbacks:
            try:
                cb(message, feature)
            except Exception as e:
                print(f"Erreur callback erreur document : {e}")

        try:
            from src.core.event_bus import global_event_bus, FeatureEvaluatedEvent
            global_event_bus.publish(FeatureEvaluatedEvent(
                feature_id=feature.feature_id,
                feature_name=feature.name,
                is_success=False,
                error_message=message
            ))
        except (ImportError, AttributeError, RuntimeError):
            pass

    def invalidate_cache(self, from_index: Optional[int] = None) -> None:
        """Invalide les instantanés d'historique lors d'une modification paramétrique."""
        if from_index is None:
            self._timeline_snapshots.clear()
        else:
            self.invalidate_from_index(from_index)

    def invalidate_for_sketch(self, sketch_id: str) -> None:
        """Invalide le cache uniquement à partir de la première opération dépendant de cette esquisse."""
        first_idx: Optional[int] = None
        for idx, feat in enumerate(self.features):
            f_sk = getattr(feat, "sketch_id", None) or getattr(feat, "start_sketch_id", None) or getattr(feat, "profile_sketch_id", None)
            if f_sk == sketch_id:
                first_idx = idx
                break
        if first_idx is not None:
            self.invalidate_cache(from_index=first_idx)

    def add_sketch(self, sketch: Sketch2D) -> None:
        """Ajoute ou met à jour une esquisse au document avec invalidation sélective de cache."""
        self.sketches[sketch.sketch_id] = sketch
        self.invalidate_for_sketch(sketch.sketch_id)
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
        """Supprime une esquisse du document et invalide sélectivement le cache."""
        if sketch_id in self.sketches:
            self.invalidate_for_sketch(sketch_id)
            del self.sketches[sketch_id]
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
        except (ImportError, AttributeError, RuntimeError):
            self._bus_connected = False

        self.rebuild()

    def _find_first_outdated_index(self, max_idx: int) -> int:
        """Identifie l'index de la première opération marquée OUTDATED."""
        for idx in range(max_idx + 1):
            if getattr(self.features[idx], "status", None) == FeatureStatus.OUTDATED:
                return idx
        return max_idx + 1

    def _purge_invalid_snapshots(self, first_outdated_idx: int) -> None:
        """Purge les instantanés en cache à partir de l'index périmé."""
        for snap_idx in list(self._timeline_snapshots.keys()):
            if snap_idx >= first_outdated_idx:
                del self._timeline_snapshots[snap_idx]

    def _find_cached_checkpoint(self, max_idx: int) -> Tuple[int, Dict[str, Solid]]:
        """Trouve le dernier instantané en cache précédant la zone à recalculer."""
        for prev_idx in range(max_idx - 1, -1, -1):
            if prev_idx in self._timeline_snapshots:
                return prev_idx + 1, dict(self._timeline_snapshots[prev_idx])
        return 0, {}

    def _evaluate_feature_step(self, feat: Feature, bodies: Dict[str, Solid]) -> Dict[str, Solid]:
        """Évalue une feature individuelle et met à jour son statut."""
        if feat.is_suppressed:
            return bodies
        try:
            if getattr(feat, "status", None) == FeatureStatus.OUTDATED:
                feat.status = FeatureStatus.OK
            return feat.evaluate(bodies, self.sketches)
        except Exception as err:
            feat.status = FeatureStatus.ERROR
            error_msg = f"Erreur lors de l'évaluation de la feature {feat.name} ({feat.feature_id}) : {err}"
            print(error_msg)
            self.last_error = error_msg
            self.build_errors.append(error_msg)
            self._notify_error(error_msg, feat)
            return bodies

    def rebuild(self) -> None:
        """
        Recalcule séquentiellement le modèle 3D avec mise en cache des étapes (Snapshots).
        Si un instantané est déjà valide à l'index de rollback demandé et qu'aucune opération n'est
        périmée (OUTDATED), restauration instantanée O(1).
        Protégé par le verrou transactionnel RLock.
        """
        with self._lock:
            max_idx = len(self.features) - 1 if self.rollback_index == -1 else self.rollback_index

            if max_idx < 0 or len(self.features) == 0:
                self.bodies = {}
                self._notify_change()
                return

            first_outdated_idx = self._find_first_outdated_index(max_idx)

            if first_outdated_idx <= max_idx:
                self._purge_invalid_snapshots(first_outdated_idx)
            elif max_idx in self._timeline_snapshots:
                # Restauration instantanée O(1) avec isolation par clonage
                self.bodies = {b_id: s.clone() for b_id, s in self._timeline_snapshots[max_idx].items()}
                self._notify_change()
                return

            start_idx, current_bodies = self._find_cached_checkpoint(max_idx)

            for idx in range(start_idx, max_idx + 1):
                current_bodies = self._evaluate_feature_step(self.features[idx], current_bodies)
                # Enregistrement d'instantanés immuables et isolés
                self._timeline_snapshots[idx] = {b_id: s.clone() for b_id, s in current_bodies.items()}

            # Restituer les matériaux physiques enregistrés pour chaque corps
            for b_id, mat_name in self.body_materials.items():
                if b_id in current_bodies:
                    current_bodies[b_id].material_name = mat_name

            self.bodies = current_bodies
            self._notify_change()

    def set_body_material(self, body_id: str, material_name: str) -> None:
        """Associe un matériau physique d'ingénierie à un corps solide spécifique."""
        with self._lock:
            self.body_materials[body_id] = material_name
            if body_id in self.bodies:
                self.bodies[body_id].material_name = material_name
            self._notify_change()

    def get_body_material(self, body_id: str) -> str:
        """Récupère le nom du matériau physique associé au corps solide."""
        return self.body_materials.get(body_id, "Acier Inoxydable 304")

    def reorder_feature(self, from_index: int, to_index: int) -> bool:
        """
        Déplace une opération dans l'historique chronologique de la timeline.
        Vérifie l'intégrité du DAG et réévalue l'historique séquentiel.
        """
        with self._lock:
            n = len(self.features)
            if from_index < 0 or from_index >= n or to_index < 0 or to_index >= n:
                return False
            if from_index == to_index:
                return True

            feat = self.features.pop(from_index)
            self.features.insert(to_index, feat)

            # Invalider le cache à partir du plus petit indice modifié
            self.invalidate_from_index(min(from_index, to_index))
            self.rebuild()
            return True

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

