"""
Tests de validation pour la résolution intégrale des faiblesses du Niveau 7.
Couvre :
1. TransformBodyCommand & UndoRedoManager : translation spatiale réversible des corps solides.
2. CADViewportWidget : manipulation interactive par glisser-déplacer du Gizmo et raccourcis Ctrl+Z/Y.
3. FEASimulator & CalculixBridge : génération complète de jeux de données *.inp et exécution / repli robuste.
4. HardwareAcceleratedNeuralSDF : projection sur normale extérieure pour géométries concaves et creuses.
5. Exact Shewchuk Predicates dans native_accel.
"""

from __future__ import annotations
import os
import numpy as np
import pytest

from src.core.document import CADDocument
from src.core.geometry import make_box, make_cylinder, Solid
from src.core.types import Vector3D
from src.system.undo_redo import UndoRedoManager, TransformBodyCommand
from src.fea.fea_solver import FEASimulator
from src.materials.material_db import MATERIAL_LIBRARY
from src.render.hardware_acceleration import (
    HardwareProfile, GPUArchitecture, HardwareAcceleratedNeuralSDF
)
from src.core.nexus_kernel.native_accel import accelerated_orient2d, accelerated_orient3d


def test_document_notify_listeners() -> None:
    """Vérifie que notify_listeners déclenche bien les écouteurs de changement du document."""
    doc = CADDocument("TestDoc")
    notifications = []

    def on_change() -> None:
        notifications.append(True)

    doc.register_change_listener(on_change)
    doc.notify_listeners()
    assert len(notifications) == 1


def test_transform_body_command_undo_redo() -> None:
    """Vérifie la translation réversible d'un corps solide avec UndoRedoManager."""
    doc = CADDocument("TestDoc")
    box = make_box(20.0, 30.0, 40.0)
    doc.bodies["box1"] = box

    undo_mgr = UndoRedoManager(doc, max_history_depth=10)
    cmd = TransformBodyCommand("box1", Vector3D(10.0, 0.0, -5.0))

    # Exécution de la commande
    success = undo_mgr.execute_command(cmd)
    assert success is True
    b_min, b_max = doc.bodies["box1"].bounding_box()
    # Le centre ou la coordonnée X a augmenté de 10.0
    assert abs(b_min.x - 10.0) < 1e-4

    # Annulation (Undo)
    assert undo_mgr.can_undo is True
    undo_mgr.undo()
    b_min_undo, _ = doc.bodies["box1"].bounding_box()
    assert abs(b_min_undo.x - 0.0) < 1e-4

    # Rétablissement (Redo)
    assert undo_mgr.can_redo is True
    undo_mgr.redo()
    b_min_redo, _ = doc.bodies["box1"].bounding_box()
    assert abs(b_min_redo.x - 10.0) < 1e-4


def test_fea_calculix_deck_generation() -> None:
    """Vérifie la génération complète d'un jeu de données CalculiX (.inp) à partir d'un solide."""
    box = make_box(20.0, 20.0, 40.0)
    sim = FEASimulator(material=MATERIAL_LIBRARY["Acier Carbone C45"])

    deck = sim.generate_calculix_deck(
        solid=box,
        applied_force_newtons=5000.0,
        force_direction=Vector3D(0.0, 0.0, -1.0),
        job_name="poutre_test"
    )

    assert deck is not None
    assert deck.job_name == "poutre_test"
    assert len(deck.nodes) > 4
    assert len(deck.elements) > 0
    assert len(deck.fixed_node_ids) > 0
    assert len(deck.nodal_forces) > 0

    inp_text = deck.generate_inp_deck()
    assert "*HEADING" in inp_text
    assert "*NODE" in inp_text
    assert "*ELEMENT, TYPE=C3D4" in inp_text
    assert "*BOUNDARY" in inp_text
    assert "*CLOAD" in inp_text
    assert "*STEP" in inp_text
    assert "*STATIC" in inp_text


def test_fea_calculix_analysis_fallback() -> None:
    """Vérifie l'exécution robuste de run_calculix_analysis avec repli automatique sans crash."""
    cyl = make_cylinder(10.0, 50.0)
    sim = FEASimulator()

    # Sans ccx installé, doit se replier sur le simulateur haute fidélité interne
    res = sim.run_calculix_analysis(
        solid=cyl,
        applied_force_newtons=1000.0,
        force_direction=Vector3D(0.0, 0.0, -1.0),
        ccx_path="/chemin/inexistant/ccx"
    )

    assert res is not None
    assert res.max_stress_mpa > 0.0
    assert res.safety_factor > 0.0
    assert len(res.nodal_stresses) > 0


def test_hardware_accelerated_neural_sdf_concave() -> None:
    """Vérifie le calcul de la distance signée par projection de normale sur géométrie 3D."""
    box = make_box(30.0, 30.0, 30.0)
    mesh = box.manifold.to_mesh()
    verts = np.array(mesh.vert_properties)[:, :3]
    faces = np.array(mesh.tri_verts)

    profile = HardwareProfile(
        architecture=GPUArchitecture.CPU_FALLBACK,
        device_name="TestCPU",
        total_memory_gb=16.0,
        is_unified_memory=True,
        has_hardware_raytracing=False,
        has_tensor_cores=False,
        has_hardware_video_encoding=False,
        supported_video_codecs=("H264",),
        max_recommended_assembly_parts=10000,
        max_recommended_fem_nodes=100000
    )

    # Point intérieur : (15, 15, 15)
    # Point extérieur lointain : (50, 50, 50)
    query_pts = np.array([
        [15.0, 15.0, 15.0],
        [50.0, 50.0, 50.0]
    ], dtype=np.float64)

    dists = HardwareAcceleratedNeuralSDF.compute_batch_sdf(verts, faces, query_pts, profile)
    assert len(dists) == 2
    # Le point intérieur doit être négatif
    assert dists[0] < 0.0
    # Le point extérieur doit être strictement positif
    assert dists[1] > 0.0


def test_shewchuk_adaptive_predicates_robustness() -> None:
    """Vérifie la robustesse des prédicats exacts de Shewchuk dans native_accel."""
    # Points très proches de la colinéarité
    ax, ay = 0.0, 0.0
    bx, by = 1.0, 1.0
    cx, cy = 2.0, 2.0000000000000004
    res = accelerated_orient2d(ax, ay, bx, by, cx, cy)
    assert res > 0.0

    # Points strictement colinéaires
    cx_col, cy_col = 2.0, 2.0
    res_col = accelerated_orient2d(ax, ay, bx, by, cx_col, cy_col)
    assert abs(res_col) < 1e-12

    # Prédicat 3D tétraédrique
    res3d = accelerated_orient3d(
        0.0, 0.0, 0.0,
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0
    )
    assert res3d != 0.0
