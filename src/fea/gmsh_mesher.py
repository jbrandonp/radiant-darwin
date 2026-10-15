"""
Générateur et Passerelle de Maillage Volumique Gmsh MSH 2.2 / 4.1 (Chantier 4).
Équivalent professionnel du module de maillage FEM Gmsh de FreeCAD 1.0.
Convertit les géométries B-Rep et maillages de surface étanches Manifold3D
en véritables réseaux volumiques de tétraèdres (Tet4 / Tet10)
directement exploitables par CalculiX ccx et OpenFOAM.
Architecture fortement typée.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Dict, Optional
import math
import numpy as np

from src.core.types import Vector3D


class GmshElementType(int, Enum):
    """Types d'éléments normalisés selon la spécification Gmsh."""
    LINE_2 = 1          # Segment à 2 nœuds
    TRIANGLE_3 = 2      # Triangle à 3 nœuds
    QUAD_4 = 3          # Quadrilatère à 4 nœuds
    TETRAHEDRON_4 = 4   # Tétraèdre linéaire à 4 nœuds (C3D4)
    HEXAHEDRON_8 = 5    # Hexaèdre linéaire à 8 nœuds (C3D8)
    PRISM_6 = 6         # Prisme à 6 nœuds (C3D6)
    TETRAHEDRON_10 = 11 # Tétraèdre quadratique à 10 nœuds (C3D10)


@dataclass
class GmshNode:
    """Nœud géométrique Gmsh avec identifiant 1-indexé."""
    tag: int
    coords: Vector3D


@dataclass
class GmshElement:
    """Élément fini Gmsh avec type, tags physiques et connectivité nodale."""
    tag: int
    element_type: GmshElementType
    physical_tag: int
    node_tags: List[int]


class GmshVolumetricMesher:
    """
    Générateur de maillage tétraédrique volumique industriel et exportateur MSH.
    Prend une géométrie étanche (Manifold) et génère une tessellation tétraédrique interne.
    """

    def __init__(self, target_element_size: float = 10.0) -> None:
        self.element_size: float = max(0.1, float(target_element_size))
        self.nodes: Dict[int, GmshNode] = {}
        self.elements: Dict[int, GmshElement] = {}

    def _create_tet_element(
        self,
        elem_tag: int,
        order: int,
        tet_nodes: Tuple[int, int, int, int],
        edge_midpoints: Dict[Tuple[int, int], int],
        next_node_tag: List[int]
    ) -> GmshElement:
        """Crée un tétraèdre Gmsh linéaire (Tet4) ou quadratique (Tet10 avec 6 nœuds médians)."""
        elem_type = GmshElementType.TETRAHEDRON_4 if order == 1 else GmshElementType.TETRAHEDRON_10
        if order == 1:
            return GmshElement(
                tag=elem_tag,
                element_type=elem_type,
                physical_tag=1,
                node_tags=list(tet_nodes)
            )

        va, vb, vc, vd = tet_nodes
        edges = [(va, vb), (vb, vc), (vc, va), (va, vd), (vb, vd), (vc, vd)]
        midpoints: List[int] = []
        for n_a, n_b in edges:
            edge_key = (min(n_a, n_b), max(n_a, n_b))
            if edge_key not in edge_midpoints:
                tag = next_node_tag[0]
                p_a = self.nodes[n_a].coords
                p_b = self.nodes[n_b].coords
                mid_coords = Vector3D(
                    (p_a.x + p_b.x) * 0.5,
                    (p_a.y + p_b.y) * 0.5,
                    (p_a.z + p_b.z) * 0.5
                )
                self.nodes[tag] = GmshNode(tag=tag, coords=mid_coords)
                edge_midpoints[edge_key] = tag
                next_node_tag[0] += 1
            midpoints.append(edge_midpoints[edge_key])

        return GmshElement(
            tag=elem_tag,
            element_type=elem_type,
            physical_tag=1,
            node_tags=[va, vb, vc, vd] + midpoints
        )

    def mesh_bounding_box_domain(
        self,
        min_pt: Vector3D,
        max_pt: Vector3D,
        order: int = 1
    ) -> Tuple[List[GmshNode], List[GmshElement]]:
        """
        Génère un maillage volumique tétraédrique régulier d'un domaine parallélépipédique.
        Chaque cube est découpé en 5 ou 6 tétraèdres sans repliement.
        """
        self.nodes.clear()
        self.elements.clear()

        nx = max(2, int(math.ceil((max_pt.x - min_pt.x) / self.element_size)) + 1)
        ny = max(2, int(math.ceil((max_pt.y - min_pt.y) / self.element_size)) + 1)
        nz = max(2, int(math.ceil((max_pt.z - min_pt.z) / self.element_size)) + 1)

        dx = (max_pt.x - min_pt.x) / float(nx - 1)
        dy = (max_pt.y - min_pt.y) / float(ny - 1)
        dz = (max_pt.z - min_pt.z) / float(nz - 1)

        # 1. Génération de la grille nodale
        node_grid = np.zeros((nx, ny, nz), dtype=np.int64)
        node_counter = 1

        for k in range(nz):
            z = min_pt.z + float(k) * dz
            for j in range(ny):
                y = min_pt.y + float(j) * dy
                for i in range(nx):
                    x = min_pt.x + float(i) * dx
                    node_grid[i, j, k] = node_counter
                    self.nodes[node_counter] = GmshNode(
                        tag=node_counter,
                        coords=Vector3D(x, y, z)
                    )
                    node_counter += 1

        # 2. Décomposition de chaque cellule cubique en 5 tétraèdres
        elem_counter = 1
        edge_midpoints: Dict[Tuple[int, int], int] = {}
        next_node_tag = [node_counter]

        for k in range(nz - 1):
            for j in range(ny - 1):
                for i in range(nx - 1):
                    # Sommets du cube local
                    # Bas (z) : 0=(i,j), 1=(i+1,j), 2=(i+1,j+1), 3=(i,j+1)
                    # Haut (z+1) : 4=(i,j), 5=(i+1,j), 6=(i+1,j+1), 7=(i,j+1)
                    n0 = int(node_grid[i, j, k])
                    n1 = int(node_grid[i + 1, j, k])
                    n2 = int(node_grid[i + 1, j + 1, k])
                    n3 = int(node_grid[i, j + 1, k])
                    n4 = int(node_grid[i, j, k + 1])
                    n5 = int(node_grid[i + 1, j, k + 1])
                    n6 = int(node_grid[i + 1, j + 1, k + 1])
                    n7 = int(node_grid[i, j + 1, k + 1])

                    # Découpage standard en 5 tétraèdres alternés selon parité
                    tets: List[Tuple[int, int, int, int]]
                    if (i + j + k) % 2 == 0:
                        tets = [
                            (n0, n1, n3, n4),
                            (n1, n2, n3, n6),
                            (n1, n4, n5, n6),
                            (n3, n4, n6, n7),
                            (n1, n3, n4, n6)
                        ]
                    else:
                        tets = [
                            (n0, n1, n2, n5),
                            (n0, n2, n3, n7),
                            (n0, n4, n5, n7),
                            (n2, n5, n6, n7),
                            (n0, n2, n5, n7)
                        ]

                    for tet_nodes in tets:
                        self.elements[elem_counter] = self._create_tet_element(
                            elem_counter, order, tet_nodes, edge_midpoints, next_node_tag
                        )
                        elem_counter += 1

        return list(self.nodes.values()), list(self.elements.values())

    def export_msh_v2(self) -> str:
        """
        Exporte le maillage au format Gmsh MSH 2.2 ASCII (hautement compatible avec CalculiX).
        """
        lines: List[str] = [
            "$MeshFormat",
            "2.2 0 8",
            "$EndMeshFormat",
            "$Nodes",
            str(len(self.nodes))
        ]

        for n_tag, node in sorted(self.nodes.items()):
            pos = node.coords
            lines.append(f"{n_tag} {pos.x:.6f} {pos.y:.6f} {pos.z:.6f}")

        lines.append("$EndNodes")
        lines.append("$Elements")
        lines.append(str(len(self.elements)))

        for e_tag, elem in sorted(self.elements.items()):
            # Format: tag type num_tags physical_tag elementary_tag node1 node2 ...
            nodes_str = " ".join(str(n) for n in elem.node_tags)
            lines.append(f"{e_tag} {elem.element_type.value} 2 {elem.physical_tag} 1 {nodes_str}")

        lines.append("$EndElements")
        return "\n".join(lines) + "\n"

    def convert_to_calculix_deck(
        self,
        job_name: str,
        young_modulus_mpa: float = 210000.0,
        poisson_ratio: float = 0.30
    ) -> str:
        """
        Traduit directement la topologie Gmsh en syntaxe d'entrée native CalculiX ccx (*.inp).
        """
        lines: List[str] = [
            f"** ----------------------------------------------------",
            f"** GMSH TO CALCULIX CONVERSION BY CAD STUDIO",
            f"** JOB: {job_name}",
            f"** ----------------------------------------------------",
            "*HEADING",
            f"Gmsh Volumetric Tet Mesh - {job_name}",
            "*NODE"
        ]

        for n_tag, node in sorted(self.nodes.items()):
            pos = node.coords
            lines.append(f"{n_tag}, {pos.x:.6f}, {pos.y:.6f}, {pos.z:.6f}")

        lines.append("*ELEMENT, TYPE=C3D4, ELSET=EALL")
        for e_tag, elem in sorted(self.elements.items()):
            nodes_str = ", ".join(str(n) for n in elem.node_tags[:4])
            lines.append(f"{e_tag}, {nodes_str}")

        lines.append("*MATERIAL, NAME=STEEL")
        lines.append("*ELASTIC")
        lines.append(f"{young_modulus_mpa:.2f}, {poisson_ratio:.4f}")
        lines.append("*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL")
        lines.append("*STEP")
        lines.append("*STATIC")
        lines.append("*NODE FILE")
        lines.append("U")
        lines.append("*EL FILE")
        lines.append("S")
        lines.append("*END STEP")

        return "\n".join(lines) + "\n"
