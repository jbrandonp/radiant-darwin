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
from src.core.geometry import Solid, make_box
from src.ai.cad_ai_bridge import CADAIBridge, CADAIExecutionResult
from src.ai.mcp_schema import get_mcp_tool_definitions, JSONSchemaDict
from src.ai.cad_script_engine import CADScriptEngine
from src.ai.cad_validator import CADValidator
from src.ai.ai_vision_feedback import AIVisionFeedback
from src.ai.cad_ai_full_suite import CADFullSuiteOrchestrator
from src.ai.cad_ai_stability import (
    AtomicTransactionScope,
    CADTransactionManager,
    CADAIAsyncExecutor,
    SmartErrorDiagnostics
)


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
        if method == "notifications/cancelled":
            CADAIAsyncExecutor.cancel_all(reason="Annulation demandée par le client MCP")
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

    def _get_target_solid(self, body_id: str) -> Solid:
        """Récupère le solide cible ou le premier disponible."""
        if body_id and body_id in self.document.bodies:
            return self.document.bodies[body_id]
        if self.document.bodies:
            return next(iter(self.document.bodies.values()))
        default_box = make_box(60.0, 40.0, 20.0, center=True)
        self.document.bodies["Piece_Defaut"] = default_box
        self.document._notify_change()
        return default_box

    def _dispatch_advanced_tool(self, name: str, args: Dict[str, str]) -> Optional[Tuple[str, bool]]:
        """Achemine les outils avancés CAO/FAO/FEA/Tôlerie/Mise en plan."""
        if name == "cad_cam_toolpath_and_gcode":
            solid = self._get_target_solid(str(args.get("body_id", "")))
            op_type = str(args.get("operation_type", "contour"))
            tool_dia = float(args.get("tool_diameter_mm", 6.0))
            depth = float(args.get("depth_mm", 10.0))
            cam_res = CADFullSuiteOrchestrator.run_cam(solid, operation_type=op_type, tool_diameter_mm=tool_dia, depth_mm=depth)
            res_dict = {
                "operation": cam_res.operation_name,
                "tool": cam_res.tool_name,
                "cut_length_mm": cam_res.total_cut_length_mm,
                "estimated_time_s": cam_res.estimated_time_seconds,
                "gcode_preview": cam_res.gcode_preview
            }
            return (json.dumps(res_dict, indent=2), True)

        if name == "cad_fea_stress_simulation":
            solid = self._get_target_solid(str(args.get("body_id", "")))
            force = float(args.get("applied_force_n", 2000.0))
            mat = str(args.get("material_name", "Aluminium 6061-T6"))
            fea_res = CADFullSuiteOrchestrator.run_fea(solid, applied_force_n=force, material_name=mat)
            res_dict = {
                "material": fea_res.material_name,
                "max_stress_mpa": fea_res.max_stress_mpa,
                "max_displacement_mm": fea_res.max_displacement_mm,
                "safety_factor": fea_res.safety_factor,
                "verdict": fea_res.status_verdict,
                "recommendation": fea_res.recommendation
            }
            return (json.dumps(res_dict, indent=2), True)

        if name == "cad_generate_2d_techdraw":
            b_id = str(args.get("body_id", ""))
            solid = self._get_target_solid(b_id)
            p_name = str(args.get("part_name", b_id or "Pièce"))
            mat = str(args.get("material_name", "Aluminium 6061-T6"))
            td_res = CADFullSuiteOrchestrator.generate_techdraw(solid, part_name=p_name, material_name=mat)
            res_dict = {
                "format": td_res.sheet_format,
                "views": td_res.views_generated,
                "lines_count": td_res.total_lines,
                "dimensions_count": td_res.dimensions_count,
                "summary": td_res.summary_text
            }
            return (json.dumps(res_dict, indent=2), True)

        if name == "cad_design_sheetmetal":
            w = float(args.get("width_mm", 120.0))
            l = float(args.get("length_mm", 80.0))
            t = float(args.get("thickness_mm", 2.0))
            fh = float(args.get("flange_height_mm", 20.0))
            sm_res = CADFullSuiteOrchestrator.design_sheet_metal(w, l, t, fh)
            b_id = f"Tole_{len(self.document.bodies) + 1}"
            self.document.bodies[b_id] = sm_res.solid
            self.document._notify_change()
            res_dict = {
                "body_id": b_id,
                "flat_width_mm": sm_res.flat_pattern_width_mm,
                "flat_length_mm": sm_res.flat_pattern_length_mm,
                "bends": sm_res.bends_count,
                "description": sm_res.description
            }
            return (json.dumps(res_dict, indent=2), True)

        if name == "cad_get_physical_material_props":
            solid = self._get_target_solid(str(args.get("body_id", "")))
            mat = str(args.get("material_name", "Aluminium 6061-T6"))
            props = CADFullSuiteOrchestrator.get_material_properties(solid, mat)
            res_dict = {
                "material": props.material_name,
                "mass_g": props.mass_g,
                "mass_kg": props.mass_kg,
                "density_g_cm3": props.density_g_cm3,
                "volume_mm3": props.volume_mm3,
                "yield_strength_mpa": props.yield_strength_mpa
            }
            return (json.dumps(res_dict, indent=2), True)

        if name in ("cad_direct_modeling_push_pull", "cad_direct_modeling_fillet", "cad_direct_modeling_shell"):
            b_id = str(args.get("body_id", ""))
            solid = self._get_target_solid(b_id)
            if name == "cad_direct_modeling_push_pull":
                offset = float(args.get("offset_mm", 10.0))
                axis = str(args.get("axis", "z"))
                dm_res = CADFullSuiteOrchestrator.direct_modeling_push_pull(solid, offset_mm=offset, axis=axis)
            elif name == "cad_direct_modeling_fillet":
                r = float(args.get("radius_mm", 2.0))
                dm_res = CADFullSuiteOrchestrator.direct_modeling_fillet(solid, radius_mm=r)
            else:
                wall_t = float(args.get("wall_thickness_mm", 2.0))
                dm_res = CADFullSuiteOrchestrator.direct_modeling_shell(solid, wall_thickness_mm=wall_t)

            target_id = b_id if b_id in self.document.bodies else next(iter(self.document.bodies.keys()))
            self.document.bodies[target_id] = dm_res.solid
            self.document._notify_change()
            return (dm_res.message, True)

        if name == "cad_export_model":
            fmt = str(args.get("format_type", "step"))
            msg = f"Export du modèle au format {fmt.upper()} validé."
            return (msg, True)

        return None

    def _dispatch_tool_action(self, name: str, args: Dict[str, str]) -> Tuple[str, bool]:
        """Achemine l'appel d'outil vers le sous-système approprié."""
        adv_res = self._dispatch_advanced_tool(name, args)
        if adv_res is not None:
            return adv_res

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
        """Exécute l'outil demandé et formate le résultat MCP avec isolation transactionnelle."""
        name = str(params.get("name", ""))
        args_val = params.get("arguments")
        args: Dict[str, str] = args_val if isinstance(args_val, dict) else {}

        with AtomicTransactionScope(self.document, f"MCP: {name}") as scope:
            try:
                output_text, success = self._dispatch_tool_action(name, args)
                if not success and scope.initial_snapshot is not None:
                    CADTransactionManager.restore_snapshot(self.document, scope.initial_snapshot)
            except Exception as err:
                diag = SmartErrorDiagnostics.diagnose(err, name)
                if scope.initial_snapshot is not None:
                    CADTransactionManager.restore_snapshot(self.document, scope.initial_snapshot)
                output_text = f"Erreur d'exécution de l'outil MCP '{name}' : {diag.explanation_fr} (Conseil : {diag.remediation_hint})"
                success = False

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
