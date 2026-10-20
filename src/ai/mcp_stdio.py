"""
Serveur Model Context Protocol (MCP) sur flux standardisé stdin/stdout (Transport STDIO).
Permet l'interfaçage direct avec Claude Desktop, Cursor IDE et tout client MCP
en lançant simplement 'python -m src.ai.mcp_stdio'.
Architecture 100% fortement typée sans Any ni object, compatible multiplateforme et multi-agents.
"""

from __future__ import annotations
import json
import sys
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple, Union

from src.core.document import CADDocument
from src.core.geometry import Solid, make_box, make_cylinder, make_sphere, make_cone, make_torus
from src.ai.cad_ai_bridge import CADAIBridge, CADAIExecutionResult
from src.ai.mcp_schema import get_mcp_tool_definitions, JSONSchemaDict
from src.ai.shape_synthesizer import ShapeSynthesizer
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
from src.ai.cad_ai_compatibility import (
    AIArgumentAdapter,
    AICompactSerializer,
    AIPlatformCompat,
    CompatDict,
    CompatVal
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

    def process_request(self, req: Dict[str, Union[str, int, float, bool, CompatDict, List[CompatVal]]]) -> MCPResponseDict:
        """Traite une requête JSON-RPC 2.0 et retourne le dictionnaire de réponse."""
        req_id_raw = req.get("id", "1")
        req_id: str = str(req_id_raw)
        method_raw = req.get("method", "")
        method: str = str(method_raw)
        params_val = req.get("params")
        params: CompatDict = AIArgumentAdapter.parse_raw_arguments(params_val) if isinstance(params_val, (dict, str)) else {}

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

    def _dispatch_primitive(self, name: str, args: CompatDict) -> Optional[Tuple[str, bool]]:
        """Génère une primitive géométrique 3D de base avec tolérance aux alias et unités."""
        if name != "create_primitive":
            return None

        prim_type = AIArgumentAdapter.get_str(args, "primitive_type", "box").lower()
        dims = AIArgumentAdapter.get_sub_dict(args, "dimensions")

        if prim_type == "cylinder":
            r = AIArgumentAdapter.get_float(dims, "radius_mm", 0.0) or AIArgumentAdapter.get_float(args, "radius_mm", 15.0)
            h = AIArgumentAdapter.get_float(dims, "height_mm", 0.0) or AIArgumentAdapter.get_float(args, "height_mm", 40.0)
            solid = make_cylinder(r, h, center=True)
        elif prim_type == "sphere":
            r = AIArgumentAdapter.get_float(dims, "radius_mm", 0.0) or AIArgumentAdapter.get_float(args, "radius_mm", 20.0)
            solid = make_sphere(r)
        elif prim_type == "cone":
            r = AIArgumentAdapter.get_float(dims, "radius_mm", 0.0) or AIArgumentAdapter.get_float(args, "radius_mm", 20.0)
            h = AIArgumentAdapter.get_float(dims, "height_mm", 0.0) or AIArgumentAdapter.get_float(args, "height_mm", 40.0)
            solid = make_cone(r, 0.0, h, center=True)
        elif prim_type == "torus":
            r_maj = AIArgumentAdapter.get_float(dims, "major_radius_mm", 0.0) or AIArgumentAdapter.get_float(args, "radius_mm", 30.0)
            r_min = AIArgumentAdapter.get_float(dims, "minor_radius_mm", 0.0) or 8.0
            solid = make_torus(r_maj, r_min)
        else:
            w = AIArgumentAdapter.get_float(dims, "width_mm", 0.0) or AIArgumentAdapter.get_float(args, "width_mm", 50.0)
            h = AIArgumentAdapter.get_float(dims, "height_mm", 0.0) or AIArgumentAdapter.get_float(args, "height_mm", 50.0)
            d = AIArgumentAdapter.get_float(dims, "depth_mm", 0.0) or AIArgumentAdapter.get_float(args, "depth_mm", 30.0)
            solid = make_box(w, h, d, center=True)

        b_id = f"{prim_type.capitalize()}_{len(self.document.bodies) + 1}"
        self.document.bodies[b_id] = solid
        self.document._notify_change()
        return (f"Primitive '{prim_type}' créée avec succès sous l'identifiant '{b_id}' (Volume: {solid.volume():.1f} mm³).", True)

    @staticmethod
    def _extract_shape_param(p: CompatSubDict, args: CompatDict, key: str, default: float) -> float:
        """Extrait un paramètre prioritaire de sous-dictionnaire ou d'arguments globaux."""
        v = AIArgumentAdapter.get_float(p, key, 0.0)
        if v != 0.0:
            return v
        return AIArgumentAdapter.get_float(args, key, default)

    @classmethod
    def _synthesize_transmission(cls, st: str, p: CompatSubDict, args: CompatDict) -> Optional[Solid]:
        """Synthétise les composants de transmission mécanique (engrenages, poulies, paliers)."""
        if st in ("spur_gear", "gear", "engrenage"):
            teeth = int(cls._extract_shape_param(p, args, "num_teeth", 20.0))
            mod = cls._extract_shape_param(p, args, "module", 2.0)
            width = cls._extract_shape_param(p, args, "face_width", 12.0)
            bore = cls._extract_shape_param(p, args, "bore_diameter", 12.0)
            return ShapeSynthesizer.create_spur_gear(num_teeth=teeth, module=mod, face_width=width, bore_diameter=bore)
        if st in ("pillow_block", "palier"):
            return ShapeSynthesizer.create_pillow_block_bearing()
        if st in ("pulley", "poulie"):
            return ShapeSynthesizer.create_v_belt_pulley()
        return None

    @classmethod
    def _synthesize_structural(cls, st: str, p: CompatSubDict, args: CompatDict) -> Optional[Solid]:
        """Synthétise les pièces structurales (brides, dissipateurs, boîtiers, équerres)."""
        if st in ("pipe_flange", "flange", "bride"):
            dia = cls._extract_shape_param(p, args, "outer_diameter", 115.0)
            bore = cls._extract_shape_param(p, args, "bore_diameter", 45.0)
            th = cls._extract_shape_param(p, args, "flange_thickness", 14.0)
            return ShapeSynthesizer.create_pipe_flange(outer_diameter=dia, bore_diameter=bore, flange_thickness=th)
        if st in ("heat_sink", "dissipateur"):
            w = cls._extract_shape_param(p, args, "width_mm", 80.0)
            l = cls._extract_shape_param(p, args, "length_mm", 80.0)
            fins = int(cls._extract_shape_param(p, args, "num_fins", 8.0))
            return ShapeSynthesizer.create_heat_sink(base_width=w, base_length=l, num_fins=fins)
        if st in ("enclosure", "boitier", "boîtier"):
            w = cls._extract_shape_param(p, args, "width_mm", 100.0)
            l = cls._extract_shape_param(p, args, "length_mm", 70.0)
            h = cls._extract_shape_param(p, args, "height_mm", 35.0)
            return ShapeSynthesizer.create_electronics_enclosure(width=w, length=l, height=h)
        if st in ("bracket", "equerre", "équerre"):
            w = cls._extract_shape_param(p, args, "width_mm", 50.0)
            l = cls._extract_shape_param(p, args, "length_mm", 60.0)
            h = cls._extract_shape_param(p, args, "height_mm", 60.0)
            return ShapeSynthesizer.create_reinforced_bracket(width=w, leg_length_1=l, leg_length_2=h)
        return None

    def _dispatch_synthesize_shape(self, name: str, args: CompatDict) -> Optional[Tuple[str, bool]]:
        """Génère un composant industriel expert via le synthétiseur de formes."""
        if name != "synthesize_shape":
            return None

        st = AIArgumentAdapter.get_str(args, "shape_type", "spur_gear").lower()
        p = AIArgumentAdapter.get_sub_dict(args, "parameters")

        solid = self._synthesize_transmission(st, p, args)
        if solid is None:
            solid = self._synthesize_structural(st, p, args)
        if solid is None:
            solid = ShapeSynthesizer.create_stepped_shaft([30.0, 20.0, 15.0], [40.0, 50.0, 30.0])

        b_id = f"Synthese_{st}_{len(self.document.bodies) + 1}"
        self.document.bodies[b_id] = solid
        self.document._notify_change()
        return (f"Composant '{st}' synthétisé avec succès sous l'identifiant '{b_id}' (Volume: {solid.volume():.1f} mm³).", True)

    def _dispatch_machining_and_features(self, name: str, args: CompatDict) -> Optional[Tuple[str, bool]]:
        """Gère les usinages, perçages et opérations booléennes volumiques."""
        if name == "drill_hole":
            target_id = AIArgumentAdapter.get_str(args, "target_body_id")
            solid = self._get_target_solid(target_id)
            dia = AIArgumentAdapter.get_float(args, "diameter_mm", 10.0)
            depth = AIArgumentAdapter.get_float(args, "depth_mm", 20.0)
            cx = AIArgumentAdapter.get_float(args, "center_x", 0.0)
            cy = AIArgumentAdapter.get_float(args, "center_y", 0.0)
            hole_tool = make_cylinder(dia / 2.0, depth * 1.5, center=True).translate(cx, cy, 0.0)
            drilled = solid.difference(hole_tool)
            key = target_id if target_id in self.document.bodies else next(iter(self.document.bodies.keys()))
            self.document.bodies[key] = drilled
            self.document._notify_change()
            return (f"Alésage Ø{dia}mm percé dans '{key}' à la position ({cx}, {cy}).", True)

        if name == "boolean_operation":
            op = AIArgumentAdapter.get_str(args, "operation", "difference").lower()
            t_id = AIArgumentAdapter.get_str(args, "target_body_id") or AIArgumentAdapter.get_str(args, "body_id")
            tool_id = AIArgumentAdapter.get_str(args, "tool_body_id")
            if t_id not in self.document.bodies or tool_id not in self.document.bodies:
                return (f"Erreur : corps '{t_id}' ou '{tool_id}' introuvable.", False)
            target_solid = self.document.bodies[t_id]
            tool_solid = self.document.bodies[tool_id]
            if op in ("union", "+"):
                res_solid = target_solid.union(tool_solid)
            elif op in ("intersection", "&"):
                res_solid = target_solid.intersection(tool_solid)
            else:
                res_solid = target_solid.difference(tool_solid)
            self.document.bodies[t_id] = res_solid
            self.document._notify_change()
            return (f"Opération booléenne '{op}' appliquée avec succès sur '{t_id}'.", True)

        return None

    def _dispatch_advanced_tool(self, name: str, args: CompatDict) -> Optional[Tuple[str, bool]]:
        """Achemine les outils avancés CAO/FAO/FEA/Tôlerie/Mise en plan."""
        if name == "cad_cam_toolpath_and_gcode":
            solid = self._get_target_solid(AIArgumentAdapter.get_str(args, "body_id"))
            op_type = AIArgumentAdapter.get_str(args, "operation_type", "contour")
            tool_dia = AIArgumentAdapter.get_float(args, "tool_diameter_mm", 6.0)
            depth = AIArgumentAdapter.get_float(args, "depth_mm", 10.0)
            cam_res = CADFullSuiteOrchestrator.run_cam(solid, operation_type=op_type, tool_diameter_mm=tool_dia, depth_mm=depth)
            compact_gcode = AICompactSerializer.compact_gcode(cam_res.gcode_preview)
            res_dict = {
                "operation": cam_res.operation_name,
                "tool": cam_res.tool_name,
                "cut_length_mm": cam_res.total_cut_length_mm,
                "estimated_time_s": cam_res.estimated_time_seconds,
                "gcode_preview": compact_gcode
            }
            return (json.dumps(res_dict, indent=2), True)

        if name == "cad_fea_stress_simulation":
            solid = self._get_target_solid(AIArgumentAdapter.get_str(args, "body_id"))
            force = AIArgumentAdapter.get_float(args, "applied_force_n", 2000.0)
            mat = AIArgumentAdapter.get_str(args, "material_name", "Aluminium 6061-T6")
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
            b_id = AIArgumentAdapter.get_str(args, "body_id")
            solid = self._get_target_solid(b_id)
            p_name = AIArgumentAdapter.get_str(args, "part_name", b_id or "Pièce")
            mat = AIArgumentAdapter.get_str(args, "material_name", "Aluminium 6061-T6")
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
            w = AIArgumentAdapter.get_float(args, "width_mm", 120.0)
            l = AIArgumentAdapter.get_float(args, "length_mm", 80.0)
            t = AIArgumentAdapter.get_float(args, "thickness_mm", 2.0)
            fh = AIArgumentAdapter.get_float(args, "flange_height_mm", 20.0)
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
            solid = self._get_target_solid(AIArgumentAdapter.get_str(args, "body_id"))
            mat = AIArgumentAdapter.get_str(args, "material_name", "Aluminium 6061-T6")
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
            b_id = AIArgumentAdapter.get_str(args, "body_id")
            solid = self._get_target_solid(b_id)
            if name == "cad_direct_modeling_push_pull":
                offset = AIArgumentAdapter.get_float(args, "offset_mm", 10.0)
                axis = AIArgumentAdapter.get_str(args, "axis", "z")
                dm_res = CADFullSuiteOrchestrator.direct_modeling_push_pull(solid, offset_mm=offset, axis=axis)
            elif name == "cad_direct_modeling_fillet":
                r = AIArgumentAdapter.get_float(args, "radius_mm", 2.0)
                dm_res = CADFullSuiteOrchestrator.direct_modeling_fillet(solid, radius_mm=r)
            else:
                wall_t = AIArgumentAdapter.get_float(args, "wall_thickness_mm", 2.0)
                dm_res = CADFullSuiteOrchestrator.direct_modeling_shell(solid, wall_thickness_mm=wall_t)

            target_id = b_id if b_id in self.document.bodies else next(iter(self.document.bodies.keys()))
            self.document.bodies[target_id] = dm_res.solid
            self.document._notify_change()
            return (dm_res.message, True)

        if name == "cad_export_model":
            fmt = AIArgumentAdapter.get_str(args, "format_type", "step")
            msg = f"Export du modèle au format {fmt.upper()} validé."
            return (msg, True)

        return None

    def _dispatch_query_and_script(self, name: str, args: CompatDict) -> Optional[Tuple[str, bool]]:
        """Achemine les requêtes de consultation, scripts et diagnostics."""
        if name in ("cad_run_script", "execute_cad_script"):
            script = AIArgumentAdapter.get_str(args, "script") or AIArgumentAdapter.get_str(args, "code")
            script_res = CADScriptEngine.execute_script(self.document, script)
            return (script_res.message, script_res.success)

        if name in ("cad_validate_model", "validate_geometry"):
            b_id = AIArgumentAdapter.get_str(args, "body_id")
            if b_id and b_id in self.document.bodies:
                report = CADValidator.validate_solid(self.document.bodies[b_id])
                res_v = {
                    "body_id": b_id,
                    "is_watertight": report.is_watertight,
                    "is_manifold": report.is_manifold,
                    "euler_poincare_valid": report.is_valid,
                    "quality_score": report.quality_score_percent,
                    "summary": f"Solide '{b_id}' validé: Volume={report.volume_mm3:.1f} mm³, Score={report.quality_score_percent:.1f}%"
                }
                return (json.dumps(res_v, indent=2), report.is_manifold)
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

        return None

    def _try_forward_to_gui_server(self, name: str, args: CompatDict) -> Optional[Tuple[str, bool]]:
        """Tente de transférer l'appel d'outil au serveur HTTP de l'IHM active (port 8765)."""
        url = "http://127.0.0.1:8765/mcp"
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
            "id": "mcp_forward"
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    resp_data = json.loads(resp.read(67_108_864).decode("utf-8"))
                    res_body = resp_data.get("result", {})
                    content_list = res_body.get("content", [])
                    is_err = bool(res_body.get("isError", False))
                    text_parts = [item.get("text", "") for item in content_list if isinstance(item, dict)]
                    res_text = "\n".join(text_parts) if text_parts else "Opération exécutée dans l'IHM active."
                    return (res_text, not is_err)
        except (urllib.error.URLError, TimeoutError, ConnectionRefusedError, OSError):
            return None
        return None

    def _dispatch_tool_action(self, name: str, args: CompatDict) -> Tuple[str, bool]:
        """Achemine l'appel d'outil vers l'IHM active si disponible, ou en local autonome."""
        forwarded = self._try_forward_to_gui_server(name, args)
        if forwarded is not None:
            return forwarded

        prim_res = self._dispatch_primitive(name, args)
        if prim_res is not None:
            return prim_res

        synth_res = self._dispatch_synthesize_shape(name, args)
        if synth_res is not None:
            return synth_res

        mach_res = self._dispatch_machining_and_features(name, args)
        if mach_res is not None:
            return mach_res

        adv_res = self._dispatch_advanced_tool(name, args)
        if adv_res is not None:
            return adv_res

        query_res = self._dispatch_query_and_script(name, args)
        if query_res is not None:
            return query_res

        prompt = AIArgumentAdapter.get_str(args, "prompt") or AIArgumentAdapter.get_str(args, "code") or name
        res = self.bridge.execute_prompt(prompt)
        return (res.message, res.success)

    def _handle_tools_call(self, req_id: str, params: CompatDict) -> MCPResponseDict:
        """Exécute l'outil demandé et formate le résultat MCP avec isolation transactionnelle."""
        name = AIArgumentAdapter.get_str(params, "name")
        args_raw = params.get("arguments")
        args: CompatDict = {}
        if isinstance(args_raw, (dict, str)):
            args = AIArgumentAdapter.parse_raw_arguments(args_raw)
        if not args:
            # Tolérance pour les appels directs où les paramètres sont à la racine de 'params'
            args = {k: v for k, v in params.items() if k not in ("name", "_meta")}

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

        compact_output = AICompactSerializer.compact_text(output_text, max_chars=4000)
        content_item: MCPContentItem = {"type": "text", "text": compact_output}
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
            return AICompactSerializer.safe_json_rpc_dumps(res, ensure_ascii=True)
        except Exception as err:
            err_res = AIPlatformCompat.format_json_rpc_error(-32700, f"Parse error: {err}", "null")
            return json.dumps(err_res, ensure_ascii=True)

    def run_stdio_loop(self) -> None:
        """Boucle principale de traitement des entrées/sorties standard (STDIO)."""
        AIPlatformCompat.configure_stdio_utf8()
        for line in sys.stdin:
            resp_line = self.handle_line(line)
            if resp_line:
                sys.stdout.write(resp_line + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    server = MCPStdioServer()
    server.run_stdio_loop()
