"""
Noyau Géométrique Hybride NEXUS-3D : Topologie B-Rep Analytique & Graphe Frontière.
Inspiré de la rigueur topologique d'OpenCASCADE (OCCT) et de la sûreté mémoire de Truck (Rust).
Définit la hiérarchie topologique formelle :
Vertex -> Edge (Curve) -> Wire -> Face (Surface) -> Shell -> BRep.
Typage statique exhaustif et architecture modulaire.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Tuple, Optional, Sequence, Union
import numpy as np


class SurfaceType(Enum):
    """Types de surfaces analytiques et NURBS supportées par NEXUS-3D."""
    PLANE = "plane"
    CYLINDER = "cylinder"
    SPHERE = "sphere"
    CONE = "cone"
    TORUS = "torus"
    NURBS = "nurbs"


class CurveType(Enum):
    """Types de courbes 3D analytiques supportées."""
    LINE = "line"
    CIRCLE = "circle"
    ELLIPSE = "ellipse"
    BSPLINE = "bspline"


@dataclass(frozen=True)
class NexusVertex:
    """Sommet topologique 0D (Vertex) avec coordonnées spatiales et identifiant invariant."""
    vertex_id: str
    x: float
    y: float
    z: float
    tolerance: float = 1e-6

    @property
    def point(self) -> np.ndarray:
        """Coordonnées vectorielles du sommet sous forme de vecteur 3D."""
        return np.array([self.x, self.y, self.z], dtype=np.float64)

    def distance_to(self, other: NexusVertex) -> float:
        """Distance euclidienne vers un autre sommet."""
        return float(np.linalg.norm(self.point - other.point))


class NexusCurve:
    """Courbe 3D analytique paramétrique continue C(t)."""

    def __init__(self, curve_id: str, curve_type: CurveType) -> None:
        self.curve_id: str = curve_id
        self.curve_type: CurveType = curve_type

    def evaluate(self, t: float) -> np.ndarray:
        """Évalue la position 3D au paramètre t."""
        raise NotImplementedError

    def tangent(self, t: float) -> np.ndarray:
        """Vecteur tangent unitaire normalisé au paramètre t."""
        raise NotImplementedError

    def length(self) -> float:
        """Longueur totale de la courbe."""
        raise NotImplementedError


class NexusLineCurve(NexusCurve):
    """Segment de droite 3D défini par un point de départ et un point d'arrivée."""

    def __init__(self, curve_id: str, start: np.ndarray, end: np.ndarray) -> None:
        super().__init__(curve_id, CurveType.LINE)
        self.start: np.ndarray = np.array(start, dtype=np.float64)
        self.end: np.ndarray = np.array(end, dtype=np.float64)
        self._dir: np.ndarray = self.end - self.start
        self._len: float = float(np.linalg.norm(self._dir))

    def evaluate(self, t: float) -> np.ndarray:
        """t varie de 0.0 à 1.0 le long du segment."""
        return self.start + t * self._dir

    def tangent(self, t: float) -> np.ndarray:
        if self._len < 1e-9:
            return np.array([0.0, 0.0, 1.0], dtype=np.float64)
        return self._dir / self._len

    def length(self) -> float:
        return self._len


class NexusCircleCurve(NexusCurve):
    """Arc ou cercle 3D dans l'espace euclidien."""

    def __init__(self, curve_id: str, center: np.ndarray, normal: np.ndarray, radius: float) -> None:
        super().__init__(curve_id, CurveType.CIRCLE)
        self.center: np.ndarray = np.array(center, dtype=np.float64)
        n = np.array(normal, dtype=np.float64)
        norm_n = float(np.linalg.norm(n))
        self.normal: np.ndarray = n / norm_n if norm_n > 1e-9 else np.array([0.0, 0.0, 1.0], dtype=np.float64)
        self.radius: float = float(max(1e-6, radius))

        # Repère orthonormal local u, v dans le plan du cercle
        ref = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        if abs(float(np.dot(self.normal, ref))) > 0.9:
            ref = np.array([0.0, 1.0, 0.0], dtype=np.float64)
        u = np.cross(self.normal, ref)
        self.u_dir: np.ndarray = u / float(np.linalg.norm(u))
        self.v_dir: np.ndarray = np.cross(self.normal, self.u_dir)

    def evaluate(self, t: float) -> np.ndarray:
        """t est l'angle en radians de 0 à 2*pi."""
        return self.center + self.radius * (np.cos(t) * self.u_dir + np.sin(t) * self.v_dir)

    def tangent(self, t: float) -> np.ndarray:
        tang = -np.sin(t) * self.u_dir + np.cos(t) * self.v_dir
        return tang / float(np.linalg.norm(tang))

    def length(self) -> float:
        return 2.0 * float(np.pi) * self.radius


@dataclass
class NexusEdge:
    """Arête topologique 1D reliant deux sommets le long d'une courbe 3D."""
    edge_id: str
    curve: NexusCurve
    start_vertex: NexusVertex
    end_vertex: NexusVertex
    is_reversed: bool = False

    @property
    def length(self) -> float:
        """Longueur de l'arête."""
        return self.curve.length()


@dataclass
class NexusWire:
    """Boucle orientée fermée d'arêtes contiguës définissant la frontière d'une face."""
    wire_id: str
    edges: List[NexusEdge] = field(default_factory=list)
    is_closed: bool = True

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @property
    def total_perimeter(self) -> float:
        return sum(e.length for e in self.edges)


class NexusSurface:
    """Surface analytique paramétrique continue S(u, v)."""

    def __init__(self, surface_id: str, surface_type: SurfaceType) -> None:
        self.surface_id: str = surface_id
        self.surface_type: SurfaceType = surface_type

    def evaluate(self, u: float, v: float) -> np.ndarray:
        """Évalue le point spatial 3D S(u, v)."""
        raise NotImplementedError

    def normal(self, u: float, v: float) -> np.ndarray:
        """Normale unitaire à la surface au point (u, v)."""
        raise NotImplementedError

    def gaussian_curvature(self, u: float, v: float) -> float:
        """Courbure gaussienne K = kappa_1 * kappa_2."""
        raise NotImplementedError

    def mean_curvature(self, u: float, v: float) -> float:
        """Courbure moyenne H = (kappa_1 + kappa_2) / 2."""
        raise NotImplementedError


class NexusPlaneSurface(NexusSurface):
    """Surface plane infinie définie par une origine et une normale."""

    def __init__(self, surface_id: str, origin: np.ndarray, normal: np.ndarray) -> None:
        super().__init__(surface_id, SurfaceType.PLANE)
        self.origin: np.ndarray = np.array(origin, dtype=np.float64)
        n = np.array(normal, dtype=np.float64)
        norm_n = float(np.linalg.norm(n))
        self._normal: np.ndarray = n / norm_n if norm_n > 1e-9 else np.array([0.0, 0.0, 1.0], dtype=np.float64)

        # Repère orthonormal local u_dir, v_dir
        ref = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        if abs(float(np.dot(self._normal, ref))) > 0.9:
            ref = np.array([0.0, 1.0, 0.0], dtype=np.float64)
        u = np.cross(self._normal, ref)
        self.u_dir: np.ndarray = u / float(np.linalg.norm(u))
        self.v_dir: np.ndarray = np.cross(self._normal, self.u_dir)

    def evaluate(self, u: float, v: float) -> np.ndarray:
        return self.origin + u * self.u_dir + v * self.v_dir

    def normal(self, u: float, v: float) -> np.ndarray:
        return self._normal

    def gaussian_curvature(self, u: float, v: float) -> float:
        return 0.0  # Plan : courbures nulles

    def mean_curvature(self, u: float, v: float) -> float:
        return 0.0


class NexusCylinderSurface(NexusSurface):
    """Surface cylindrique analytique de rayon R et d'axe Z local."""

    def __init__(self, surface_id: str, origin: np.ndarray, axis: np.ndarray, radius: float) -> None:
        super().__init__(surface_id, SurfaceType.CYLINDER)
        self.origin: np.ndarray = np.array(origin, dtype=np.float64)
        ax = np.array(axis, dtype=np.float64)
        self.axis: np.ndarray = ax / float(np.linalg.norm(ax))
        self.radius: float = float(max(1e-6, radius))

        ref = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        if abs(float(np.dot(self.axis, ref))) > 0.9:
            ref = np.array([0.0, 1.0, 0.0], dtype=np.float64)
        u = np.cross(self.axis, ref)
        self.u_dir: np.ndarray = u / float(np.linalg.norm(u))
        self.v_dir: np.ndarray = np.cross(self.axis, self.u_dir)

    def evaluate(self, u: float, v: float) -> np.ndarray:
        """u est l'angle azimutal en radians, v est la hauteur le long de l'axe."""
        return self.origin + self.radius * (np.cos(u) * self.u_dir + np.sin(u) * self.v_dir) + v * self.axis

    def normal(self, u: float, v: float) -> np.ndarray:
        radial = np.cos(u) * self.u_dir + np.sin(u) * self.v_dir
        return radial / float(np.linalg.norm(radial))

    def gaussian_curvature(self, u: float, v: float) -> float:
        return 0.0  # Cylindre : surface développable

    def mean_curvature(self, u: float, v: float) -> float:
        return 1.0 / (2.0 * self.radius)


class NexusSphereSurface(NexusSurface):
    """Surface sphérique analytique de centre C et de rayon R."""

    def __init__(self, surface_id: str, center: np.ndarray, radius: float) -> None:
        super().__init__(surface_id, SurfaceType.SPHERE)
        self.center: np.ndarray = np.array(center, dtype=np.float64)
        self.radius: float = float(max(1e-6, radius))

    def evaluate(self, u: float, v: float) -> np.ndarray:
        """u est la longitude [0, 2pi], v est la latitude [-pi/2, pi/2]."""
        x = self.radius * np.cos(v) * np.cos(u)
        y = self.radius * np.cos(v) * np.sin(u)
        z = self.radius * np.sin(v)
        return self.center + np.array([x, y, z], dtype=np.float64)

    def normal(self, u: float, v: float) -> np.ndarray:
        pt = self.evaluate(u, v) - self.center
        return pt / float(np.linalg.norm(pt))

    def gaussian_curvature(self, u: float, v: float) -> float:
        return 1.0 / (self.radius ** 2)

    def mean_curvature(self, u: float, v: float) -> float:
        return 1.0 / self.radius


@dataclass
class NexusFace:
    """Face topologique 2D délimitée par une surface support et des boucles de découpe."""
    face_id: str
    surface: NexusSurface
    outer_wire: NexusWire
    inner_wires: List[NexusWire] = field(default_factory=list)
    area: float = 0.0

    @property
    def surface_type(self) -> SurfaceType:
        return self.surface.surface_type


@dataclass
class NexusShell:
    """Coque topologique fermée orientée composée de faces contiguës."""
    shell_id: str
    faces: List[NexusFace] = field(default_factory=list)
    is_closed: bool = True

    @property
    def face_count(self) -> int:
        return len(self.faces)

    @property
    def total_area(self) -> float:
        return sum(f.area for f in self.faces)


class NexusBRep:
    """
    Graphe topologique complet Boundary Representation (B-Rep).
    Fournit la vérification formelle des invariants topologiques (Formule d'Euler-Poincaré).
    """

    def __init__(self, brep_id: str) -> None:
        self.brep_id: str = brep_id
        self.vertices: Dict[str, NexusVertex] = {}
        self.edges: Dict[str, NexusEdge] = {}
        self.wires: Dict[str, NexusWire] = {}
        self.faces: Dict[str, NexusFace] = {}
        self.shells: Dict[str, NexusShell] = {}

    def add_vertex(self, vertex: NexusVertex) -> None:
        self.vertices[vertex.vertex_id] = vertex

    def add_edge(self, edge: NexusEdge) -> None:
        self.edges[edge.edge_id] = edge

    def add_wire(self, wire: NexusWire) -> None:
        self.wires[wire.wire_id] = wire

    def add_face(self, face: NexusFace) -> None:
        self.faces[face.face_id] = face

    def add_shell(self, shell: NexusShell) -> None:
        self.shells[shell.shell_id] = shell

    def euler_characteristic(self) -> int:
        """
        Calcule la caractéristique d'Euler-Poincaré chi = V - E + F.
        Pour un solide sphérique simple sans trou (genre 0), chi = 2.
        """
        v = len(self.vertices)
        e = len(self.edges)
        f = len(self.faces)
        return v - e + f

    def is_euler_valid(self, expected_genus: int = 0) -> bool:
        """Vérifie si la topologie respecte le théorème d'Euler pour le genre spécifié : chi = 2 - 2*G."""
        expected_chi = 2 - 2 * expected_genus
        return self.euler_characteristic() == expected_chi

    def to_summary_dict(self) -> Dict[str, Union[int, float, bool, str]]:
        """Génère un dictionnaire d'inspection topologique certifié."""
        return {
            "brep_id": self.brep_id,
            "vertex_count": len(self.vertices),
            "edge_count": len(self.edges),
            "wire_count": len(self.wires),
            "face_count": len(self.faces),
            "shell_count": len(self.shells),
            "euler_characteristic": self.euler_characteristic(),
            "is_closed_shell": all(s.is_closed for s in self.shells.values()) if self.shells else False
        }
