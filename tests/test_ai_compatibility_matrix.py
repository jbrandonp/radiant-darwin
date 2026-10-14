"""
Suite de tests complète d'interopérabilité et matrice de compatibilité IA (AI Compatibility Matrix).
Vérifie la robustesse face aux variations des agents (Claude Desktop, Cursor, OpenAI, Ollama, LangChain) :
1. Désérialisation d'arguments (dictionnaires, JSON stringifié, blocs markdown).
2. Coercition de types et extraction automatique d'unités physiques (mm, cm, m, in, N, kN, deg, rad, MPa, bar).
3. Résolution des synonymes et alias de paramètres (width vs largeur vs w).
4. Traitement complet des outils déclaratifs MCP (create_primitive, synthesize_shape, drill_hole, boolean_operation).
5. Sérialisation compacte et encodage UTF-8 / ASCII sûr sous Windows.
"""

import json
import math
import pytest

from src.core.document import CADDocument
from src.core.geometry import make_box, make_cylinder
from src.ai.cad_ai_compatibility import (
    AIArgumentAdapter,
    AIParameterAliases,
    AICompactSerializer,
    AIPlatformCompat
)
from src.ai.mcp_stdio import MCPStdioServer


class TestAIArgumentAdapter:
    """Vérifie la robustesse de l'analyseur d'arguments face aux hallucinations et formats des LLMs."""

    def test_parse_raw_arguments_dict(self) -> None:
        raw = {"width_mm": 100.0, "height_mm": 50.0}
        parsed = AIArgumentAdapter.parse_raw_arguments(raw)
        assert parsed["width_mm"] == 100.0
        assert parsed["height_mm"] == 50.0

    def test_parse_raw_arguments_stringified_json(self) -> None:
        """Format standard OpenAI Function Calling."""
        raw = json.dumps({"width_mm": 120.0, "applied_force_n": 1500.0})
        parsed = AIArgumentAdapter.parse_raw_arguments(raw)
        assert parsed["width_mm"] == 120.0
        assert parsed["applied_force_n"] == 1500.0

    def test_parse_raw_arguments_markdown_fenced(self) -> None:
        """Format parfois renvoyé par des LLMs locaux ou proxies."""
        raw = "```json\n{\"depth_mm\": 25.4, \"material_name\": \"Acier\"}\n```"
        parsed = AIArgumentAdapter.parse_raw_arguments(raw)
        assert parsed["depth_mm"] == 25.4
        assert parsed["material_name"] == "Acier"

    def test_parse_raw_arguments_none_and_invalid(self) -> None:
        assert AIArgumentAdapter.parse_raw_arguments(None) == {}
        assert AIArgumentAdapter.parse_raw_arguments("invalide non json") == {}

    def test_get_float_with_units(self) -> None:
        args = {
            "val_mm": "15mm",
            "val_cm": "2.5 cm",
            "val_m": "0.1 m",
            "val_in": "2 in",
            "val_force_n": "2500N",
            "val_force_kn": "3.5 kN",
            "val_angle_deg": "45 deg",
            "val_angle_symbol": "90°",
            "val_angle_rad": f"{math.pi / 2.0} rad",
            "val_pressure_mpa": "350 MPa",
            "val_pressure_bar": "50 bar",
            "val_comma": "12,7 mm"
        }
        assert AIArgumentAdapter.get_float(args, "val_mm") == pytest.approx(15.0)
        assert AIArgumentAdapter.get_float(args, "val_cm") == pytest.approx(25.0)
        assert AIArgumentAdapter.get_float(args, "val_m") == pytest.approx(100.0)
        assert AIArgumentAdapter.get_float(args, "val_in") == pytest.approx(50.8)
        assert AIArgumentAdapter.get_float(args, "val_force_n") == pytest.approx(2500.0)
        assert AIArgumentAdapter.get_float(args, "val_force_kn") == pytest.approx(3500.0)
        assert AIArgumentAdapter.get_float(args, "val_angle_deg") == pytest.approx(45.0)
        assert AIArgumentAdapter.get_float(args, "val_angle_symbol") == pytest.approx(90.0)
        assert AIArgumentAdapter.get_float(args, "val_angle_rad") == pytest.approx(90.0)
        assert AIArgumentAdapter.get_float(args, "val_pressure_mpa") == pytest.approx(350.0)
        assert AIArgumentAdapter.get_float(args, "val_pressure_bar") == pytest.approx(5.0)
        assert AIArgumentAdapter.get_float(args, "val_comma") == pytest.approx(12.7)

    def test_get_int_coercion(self) -> None:
        args = {"count_str": "24", "count_flt": 18.9, "count_unit": "12 dents"}
        assert AIArgumentAdapter.get_int(args, "count_str") == 24
        assert AIArgumentAdapter.get_int(args, "count_flt") == 19
        assert AIArgumentAdapter.get_int(args, "count_unit") == 12

    def test_get_bool_coercion(self) -> None:
        assert AIArgumentAdapter.get_bool({"flag": "true"}, "flag") is True
        assert AIArgumentAdapter.get_bool({"flag": "yes"}, "flag") is True
        assert AIArgumentAdapter.get_bool({"flag": "oui"}, "flag") is True
        assert AIArgumentAdapter.get_bool({"flag": "1"}, "flag") is True
        assert AIArgumentAdapter.get_bool({"flag": "false"}, "flag") is False
        assert AIArgumentAdapter.get_bool({"flag": "no"}, "flag") is False
        assert AIArgumentAdapter.get_bool({"flag": "non"}, "flag") is False
        assert AIArgumentAdapter.get_bool({"flag": "0"}, "flag") is False
        assert AIArgumentAdapter.get_bool({}, "flag", default=True) is True

    def test_get_sub_dict_stringified(self) -> None:
        args = {"dimensions": "{\"width_mm\": 50, \"height_mm\": 30}"}
        sub = AIArgumentAdapter.get_sub_dict(args, "dimensions")
        assert sub["width_mm"] == 50
        assert sub["height_mm"] == 30


class TestAIParameterAliases:
    """Vérifie la normalisation des alias et la protection des mots-clés réservés."""

    def test_reserved_keys_unaltered(self) -> None:
        assert AIParameterAliases.get_canonical_key("name") == "name"
        assert AIParameterAliases.get_canonical_key("method") == "method"
        assert AIParameterAliases.get_canonical_key("id") == "id"
        assert AIParameterAliases.get_canonical_key("params") == "params"

    def test_aliases_resolution(self) -> None:
        assert AIParameterAliases.get_canonical_key("largeur") == "width_mm"
        assert AIParameterAliases.get_canonical_key("w") == "width_mm"
        assert AIParameterAliases.get_canonical_key("longueur") == "length_mm"
        assert AIParameterAliases.get_canonical_key("hauteur") == "height_mm"
        assert AIParameterAliases.get_canonical_key("profondeur") == "depth_mm"
        assert AIParameterAliases.get_canonical_key("force") == "applied_force_n"
        assert AIParameterAliases.get_canonical_key("charge") == "applied_force_n"
        assert AIParameterAliases.get_canonical_key("fraise") == "tool_diameter_mm"
        assert AIParameterAliases.get_canonical_key("materiau") == "material_name"


class TestMCPStdioServerCompatibility:
    """Vérifie l'exécution directe des requêtes MCP avec les variations de formats d'agents."""

    def test_create_primitive_cylinder_with_units(self) -> None:
        server = MCPStdioServer()
        req = {
            "jsonrpc": "2.0",
            "id": "test_1",
            "method": "tools/call",
            "params": {
                "name": "create_primitive",
                "arguments": {
                    "primitive_type": "cylinder",
                    "radius_mm": "15mm",
                    "height_mm": "60mm"
                }
            }
        }
        resp = server.process_request(req)
        assert resp["result"]["isError"] is False
        assert len(server.document.bodies) == 1
        body = next(iter(server.document.bodies.values()))
        assert body.volume() > 0.0

    def test_create_primitive_nested_dims_stringified_openai(self) -> None:
        server = MCPStdioServer()
        req = {
            "jsonrpc": "2.0",
            "id": "test_2",
            "method": "tools/call",
            "params": {
                "name": "create_primitive",
                "arguments": json.dumps({
                    "primitive_type": "box",
                    "dimensions": {"width_mm": "50mm", "height_mm": "30mm", "depth_mm": "20mm"}
                })
            }
        }
        resp = server.process_request(req)
        assert resp["result"]["isError"] is False
        assert len(server.document.bodies) == 1

    def test_synthesize_shape_spur_gear_and_flange(self) -> None:
        server = MCPStdioServer()
        req_gear = {
            "jsonrpc": "2.0",
            "id": "gear_1",
            "method": "tools/call",
            "params": {
                "name": "synthesize_shape",
                "arguments": {
                    "shape_type": "spur_gear",
                    "parameters": {"num_teeth": "16", "module": "2.5mm", "face_width": "15mm"}
                }
            }
        }
        resp_gear = server.process_request(req_gear)
        assert resp_gear["result"]["isError"] is False
        assert any("spur_gear" in k for k in server.document.bodies.keys())

    def test_drill_hole_with_units_and_aliases(self) -> None:
        server = MCPStdioServer()
        box = make_box(80.0, 80.0, 30.0, center=True)
        server.document.bodies["Plaque_Support"] = box

        req_drill = {
            "jsonrpc": "2.0",
            "id": "drill_1",
            "method": "tools/call",
            "params": {
                "name": "drill_hole",
                "arguments": {
                    "target_body_id": "Plaque_Support",
                    "diameter_mm": "12mm",
                    "depth_mm": "30mm",
                    "center_x": 0.0,
                    "center_y": 0.0
                }
            }
        }
        resp_drill = server.process_request(req_drill)
        assert resp_drill["result"]["isError"] is False
        drilled_body = server.document.bodies["Plaque_Support"]
        assert drilled_body.volume() < box.volume()

    def test_boolean_operation_mcp(self) -> None:
        server = MCPStdioServer()
        b1 = make_box(40.0, 40.0, 40.0, center=True)
        b2 = make_cylinder(10.0, 50.0, center=True)
        server.document.bodies["Bloc"] = b1
        server.document.bodies["Cyl"] = b2

        req_bool = {
            "jsonrpc": "2.0",
            "id": "bool_1",
            "method": "tools/call",
            "params": {
                "name": "boolean_operation",
                "arguments": {
                    "operation": "difference",
                    "target_body_id": "Bloc",
                    "tool_body_id": "Cyl"
                }
            }
        }
        resp_bool = server.process_request(req_bool)
        assert resp_bool["result"]["isError"] is False
        assert server.document.bodies["Bloc"].volume() < b1.volume()

    def test_flattened_params_ollama_compatibility(self) -> None:
        """Modèles locaux passant les arguments directement à la racine de 'params'."""
        server = MCPStdioServer()
        req = {
            "jsonrpc": "2.0",
            "id": "ollama_1",
            "method": "tools/call",
            "params": {
                "name": "create_primitive",
                "primitive_type": "sphere",
                "radius_mm": "25mm"
            }
        }
        resp = server.process_request(req)
        assert resp["result"]["isError"] is False
        assert len(server.document.bodies) == 1

    def test_inspect_and_validate_geometry_mcp(self) -> None:
        server = MCPStdioServer()
        server.document.bodies["Cube"] = make_box(20.0, 20.0, 20.0)

        # Inspect
        resp_inspect = server.process_request({
            "jsonrpc": "2.0",
            "id": "insp_1",
            "method": "tools/call",
            "params": {"name": "inspect_scene"}
        })
        assert resp_inspect["result"]["isError"] is False

        # Validate
        resp_val = server.process_request({
            "jsonrpc": "2.0",
            "id": "val_1",
            "method": "tools/call",
            "params": {"name": "validate_geometry", "arguments": {"body_id": "Cube"}}
        })
        assert resp_val["result"]["isError"] is False


class TestAICompactSerializerAndEncoding:
    """Vérifie le respect de la fenêtre de contexte et la conformité d'encodage."""

    def test_compact_text_truncation(self) -> None:
        huge_text = "A" * 5000
        compacted = AICompactSerializer.compact_text(huge_text, max_chars=1000)
        assert len(compacted) < 1500
        assert "Contenu tronqué pour respecter la fenêtre de contexte IA" in compacted

    def test_compact_gcode(self) -> None:
        lines = [f"G1 X{i} Y{i} F1000" for i in range(100)]
        gcode = "\n".join(lines)
        compacted = AICompactSerializer.compact_gcode(gcode, max_lines=40)
        assert "lignes de trajectoire CNC omises" in compacted

    def test_safe_json_dumps_preserves_accents_as_ascii(self) -> None:
        """Immunise contre les erreurs de décodage cp1252 / ASCII de Windows."""
        data = {"message": "Pièce usinée à 45° avec boîte en aluminium"}
        serialized = AICompactSerializer.safe_json_rpc_dumps(data, ensure_ascii=True)
        # Ne doit contenir aucun caractère non-ASCII (> 127)
        assert all(ord(c) < 128 for c in serialized)
        # Mais le décodage JSON restitue exactement les caractères originaux
        restored = json.loads(serialized)
        assert restored["message"] == "Pièce usinée à 45° avec boîte en aluminium"

    def test_configure_stdio_utf8(self) -> None:
        # Doit s'exécuter sans lever d'exception
        res = AIPlatformCompat.configure_stdio_utf8()
        assert isinstance(res, bool)
