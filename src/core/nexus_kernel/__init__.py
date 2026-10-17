"""
Noyau Géométrique & Multiphysique Unifié NEXUS-3D (Next-Gen AI-Native Geometric Kernel).
Intègre la topologie B-Rep rigoureuse d'OpenCASCADE / Truck, la modélisation hybride
de ZW3D Overdrive, l'arithmétique exacte de Manifold3D, et les 14 piliers de rupture technologique :
1. Prédicats géométriques adaptatifs exacts de Shewchuk (RobustGeometricPredicates).
2. Quaternions duaux SE(3) et pipeline multi-échelle Relative-To-Eye (DualQuaternion, RelativeToEyePipeline).
3. Arène mémoire générationnelle O(1) de type SlotMap / ECS (GenerationalArena, ArenaKey).
4. Graphe de calcul incrémental adressé par le contenu (IncrementalExecutionDAG, DAGNode).
5. Barrière de contact non-linéaire inviolable IPC et optimisation physique adjointe (IncrementalPotentialContact, AdjointSensitivityEngine).
6. Opérateurs topologiques formels d'Euler-Poincaré (NexusEulerOperators).
7. Interfaces IA natives (NeuralSDFEngine, DifferentiableGeometryEngine, CADTokenizer).
8. Quadrature de Saye sur cellules coupées pour CutFEM (SayeImplicitQuadrature, SayeQuadratureRule).
9. Surfaces développables K=0 et dépouille industrielle (RuledDevelopableSurface, IsoclinicDraftEngine).
10. Élagage d'arbres CSG/SDF par arithmétique d'intervalles type Fidget (SDFInterval, SDFIntervalTreeNode).
11. Cinématique des boucles fermées dans l'espace opérationnel (ClosedLoopKinematicEngine).
12. Topologie B-Rep étanche avec arête 3D maîtresse (WatertightTrimmedEdge, CoordinatedMeshSealer).
13. Intégration symplectique alpha-généralisée et formulation anti-locking (GeneralizedAlphaIntegrator, VolumetricLockingMitigation).

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
from src.core.nexus_kernel.saye_quadrature import (
    QuadraturePoint3D, SayeQuadratureRule, SayeImplicitQuadrature
)
from src.core.nexus_kernel.developable_surfaces import (
    DraftDiagnostic, RuledDevelopableSurface, IsoclinicDraftEngine
)
from src.core.nexus_kernel.fidget_interval_tree import (
    CSGOpType, SDFInterval, SDFIntervalTreeNode
)
from src.core.nexus_kernel.closed_loop_kinematics import (
    ClosedLoopDynamicsResult, ClosedLoopKinematicEngine
)
from src.core.nexus_kernel.trimmed_brep_watertight import (
    CoordinatedBoundaryVertex, WatertightEdgeReport, WatertightTrimmedEdge, CoordinatedMeshSealer,
    SurfaceSurfaceIntersectionSolver
)
from src.core.nexus_kernel.symplectic_integrator import (
    GeneralizedAlphaStepResult, GeneralizedAlphaIntegrator, VolumetricLockingMitigation
)
from src.core.nexus_kernel.native_accel import (
    NativeAccelerationEngine, AccelerationBackend,
    accelerated_orient2d, accelerated_orient3d,
    accelerated_interval_overlap, accelerated_saye_quadrature,
    accelerated_nurbs_knot_span
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
    "CutFEMStabilizer", "SmallDisplacementTorsor",
    "QuadraturePoint3D", "SayeQuadratureRule", "SayeImplicitQuadrature",
    "DraftDiagnostic", "RuledDevelopableSurface", "IsoclinicDraftEngine",
    "CSGOpType", "SDFInterval", "SDFIntervalTreeNode",
    "ClosedLoopDynamicsResult", "ClosedLoopKinematicEngine",
    "CoordinatedBoundaryVertex", "WatertightEdgeReport", "WatertightTrimmedEdge", "CoordinatedMeshSealer",
    "SurfaceSurfaceIntersectionSolver",
    "GeneralizedAlphaStepResult", "GeneralizedAlphaIntegrator", "VolumetricLockingMitigation",
    "NativeAccelerationEngine", "AccelerationBackend", "accelerated_orient2d", "accelerated_orient3d",
    "accelerated_interval_overlap", "accelerated_saye_quadrature", "accelerated_nurbs_knot_span"
]
