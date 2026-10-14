"""
Définitions et schémas officiels du protocole Model Context Protocol (MCP Tool Registry).
Permet aux modèles de langage (Claude, ChatGPT, Cursor, Antigravity) de découvrir
et d'invoquer les fonctions de modélisation CAO par Function Calling structuré (JSON-RPC 2.0).
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

from src.core.document import CADDocument
from src.core.geometry import (
    Solid, make_box, make_cylinder, make_sphere, make_cone, make_torus
)
from src.core.types import Vector3D
from src.ai.shape_synthesizer import ShapeSynthesizer
from src.ai.cad_validator import CADValidator, ValidationReport, InterferenceReport
from src.ai.cad_script_engine import CADScriptEngine, ScriptExecutionResult

# Typage strict pour les dictionnaires JSON Schema sans Any ni object
SchemaVal = Union[str, int, float, bool, None, List[str], Dict[str, Union[str, List[str], Dict[str, str]]]]
SchemaProperties = Dict[str, Dict[str, Union[str, List[str], Dict[str, str]]]]
JSONSchemaDict = Dict[str, Union[str, List[str], SchemaProperties]]


@dataclass
class MCPToolDefinition:
    """Définition d'un outil MCP conforme aux spécifications 2024-11-05."""
    name: str
    description: str
    inputSchema: JSONSchemaDict


class MCPToolRegistry:
    """Registre des outils CAO exposés aux agents IA par le protocole MCP."""

    @classmethod
    def get_tools(cls) -> List[MCPToolDefinition]:
        """Retourne la liste des outils déclarés avec leurs schémas de paramètres complets."""
        return [
            MCPToolDefinition(
                name="create_primitive",
                description="Crée une primitive géométrique 3D de base (box, cylinder, sphere, cone, torus).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "primitive_type": {
                            "type": "string",
                            "description": "Type de primitive : 'box', 'cylinder', 'sphere', 'cone', 'torus'."
                        },
                        "dimensions": {
                            "type": "object",
                            "description": "Dimensions associées (ex: width, height, depth pour box; radius, height pour cylinder)."
                        }
                    },
                    "required": ["primitive_type"]
                }
            ),
            MCPToolDefinition(
                name="synthesize_shape",
                description="Génère une pièce industrielle complexe (engrenage, bride, dissipateur, boîtier, équerre, arbre étagé).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "shape_type": {
                            "type": "string",
                            "description": "Type de pièce : 'spur_gear', 'pipe_flange', 'heat_sink', 'enclosure', 'bracket', 'stepped_shaft'."
                        },
                        "parameters": {
                            "type": "object",
                            "description": "Paramètres géométriques de conception industrielle."
                        }
                    },
                    "required": ["shape_type"]
                }
            ),
            MCPToolDefinition(
                name="drill_hole",
                description="Perce un alésage cylindrique paramétrique dans une pièce cible.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "target_body_id": {
                            "type": "string",
                            "description": "Identifiant de la pièce cible à percer."
                        },
                        "diameter_mm": {
                            "type": "number",
                            "description": "Diamètre de l'alésage en millimètres."
                        },
                        "depth_mm": {
                            "type": "number",
                            "description": "Profondeur de perçage en millimètres."
                        },
                        "center_x": {
                            "type": "number",
                            "description": "Position X du centre du perçage."
                        },
                        "center_y": {
                            "type": "number",
                            "description": "Position Y du centre du perçage."
                        }
                    },
                    "required": ["target_body_id", "diameter_mm", "depth_mm"]
                }
            ),
            MCPToolDefinition(
                name="boolean_operation",
                description="Applique une opération booléenne volumique (union, difference, intersection) entre deux corps.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "description": "'union', 'difference', ou 'intersection'."
                        },
                        "target_body_id": {
                            "type": "string",
                            "description": "Identifiant du corps cible récepteur."
                        },
                        "tool_body_id": {
                            "type": "string",
                            "description": "Identifiant du corps outil qui opère sur la cible."
                        }
                    },
                    "required": ["operation", "target_body_id", "tool_body_id"]
                }
            ),
            MCPToolDefinition(
                name="inspect_scene",
                description="Renvoie l'inspection physique complète de la scène (corps, volumes, masses, encombrements).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "body_id": {
                            "type": "string",
                            "description": "Optionnel: identifiant d'un corps spécifique à inspecter."
                        }
                    }
                }
            ),
            MCPToolDefinition(
                name="validate_geometry",
                description="Valide l'intégrité topologique (Euler-Poincaré), l'étanchéité et la manufacturabilité d'une pièce.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "body_id": {
                            "type": "string",
                            "description": "Identifiant de la pièce à valider."
                        }
                    },
                    "required": ["body_id"]
                }
            ),
            MCPToolDefinition(
                name="check_clashes",
                description="Détecte les interférences physiques et collisions volumiques entre les corps de l'assemblage.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            MCPToolDefinition(
                name="execute_cad_script",
                description="Exécute un script Python déclaratif Code-as-CAD dans l'environnement sécurisé de CAD Studio.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Code Python utilisant l'objet contextuel 'cad'."
                        }
                    },
                    "required": ["code"]
                }
            ),
            MCPToolDefinition(
                name="clear_scene",
                description="Réinitialise la scène en supprimant tous les corps solides et esquisses.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            )
        ]
