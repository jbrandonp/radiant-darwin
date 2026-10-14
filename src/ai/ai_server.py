"""
Serveur API local et passerelle MCP pour le pilotage externe par IA (CAD-AI Server).
Fournit des points d'accès REST / JSON-RPC légers pour permettre à n'importe quel agent externe
(Claude, ChatGPT, Cursor, Ollama, Antigravity) de contrôler CAD Studio en temps réel.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
import http.server
import json
import threading
from typing import Dict, List, Optional, Tuple, Union

from src.core.document import CADDocument
from src.ai.cad_ai_bridge import CADAIBridge, CADAIExecutionResult

JSONPrimitive = Union[str, int, float, bool, None]
JSONDict = Dict[str, Union[JSONPrimitive, Dict[str, Optional[float]], List[Dict[str, float]]]]


class CADAIServerHandler(http.server.BaseHTTPRequestHandler):
    """Gestionnaire de requêtes HTTP REST pour les commandes de CAO par l'IA."""

    bridge: Optional[CADAIBridge] = None

    def do_GET(self) -> None:
        """Point d'accès de lecture d'état de la scène et des métriques."""
        if self.path == "/api/cad/status":
            self._handle_status_request()
        elif self.path == "/api/cad/health":
            self._send_json_response(200, {"status": "ok", "engine": "NEXUS-3D SOTA"})
        else:
            self._send_json_response(404, {"error": "Endpoint non trouvé"})

    def do_POST(self) -> None:
        """Point d'accès d'exécution d'instructions géométriques."""
        if self.path == "/api/cad/prompt":
            self._handle_prompt_execution()
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

    def _handle_prompt_execution(self) -> None:
        """Reçoit une consigne textuelle et l'exécute sur le modèle."""
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
                "dimensions_mm": dims_dict
            })
        except Exception as e:
            self._send_json_response(500, {"error": f"Erreur de traitement: {str(e)}"})

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
