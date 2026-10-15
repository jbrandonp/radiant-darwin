"""
Ateliers Métiers Spécialisés de CAD Studio (Specialized Workbenches).
Regroupe les modules avancés :
- BIM & Architecture conforme IFC4
- Robotique Industrielle 6 axes & ROS URDF
- Aérodynamique, VLM, Poutres de Timoshenko & Aéroélasticité
- ECAD / MCAD Intégration PCB (Gerber RS-274X, KiCad PCB) & Twin thermique
Typage statique exhaustif et architecture modulaire.
"""

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
    DHParameter,
    DenavitHartenbergParameter,
    URDFInertial,
    URDFVisual,
    URDFJoint,
    URDFLink,
    RobotArm6Axis,
)
from src.specialized.aerodynamics_solver import (
    FluidFlowProperties,
    AirfoilSurfaceData,
    AerodynamicForces,
    ThinAirfoilPolar,
    VortexLatticeResult,
    BeamBoundaryCondition,
    BeamCrossSection,
    BeamStructuralAnalysisResult,
    AerodynamicReport,
    AerodynamicsSolver,
    StructuralBeamSolver,
)
from src.specialized.pcb_integrator import (
    PCBBoard,
    PCBComponent3D,
    GerberAperture,
    RS274XParser,
    KiCadPCBParser,
)
from src.specialized.ecad_thermal_twin import (
    IPCLayerType,
    CopperTrace,
    SMTComponent,
    ECADThermalReport,
    ECADThermalTwin,
)

__all__ = [
    # BIM
    "BIMMaterialType",
    "BIMLayer",
    "BIMOpening",
    "BIMRebar",
    "BIMSlab",
    "BIMWindow",
    "BIMSpace",
    "BIMWall",
    "BIMBuildingStorey",
    "export_bim_to_ifc4",
    # Robotics
    "DHParameter",
    "DenavitHartenbergParameter",
    "URDFInertial",
    "URDFVisual",
    "URDFJoint",
    "URDFLink",
    "RobotArm6Axis",
    # Aerodynamics & Aeroelasticity
    "FluidFlowProperties",
    "AirfoilSurfaceData",
    "AerodynamicForces",
    "ThinAirfoilPolar",
    "VortexLatticeResult",
    "BeamBoundaryCondition",
    "BeamCrossSection",
    "BeamStructuralAnalysisResult",
    "AerodynamicReport",
    "AerodynamicsSolver",
    "StructuralBeamSolver",
    # ECAD / PCB Integrator
    "PCBBoard",
    "PCBComponent3D",
    "GerberAperture",
    "RS274XParser",
    "KiCadPCBParser",
    # ECAD Thermal Twin
    "IPCLayerType",
    "CopperTrace",
    "SMTComponent",
    "ECADThermalReport",
    "ECADThermalTwin",
]
