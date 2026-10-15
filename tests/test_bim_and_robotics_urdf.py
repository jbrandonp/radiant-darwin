"""
Tests unitaires pour l'extension BIM (IFCSLAB, IFCWINDOW, IFCSPACE) et la cinématique robotique URDF.
"""

from __future__ import annotations
import math
import numpy as np
import pytest

from src.specialized.bim_engine import (
    BIMMaterialType,
    BIMLayer,
    BIMOpening,
    BIMRebar,
    BIMSlab,
    BIMWindow,
    BIMSpace,
    BIMWall,
    BIMBuildingStorey,
    export_bim_to_ifc4,
)
from src.specialized.robot_kinematics import (
    RobotArm6Axis,
    URDFJoint,
    URDFLink,
    URDFInertial,
    URDFVisual,
)


def test_bim_slab_and_window_and_space():
    """Vérifie la modélisation de dalle, fenêtre, espace intérieur et leur export IFC4."""
    rebar = BIMRebar(rebar_id="HA12", diameter_mm=12.0, length_mm=5000.0, count=10)
    assert rebar.steel_weight_kg > 0.0

    slab = BIMSlab(slab_id="Dalle_RDC", length_mm=6000.0, width_mm=5000.0, thickness_mm=220.0)
    slab.add_rebar(rebar)
    assert slab.area_m2 == pytest.approx(30.0, abs=1e-4)
    assert slab.volume_m3 == pytest.approx(6.6, abs=1e-3)

    solid_slab = slab.to_solid()
    assert solid_slab.is_watertight() is True
    assert solid_slab.get_volume() > 0.0

    win = BIMWindow(window_id="Baie_Vitree_Sud", width_mm=2400.0, height_mm=2150.0)
    assert win.area_m2 == pytest.approx(5.16, abs=1e-2)

    space = BIMSpace(space_id="Salon_Sejour", name="Séjour", area_m2=42.0, height_mm=2800.0)
    assert space.volume_m3 == pytest.approx(117.6, abs=1e-2)

    storey = BIMBuildingStorey(name="Niveau_1", elevation=3.0)
    storey.add_slab(slab)
    storey.add_window(win)
    storey.add_space(space)

    assert storey.total_slab_area() == pytest.approx(30.0, abs=1e-4)
    assert storey.total_usable_floor_area() == pytest.approx(42.0, abs=1e-4)

    ifc_text = export_bim_to_ifc4([storey])
    assert "IFC4" in ifc_text
    assert "IFCSLAB" in ifc_text
    assert "IFCWINDOW" in ifc_text
    assert "IFCSPACE" in ifc_text
    assert "Dalle_RDC" in ifc_text
    assert "Baie_Vitree_Sud" in ifc_text
    assert "Salon_Sejour" in ifc_text


def test_robot_arm_urdf_generation_and_parsing():
    """Vérifie la génération standard d'un fichier URDF ROS et son analyse par le parseur."""
    robot = RobotArm6Axis(model_name="KUKA_KR6_6DoF")

    # Génération du document XML URDF
    urdf_content = robot.to_urdf()
    assert "<robot name=\"KUKA_KR6_6DoF\">" in urdf_content
    assert "<link name=\"base_link\">" in urdf_content
    assert "<link name=\"link_6\">" in urdf_content
    assert "<joint name=\"joint_1\" type=\"revolute\">" in urdf_content
    assert "<joint name=\"joint_6\" type=\"revolute\">" in urdf_content

    # Analyse et reconstruction par le parseur URDF
    joints = RobotArm6Axis.parse_urdf(urdf_content)
    assert len(joints) == 6
    assert joints[0].name == "joint_1"
    assert joints[0].parent_link == "base_link"
    assert joints[0].child_link == "link_1"
    assert joints[5].name == "joint_6"
    assert joints[5].parent_link == "link_5"
    assert joints[5].child_link == "link_6"

    # Vérification des limites articulaires
    for j in joints:
        assert j.lower_limit_rad == pytest.approx(-3.14159, abs=1e-3)
        assert j.upper_limit_rad == pytest.approx(3.14159, abs=1e-3)
        assert j.effort_limit > 0.0
