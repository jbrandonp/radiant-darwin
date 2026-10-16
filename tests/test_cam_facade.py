"""
Tests de validation de la façade canonique du package src.cam.
Vérifie la ré-exportation exhaustive et le bon fonctionnement des classes de FAO.
"""

from __future__ import annotations
import pytest

from src.core.types import Vector3D
from src.cam import (
    ToolType,
    CNCTool,
    ToolpathPoint,
    ToolpathOperation,
    CAMEngine,
    MachineKinematics5Axis,
    ToolHolderGeometry,
    FiveAxisToolPoint,
    FiveAxisGougeReport,
    FiveAxisGougeChecker,
    RTCPKinematicsEngine,
    GCodeArcInterpolator,
    StressTensor3D,
    FiberTowWaypoint,
    FiberTowTrajectory,
    AutomatedFiberPlacementEngine,
    CMMPointRecord,
    MetrologyInspectionReport,
    IterativeClosestPointAligner,
    CNCDialect,
    MachiningMetrics,
    IndustrialPostProcessor,
    StockVoxelReport,
    VolumetricStockSimulator,
    CNCPostProcessorRegistry,
)


def test_cam_facade_symbols_present() -> None:
    """Vérifie que tous les symboles sont bien exportés et instanciables."""
    assert ToolType.END_MILL is not None
    assert MachineKinematics5Axis.TABLE_TABLE_AC is not None
    assert CNCDialect.FANUC is not None

    tool = CNCTool("T1", "Fraise 6mm", ToolType.END_MILL, 6.0, 50.0)
    assert tool.diameter_mm == 6.0

    stress = StressTensor3D(100.0, 50.0, 20.0, 0.0, 0.0, 0.0)
    assert stress.sig_xx == 100.0


def test_cam_facade_rtcp_kinematics() -> None:
    """Vérifie l'instanciation du moteur RTCP via la façade."""
    engine = RTCPKinematicsEngine(
        kinematics_type=MachineKinematics5Axis.TABLE_TABLE_AC,
        pivot_offset_xyz=(0.0, 0.0, 200.0),
        tool_length_gage_mm=100.0
    )
    assert engine.tool_length == 100.0


def test_cam_facade_post_processor() -> None:
    """Vérifie le post-processeur industriel via la façade."""
    ops: list[ToolpathOperation] = []
    metrics = IndustrialPostProcessor.calculate_metrics(ops)
    assert metrics.total_distance_mm == 0.0
