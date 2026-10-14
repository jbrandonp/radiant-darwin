"""
Noyau Géométrique & Multiphysique Unifié NEXUS-3D (Next-Gen AI-Native Geometric Kernel).
Intègre la topologie B-Rep rigoureuse d'OpenCASCADE / Truck, la modélisation hybride
de ZW3D Overdrive, l'arithmétique exacte de Manifold3D, et les piliers de rupture technologique :
1. Prédicats géométriques adaptatifs exacts de Shewchuk (RobustGeometricPredicates).
2. Quaternions duaux SE(3) et pipeline multi-échelle Relative-To-Eye (DualQuaternion, RelativeToEyePipeline).
3. Arène mémoire générationnelle O(1) de type SlotMap / ECS (GenerationalArena, ArenaKey).
4. Graphe de calcul incrémental adressé par le contenu (IncrementalExecutionDAG, DAGNode).
5. Barrière de contact non-linéaire inviolable IPC et optimisation physique adjointe (IncrementalPotentialContact, AdjointSensitivityEngine).
6. Opérateurs topologiques formels d'Euler-Poincaré (NexusEulerOperators).
7. Interfaces IA natives (NeuralSDFEngine, DifferentiableGeometryEngine, CADTokenizer).

Typage statique exhaustif et architecture modulaire certifiée.
"""

from src.core.nexus_kernel.brep_topology import (
    SurfaceType, CurveType, NexusVertex, NexusCurve, NexusLineCurve,
    NexusCircleCurve, NexusEdge, NexusWire, NexusSurface, NexusPlaneSurface,
    NexusCylinderSurface, NexusSphereSurface, NexusFace, NexusShell, NexusBRep
)
from src.core.nexus_kernel.euler_operators import (
    NexusEulerOperators, EulerPoincareDiagnostic
)
from src.core.nexus_kernel.hybrid_solid import NexusSolid
from src.core.nexus_kernel.ai_interfaces import (
    NeuralSDFEngine, DifferentiableGeometryEngine, CADTokenizer, LatentShapeEmbedding
)
from src.core.nexus_kernel.robust_predicates import (
    RobustGeometricPredicates, Orientation
)
from src.core.nexus_kernel.dual_quaternions import (
    Quaternion, DualQuaternion, RelativeToEyePipeline
)
from src.core.nexus_kernel.generational_arena import (
    ArenaKey, GenerationalArena
)
from src.core.nexus_kernel.incremental_dag import (
    DAGNode, IncrementalExecutionDAG, ExecutionStats
)
from src.core.nexus_kernel.unified_physics import (
    IncrementalPotentialContact, IPCBarrierResult,
    AdjointSensitivityEngine, AdjointSensitivityResult,
    CutFEMStabilizer, SmallDisplacementTorsor
)

__all__ = [
    "SurfaceType", "CurveType", "NexusVertex", "NexusCurve", "NexusLineCurve",
    "NexusCircleCurve", "NexusEdge", "NexusWire", "NexusSurface", "NexusPlaneSurface",
    "NexusCylinderSurface", "NexusSphereSurface", "NexusFace", "NexusShell", "NexusBRep",
    "NexusEulerOperators", "EulerPoincareDiagnostic",
    "NexusSolid", "NeuralSDFEngine", "DifferentiableGeometryEngine", "CADTokenizer",
    "LatentShapeEmbedding",
    "RobustGeometricPredicates", "Orientation",
    "Quaternion", "DualQuaternion", "RelativeToEyePipeline",
    "ArenaKey", "GenerationalArena",
    "DAGNode", "IncrementalExecutionDAG", "ExecutionStats",
    "IncrementalPotentialContact", "IPCBarrierResult",
    "AdjointSensitivityEngine", "AdjointSensitivityResult",
    "CutFEMStabilizer", "SmallDisplacementTorsor"
]
