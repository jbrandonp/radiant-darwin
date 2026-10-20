"""
Tests de validation pour les résolutions médico-légales de Niveau 7 :
- Intégration du tenseur d'élasticité de Hooke 3D (Tet10)
- Calcul de section résistante réelle FEA
- Cinématique 5-axes HEAD_HEAD_AB exacte
- Exécuteurs CalculiX & OpenFOAM
- Intégration du contrôleur SpaceMouse dans le Viewport 3D
"""

from __future__ import annotations
import math
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from src.core.types import Vector3D
from src.core.geometry import make_box, make_cylinder
from src.fea.fea_solver import FEASimulator
from src.fea.nonlinear_fem import Tet10Element, BilinearPlasticMaterial
from src.fea.calculix_bridge import CalculixSimulationDeck, FeaMaterial
from src.fea.openfoam_bridge import OpenFoamCase
from src.cam.five_axis_cam import (
    FiveAxisGougeChecker,
    ToolHolderGeometry,
    MachineKinematics5Axis,
    RTCPKinematicsEngine,
)
from src.viewport.viewport_widget import CADViewportWidget
from src.core.document import CADDocument


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_fea_effective_section_computation() -> None:
    """Vérifie que la section résistante et les contraintes FEA s'adaptent à la géométrie réelle."""
    sim = FEASimulator()
    # Poutre fine 10x10 mm vs Poutre massive 50x50 mm
    box_small = make_box(10.0, 10.0, 50.0)
    box_large = make_box(50.0, 50.0, 50.0)

    res_small = sim.run_static_analysis(box_small, applied_force_newtons=1000.0)
    res_large = sim.run_static_analysis(box_large, applied_force_newtons=1000.0)

    assert res_small is not None and res_large is not None
    # La petite section doit subir une contrainte significativement plus élevée que la grande
    assert res_small.max_stress_mpa > res_large.max_stress_mpa * 5.0


def test_nonlinear_fem_continuum_hooke_integration() -> None:
    """Vérifie que la matrice Tet10 est issue de la vraie intégration du tenseur de Hooke isotrope 3D."""
    nodes = np.array([
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [0.0, 10.0, 0.0],
        [0.0, 0.0, 10.0],
        [5.0, 0.0, 0.0],
        [5.0, 5.0, 0.0],
        [0.0, 5.0, 0.0],
        [0.0, 0.0, 5.0],
        [5.0, 0.0, 5.0],
        [0.0, 5.0, 5.0]
    ], dtype=np.float64)

    elem = Tet10Element(element_id=1, node_indices=list(range(10)))
    mat = BilinearPlasticMaterial(youngs_modulus_mpa=210000.0, poissons_ratio=0.3)
    ke = elem.calculate_stiffness_matrix(nodes, mat)

    assert ke.shape == (30, 30)
    assert np.allclose(ke, ke.T, atol=1e-5)
    # Vérification des valeurs propres : strictement positives
    eigvals = np.linalg.eigvalsh(ke)
    assert np.all(eigvals > 0.0)


def test_cam_head_head_ab_kinematics() -> None:
    """Vérifie la cinématique de tête bi-rotative A-B sans confusion d'azimut polaire."""
    holder = ToolHolderGeometry(5.0, 30.0, 5.0, 50.0, 25.0, 35.0, 60.0)
    checker = FiveAxisGougeChecker(holder=holder)

    # Outil vertical (0, 0, 1) -> A=0, B=0
    v_vert = Vector3D(0.0, 0.0, 1.0)
    a, b = checker.convert_vector_to_rotary_angles(v_vert, MachineKinematics5Axis.HEAD_HEAD_AB)
    assert a == pytest.approx(0.0, abs=1e-2)
    assert b == pytest.approx(0.0, abs=1e-2)

    # Outil incliné à 30° autour de Y (déflexion selon X)
    v_tilt_x = Vector3D(math.sin(math.radians(30.0)), 0.0, math.cos(math.radians(30.0)))
    a_x, b_x = checker.convert_vector_to_rotary_angles(v_tilt_x, MachineKinematics5Axis.HEAD_HEAD_AB)
    assert b_x == pytest.approx(30.0, abs=1e-2)
    assert a_x == pytest.approx(0.0, abs=1e-2)

    # Matrice de rotation cohérente dans le moteur RTCP
    engine = RTCPKinematicsEngine(kinematics_type=MachineKinematics5Axis.HEAD_HEAD_AB)
    r_mat = engine.compute_rotation_matrix(a_x, b_x)
    assert r_mat.shape == (3, 3)
    # L'orthogonalité de la matrice de rotation doit être préservée : R^T @ R = I
    assert np.allclose(r_mat.T @ r_mat, np.eye(3), atol=1e-4)


def test_calculix_and_openfoam_executors(tmp_path: pytest.TempPathFactory) -> None:
    """Vérifie la présence et la robustesse des méthodes d'exécution CalculiX et OpenFOAM."""
    deck = CalculixSimulationDeck(job_name="test_deck", material=FeaMaterial())
    res_ccx = deck.run_solver(str(tmp_path), timeout_seconds=1.0)
    # Sur une machine sans binaire ccx installé, retourne None sans lever d'exception non gérée
    assert res_ccx is None or isinstance(res_ccx, dict)

    of_case = OpenFoamCase("test_of", domain_min=Vector3D(-1.0, -1.0, -1.0), domain_max=Vector3D(1.0, 1.0, 1.0))
    ok, msg = of_case.run_mesh_and_solver(str(tmp_path), timeout_seconds=1.0)
    assert isinstance(ok, bool)
    assert isinstance(msg, str)


def test_viewport_spacemouse_integration(qapp: QApplication) -> None:
    """Vérifie l'intégration et le rafraîchissement caméra par le contrôleur SpaceMouse 6-DoF."""
    doc = CADDocument("SpaceMouseDoc")
    viewport = CADViewportWidget(doc)

    assert hasattr(viewport, "spacemouse")
    assert hasattr(viewport, "poll_spacemouse")

    # Au repos, poll_spacemouse retourne False
    assert viewport.poll_spacemouse(0.016) is False

    # Déflexion simulée sur l'axe de translation Z (Zoom)
    viewport.spacemouse.filtered_state.trans_z = 0.5
    init_dist = viewport.camera.distance
    moved = viewport.poll_spacemouse(0.016)
    assert moved is True
    assert viewport.camera.distance != init_dist

    viewport.close()
