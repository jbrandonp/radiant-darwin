"""
Module de FAO (CAM) et génération de G-Code.
Fournit le calcul de trajectoires 2D.5, 3 axes, 5 axes continus avec cinématique RTCP,
placement de fibres AFP, métrologie CMM et simulation volumique de matière.
"""

from src.cam.cam_engine import ToolType, CNCTool, ToolpathPoint, ToolpathOperation, CAMEngine
from src.cam.five_axis_cam import (
    MachineKinematics5Axis,
    ToolHolderGeometry,
    FiveAxisToolPoint,
    FiveAxisGougeReport,
    FiveAxisGougeChecker,
    RTCPKinematicsEngine,
    GCodeArcInterpolator,
)
from src.cam.fiber_placement_afp import (
    StressTensor3D,
    FiberTowWaypoint,
    FiberTowTrajectory,
    AutomatedFiberPlacementEngine,
)
from src.cam.metrology_cmm_icp import (
    CMMPointRecord,
    MetrologyInspectionReport,
    IterativeClosestPointAligner,
)
from src.cam.post_processors import (
    CNCDialect,
    MachiningMetrics,
    IndustrialPostProcessor,
)
from src.cam.volumetric_simulator import (
    StockVoxelReport,
    VolumetricStockSimulator,
    CNCPostProcessorRegistry,
)

__all__ = [
    "ToolType",
    "CNCTool",
    "ToolpathPoint",
    "ToolpathOperation",
    "CAMEngine",
    "MachineKinematics5Axis",
    "ToolHolderGeometry",
    "FiveAxisToolPoint",
    "FiveAxisGougeReport",
    "FiveAxisGougeChecker",
    "RTCPKinematicsEngine",
    "GCodeArcInterpolator",
    "StressTensor3D",
    "FiberTowWaypoint",
    "FiberTowTrajectory",
    "AutomatedFiberPlacementEngine",
    "CMMPointRecord",
    "MetrologyInspectionReport",
    "IterativeClosestPointAligner",
    "CNCDialect",
    "MachiningMetrics",
    "IndustrialPostProcessor",
    "StockVoxelReport",
    "VolumetricStockSimulator",
    "CNCPostProcessorRegistry",
]
