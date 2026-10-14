"""
Noyau Géométrique Hybride NEXUS-3D (Next-Gen AI-Native Geometric Kernel).
Intègre la topologie B-Rep rigoureuse d'OpenCASCADE / Truck, la modélisation hybride
de ZW3D Overdrive, et l'arithmétique exacte de Manifold3D avec des interfaces natives
pour l'intelligence artificielle (Neural SDF, Géométrie Différentiable, CAD Tokenizer).
Typage strict exhaustif, zéro Any, zéro object.
"""

from src.core.nexus_kernel.brep_topology import (
    SurfaceType, CurveType, NexusVertex, NexusCurve, NexusLineCurve,
    NexusCircleCurve, NexusEdge, NexusWire, NexusSurface, NexusPlaneSurface,
    NexusCylinderSurface, NexusSphereSurface, NexusFace, NexusShell, NexusBRep
)
from src.core.nexus_kernel.hybrid_solid import NexusSolid
from src.core.nexus_kernel.ai_interfaces import (
    NeuralSDFEngine, DifferentiableGeometryEngine, CADTokenizer, LatentShapeEmbedding
)

__all__ = [
    "SurfaceType", "CurveType", "NexusVertex", "NexusCurve", "NexusLineCurve",
    "NexusCircleCurve", "NexusEdge", "NexusWire", "NexusSurface", "NexusPlaneSurface",
    "NexusCylinderSurface", "NexusSphereSurface", "NexusFace", "NexusShell", "NexusBRep",
    "NexusSolid", "NeuralSDFEngine", "DifferentiableGeometryEngine", "CADTokenizer",
    "LatentShapeEmbedding"
]
