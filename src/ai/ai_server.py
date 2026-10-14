"""
Serveur API local et passerelle MCP pour le pilotage externe par IA (CAD-AI Server).
Fournit des points d'accès REST et un serveur JSON-RPC 2.0 conforme au protocole
Model Context Protocol (MCP) pour Claude Desktop, Cursor, Antigravity et les agents autonomes.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
import http.server
import json
import threading
from typing import Dict, List, Optional, Tuple, Union, Callable

from src.core.document import CADDocument
from src.ai.cad_ai_bridge import CADAIBridge, CADAIExecutionResult
from src.ai.cad_validator import CADValidator, ValidationReport, InterferenceReport
from src.ai.cad_script_engine import CADScriptEngine, ScriptExecutionResult
from src.ai.mcp_schema import MCPToolRegistry, JSONSchemaDict
from src.ai.ai_vision_feedback import AIVisionFeedback
from src.ai.ai_connector_config import AIConnectorConfigGenerator

JSONPrimitive = Union[str, int, float, bool, None]
JSONVal = Union[
    JSONPrimitive,
    Dict[str, JSONPrimitive],
    Dict[str, Optional[float]],
    Dict[str, bool],
    List[str],
    List[Dict[str, float]],
    List[Dict[str, str]],
    List[Dict[str, JSONPrimitive]],
    List[Dict[str, Union[str, float, bool]]],
    Dict[str, Union[JSONPrimitive, Dict[str, bool]]],
    Dict[str, Union[JSONPrimitive, int, str]],
    JSONSchemaDict
]
JSONDict = Dict[str, Union[JSONVal, List[JSONVal], Dict[str, JSONVal]]]


class CADAIServerHandler(http.server.BaseHTTPRequestHandler):
    """Gestionnaire de requêtes HTTP REST et JSON-RPC MCP pour le pilotage IA."""

    bridge: Optional[CADAIBridge] = None

    def _handle_connect_claude(self) -> None:
        """Fournit la configuration prête à l'emploi pour Claude Desktop."""
        gen = AIConnectorConfigGenerator()
        snip = gen.generate_claude_desktop_config()
        self._send_json_response(200, {
            "client": snip.client_name,
            "config_json": snip.config_json,
            "path": snip.target_filepath,
            "instructions": snip.instructions
        })

    def _handle_connect_cursor(self) -> None:
        """Fournit la configuration prête à l'emploi pour Cursor IDE."""
        gen = AIConnectorConfigGenerator()
        snip = gen.generate_cursor_config()
        self._send_json_response(200, {
            "client": snip.client_name,
            "config_json": snip.config_json,
            "path": snip.target_filepath,
            "instructions": snip.instructions
        })

    def _handle_connect_install_claude(self) -> None:
        """Installe automatiquement la configuration MCP dans Claude Desktop."""
        gen = AIConnectorConfigGenerator()
        ok, msg = gen.install_to_claude_desktop()
        self._send_json_response(200 if ok else 500, {"success": ok, "message": msg})

    def do_GET(self) -> None:
        """Points d'accès de lecture d'état, diagnostic, vision et découverte MCP."""
        get_routes: Dict[str, Callable[[], None]] = {
            "/api/cad/status": self._handle_status_request,
            "/api/cad/health": lambda: self._send_json_response(200, {"status": "ok", "engine": "NEXUS-3D SOTA", "mcp_enabled": True}),
            "/api/cad/clashes": self._handle_clashes_request,
            "/api/cad/mcp/tools": self._handle_mcp_tools_list_request,
            "/api/cad/vision": self._handle_vision_request,
            "/api/cad/connect/claude": self._handle_connect_claude,
            "/api/cad/connect/cursor": self._handle_connect_cursor,
        }
        handler = get_routes.get(self.path)
        if handler is not None:
            handler()
        else:
            self._send_json_response(404, {"error": "Endpoint non trouvé"})

    def do_POST(self) -> None:
        """Points d'accès d'exécution (prompt libre, code-as-cad, validation, protocole MCP)."""
        post_routes: Dict[str, Callable[[], None]] = {
            "/api/cad/prompt": self._handle_prompt_execution,
            "/api/cad/script": self._handle_script_execution,
            "/api/cad/validate": self._handle_validate_request,
            "/mcp": self._handle_mcp_request,
            "/api/mcp": self._handle_mcp_request,
            "/api/cad/connect/install_claude": self._handle_connect_install_claude,
        }
        handler = post_routes.get(self.path)
        if handler is not None:
            handler()
        else:
            self._send_json_response(404, {"error": "Endpoint non trouvé"})


    def _handle_status_request(self) -> None:
        """Retourne l'état complet de la scène géométrique."""
        if self.bridge is None:
            self._send_json_response(500, {"error": "Passerelle non initialisée"})
            return

        doc = self.bridge.doc
        bodies_info: List[Dict[str, float]] = []
        total_vol = 0.0

        for b_id, body in doc.bodies.items():
            v = body.volume()
            total_vol += v
            bodies_info.append({"body_id": b_id, "volume_mm3": v})

        resp_data = {
            "status": "ok",
            "document_name": doc.name,
            "num_bodies": len(doc.bodies),
            "active_bodies": len(doc.bodies),
            "total_volume_mm3": total_vol,
            "bodies": bodies_info
        }
        self._send_json_response(200, resp_data)

    def _handle_clashes_request(self) -> None:
        """Détecte les collisions et interférences volumiques dans la scène."""
        if self.bridge is None:
            self._send_json_response(500, {"error": "Passerelle non initialisée"})
            return

        reports = CADValidator.check_scene_interferences(self.bridge.doc.bodies)
        items: List[Dict[str, Union[str, float, bool]]] = []
        for r in reports:
            items.append({
                "body_1": r.body_1_id,
                "body_2": r.body_2_id,
                "has_collision": r.has_collision,
                "clash_volume_mm3": r.clash_volume_mm3,
                "description": r.description
            })

        self._send_json_response(200, {
            "status": "ok",
            "clashes_count": len(reports),
            "clashes": items
        })

    def _handle_mcp_tools_list_request(self) -> None:
        """Retourne le catalogue complet des outils MCP disponibles."""
        tools_data = [
            {"name": t.name, "description": t.description}
            for t in MCPToolRegistry.get_tools()
        ]
        self._send_json_response(200, {
            "status": "ok",
            "tools_count": len(tools_data),
            "tools": tools_data
        })

    def _handle_vision_request(self) -> None:
        """Capture et renvoie un instantané 3D en Base64 pour l'IA multimodale."""
        if self.bridge is None:
            self._send_json_response(500, {"error": "Passerelle non initialisée"})
            return
        vis = AIVisionFeedback.capture_document_view(self.bridge.doc)
        self._send_json_response(200, {
            "has_image": vis.has_image,
            "data_uri": vis.data_uri,
            "width": vis.width,
            "height": vis.height,
            "bounding_diag_mm": vis.bounding_diag_mm,
            "description": vis.description
        })

    def _handle_prompt_execution(self) -> None:
        """Reçoit une consigne textuelle libre et l'exécute sur le modèle."""
        if self.bridge is None:
            self._send_json_response(500, {"error": "Passerelle non initialisée"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length)

        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json_response(400, {"error": "Format JSON invalide."})
            return

        try:
            prompt = str(payload.get("prompt", "")).strip()
            if not prompt:
                self._send_json_response(400, {"error": "Le champ 'prompt' est requis."})
                return

            result: CADAIExecutionResult = self.bridge.execute_natural_language_prompt(prompt)

            dims_dict = None
            if result.bounding_box_dims_mm is not None:
                dims_dict = {
                    "width": result.bounding_box_dims_mm.x,
                    "height": result.bounding_box_dims_mm.y,
                    "depth": result.bounding_box_dims_mm.z
                }

            self._send_json_response(200, {
                "success": result.success,
                "message": result.message,
                "command": result.command_executed,
                "body_id": result.body_id,
                "volume_mm3": result.volume_mm3,
                "mass_aluminum_g": result.mass_aluminum_g,
                "mass_steel_g": result.mass_steel_g,
                "is_manifold": result.is_manifold,
                "quality_score": result.quality_score,
                "dimensions_mm": dims_dict
            })
        except Exception as e:
            self._send_json_response(500, {"error": f"Erreur de traitement: {str(e)}"})

    def _handle_script_execution(self) -> None:
        """Exécute un script Python déclaratif Code-as-CAD dans l'environnement cloisonné."""
        if self.bridge is None:
            self._send_json_response(500, {"error": "Passerelle non initialisée"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length)

        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json_response(400, {"error": "Format JSON invalide."})
            return

        code_str = str(payload.get("code", "")).strip()
        if not code_str:
            self._send_json_response(400, {"error": "Le champ 'code' est requis."})
            return

        res: ScriptExecutionResult = CADScriptEngine.execute_script(self.bridge.doc, code_str)
        self._send_json_response(200, {
            "success": res.success,
            "message": res.message,
            "bodies_created": res.bodies_created,
            "execution_time_ms": res.execution_time_ms
        })

    def _handle_validate_request(self) -> None:
        """Valide la géométrie d'une pièce spécifique."""
        if self.bridge is None:
            self._send_json_response(500, {"error": "Passerelle non initialisée"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length)

        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json_response(400, {"error": "Format JSON invalide."})
            return

        b_id = str(payload.get("body_id", "")).strip()
        if not b_id or b_id not in self.bridge.doc.bodies:
            self._send_json_response(404, {"error": f"Pièce '{b_id}' non trouvée dans la scène."})
            return

        solid = self.bridge.doc.bodies[b_id]
        rep = CADValidator.validate_solid(solid)

        self._send_json_response(200, {
            "body_id": b_id,
            "is_valid": rep.is_valid,
            "is_manifold": rep.is_manifold,
            "volume_mm3": rep.volume_mm3,
            "surface_area_mm2": rep.surface_area_mm2,
            "euler_characteristic": rep.euler_characteristic,
            "genus": rep.genus,
            "quality_score_percent": rep.quality_score_percent,
            "warnings": rep.warnings
        })

    def _handle_mcp_request(self) -> None:
        """Point d'accès Model Context Protocol (MCP) conforme à la spécification JSON-RPC 2.0."""
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length)

        try:
            req = json.loads(body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json_response(400, {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}})
            return

        method = str(req.get("method", ""))
        req_id = req.get("id", 1)

        if method == "initialize":
            self._send_json_response(200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "cad-studio-mcp", "version": "1.0.0"},
                    "capabilities": {"tools": {"listChanged": False}}
                }
            })
        elif method == "tools/list":
            tools_list = [
                {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
                for t in MCPToolRegistry.get_tools()
            ]
            self._send_json_response(200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools_list}
            })
        elif method == "tools/call":
            params = req.get("params", {})
            t_name = str(params.get("name", ""))
            args = params.get("arguments", {})
            out_txt, is_err = self._dispatch_mcp_tool(t_name, args)
            self._send_json_response(200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": out_txt}],
                    "isError": is_err
                }
            })
        else:
            self._send_json_response(200, {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Méthode '{method}' non supportée"}
            })

    def _dispatch_mcp_tool(self, name: str, args: Dict[str, Union[str, float, int, bool]]) -> Tuple[str, bool]:
        """Exécute un outil MCP spécifique et retourne (texte_résultat, est_erreur)."""
        if self.bridge is None:
            return ("Passerelle non initialisée", True)

        doc = self.bridge.doc
        if name == "clear_scene":
            doc.bodies.clear()
            doc.features.clear()
            doc._notify_change()
            return ("Scène réinitialisée avec succès.", False)

        if name == "inspect_scene":
            return (self._mcp_inspect_scene(doc), False)

        if name == "validate_geometry":
            return self._mcp_validate(doc, str(args.get("body_id", "")))

        if name == "check_clashes":
            return self._mcp_check_clashes(doc)

        if name == "execute_cad_script":
            code = str(args.get("code", ""))
            res = CADScriptEngine.execute_script(doc, code)
            return (res.message, not res.success)

        return self._mcp_create_or_synthesize(name, args)

    def _mcp_inspect_scene(self, doc: CADDocument) -> str:
        """Inspecte les corps solides actifs dans la scène pour l'IA."""
        if not doc.bodies:
            return "La scène est vide (aucun corps solide)."
        lines: List[str] = [f"Scène '{doc.name}' ({len(doc.bodies)} corps) :"]
        for bid, b in doc.bodies.items():
            lines.append(f" - {bid} : Volume={b.volume():.1f} mm³, Genre={b.genus()}, Sommets={b.num_vertices()}")
        return "\n".join(lines)

    def _mcp_validate(self, doc: CADDocument, body_id: str) -> Tuple[str, bool]:
        """Valide un corps spécifique pour un outil MCP."""
        if body_id not in doc.bodies:
            return (f"Corps '{body_id}' introuvable.", True)
        rep = CADValidator.validate_solid(doc.bodies[body_id])
        txt = (
            f"Validation de '{body_id}' : {'VALIDE' if rep.is_valid else 'ANOMALIE'} | "
            f"Volume: {rep.volume_mm3:.1f} mm³, Euler χ={rep.euler_characteristic}, Score={rep.quality_score_percent:.0f}%."
        )
        return (txt, not rep.is_valid)

    def _mcp_check_clashes(self, doc: CADDocument) -> Tuple[str, bool]:
        """Vérifie les collisions entre pièces pour un outil MCP."""
        reports = CADValidator.check_scene_interferences(doc.bodies)
        if not reports:
            return ("Aucune collision détectée. Assemblage géométriquement sain.", False)
        return ("\n".join(r.description for r in reports), True)

    def _mcp_create_or_synthesize(self, name: str, args: Dict[str, Union[str, float, int, bool]]) -> Tuple[str, bool]:
        """Gère la création de primitives et la synthèse de formes pour les outils MCP."""
        if self.bridge is None:
            return ("Passerelle non initialisée", True)

        if name == "create_primitive":
            ptype = str(args.get("primitive_type", "box"))
            res = self.bridge.execute_natural_language_prompt(f"Crée un {ptype}")
            return (res.message, not res.success)

        if name == "synthesize_shape":
            stype = str(args.get("shape_type", "gear"))
            res = self.bridge.execute_natural_language_prompt(f"Crée un {stype}")
            return (res.message, not res.success)

        if name == "drill_hole":
            dia = float(args.get("diameter_mm", 10.0))
            depth = float(args.get("depth_mm", 20.0))
            res = self.bridge.execute_natural_language_prompt(f"Perce un trou de diamètre {dia} profondeur {depth}")
            return (res.message, not res.success)

        return (f"Outil MCP inconnu: {name}", True)

    def _send_json_response(self, code: int, data: JSONDict) -> None:
        """Envoie la réponse HTTP au format JSON."""
        encoded = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Tuple[str, ...]) -> None:
        """Désactive l'affichage verbeux des logs standard pour rester silencieux."""
        pass


class CADAIServer:
    """Serveur HTTP autonome orchestrant les requêtes d'agents IA vers CAD Studio."""

    def __init__(self, bridge: CADAIBridge, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.bridge: CADAIBridge = bridge
        self.host: str = host
        self.port: int = port
        self._server: Optional[http.server.HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Démarre le serveur dans un thread d'arrière-plan."""
        CADAIServerHandler.bridge = self.bridge
        self._server = http.server.HTTPServer((self.host, self.port), CADAIServerHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Arrête le serveur proprement."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
