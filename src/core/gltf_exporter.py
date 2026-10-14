"""
Exportateur de Maquettes Numériques glTF 2.0 PBR (Pillar 6).
Génère des fichiers standards glTF 2.0 conformes Khronos Group avec matériaux PBR
(Physically Based Rendering) : canal rugosité, métallicité, normales par sommet,
et encodage binaire Base64 auto-contenu pour visualisation web (Three.js, Babylon.js, Blender).
Architecture fortement typée.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
import base64
import json
import struct
import numpy as np

from src.core.types import Vector3D


@dataclass
class PbrMaterial:
    """Propriétés optiques et photoréalistes PBR."""
    name: str = "Industrial_Steel"
    base_color_rgba: Tuple[float, float, float, float] = (0.75, 0.78, 0.82, 1.0)
    metallic_factor: float = 0.85
    roughness_factor: float = 0.25


class GltfExporter:
    """
    Exportateur de géométrie 3D triangulée au standard glTF 2.0 avec tampons binaires intégrés.
    """

    def export_mesh_to_gltf(
        self,
        vertices: List[Vector3D],
        triangles: List[Tuple[int, int, int]],
        material: Optional[PbrMaterial] = None
    ) -> str:
        """
        Convertit un ensemble de sommets et triangles en document JSON glTF 2.0 valide.
        """
        if material is None:
            material = PbrMaterial()

        num_verts = len(vertices)
        num_indices = len(triangles) * 3

        if num_verts == 0 or len(triangles) == 0:
            # Document glTF minimal vide
            empty_doc = {
                "asset": {"version": "2.0", "generator": "CAD Studio glTF 2.0 PBR Exporter"},
                "scenes": [{"nodes": []}],
                "scene": 0
            }
            return json.dumps(empty_doc, indent=2)

        # 1. Calcul des normales par sommet (moyenne des faces incidentes)
        normals: List[Vector3D] = [Vector3D(0.0, 0.0, 0.0) for _ in range(num_verts)]
        for v0_idx, v1_idx, v2_idx in triangles:
            p0 = vertices[v0_idx]
            p1 = vertices[v1_idx]
            p2 = vertices[v2_idx]
            edge1 = p1.subtract(p0)
            edge2 = p2.subtract(p0)
            fn = edge1.cross(edge2)
            if fn.length() > 1e-8:
                fn_norm = fn.normalize()
                normals[v0_idx] = normals[v0_idx].add(fn_norm)
                normals[v1_idx] = normals[v1_idx].add(fn_norm)
                normals[v2_idx] = normals[v2_idx].add(fn_norm)

        normalized_normals: List[Vector3D] = []
        for n in normals:
            if n.length() > 1e-6:
                normalized_normals.append(n.normalize())
            else:
                normalized_normals.append(Vector3D(0.0, 0.0, 1.0))

        # 2. Construction des tampons binaires : Positions, Normales, Indices
        pos_bytes = bytearray()
        norm_bytes = bytearray()
        idx_bytes = bytearray()

        min_pos = [float("inf"), float("inf"), float("inf")]
        max_pos = [float("-inf"), float("-inf"), float("-inf")]

        for v in vertices:
            pos_bytes.extend(struct.pack("<fff", v.x, v.y, v.z))
            min_pos[0] = min(min_pos[0], v.x)
            min_pos[1] = min(min_pos[1], v.y)
            min_pos[2] = min(min_pos[2], v.z)
            max_pos[0] = max(max_pos[0], v.x)
            max_pos[1] = max(max_pos[1], v.y)
            max_pos[2] = max(max_pos[2], v.z)

        for n in normalized_normals:
            norm_bytes.extend(struct.pack("<fff", n.x, n.y, n.z))

        for v0, v1, v2 in triangles:
            idx_bytes.extend(struct.pack("<III", v0, v1, v2))

        # Alignement mémoire sur 4 octets
        def pad_4(b: bytearray) -> bytearray:
            rem = len(b) % 4
            if rem != 0:
                b.extend(b"\x00" * (4 - rem))
            return b

        pos_bytes = pad_4(pos_bytes)
        norm_bytes = pad_4(norm_bytes)
        idx_bytes = pad_4(idx_bytes)

        offset_pos = 0
        len_pos = len(pos_bytes)

        offset_norm = len_pos
        len_norm = len(norm_bytes)

        offset_idx = offset_norm + len_norm
        len_idx = len(idx_bytes)

        total_buffer = pos_bytes + norm_bytes + idx_bytes
        b64_buffer = base64.b64encode(total_buffer).decode("ascii")
        buffer_uri = f"data:application/octet-stream;base64,{b64_buffer}"

        gltf_dict = {
            "asset": {
                "version": "2.0",
                "generator": "CAD Studio glTF 2.0 PBR Exporter"
            },
            "scene": 0,
            "scenes": [
                {
                    "name": "DefaultScene",
                    "nodes": [0]
                }
            ],
            "nodes": [
                {
                    "name": "CADModelNode",
                    "mesh": 0
                }
            ],
            "materials": [
                {
                    "name": material.name,
                    "pbrMetallicRoughness": {
                        "baseColorFactor": [
                            material.base_color_rgba[0],
                            material.base_color_rgba[1],
                            material.base_color_rgba[2],
                            material.base_color_rgba[3]
                        ],
                        "metallicFactor": material.metallic_factor,
                        "roughnessFactor": material.roughness_factor
                    }
                }
            ],
            "meshes": [
                {
                    "name": "ManifoldMesh",
                    "primitives": [
                        {
                            "attributes": {
                                "POSITION": 0,
                                "NORMAL": 1
                            },
                            "indices": 2,
                            "material": 0,
                            "mode": 4  # TRIANGLES
                        }
                    ]
                }
            ],
            "accessors": [
                {
                    "bufferView": 0,
                    "byteOffset": 0,
                    "componentType": 5126,  # FLOAT
                    "count": num_verts,
                    "type": "VEC3",
                    "min": min_pos,
                    "max": max_pos
                },
                {
                    "bufferView": 1,
                    "byteOffset": 0,
                    "componentType": 5126,  # FLOAT
                    "count": num_verts,
                    "type": "VEC3"
                },
                {
                    "bufferView": 2,
                    "byteOffset": 0,
                    "componentType": 5125,  # UNSIGNED_INT
                    "count": num_indices,
                    "type": "SCALAR"
                }
            ],
            "bufferViews": [
                {
                    "buffer": 0,
                    "byteOffset": offset_pos,
                    "byteLength": len_pos,
                    "target": 34962  # ARRAY_BUFFER
                },
                {
                    "buffer": 0,
                    "byteOffset": offset_norm,
                    "byteLength": len_norm,
                    "target": 34962  # ARRAY_BUFFER
                },
                {
                    "buffer": 0,
                    "byteOffset": offset_idx,
                    "byteLength": len_idx,
                    "target": 34963  # ELEMENT_ARRAY_BUFFER
                }
            ],
            "buffers": [
                {
                    "byteLength": len(total_buffer),
                    "uri": buffer_uri
                }
            ]
        }

        return json.dumps(gltf_dict, indent=2)
