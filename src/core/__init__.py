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
    HelixFeature, RibFeature
)
from src.core.document import CADDocument
from src.core.exporter import CADExporter
from src.core.serializer import ProjectSerializer
from src.core.parameters import UserParameter, SafeExpressionEvaluator, ParameterTable

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
    "CADDocument",
    "CADExporter",
    "ProjectSerializer",
    "UserParameter",
    "SafeExpressionEvaluator",
    "ParameterTable",
]
