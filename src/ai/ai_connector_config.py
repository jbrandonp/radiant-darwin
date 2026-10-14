"""
Générateur de configurations et manifestes de connexion automatique pour les assistants IA.
Permet d'interfacer CAD Studio en 1 clic avec Claude Desktop, Cursor, Antigravity,
Windsurf, Roo Code et tout agent respectant le protocole MCP (Model Context Protocol).
Architecture 100% fortement typée sans Any ni object.
"""

from __future__ import annotations
import json
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class AIClientConfigSnippet:
    """Snippet de configuration prêt à l'emploi pour un client IA spécifique."""
    client_name: str
    target_filepath: str
    config_json: str
    instructions: str


class AIConnectorConfigGenerator:
    """Génère les configurations d'interfaçage pour tous les clients IA du marché."""

    def __init__(self, project_root: Optional[str] = None, python_executable: Optional[str] = None) -> None:
        self.project_root: str = project_root if project_root is not None else os.path.abspath(os.getcwd())
        self.python_exe: str = python_executable if python_executable is not None else sys.executable

    def generate_claude_desktop_config(self) -> AIClientConfigSnippet:
        """Génère la configuration officielle pour Claude Desktop (MCP STDIO)."""
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        target_path = os.path.join(appdata, "Claude", "claude_desktop_config.json")

        cfg = {
            "mcpServers": {
                "cad-studio": {
                    "command": self.python_exe.replace("\\", "/"),
                    "args": ["-m", "src.ai.mcp_stdio"],
                    "cwd": self.project_root.replace("\\", "/")
                }
            }
        }
        json_str = json.dumps(cfg, indent=2)
        instructions = (
            f"Collez ce bloc dans votre fichier '{target_path}'.\n"
            "Redémarrez Claude Desktop : CAD Studio apparaîtra avec une icône de prise électrique "
            "et 9 outils de conception mécanique 3D disponibles !"
        )
        return AIClientConfigSnippet("Claude Desktop", target_path, json_str, instructions)

    def generate_cursor_config(self) -> AIClientConfigSnippet:
        """Génère la configuration MCP pour l'éditeur Cursor (.cursor/mcp.json)."""
        target_path = os.path.join(self.project_root, ".cursor", "mcp.json")
        cfg = {
            "mcpServers": {
                "cad-studio": {
                    "command": self.python_exe.replace("\\", "/"),
                    "args": ["-m", "src.ai.mcp_stdio"],
                    "cwd": self.project_root.replace("\\", "/")
                }
            }
        }
        json_str = json.dumps(cfg, indent=2)
        instructions = f"Fichier généré dans '{target_path}'. Cursor reconnaîtra les outils CAO automatiquement."
        return AIClientConfigSnippet("Cursor IDE", target_path, json_str, instructions)

    def generate_antigravity_config(self) -> AIClientConfigSnippet:
        """Génère la configuration pour Google Antigravity / Gemini CLI."""
        home = os.path.expanduser("~")
        target_path = os.path.join(home, ".gemini", "antigravity", "mcp", "cad-studio.json")
        cfg = {
            "server_name": "cad-studio",
            "transport": "stdio",
            "command": self.python_exe.replace("\\", "/"),
            "args": ["-m", "src.ai.mcp_stdio"],
            "cwd": self.project_root.replace("\\", "/")
        }
        json_str = json.dumps(cfg, indent=2)
        instructions = f"Sauvegardez dans '{target_path}' pour intégration native dans Antigravity."
        return AIClientConfigSnippet("Antigravity / Gemini", target_path, json_str, instructions)

    def generate_http_curl_snippet(self, host: str = "127.0.0.1", port: int = 8765) -> str:
        """Produit un exemple de commande cURL pour tester la connexion JSON-RPC MCP."""
        url = f"http://{host}:{port}/mcp"
        payload = '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'
        return f"curl -X POST {url} -H \"Content-Type: application/json\" -d '{payload}'"

    def install_to_claude_desktop(self) -> Tuple[bool, str]:
        """Installe automatiquement la configuration dans Claude Desktop en fusionnant avec l'existant."""
        snippet = self.generate_claude_desktop_config()
        path = snippet.target_filepath

        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            existing_data: Dict[str, Dict[str, Dict[str, List[str]]]] = {}

            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    try:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            existing_data = loaded
                    except json.JSONDecodeError:
                        existing_data = {}

            if "mcpServers" not in existing_data or not isinstance(existing_data["mcpServers"], dict):
                existing_data["mcpServers"] = {}

            existing_data["mcpServers"]["cad-studio"] = {
                "command": self.python_exe.replace("\\", "/"),
                "args": ["-m", "src.ai.mcp_stdio"],
                "cwd": self.project_root.replace("\\", "/")
            }

            with open(path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2)

            return True, f"Configuration installée avec succès dans '{path}'."
        except Exception as err:
            return False, f"Erreur lors de l'installation dans Claude Desktop : {err}"
