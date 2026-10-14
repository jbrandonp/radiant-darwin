"""
Package principal du moteur de CAO paramétrique.
"""

from src.core.types import Vector3D, Point2D, PlaneType, BooleanOperation, FeatureStatus, MeshBuffer, ColorRGBA
from src.core.geometry import Solid, make_box, make_cylinder, make_sphere, make_cone, make_torus, make_wedge, extrude_polygon
from src.core.sketch import Sketch2D, SketchRectangle, SketchCircle, SketchPolygon
from src.core.feature import (
    Feature, BoxFeature, CylinderFeature, SphereFeature, ConeFeature, TorusFeature,
    WedgeFeature, ExtrudeFeature, BooleanFeature
)
from src.core.operations_advanced import (
    RevolveFeature, LinearPatternFeature, CircularPatternFeature,
    MirrorFeature, HoleFeature, ShellFeature, PipeFeature,
    PocketFeature, DatumPlaneFeature, GrooveFeature, MultiTransformFeature,
    HelixFeature, RibFeature, SplitFeature, SubtractiveLoftFeature, SubtractiveSweepFeature
)
from src.core.document import CADDocument
from src.core.exporter import CADExporter
from src.core.serializer import ProjectSerializer
from src.core.parameters import UserParameter, SafeExpressionEvaluator, ParameterTable
from src.core.interfaces import GeometryProvider, FeatureEvaluator, ExporterService, WorkbenchModule, PipelineStage
from src.core.event_bus import CADEventBus, CADEvent, DocumentModifiedEvent, FeatureEvaluatedEvent, SelectionChangedEvent, TimelineRollbackEvent, WorkbenchChangedEvent, global_event_bus
from src.core.registry import FeatureRegistry, FeatureCategory, FeatureDescriptor, WorkbenchRegistry, WorkbenchDescriptor
from src.core.pipeline import LegoPipeline, TranslateStage, RotateStage, ScaleStage, BooleanStage, SimplifyStage, InspectorCallbackStage
from src.core.industrial_analyzer import (
    compute_draft_angles, compute_wall_thickness, heal_and_validate_mesh,
    DraftAngleResult, WallThicknessResult, MeshHealingReport
)
from src.core.generative_lattices import (
    LatticeType, make_octet_cell, make_tpms_gyroid_cell,
    generate_lattice_volume, create_lightweight_infilled_part
)
from src.core.nexus_kernel import (
    NexusSolid, NexusBRep, NexusVertex, NexusEdge, NexusWire, NexusFace, NexusShell,
    NeuralSDFEngine, DifferentiableGeometryEngine, CADTokenizer, LatentShapeEmbedding
)
from src.core.modifier_stack import (
    ModifierStack, CADModifier, ModifierType,
    MirrorModifier, ArrayModifier, SolidifyModifier, BevelModifier, BooleanModifier
)
from src.core.push_pull import PushPullEngine, PushPullResult
from src.core.joint_solver import (
    FusionJointType, JointLimit, JointAnchor, AssemblyJoint, JointKinematicSolver
)

__all__ = [
    "Vector3D",
    "Point2D",
    "PlaneType",
    "BooleanOperation",
    "FeatureStatus",
    "MeshBuffer",
    "ColorRGBA",
    "Solid",
    "make_box",
    "make_cylinder",
    "make_sphere",
    "make_cone",
    "extrude_polygon",
    "Sketch2D",
    "SketchRectangle",
    "SketchCircle",
    "SketchPolygon",
    "Feature",
    "BoxFeature",
    "CylinderFeature",
    "SphereFeature",
    "ExtrudeFeature",
    "BooleanFeature",
    "RevolveFeature",
    "LinearPatternFeature",
    "CircularPatternFeature",
    "MirrorFeature",
    "HoleFeature",
    "ShellFeature",
    "PocketFeature",
    "DatumPlaneFeature",
    "GrooveFeature",
    "MultiTransformFeature",
    "HelixFeature",
    "RibFeature",
    "SplitFeature",
    "SubtractiveLoftFeature",
    "SubtractiveSweepFeature",
    "CADDocument",
    "CADExporter",
    "ProjectSerializer",
    "UserParameter",
    "SafeExpressionEvaluator",
    "ParameterTable",
    "GeometryProvider",
    "FeatureEvaluator",
    "ExporterService",
    "WorkbenchModule",
    "PipelineStage",
    "CADEventBus",
    "CADEvent",
    "DocumentModifiedEvent",
    "FeatureEvaluatedEvent",
    "SelectionChangedEvent",
    "TimelineRollbackEvent",
    "WorkbenchChangedEvent",
    "global_event_bus",
    "FeatureRegistry",
    "FeatureCategory",
    "FeatureDescriptor",
    "WorkbenchRegistry",
    "WorkbenchDescriptor",
    "LegoPipeline",
    "TranslateStage",
    "RotateStage",
    "ScaleStage",
    "BooleanStage",
    "SimplifyStage",
    "InspectorCallbackStage",
    "compute_draft_angles",
    "compute_wall_thickness",
    "heal_and_validate_mesh",
    "DraftAngleResult",
    "WallThicknessResult",
    "MeshHealingReport",
    "LatticeType",
    "make_octet_cell",
    "make_tpms_gyroid_cell",
    "generate_lattice_volume",
    "create_lightweight_infilled_part",
    "NexusSolid",
    "NexusBRep",
    "NexusVertex",
    "NexusEdge",
    "NexusWire",
    "NexusFace",
    "NexusShell",
    "NeuralSDFEngine",
    "DifferentiableGeometryEngine",
    "CADTokenizer",
    "LatentShapeEmbedding",
    "ModifierStack",
    "CADModifier",
    "ModifierType",
    "MirrorModifier",
    "ArrayModifier",
    "SolidifyModifier",
    "BevelModifier",
    "BooleanModifier",
    "PushPullEngine",
    "PushPullResult",
    "FusionJointType",
    "JointLimit",
    "JointAnchor",
    "AssemblyJoint",
    "JointKinematicSolver",
]
