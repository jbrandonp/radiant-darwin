"""
Module de calcul et simulation par éléments finis (FEA / CFD).
Exporte les solveurs, passerelles industrielles CalculiX/OpenFOAM et mailleur Gmsh.
"""

from src.fea.calculix_bridge import (
    CalculixBridge,
    CalculixResultParser,
    CalculixSimulationDeck,
    FeaElementType,
    FeaMaterial,
    FeaNodalResult,
    NodalForce,
)
from src.fea.fea_solver import FEAResult, FEASimulator
from src.fea.gmsh_mesher import (
    GmshElement,
    GmshElementType,
    GmshNode,
    GmshVolumetricMesher,
)
from src.fea.nonlinear_fem import (
    BilinearPlasticMaterial,
    FrictionalContactPair,
    LinearTetraDemoSolver,
    NonlinearFEASolver,
    Tet10Element,
)
from src.fea.openfoam_bridge import (
    CfdBoundaryCondition,
    CfdFluidType,
    CfdTurbulenceModel,
    OpenFoamCase,
    OpenFoamCaseGenerator,
)

__all__ = [
    "BilinearPlasticMaterial",
    "CalculixBridge",
    "CalculixResultParser",
    "CalculixSimulationDeck",
    "CfdBoundaryCondition",
    "CfdFluidType",
    "CfdTurbulenceModel",
    "FEAResult",
    "FEASimulator",
    "FeaElementType",
    "FeaMaterial",
    "FeaNodalResult",
    "FrictionalContactPair",
    "GmshElement",
    "GmshElementType",
    "GmshNode",
    "GmshVolumetricMesher",
    "LinearTetraDemoSolver",
    "NodalForce",
    "NonlinearFEASolver",
    "OpenFoamCase",
    "OpenFoamCaseGenerator",
    "Tet10Element",
]
