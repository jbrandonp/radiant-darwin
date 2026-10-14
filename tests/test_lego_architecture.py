"""
Tests unitaires de l'Architecture LEGO (Contrats, Protocoles, EventBus, Registry, Pipeline).
Vérifie la modularité 'qualité Apple' : découplage absolu, conformité aux protocoles,
extensibilité par enregistrement dynamique et composabilité par pipeline fluide.
"""

import pytest
import numpy as np

from src.core.interfaces import (
    GeometryProvider, FeatureEvaluator, ExporterService, WorkbenchModule, PipelineStage
)
from src.core.geometry import Solid, make_box, make_cylinder
from src.core.types import Vector3D, BooleanOperation, FeatureStatus
from src.core.feature import BoxFeature
from src.core.document import CADDocument
from src.core.event_bus import (
    CADEventBus, CADEvent, DocumentModifiedEvent, TimelineRollbackEvent, SelectionChangedEvent
)
from src.core.registry import (
    FeatureRegistry, FeatureCategory, FeatureDescriptor, WorkbenchRegistry, bootstrap_default_features
)
from src.core.pipeline import (
    LegoPipeline, TranslateStage, RotateStage, ScaleStage, BooleanStage,
    SimplifyStage, InspectorCallbackStage
)


def test_protocol_conformance_geometry_provider():
    """Vérifie que la classe Solid implémente fidèlement le protocole GeometryProvider."""
    box = make_box(20.0, 30.0, 40.0)
    assert isinstance(box, GeometryProvider)
    assert box.volume() > 0.0
    assert box.surface_area() > 0.0
    b_min, b_max = box.bounding_box()
    assert b_max.x > b_min.x
    buf = box.to_mesh_buffer()
    assert not buf.is_empty()
    assert not box.is_empty()


def test_protocol_conformance_feature_evaluator():
    """Vérifie que les fonctionnalités implémentent le protocole FeatureEvaluator."""
    feat = BoxFeature("f1", "TestBox", width=10.0, height=20.0, depth=30.0)
    assert isinstance(feat, FeatureEvaluator)
    assert feat.feature_id == "f1"
    assert feat.name == "TestBox"
    assert feat.status == FeatureStatus.OK
    assert not feat.is_suppressed


def test_event_bus_publish_subscribe_and_isolation():
    """Vérifie la diffusion d'événements, le filtrage par type et l'isolation des erreurs."""
    bus = CADEventBus()
    received_docs: list[DocumentModifiedEvent] = []
    received_rollbacks: list[TimelineRollbackEvent] = []

    # Abonnements
    unsub_doc = bus.subscribe(DocumentModifiedEvent, lambda e: received_docs.append(e))
    unsub_rb = bus.subscribe(TimelineRollbackEvent, lambda e: received_rollbacks.append(e))

    # Écouteur défaillant pour vérifier l'isolation
    def faulty_handler(e: DocumentModifiedEvent) -> None:
        raise RuntimeError("Crash intentionnel dans l'écouteur")

    bus.subscribe(DocumentModifiedEvent, faulty_handler)

    # Émission
    e1 = DocumentModifiedEvent(document_name="TestDoc", num_bodies=2, num_features=5)
    notified = bus.publish(e1)
    assert notified == 2  # 1 valide + 1 faulty géré sans crash
    assert len(received_docs) == 1
    assert received_docs[0].document_name == "TestDoc"
    assert len(received_rollbacks) == 0

    # Émission rollback
    e2 = TimelineRollbackEvent(previous_index=5, new_index=2, max_index=5)
    bus.publish(e2)
    assert len(received_rollbacks) == 1
    assert received_rollbacks[0].new_index == 2

    # Désabonnement
    unsub_doc()
    bus.publish(DocumentModifiedEvent(document_name="Doc2", num_bodies=1, num_features=1))
    assert len(received_docs) == 1  # Pas d'incrément après désabonnement


def test_feature_registry_discovery_and_instantiation():
    """Vérifie l'enregistrement dynamique, la découverte et la création de briques LEGO."""
    bootstrap_default_features()
    all_features = FeatureRegistry.list_all()
    assert len(all_features) >= 15

    # Découverte par catégorie
    primitives = FeatureRegistry.list_by_category(FeatureCategory.PRIMITIVE)
    assert any(p.class_name == "BoxFeature" for p in primitives)
    assert any(p.class_name == "CylinderFeature" for p in primitives)

    # Création dynamique via fabrique
    feat = FeatureRegistry.create("BoxFeature", "feat_box", "MonBloc", width=30.0, height=40.0, depth=50.0)
    assert feat is not None
    assert feat.name == "MonBloc"
    assert feat.parameters["width"] == 30.0

    # Classe inexistante retourne proprement None
    assert FeatureRegistry.create("NonExistentFeature", "id1") is None


def test_lego_pipeline_chaining_and_fluent_api():
    """Vérifie le chaînage fluide d'opérations géométriques et l'historique intermédiaire."""
    initial_box = make_box(20.0, 20.0, 20.0)
    tool_cyl = make_cylinder(5.0, 30.0)

    probe_volumes: list[float] = []

    pipeline = (
        LegoPipeline[Solid]("UsineDePiece")
        .add_stage(TranslateStage(Vector3D(10.0, 0.0, 0.0)))
        .add_stage(RotateStage(0.0, 0.0, 45.0))
        .add_stage(BooleanStage(tool_cyl, BooleanOperation.CUT))
        .add_stage(InspectorCallbackStage(lambda s: probe_volumes.append(s.volume())))
        .add_stage(SimplifyStage(tolerance=0.01))
    )

    assert pipeline.stage_count() == 5

    # Exécution avec suivi de l'historique complet
    history = pipeline.execute_with_history(initial_box)
    assert len(history) == 6  # Input + 5 étapes
    assert history[0][0] == "Input"
    assert "Translate" in history[1][0]
    assert "Rotate" in history[2][0]
    assert "Boolean_cut" in history[3][0]

    final_solid = history[-1][1]
    assert isinstance(final_solid, Solid)
    assert not final_solid.is_empty()
    # Le perçage a bien réduit le volume
    assert len(probe_volumes) == 1
    assert probe_volumes[0] < initial_box.volume()


def test_document_emits_lego_events():
    """Vérifie que les mutations de CADDocument diffusent des événements sur le bus global."""
    from src.core.event_bus import global_event_bus

    captured_events: list[CADEvent] = []
    unsub1 = global_event_bus.subscribe(DocumentModifiedEvent, lambda e: captured_events.append(e))
    unsub2 = global_event_bus.subscribe(TimelineRollbackEvent, lambda e: captured_events.append(e))

    doc = CADDocument("MonProjetLego")
    f1 = BoxFeature("f1", "Box", width=10, height=10, depth=10)
    doc.add_feature(f1)

    assert any(isinstance(e, DocumentModifiedEvent) for e in captured_events)

    doc.set_rollback_index(-1)
    assert any(isinstance(e, TimelineRollbackEvent) for e in captured_events)

    unsub1()
    unsub2()
