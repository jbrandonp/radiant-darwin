"""
Atelier Métier BIM & Architecture Numérique Conforme IFC4 (BIM Workbench).
Permet la modélisation de bâtiments multi-niveaux, murs multicouches, dalles,
ouvertures de portes/fenêtres, ferraillage de béton armé (Rebar) et export standard IFC4.
Typage statique exhaustif et architecture modulaire.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Tuple, Optional, Sequence, Union
import numpy as np

from src.core.nexus_kernel.hybrid_solid import NexusSolid


class BIMMaterialType(Enum):
    """Matériaux normalisés du bâtiment."""
    CONCRETE = "concrete"
    INSULATION = "insulation"
    BRICK = "brick"
    GYPSUM = "gypsum"
    GLASS = "glass"
    STEEL = "steel"
    WOOD = "wood"


@dataclass
class BIMLayer:
    """Couche élémentaire d'un mur multicouche (complexe isolant/porteur)."""
    name: str = "Couche"
    thickness: float = 0.20  # en mètres ou mm
    material: Union[BIMMaterialType, str] = BIMMaterialType.CONCRETE
    thickness_mm: float = 200.0

    def __post_init__(self) -> None:
        if self.thickness < 5.0 and self.thickness_mm == 200.0:
            # Spécifié en mètres
            self.thickness_mm = self.thickness * 1000.0
        elif self.thickness >= 5.0:
            self.thickness_mm = self.thickness


@dataclass
class BIMOpening:
    """Réservation pour porte ou fenêtre dans un mur."""
    name: str = "Ouverture"
    opening_id: str = ""
    offset_x: float = 0.0
    elevation_z: float = 0.0
    width: float = 1.0
    height: float = 1.0
    width_mm: float = 1000.0
    height_mm: float = 1000.0
    sill_height_mm: float = 0.0
    offset_along_wall_mm: float = 0.0

    def __post_init__(self) -> None:
        if not self.opening_id:
            self.opening_id = self.name
        if self.width < 20.0 and self.width_mm == 1000.0:
            self.width_mm = self.width * 1000.0
        if self.height < 20.0 and self.height_mm == 1000.0:
            self.height_mm = self.height * 1000.0
        if self.offset_x > 0.0 and self.offset_along_wall_mm == 0.0:
            self.offset_along_wall_mm = self.offset_x * (1000.0 if self.offset_x < 20.0 else 1.0)
        if self.elevation_z > 0.0 and self.sill_height_mm == 0.0:
            self.sill_height_mm = self.elevation_z * (1000.0 if self.elevation_z < 20.0 else 1.0)


@dataclass
class BIMRebar:
    """Armature de ferraillage de béton armé (Barre d'acier nervuré)."""
    rebar_id: str = "Rebar_HA"
    diameter_mm: float = 12.0
    length_mm: float = 2000.0
    spacing_mm: float = 200.0
    steel_grade: str = "B500B"
    count: int = 1
    shape_type: str = "straight"

    @property
    def steel_weight_kg(self) -> float:
        """Masse d'acier calculée : volume * masse volumique (7850 kg/m³)."""
        radius_m = (self.diameter_mm / 2.0) / 1000.0
        length_m = self.length_mm / 1000.0
        vol_m3 = float(np.pi) * (radius_m ** 2) * length_m * float(self.count)
        return vol_m3 * 7850.0


class BIMWall:
    """Mur de bâtiment paramétrique avec calepinage multicouche et baies vitrées."""

    def __init__(
        self,
        name: str = "Mur",
        wall_id: Optional[str] = None,
        length: Optional[float] = None,
        height: Optional[float] = None,
        start_point: Optional[Tuple[float, float]] = None,
        end_point: Optional[Tuple[float, float]] = None,
        height_mm: float = 2800.0,
        layers: Optional[List[BIMLayer]] = None,
        openings: Optional[List[BIMOpening]] = None,
        rebars: Optional[List[BIMRebar]] = None
    ) -> None:
        self.wall_id: str = wall_id or name
        self.name: str = self.wall_id

        # Longueur et points
        if length is not None:
            # En mètres
            len_mm = length * 1000.0 if length < 50.0 else length
            self.start_point: np.ndarray = np.array([0.0, 0.0], dtype=np.float64)
            self.end_point: np.ndarray = np.array([len_mm, 0.0], dtype=np.float64)
        elif start_point is not None and end_point is not None:
            self.start_point = np.array(start_point, dtype=np.float64)
            self.end_point = np.array(end_point, dtype=np.float64)
        else:
            self.start_point = np.array([0.0, 0.0], dtype=np.float64)
            self.end_point = np.array([5000.0, 0.0], dtype=np.float64)

        if height is not None:
            self.height_mm: float = height * 1000.0 if height < 50.0 else height
        else:
            self.height_mm = float(max(100.0, height_mm))

        self.layers: List[BIMLayer] = layers if layers is not None else [
            BIMLayer("Porteur", 0.20, BIMMaterialType.CONCRETE, 200.0)
        ]
        self.openings: List[BIMOpening] = openings or []
        self.rebars: List[BIMRebar] = rebars or []

    @property
    def length_mm(self) -> float:
        """Longueur linéaire du mur en millimètres."""
        return float(np.linalg.norm(self.end_point - self.start_point))

    @property
    def length(self) -> float:
        """Longueur en mètres."""
        return self.length_mm / 1000.0

    @property
    def height(self) -> float:
        """Hauteur en mètres."""
        return self.height_mm / 1000.0

    @property
    def total_thickness_mm(self) -> float:
        """Épaisseur totale cumulée des couches du mur."""
        return sum(layer.thickness_mm for layer in self.layers)

    def add_opening(self, opening: BIMOpening) -> None:
        """Ajoute une ouverture (porte ou fenêtre) dans le mur."""
        self.openings.append(opening)

    def add_rebar(self, rebar: BIMRebar) -> None:
        """Ajoute un ferraillage d'armature au mur."""
        self.rebars.append(rebar)

    def generate_solid_geometry(self) -> NexusSolid:
        """Génère le solide volumique du mur avec découpe de ses ouvertures."""
        return self.to_solid()

    def to_solid(self) -> NexusSolid:
        """Génère le solide volumique du mur avec découpe de ses ouvertures."""
        len_w = max(1.0, self.length_mm)
        th_w = max(1.0, self.total_thickness_mm)
        h_w = max(1.0, self.height_mm)

        wall_solid = NexusSolid.make_box(len_w, th_w, h_w, name=f"Wall_{self.wall_id}")

        for op in self.openings:
            op_box = NexusSolid.make_box(
                op.width_mm,
                th_w * 1.5,
                op.height_mm,
                name=f"Cut_{op.opening_id}"
            )
            wall_solid = wall_solid.difference(op_box)

        return wall_solid


class BIMBuildingStorey:
    """Niveau ou étage de bâtiment regroupant murs, dalles et armatures."""

    def __init__(
        self,
        name: str = "Etage",
        storey_name: Optional[str] = None,
        elevation: float = 0.0,
        elevation_mm: Optional[float] = None,
        height_mm: float = 3000.0,
        walls: Optional[List[BIMWall]] = None
    ) -> None:
        self.storey_name: str = storey_name or name
        self.name: str = self.storey_name
        self.elevation_mm: float = elevation_mm if elevation_mm is not None else (elevation * 1000.0 if elevation < 100.0 else elevation)
        self.height_mm: float = float(height_mm)
        self.walls: List[BIMWall] = walls or []
        self.rebars: List[BIMRebar] = []

    def add_wall(self, wall: BIMWall) -> None:
        self.walls.append(wall)

    def add_rebar(self, rebar: BIMRebar) -> None:
        self.rebars.append(rebar)

    def total_wall_area(self) -> float:
        """Surface totale des murs en m²."""
        return sum(w.length * w.height for w in self.walls)

    def export_ifc4_snippet(self) -> str:
        """Génère un extrait de code standard IFC4 représentant l'étage et ses éléments."""
        lines = [
            f"/* Export IFC4 de l'étage {self.storey_name} */",
            f"#100 = IFCBUILDINGSTOREY('GUID_{self.storey_name}', $, '{self.storey_name}', $, $, $, $, {self.elevation_mm}, .ELEMENT., {self.height_mm});"
        ]
        for i, w in enumerate(self.walls):
            lines.append(
                f"#10{i+1} = IFCWALLSTANDARDCASE('GUID_W{i}', $, '{w.wall_id}', $, $, $, $, $, .SOLID_WALL.);"
            )
            for j, rb in enumerate(w.rebars):
                lines.append(
                    f"#20{i}_{j} = IFCREINFORCINGBAR('GUID_RB_{i}_{j}', $, '{rb.rebar_id}', $, $, $, $, {rb.diameter_mm}, '{rb.steel_grade}');"
                )
        return "\n".join(lines)


def export_bim_to_ifc4(storeys: List[BIMBuildingStorey]) -> str:
    """Exporte l'ensemble des étages et éléments architecturaux au format standard IFC4."""
    header = [
        "ISO-10303-21;",
        "HEADER;",
        "FILE_DESCRIPTION(('CAD Studio BIM Export IFC4'), '2;1');",
        "FILE_NAME('building_project.ifc', '2026-10-14T12:00:00', ('Architect'), ('Engineering'), 'CAD Studio', '', '');",
        "FILE_SCHEMA(('IFC4'));",
        "ENDSEC;",
        "DATA;",
        "#1 = IFCPROJECT('GUID_PROJ', $, 'Projet_Principal', $, $, $, $, (#10), #20);",
        "#10 = IFCGEOMETRICREPRESENTATIONCONTEXT($, 'Model', 3, 1.E-05, #11, $);",
        "#11 = IFCAXIS2PLACEMENT3D(#12, #13, #14);",
        "#12 = IFCCARTESIANPOINT((0., 0., 0.));",
        "#13 = IFCDIRECTION((0., 0., 1.));",
        "#14 = IFCDIRECTION((1., 0., 0.));",
    ]
    body: List[str] = []
    for s in storeys:
        body.append(s.export_ifc4_snippet())

    footer = [
        "ENDSEC;",
        "END-ISO-10303-21;"
    ]
    return "\n".join(header + body + footer)
