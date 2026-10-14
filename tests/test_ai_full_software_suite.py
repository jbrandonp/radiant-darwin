"""
Suite de tests validant l'orchestration complète de toutes les fonctionnalités du logiciel par l'IA :
- FAO / CAM (G-Code & parcours d'outils)
- FEA / Simulation par éléments finis (von Mises & facteur de sécurité)
- TechDraw (Mise en plan 2D normalisée ISO)
- Tôlerie industrielle (Sheet Metal & Déplié flan)
- Physique des matériaux & calcul de masse précis
- Modélisation directe (Push-Pull, Congé, Coque)
- Intégration Code-as-CAD et protocole MCP STDIO
"""

from __future__ import annotations
import json
import pytest

from src.core.document import CADDocument
from src.core.geometry import make_box, make_cylinder
from src.ai.cad_ai_bridge import CADAIBridge, AICommandType
from src.ai.cad_ai_full_suite import CADFullSuiteOrchestrator
from src.ai.cad_script_engine import CADScriptEngine
from src.ai.mcp_stdio import MCPStdioServer
from src.ai.mcp_schema import MCPToolRegistry


# =========================================================================
# 1. Tests CADFullSuiteOrchestrator
# =========================================================================

def test_full_suite_cam_gcode() -> None:
    box = make_box(60.0, 40.0, 20.0, center=True)
    res = CADFullSuiteOrchestrator.run_cam(
        box,
        operation_type="contour",
        tool_diameter_mm=6.0,
        depth_mm=10.0,
        feedrate_mm_min=1000.0
    )
    assert res.total_passes >= 1
    assert res.total_cut_length_mm > 0.0
    assert res.gcode_lines_count > 5
    assert "G21" in res.gcode_preview or "G90" in res.gcode_preview


def test_full_suite_fea_simulation() -> None:
    box = make_box(40.0, 40.0, 40.0, center=True)
    res = CADFullSuiteOrchestrator.run_fea(
        box,
        applied_force_n=2500.0,
        material_name="Aluminium 6061-T6"
    )
    assert res.is_safe is True
    assert res.safety_factor > 1.0
    assert res.max_stress_mpa > 0.0
    assert "CONFORME" in res.status_verdict


def test_full_suite_techdraw_generation() -> None:
    box = make_box(50.0, 30.0, 20.0, center=True)
    res = CADFullSuiteOrchestrator.generate_techdraw(box, part_name="Test_Part")
    assert len(res.views_generated) == 4
    assert res.total_lines > 10
    assert res.dimensions_count > 0
    assert "A3" in res.sheet_format


def test_full_suite_sheet_metal() -> None:
    res = CADFullSuiteOrchestrator.design_sheet_metal(
        width_mm=100.0,
        length_mm=80.0,
        thickness_mm=2.0,
        flange_height_mm=20.0
    )
    assert res.bends_count == 2
    assert res.flat_pattern_width_mm == 100.0
    assert res.flat_pattern_length_mm > 80.0
    assert res.solid.volume() > 0.0


def test_full_suite_material_properties() -> None:
    box = make_box(100.0, 50.0, 20.0, center=True)
    props = CADFullSuiteOrchestrator.get_material_properties(box, "Acier Inox 316L")
    assert "Inoxydable" in props.material_name or "Inox" in props.material_name
    assert props.mass_g > 500.0
    assert props.density_g_cm3 >= 7.8



def test_full_suite_direct_modeling_push_pull_and_shell() -> None:
    box = make_box(40.0, 40.0, 30.0, center=True)
    v0 = box.volume()

    # Push-Pull
    pp_res = CADFullSuiteOrchestrator.direct_modeling_push_pull(box, offset_mm=10.0, axis="z")
    assert pp_res.volume_after_mm3 > v0

    # Shell
    sh_res = CADFullSuiteOrchestrator.direct_modeling_shell(box, wall_thickness_mm=2.0)
    assert sh_res.volume_after_mm3 < v0


# =========================================================================
# 2. Tests CADAIBridge (Intents Naturels en Langage Naturel)
# =========================================================================

def test_bridge_natural_language_cam() -> None:
    doc = CADDocument("Test CAM")
    doc.bodies["B1"] = make_box(50.0, 50.0, 20.0)
    bridge = CADAIBridge(doc)

    res = bridge.execute_prompt("Génère l'usinage et le G-code de contournage")
    assert res.success is True
    assert res.command_type == AICommandType.RUN_CAM
    assert "FAO réussie" in res.message


def test_bridge_natural_language_fea() -> None:
    doc = CADDocument("Test FEA")
    doc.bodies["B1"] = make_box(50.0, 50.0, 20.0)
    bridge = CADAIBridge(doc)

    res = bridge.execute_prompt("Simule la résistance mécanique sous charge de 3000N en Titane")
    assert res.success is True
    assert res.command_type == AICommandType.RUN_FEA
    assert "von Mises" in res.message


def test_bridge_natural_language_techdraw() -> None:
    doc = CADDocument("Test TechDraw")
    doc.bodies["B1"] = make_box(60.0, 40.0, 25.0)
    bridge = CADAIBridge(doc)

    res = bridge.execute_prompt("Fais la mise en plan 2D technique de la pièce")
    assert res.success is True
    assert res.command_type == AICommandType.GENERATE_TECHDRAW
    assert "Planche ISO A3" in res.message


def test_bridge_natural_language_sheet_metal() -> None:
    doc = CADDocument("Test SheetMetal")
    bridge = CADAIBridge(doc)

    res = bridge.execute_prompt("Conçois une tôle pliée 120x80 épaisseur 2mm avec deux rebords")
    assert res.success is True
    assert res.command_type == AICommandType.DESIGN_SHEET_METAL
    assert len(doc.bodies) == 1
    assert "Patron à plat" in res.message


def test_bridge_natural_language_materials() -> None:
    doc = CADDocument("Test Mat")
    doc.bodies["B1"] = make_box(50.0, 50.0, 20.0)
    bridge = CADAIBridge(doc)

    res = bridge.execute_prompt("Applique le matériau Inox 316L et calcule la masse")
    assert res.success is True
    assert res.command_type == AICommandType.ASSIGN_MATERIAL
    assert res.mass_steel_g > 0.0


def test_bridge_natural_language_direct_modeling() -> None:
    doc = CADDocument("Test Direct")
    doc.bodies["B1"] = make_box(50.0, 50.0, 20.0)
    bridge = CADAIBridge(doc)

    res = bridge.execute_prompt("Pousse la face supérieure de 10mm")
    assert res.success is True
    assert res.command_type == AICommandType.DIRECT_MODELING


# =========================================================================
# 3. Tests CADScriptEngine (Code-as-CAD Étendu)
# =========================================================================

def test_script_engine_extended_apis() -> None:
    doc = CADDocument("Test Script Extended")
    script = """
b = cad.box(40, 40, 20)
cad.commit(b, 'Piece_A')
cam_info = cad.cam('Piece_A', 'contour', 8.0)
fea_info = cad.fea('Piece_A', 1500.0)
mat_info = cad.material('Piece_A', 'Aluminium 6061-T6')
"""
    res = CADScriptEngine.execute_script(doc, script)
    assert res.success is True
    assert "Piece_A_1" in res.bodies_created


# =========================================================================
# 4. Tests MCPStdioServer (Outils Avancés MCP)
# =========================================================================

def test_mcp_stdio_advanced_tools_calls() -> None:
    server = MCPStdioServer()
    # Ajoute une boîte
    server.process_request({
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tools/call",
        "params": {"name": "create_primitive", "arguments": {"primitive_type": "box"}}
    })

    # 1. CAM
    cam_resp = server.process_request({
        "jsonrpc": "2.0",
        "id": "2",
        "method": "tools/call",
        "params": {
            "name": "cad_cam_toolpath_and_gcode",
            "arguments": {"depth_mm": "8.0"}
        }
    })
    assert cam_resp["result"]["isError"] is False
    assert "gcode_preview" in cam_resp["result"]["content"][0]["text"]

    # 2. FEA
    fea_resp = server.process_request({
        "jsonrpc": "2.0",
        "id": "3",
        "method": "tools/call",
        "params": {
            "name": "cad_fea_stress_simulation",
            "arguments": {"applied_force_n": "2000"}
        }
    })
    assert fea_resp["result"]["isError"] is False
    assert "max_stress_mpa" in fea_resp["result"]["content"][0]["text"]

    # 3. TechDraw
    td_resp = server.process_request({
        "jsonrpc": "2.0",
        "id": "4",
        "method": "tools/call",
        "params": {
            "name": "cad_generate_2d_techdraw",
            "arguments": {"part_name": "Support_Moteur"}
        }
    })
    assert td_resp["result"]["isError"] is False
    assert "views" in td_resp["result"]["content"][0]["text"]

    # 4. SheetMetal
    sm_resp = server.process_request({
        "jsonrpc": "2.0",
        "id": "5",
        "method": "tools/call",
        "params": {
            "name": "cad_design_sheetmetal",
            "arguments": {"width_mm": "100", "length_mm": "60"}
        }
    })
    assert sm_resp["result"]["isError"] is False
    assert "flat_width_mm" in sm_resp["result"]["content"][0]["text"]

    # 5. Material
    mat_resp = server.process_request({
        "jsonrpc": "2.0",
        "id": "6",
        "method": "tools/call",
        "params": {
            "name": "cad_get_physical_material_props",
            "arguments": {"material_name": "Acier Inox 316L"}
        }
    })
    assert mat_resp["result"]["isError"] is False
    assert "mass_g" in mat_resp["result"]["content"][0]["text"]
