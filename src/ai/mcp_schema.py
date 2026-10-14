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

    def to_dict(self) -> Dict[str, Union[str, JSONSchemaDict]]:
        """Sérialise l'outil sous forme de dictionnaire JSON standard."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema
        }



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
            ),
            MCPToolDefinition(
                name="cad_create_parametric_shape",
                description="Génère ou modélise une pièce paramétrique ou commande en langage naturel dans CAD Studio.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Description en langage naturel ou instruction de modélisation CAO."
                        }
                    },
                    "required": ["prompt"]
                }
            ),
            MCPToolDefinition(
                name="cad_run_script",
                description="Exécute un script Python déclaratif Code-as-CAD dans l'environnement CAD Studio.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "script": {
                            "type": "string",
                            "description": "Script Python utilisant le contexte fluide 'cad'."
                        }
                    },
                    "required": ["script"]
                }
            ),
            MCPToolDefinition(
                name="cad_validate_model",
                description="Valide l'intégrité topologique, l'étanchéité et les interférences de tous les solides de la scène.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            MCPToolDefinition(
                name="cad_capture_vision",
                description="Génère une capture visuelle isométrique 3D haute définition de la scène actuelle.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "width": {
                            "type": "number",
                            "description": "Largeur de l'image de rendu en pixels (défaut: 512)."
                        },
                        "height": {
                            "type": "number",
                            "description": "Hauteur de l'image de rendu en pixels (défaut: 512)."
                        }
                    }
                }
            ),
            MCPToolDefinition(
                name="cad_get_scene_summary",
                description="Fournit un résumé complet et structuré du document CAO et des métriques de scène.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            MCPToolDefinition(
                name="cad_cam_toolpath_and_gcode",
                description="Génère les trajectoires d'usinage CNC (contournage, poche, perçage) et exporte le G-Code standard ISO/GRBL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "body_id": {
                            "type": "string",
                            "description": "Identifiant de la pièce à usiner (optionnel, prend la première pièce si omis)."
                        },
                        "operation_type": {
                            "type": "string",
                            "description": "Type d'opération : 'contour', 'pocket', 'drill', 'facing'."
                        },
                        "tool_diameter_mm": {
                            "type": "number",
                            "description": "Diamètre de la fraise en mm (défaut: 6.0)."
                        },
                        "depth_mm": {
                            "type": "number",
                            "description": "Profondeur totale d'usinage en mm (défaut: 10.0)."
                        }
                    }
                }
            ),
            MCPToolDefinition(
                name="cad_fea_stress_simulation",
                description="Exécute une analyse par éléments finis (FEA), calcule les contraintes de von Mises, le déplacement maximal et le facteur de sécurité.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "body_id": {
                            "type": "string",
                            "description": "Identifiant de la pièce à simuler."
                        },
                        "applied_force_n": {
                            "type": "number",
                            "description": "Effort appliqué en Newtons (défaut: 2000.0)."
                        },
                        "material_name": {
                            "type": "string",
                            "description": "Matériau physique ('Aluminium 6061-T6', 'Acier Inox 316L', 'Titane Ti-6Al-4V', 'Acier Carbone C45')."
                        }
                    }
                }
            ),
            MCPToolDefinition(
                name="cad_generate_2d_techdraw",
                description="Génère la mise en plan technique 2D normalisée ISO (4 vues orthogonales, cartouche et cotations).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "body_id": {
                            "type": "string",
                            "description": "Identifiant de la pièce à mettre en plan."
                        },
                        "part_name": {
                            "type": "string",
                            "description": "Titre du projet dans le cartouche ISO."
                        },
                        "material_name": {
                            "type": "string",
                            "description": "Désignation du matériau normalisé."
                        }
                    }
                }
            ),
            MCPToolDefinition(
                name="cad_design_sheetmetal",
                description="Conçoit une pièce de tôlerie industrielle avec plis et calcule le développé à plat (flan) pour découpe laser.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "width_mm": {
                            "type": "number",
                            "description": "Largeur de base de la tôle en mm."
                        },
                        "length_mm": {
                            "type": "number",
                            "description": "Longueur de base de la tôle en mm."
                        },
                        "thickness_mm": {
                            "type": "number",
                            "description": "Épaisseur nominale de la tôle en mm (défaut: 2.0)."
                        },
                        "flange_height_mm": {
                            "type": "number",
                            "description": "Hauteur des rebords pliés en mm (défaut: 20.0)."
                        }
                    }
                }
            ),
            MCPToolDefinition(
                name="cad_get_physical_material_props",
                description="Calcule les propriétés physiques et massiques exactes (masse en kg/g, centre de gravité, limite d'élasticité) selon le matériau choisi.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "body_id": {
                            "type": "string",
                            "description": "Identifiant de la pièce cible."
                        },
                        "material_name": {
                            "type": "string",
                            "description": "Matériau ('Aluminium 6061-T6', 'Acier Inox 316L', 'Titane Ti-6Al-4V', 'Laiton CuZn39Pb3')."
                        }
                    }
                }
            ),
            MCPToolDefinition(
                name="cad_direct_modeling_push_pull",
                description="Modélisation directe : extrusion ou retrait d'une face de solide selon un axe (Push-Pull).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "body_id": {
                            "type": "string",
                            "description": "Identifiant de la pièce cible."
                        },
                        "offset_mm": {
                            "type": "number",
                            "description": "Distance de décalage en mm (positif pour étendre, négatif pour retirer)."
                        },
                        "axis": {
                            "type": "string",
                            "description": "Axe de décalage ('x', 'y', ou 'z')."
                        }
                    },
                    "required": ["offset_mm"]
                }
            ),
            MCPToolDefinition(
                name="cad_direct_modeling_fillet",
                description="Applique un congé ou adoucissement de rayon spécifié sur un corps solide.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "body_id": {
                            "type": "string",
                            "description": "Identifiant de la pièce cible."
                        },
                        "radius_mm": {
                            "type": "number",
                            "description": "Rayon du congé en mm."
                        }
                    },
                    "required": ["radius_mm"]
                }
            ),
            MCPToolDefinition(
                name="cad_direct_modeling_shell",
                description="Évide un corps solide pour créer une coque mince avec épaisseur de paroi constante.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "body_id": {
                            "type": "string",
                            "description": "Identifiant de la pièce cible."
                        },
                        "wall_thickness_mm": {
                            "type": "number",
                            "description": "Épaisseur de paroi de la coque en mm."
                        }
                    },
                    "required": ["wall_thickness_mm"]
                }
            ),
            MCPToolDefinition(
                name="cad_export_model",
                description="Exporte le document ou une pièce au format STEP, STL, OBJ ou DXF.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "format_type": {
                            "type": "string",
                            "description": "Format d'export : 'step', 'stl', 'obj', 'dxf'."
                        },
                        "filepath": {
                            "type": "string",
                            "description": "Chemin de destination optionnel."
                        }
                    },
                    "required": ["format_type"]
                }
            )
        ]



def get_mcp_tool_definitions() -> List[Dict[str, Union[str, JSONSchemaDict]]]:
    """Retourne la liste de tous les outils MCP enregistrés sous forme de dictionnaires."""
    return [t.to_dict() for t in MCPToolRegistry.get_tools()]

