"""
Plans et repères de référence géométriques auxiliaires (Datum Planes).
Supporte les décalages cartésiens et les modes d'attachement dynamiques.
"""
from __future__ import annotations
from enum import Enum
from typing import Dict, Optional, Tuple
import numpy as np

from src.core.types import FeatureStatus, Vector3D, Point2D, PlaneType
from src.core.geometry import Solid
from src.core.feature import Feature
from src.core.sketch import Sketch2D

class DatumPlaneFeature(Feature):
    """
    Plan de référence paramétrique auxiliaire (FreeCAD PartDesign Datum Plane).
    Définit un plan de construction décalé ou orienté pour y attacher des esquisses.
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Datum Plane",
        base_plane: PlaneType = PlaneType.XY,
        offset_distance: float = 0.0
    ) -> None:
        super().__init__(feature_id, name)
        self.base_plane = base_plane
        self.parameters = {
            "offset_distance": float(offset_distance),
        }

    def evaluate(self, existing_bodies: Dict[str, Solid], sketches: Dict[str, Sketch2D]) -> Dict[str, Solid]:
        """Un plan de référence est un élément de construction non volumique."""
        self.status = FeatureStatus.OK
        return dict(existing_bodies)

    def attach_to_sketch(self, sketch: Sketch2D) -> None:
        """Associe ce plan de référence à une esquisse pour définir son plan et son décalage."""
        sketch.plane = self.base_plane
        sketch.offset_distance = self.parameters.get("offset_distance", 0.0)


class DatumAttachmentMode(Enum):
    """Modes d'attachement géométrique dynamique pour plans de référence (FreeCAD PartDesign DatumPlane)."""
    OFFSET = "offset"
    THREE_POINTS = "three_points"
    TANGENT_TO_FACE = "tangent_to_face"
    NORMAL_TO_CURVE = "normal_to_curve"
    LINE_AND_POINT = "line_and_point"


class DynamicDatumPlaneFeature(DatumPlaneFeature):
    """
    Plan de référence dynamique multi-modes (FreeCAD PartDesign Datum Plane).
    Supporte 5 modes d'attachement géométrique formels :
    - OFFSET : décalage normal par rapport à un plan cartésien
    - THREE_POINTS : passant par 3 sommets 3D (p1, p2, p3)
    - TANGENT_TO_FACE : plan tangent à une surface courbe au point p1 avec normale donnée
    - NORMAL_TO_CURVE : plan normal à une courbe en un point p1 avec vecteur tangent donné
    - LINE_AND_POINT : passant par une droite (p1-p2) et un point externe p3
    """

    def __init__(
        self,
        feature_id: str,
        name: str = "Dynamic Datum Plane",
        mode: DatumAttachmentMode = DatumAttachmentMode.OFFSET,
        base_plane: PlaneType = PlaneType.XY,
        offset_distance: float = 0.0,
        point1: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        point2: Optional[Tuple[float, float, float]] = None,
        point3: Optional[Tuple[float, float, float]] = None,
        tangent_or_normal: Optional[Tuple[float, float, float]] = None
    ) -> None:
        super().__init__(feature_id, name, base_plane=base_plane, offset_distance=offset_distance)
        self.mode = mode
        self.point1 = point1
        self.point2 = point2
        self.point3 = point3
        self.tangent_or_normal = tangent_or_normal

        self.origin: Vector3D = Vector3D(point1[0], point1[1], point1[2])
        self.normal: Vector3D = Vector3D(0.0, 0.0, 1.0)
        self.u_axis: Vector3D = Vector3D(1.0, 0.0, 0.0)
        self.v_axis: Vector3D = Vector3D(0.0, 1.0, 0.0)
        self._compute_frame()

    def _compute_frame_three_points(self) -> None:
        p1 = np.array(self.point1, dtype=np.float64)
        p2 = np.array(self.point2, dtype=np.float64)
        p3 = np.array(self.point3, dtype=np.float64)
        v12 = p2 - p1
        v13 = p3 - p1
        norm12 = float(np.linalg.norm(v12))
        u_vec = v12 / norm12 if norm12 > 1e-9 else np.array([1.0, 0.0, 0.0])
        cross_n = np.cross(v12, v13)
        norm_n = float(np.linalg.norm(cross_n))
        n_vec = cross_n / norm_n if norm_n > 1e-9 else np.array([0.0, 0.0, 1.0])
        v_vec = np.cross(n_vec, u_vec)
        self.origin = Vector3D(float(p1[0]), float(p1[1]), float(p1[2]))
        self.normal = Vector3D(float(n_vec[0]), float(n_vec[1]), float(n_vec[2]))
        self.u_axis = Vector3D(float(u_vec[0]), float(u_vec[1]), float(u_vec[2]))
        self.v_axis = Vector3D(float(v_vec[0]), float(v_vec[1]), float(v_vec[2]))

    def _compute_frame_normal_or_tangent(self) -> None:
        p1 = np.array(self.point1, dtype=np.float64)
        raw_vec = np.array(self.tangent_or_normal, dtype=np.float64)
        norm_val = float(np.linalg.norm(raw_vec))
        n_vec = raw_vec / norm_val if norm_val > 1e-9 else np.array([0.0, 0.0, 1.0])
        ref = np.array([1.0, 0.0, 0.0]) if abs(n_vec[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u_cross = np.cross(n_vec, ref)
        u_vec = u_cross / float(np.linalg.norm(u_cross))
        v_vec = np.cross(n_vec, u_vec)
        self.origin = Vector3D(float(p1[0]), float(p1[1]), float(p1[2]))
        self.normal = Vector3D(float(n_vec[0]), float(n_vec[1]), float(n_vec[2]))
        self.u_axis = Vector3D(float(u_vec[0]), float(u_vec[1]), float(u_vec[2]))
        self.v_axis = Vector3D(float(v_vec[0]), float(v_vec[1]), float(v_vec[2]))

    def _compute_frame_line_and_point(self) -> None:
        p1 = np.array(self.point1, dtype=np.float64)
        p2 = np.array(self.point2, dtype=np.float64)
        p3 = np.array(self.point3, dtype=np.float64)
        u_raw = p2 - p1
        u_norm = float(np.linalg.norm(u_raw))
        u_vec = u_raw / u_norm if u_norm > 1e-9 else np.array([1.0, 0.0, 0.0])
        w_vec = p3 - p1
        cross_n = np.cross(u_vec, w_vec)
        norm_n = float(np.linalg.norm(cross_n))
        n_vec = cross_n / norm_n if norm_n > 1e-9 else np.array([0.0, 0.0, 1.0])
        v_vec = np.cross(n_vec, u_vec)
        self.origin = Vector3D(float(p1[0]), float(p1[1]), float(p1[2]))
        self.normal = Vector3D(float(n_vec[0]), float(n_vec[1]), float(n_vec[2]))
        self.u_axis = Vector3D(float(u_vec[0]), float(u_vec[1]), float(u_vec[2]))
        self.v_axis = Vector3D(float(v_vec[0]), float(v_vec[1]), float(v_vec[2]))

    def _compute_frame_offset(self) -> None:
        offset = self.parameters.get("offset_distance", 0.0)
        if self.base_plane == PlaneType.XY:
            self.origin = Vector3D(0.0, 0.0, offset)
            self.normal = Vector3D(0.0, 0.0, 1.0)
            self.u_axis = Vector3D(1.0, 0.0, 0.0)
            self.v_axis = Vector3D(0.0, 1.0, 0.0)
        elif self.base_plane == PlaneType.XZ:
            self.origin = Vector3D(0.0, offset, 0.0)
            self.normal = Vector3D(0.0, 1.0, 0.0)
            self.u_axis = Vector3D(1.0, 0.0, 0.0)
            self.v_axis = Vector3D(0.0, 0.0, 1.0)
        elif self.base_plane == PlaneType.YZ:
            self.origin = Vector3D(offset, 0.0, 0.0)
            self.normal = Vector3D(1.0, 0.0, 0.0)
            self.u_axis = Vector3D(0.0, 1.0, 0.0)
            self.v_axis = Vector3D(0.0, 0.0, 1.0)

    def _compute_frame(self) -> None:
        """Calcule le repère orthonormal local 3D (origin, u_axis, v_axis, normal)."""
        if self.mode == DatumAttachmentMode.THREE_POINTS and self.point2 is not None and self.point3 is not None:
            self._compute_frame_three_points()
        elif self.mode in (DatumAttachmentMode.NORMAL_TO_CURVE, DatumAttachmentMode.TANGENT_TO_FACE) and self.tangent_or_normal is not None:
            self._compute_frame_normal_or_tangent()
        elif self.mode == DatumAttachmentMode.LINE_AND_POINT and self.point2 is not None and self.point3 is not None:
            self._compute_frame_line_and_point()
        else:
            self._compute_frame_offset()

    def project_point_to_plane(self, pt_3d: Tuple[float, float, float]) -> Point2D:
        """Projette un point spatial 3D dans le repère 2D (u, v) du plan de référence."""
        p = np.array(pt_3d, dtype=np.float64)
        o = np.array([self.origin.x, self.origin.y, self.origin.z], dtype=np.float64)
        u = np.array([self.u_axis.x, self.u_axis.y, self.u_axis.z], dtype=np.float64)
        v = np.array([self.v_axis.x, self.v_axis.y, self.v_axis.z], dtype=np.float64)

        diff = p - o
        return Point2D(float(np.dot(diff, u)), float(np.dot(diff, v)))

    def get_transformation_matrix(self) -> np.ndarray:
        """Retourne la matrice homogène 4x4 de passage du repère local au repère global."""
        mat = np.eye(4, dtype=np.float64)
        mat[0:3, 0] = [self.u_axis.x, self.u_axis.y, self.u_axis.z]
        mat[0:3, 1] = [self.v_axis.x, self.v_axis.y, self.v_axis.z]
        mat[0:3, 2] = [self.normal.x, self.normal.y, self.normal.z]
        mat[0:3, 3] = [self.origin.x, self.origin.y, self.origin.z]
        return mat


