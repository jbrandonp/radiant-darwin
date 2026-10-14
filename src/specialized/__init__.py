"""
Ateliers Métiers Spécialisés de CAD Studio (Specialized Workbenches).
Regroupe les modules avancés :
- BIM & Architecture conforme IFC4
- Robotique Industrielle 6 axes
- Aérodynamique & CFD
- ECAD / MCAD Intégration PCB
Typage statique exhaustif et architecture modulaire.
"""

from src.specialized.bim_engine import BIMWall, BIMLayer, BIMOpening, BIMRebar, BIMBuildingStorey, BIMMaterialType
from src.specialized.robot_kinematics import RobotArm6Axis, DHParameter
from src.specialized.aerodynamics_solver import AerodynamicsSolver, AerodynamicReport
from src.specialized.pcb_integrator import PCBBoard, PCBComponent3D

__all__ = [
    "BIMWall", "BIMLayer", "BIMOpening", "BIMRebar", "BIMBuildingStorey", "BIMMaterialType",
    "RobotArm6Axis", "DHParameter",
    "AerodynamicsSolver", "AerodynamicReport",
    "PCBBoard", "PCBComponent3D"
]
