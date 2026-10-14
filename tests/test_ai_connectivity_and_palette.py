"""
Suite de tests pour la connectivité IA et la prise en main rapide de CAD Studio :
- Serveur MCP transport STDIO (MCPStdioServer)
- Générateur de configuration 1-clic pour Claude Desktop, Cursor et Antigravity (AIConnectorConfigGenerator)
- Rendu et retour visuel multimodal (AIVisionFeedback)
- Enrichissement du contexte partagé (CADAIBridge.get_context_summary)
- Endpoints étendus du serveur HTTP (CADAIServerHandler)
"""

from __future__ import annotations
import json
import os
import tempfile
import pytest

from src.core.document import CADDocument
from src.core.geometry import make_box, make_cylinder
from src.ai.cad_ai_bridge import CADAIBridge, AICommandType
from src.ai.mcp_stdio import MCPStdioServer
from src.ai.ai_connector_config import AIConnectorConfigGenerator
from src.ai.ai_vision_feedback import AIVisionFeedback, VisionFeedbackResult


# =========================================================================
# 1. Tests MCPStdioServer (Transport STDIO officiel)
# =========================================================================

def test_mcp_stdio_initialize() -> None:
    server = MCPStdioServer()
    req = {
        "jsonrpc": "2.0",
        "id": "init-1",
        "method": "initialize",
        "params": {}
    }
    resp = server.process_request(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == "init-1"
    assert "result" in resp
    assert resp["result"]["serverInfo"]["name"] == "cad-studio-copilot"
    assert "tools" in resp["result"]["capabilities"]


def test_mcp_stdio_tools_list() -> None:
    server = MCPStdioServer()
    req = {
        "jsonrpc": "2.0",
        "id": "list-1",
        "method": "tools/list",
        "params": {}
    }
    resp = server.process_request(req)
    assert resp["id"] == "list-1"
    tools = resp["result"]["tools"]
    assert len(tools) >= 9
    tool_names = [t["name"] for t in tools]
    assert "cad_create_parametric_shape" in tool_names
    assert "cad_run_script" in tool_names
    assert "cad_validate_model" in tool_names


def test_mcp_stdio_tools_call_script_and_vision() -> None:
    server = MCPStdioServer()

    # Appel script Code-as-CAD
    req_script = {
        "jsonrpc": "2.0",
        "id": "call-1",
        "method": "tools/call",
        "params": {
            "name": "cad_run_script",
            "arguments": {
                "script": "b = cad.box(30, 30, 10); cad.commit(b, 'Piece_Test')"
            }
        }
    }
    resp_script = server.process_request(req_script)
    assert resp_script["result"]["isError"] is False
    assert "Piece_Test" in resp_script["result"]["content"][0]["text"]
    assert len(server.document.bodies) == 1

    # Appel capture visuelle
    req_vision = {
        "jsonrpc": "2.0",
        "id": "call-2",
        "method": "tools/call",
        "params": {
            "name": "cad_capture_vision",
            "arguments": {}
        }
    }
    resp_vision = server.process_request(req_vision)
    assert resp_vision["result"]["isError"] is False
    assert "Capture 3D réussie" in resp_vision["result"]["content"][0]["text"]


def test_mcp_stdio_handle_line_json() -> None:
    server = MCPStdioServer()
    raw_line = json.dumps({"jsonrpc": "2.0", "id": "42", "method": "ping", "params": {}})
    res_str = server.handle_line(raw_line)
    assert res_str is not None
    res_obj = json.loads(res_str)
    assert res_obj["id"] == "42"

    # Erreur de parsing JSON
    bad_res = server.handle_line("NOT_JSON")
    assert bad_res is not None
    assert "Parse error" in bad_res


# =========================================================================
# 2. Tests AIConnectorConfigGenerator (Configuration 1-Clic)
# =========================================================================

def test_ai_connector_config_generation() -> None:
    gen = AIConnectorConfigGenerator(project_root="/test/project", python_executable="/test/python.exe")

    # Claude Desktop
    claude_snip = gen.generate_claude_desktop_config()
    assert claude_snip.client_name == "Claude Desktop"
    claude_data = json.loads(claude_snip.config_json)
    assert "mcpServers" in claude_data
    assert claude_data["mcpServers"]["cad-studio"]["command"] == "/test/python.exe"

    # Cursor
    cursor_snip = gen.generate_cursor_config()
    assert "mcpServers" in json.loads(cursor_snip.config_json)

    # Antigravity / Gemini
    anti_snip = gen.generate_antigravity_config()
    assert json.loads(anti_snip.config_json)["server_name"] == "cad-studio"

    # cURL snippet
    curl_cmd = gen.generate_http_curl_snippet(host="127.0.0.1", port=8765)
    assert "curl" in curl_cmd
    assert "8765/mcp" in curl_cmd


def test_ai_connector_install_to_claude_desktop_simulation() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_appdata = os.path.join(tmp_dir, "AppData", "Roaming")
        os.environ["APPDATA"] = fake_appdata
        try:
            gen = AIConnectorConfigGenerator(project_root=tmp_dir, python_executable="python")
            ok, msg = gen.install_to_claude_desktop()
            assert ok is True
            target_file = os.path.join(fake_appdata, "Claude", "claude_desktop_config.json")
            assert os.path.exists(target_file)
            with open(target_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
            assert "cad-studio" in saved["mcpServers"]
        finally:
            pass


# =========================================================================
# 3. Tests AIVisionFeedback (Vision Multimodale)
# =========================================================================

def test_ai_vision_feedback_rendered_image() -> None:
    doc = CADDocument("Test_Vision")
    box = make_box(40.0, 30.0, 20.0, center=True)
    doc.bodies["Box_1"] = box

    vis = AIVisionFeedback.capture_document_view(doc, width=256, height=256)
    assert vis.has_image is True
    assert vis.width == 256
    assert vis.height == 256
    assert vis.bounding_diag_mm > 0.0
    assert vis.data_uri.startswith("data:image/png;base64,")
    assert len(vis.base64_png) > 100


def test_ai_vision_feedback_empty_document() -> None:
    doc = CADDocument("Empty_Doc")
    vis = AIVisionFeedback.capture_document_view(doc, width=128, height=128)
    assert vis.has_image is False
    assert vis.data_uri.startswith("data:image/png;base64,")


# =========================================================================
# 4. Tests CADAIBridge (Contexte Partagé & Vision Attachée)
# =========================================================================

def test_bridge_context_summary_and_vision_attachment() -> None:
    doc = CADDocument("Contexte_Test")
    bridge = CADAIBridge(doc)

    # Exécution avec attachement de vision automatique
    res = bridge.execute_prompt("Crée une boîte de 50x40x15")
    assert res.success is True
    assert res.vision_data_uri is not None
    assert res.vision_data_uri.startswith("data:image/png;base64,")

    # Résumé de contexte structuré
    ctx = bridge.get_context_summary()
    assert ctx["document_name"] == "Contexte_Test"
    assert int(ctx["bodies_count"]) == 1
    assert float(ctx["total_volume_mm3"]) > 0.0
