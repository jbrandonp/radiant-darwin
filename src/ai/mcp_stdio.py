"""
Serveur Model Context Protocol (MCP) sur flux standardisé stdin/stdout (Transport STDIO).
Permet l'interfaçage direct avec Claude Desktop, Cursor IDE et tout client MCP
en lançant simplement 'python -m src.ai.mcp_stdio'.
Architecture 100% fortement typée sans Any ni object.
"""

from __future__ import annotations
import json
import sys
from typing import Dict, List, Optional, Tuple, Union

from src.core.document import CADDocument
from src.ai.cad_ai_bridge import CADAIBridge, CADAIExecutionResult
from src.ai.mcp_schema import get_mcp_tool_definitions, JSONSchemaDict
from src.ai.cad_script_engine import CADScriptEngine
from src.ai.cad_validator import CADValidator
from src.ai.ai_vision_feedback import AIVisionFeedback

MCPContentItem = Dict[str, str]
MCPResultVal = Union[
    str,
    int,
    bool,
    Dict[str, bool],
    Dict[str, str],
    List[MCPContentItem],
    List[Dict[str, Union[str, JSONSchemaDict]]]
]
MCPResultDict = Dict[str, Union[str, bool, Dict[str, bool], Dict[str, str], List[MCPContentItem], List[Dict[str, Union[str, JSONSchemaDict]]]]]
MCPErrorDict = Dict[str, Union[int, str]]
MCPResponseDict = Dict[str, Union[str, int, MCPResultDict, MCPErrorDict]]


class MCPStdioServer:
    """Serveur MCP conforme au standard Anthropic / OpenAI fonctionnant sur stdin/stdout."""

    def __init__(self, bridge: Optional[CADAIBridge] = None) -> None:
        self.document: CADDocument = bridge.document if bridge is not None else CADDocument("Session IA MCP")
        self.bridge: CADAIBridge = bridge if bridge is not None else CADAIBridge(self.document)

    def process_request(self, req: Dict[str, Union[str, int, Dict[str, str]]]) -> MCPResponseDict:
        """Traite une requête JSON-RPC 2.0 et retourne le dictionnaire de réponse."""
        req_id_raw = req.get("id", "1")
        req_id: str = str(req_id_raw)
        method_raw = req.get("method", "")
        method: str = str(method_raw)
        params_val = req.get("params")
        params: Dict[str, str] = params_val if isinstance(params_val, dict) else {}

        if method == "initialize":
            return self._handle_initialize(req_id)
        if method == "notifications/initialized":
            return {}
        if method == "tools/list":
            return self._handle_tools_list(req_id)
        if method == "tools/call":
            return self._handle_tools_call(req_id, params)
        if method == "ping":
            empty_res: MCPResultDict = {}
            return {"jsonrpc": "2.0", "id": req_id, "result": empty_res}

        # Méthode inconnue
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Méthode '{method}' non supportée."}
        }

    def _handle_initialize(self, req_id: str) -> MCPResponseDict:
        """Répond à la négociation initiale de protocole MCP."""
        res_data: MCPResultDict = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {
                    "listChanged": False
                }
            },
            "serverInfo": {
                "name": "cad-studio-copilot",
                "version": "2026.1"
            }
        }
        return {"jsonrpc": "2.0", "id": req_id, "result": res_data}

    def _handle_tools_list(self, req_id: str) -> MCPResponseDict:
        """Renvoie la liste des outils CAO normalisés avec schémas JSON."""
        tools = get_mcp_tool_definitions()
        res_data: MCPResultDict = {"tools": tools}
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": res_data
        }

    def _dispatch_tool_action(self, name: str, args: Dict[str, str]) -> Tuple[str, bool]:
        """Achemine l'appel d'outil vers le sous-système approprié."""
        if name in ("cad_run_script", "execute_cad_script"):
            script = str(args.get("script", "") or args.get("code", ""))
            script_res = CADScriptEngine.execute_script(self.document, script)
            return (script_res.message, script_res.success)

        if name in ("cad_validate_model", "validate_geometry"):
            diagnostics = CADValidator.get_scene_diagnostics(self.document.bodies)
            return (json.dumps(diagnostics, indent=2), True)

        if name in ("cad_get_scene_summary", "inspect_scene"):
            summary = self.bridge.get_context_summary()
            return (json.dumps(summary, indent=2), True)

        if name == "cad_capture_vision":
            vis = AIVisionFeedback.capture_document_view(self.document)
            return (f"Capture 3D réussie : {vis.description}\nData URI : {vis.data_uri[:60]}...", True)

        if name == "clear_scene":
            self.document.bodies.clear()
            self.document.features.clear()
            self.document._notify_change()
            return ("Scène réinitialisée avec succès.", True)

        if name == "check_clashes":
            clashes = CADValidator.check_scene_interferences(self.document.bodies)
            clash_list: List[Dict[str, Union[str, float]]] = [
                {"body1": c.body_1_id, "body2": c.body_2_id, "clash_vol": c.clash_volume_mm3}
                for c in clashes
            ]
            return (json.dumps(clash_list, indent=2), True)

        prompt = str(args.get("prompt", "") or args.get("code", "") or name)
        res = self.bridge.execute_prompt(prompt)
        return (res.message, res.success)

    def _handle_tools_call(self, req_id: str, params: Dict[str, str]) -> MCPResponseDict:
        """Exécute l'outil demandé et formate le résultat MCP."""
        name = str(params.get("name", ""))
        args_val = params.get("arguments")
        args: Dict[str, str] = args_val if isinstance(args_val, dict) else {}

        output_text, success = self._dispatch_tool_action(name, args)
        content_item: MCPContentItem = {"type": "text", "text": output_text}
        res_data: MCPResultDict = {
            "content": [content_item],
            "isError": not success
        }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": res_data
        }



    def handle_line(self, line: str) -> Optional[str]:
        """Traite une ligne brute de flux JSON-RPC et retourne la réponse sérialisée."""
        line = line.strip()
        if not line:
            return None
        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                return None
            res = self.process_request(req)
            if not res:
                return None
            return json.dumps(res)
        except Exception as err:
            err_res = {
                "jsonrpc": "2.0",
                "id": "null",
                "error": {"code": -32700, "message": f"Parse error: {err}"}
            }
            return json.dumps(err_res)

    def run_stdio_loop(self) -> None:
        """Boucle principale de traitement des entrées/sorties standard (STDIO)."""
        for line in sys.stdin:
            resp_line = self.handle_line(line)
            if resp_line:
                sys.stdout.write(resp_line + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    server = MCPStdioServer()
    server.run_stdio_loop()
