"""
Module de FAO (CAM) et génération de G-Code.
Fournit le calcul de trajectoires 2D.5, 3 axes, 5 axes continus avec cinématique RTCP et interpolation G02/G03.
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
]
