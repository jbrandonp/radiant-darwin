"""
Tests unitaires et d'intégration approfondis pour l'écosystème IA de CAD Studio.
Valide le synthétiseur de formes, le validateur topologique fermé (Euler-Poincaré),
le moteur de script sécurisé Code-as-CAD, le serveur MCP JSON-RPC 2.0 et le widget copilote.
"""

from __future__ import annotations
import json
import urllib.request
import urllib.error
import pytest
from typing import Dict, List

from src.core.document import CADDocument
from src.core.geometry import Solid, make_box, make_cylinder, make_sphere
from src.core.types import Vector3D
from src.ai.shape_synthesizer import ShapeSynthesizer
from src.ai.cad_validator import CADValidator, ValidationReport, InterferenceReport
from src.ai.cad_script_engine import CADScriptEngine, ScriptExecutionResult
from src.ai.mcp_schema import MCPToolRegistry
from src.ai.cad_ai_bridge import CADAIBridge, CADAIExecutionResult, AICommandType
from src.ai.ai_server import CADAIServer


class TestShapeSynthesizer:
    """Valide la génération paramétrique de formes géométriques complexes industrielles."""

    def test_create_spur_gear(self) -> None:
        gear = ShapeSynthesizer.create_spur_gear(
            num_teeth=16,
            module=2.0,
            pressure_angle_deg=20.0,
            face_width=12.0,
            bore_diameter=12.0
        )
        assert gear is not None
        assert gear.volume() > 0.0
        assert 5000.0 < gear.volume() < 25000.0

    def test_create_pipe_flange(self) -> None:
        flange = ShapeSynthesizer.create_pipe_flange(
            outer_diameter=120.0,
            inner_diameter=40.0,
            flange_thickness=15.0,
            bolt_circle_diameter=90.0,
            num_holes=6,
            hole_diameter=12.0
        )
        assert flange is not None
        assert flange.volume() > 10000.0

    def test_create_heat_sink(self) -> None:
        sink = ShapeSynthesizer.create_heat_sink(
            base_width=60.0,
            base_length=60.0,
            base_thickness=4.0,
            fin_height=25.0,
            fin_thickness=1.5,
            num_fins=8
        )
        assert sink is not None
        assert sink.volume() > 0.0

    def test_create_electronics_enclosure(self) -> None:
        enclosure = ShapeSynthesizer.create_electronics_enclosure(
            width=100.0,
            length=70.0,
            height=35.0,
            wall_thickness=2.5
        )
        assert enclosure is not None
        assert 10000.0 < enclosure.volume() < 245000.0

    def test_create_reinforced_bracket(self) -> None:
        bracket = ShapeSynthesizer.create_reinforced_bracket(
            arm_length_1=50.0,
            arm_length_2=50.0,
            width=30.0,
            thickness=5.0
        )
        assert bracket is not None
        assert bracket.volume() > 2000.0

    def test_create_stepped_shaft(self) -> None:
        diameters = [20.0, 35.0, 25.0]
        lengths = [25.0, 50.0, 30.0]
        shaft = ShapeSynthesizer.create_stepped_shaft(diameters, lengths)
        assert shaft is not None
        assert shaft.volume() > 30000.0

    def test_create_pillow_block_bearing(self) -> None:
        pillow = ShapeSynthesizer.create_pillow_block_bearing(
            base_width=120.0,
            base_depth=35.0,
            bearing_bore=25.0,
            shaft_center_height=36.5
        )
        assert pillow is not None
        assert pillow.volume() > 20000.0

    def test_create_v_belt_pulley(self) -> None:
        pulley = ShapeSynthesizer.create_v_belt_pulley(
            outer_diameter=100.0,
            pulley_width=25.0,
            bore_diameter=15.0
        )
        assert pulley is not None
        assert pulley.volume() > 20000.0


class TestCADValidator:
    """Valide les contrôles d'intégrité topologique, volumique et de clashs."""

    def test_validate_watertight_box(self) -> None:
        box = make_box(40.0, 30.0, 20.0, center=True)
        rep = CADValidator.validate_solid(box)
        assert rep.is_valid is True
        assert rep.is_manifold is True
        assert rep.euler_characteristic == 2  # Genus 0 -> Chi = 2
        assert rep.genus == 0
        assert rep.volume_mm3 > 23000.0
        assert rep.quality_score_percent >= 90.0

    def test_validate_empty_solid(self) -> None:
        empty = Solid()
        rep = CADValidator.validate_solid(empty)
        assert rep.is_valid is False
        assert rep.volume_mm3 == 0.0
        assert rep.quality_score_percent == 0.0
        assert len(rep.warnings) > 0

    def test_scene_interference_detection(self) -> None:
        # Deux boîtes qui se chevauchent
        b1 = make_box(30.0, 30.0, 30.0, center=True)
        b2 = make_box(30.0, 30.0, 30.0, center=True).translate(10.0, 0.0, 0.0)
        # Une troisième boîte isolée sans collision
        b3 = make_box(20.0, 20.0, 20.0, center=True).translate(100.0, 0.0, 0.0)

        bodies = {"box1": b1, "box2": b2, "box3": b3}
        clashes = CADValidator.check_scene_interferences(bodies)

        assert len(clashes) == 1
        assert clashes[0].has_collision is True
        assert clashes[0].clash_volume_mm3 > 0.0
        assert ("box1" in clashes[0].description) and ("box2" in clashes[0].description)


class TestCADScriptEngine:
    """Valide le moteur sécurisé Code-as-CAD Python."""

    def test_execute_safe_script(self) -> None:
        doc = CADDocument("Script Test")
        code = """
p1 = cad.box(40.0, 40.0, 10.0)
c1 = cad.cylinder(8.0, 20.0)
part = p1.difference(c1)
cad.add(part, 'Plaque_Percee')
"""
        res = CADScriptEngine.execute_script(doc, code)
        assert res.success is True
        assert len(doc.bodies) == 1
        assert "Plaque_Percee_1" in doc.bodies
        assert len(res.bodies_created) == 1

    def test_security_rejection_banned_modules(self) -> None:
        doc = CADDocument("Security Test")
        bad_code = "import os\nos.system('dir')"
        res = CADScriptEngine.execute_script(doc, bad_code)
        assert res.success is False
        assert "interdit" in res.message

    def test_security_rejection_banned_calls(self) -> None:
        doc = CADDocument("Security Test")
        bad_code = "eval('1+1')"
        res = CADScriptEngine.execute_script(doc, bad_code)
        assert res.success is False
        assert "interdit" in res.message


class TestCADAIBridge:
    """Vérifie la compréhension en langage naturel et l'enrichissement diagnostique."""

    def test_parse_and_create_box(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        res = bridge.interpret_and_execute("Crée un cube de 40x30x20")
        assert res.success is True
        assert res.command_type == AICommandType.CREATE_PRIMITIVE
        assert len(doc.bodies) == 1
        assert res.is_manifold is True

    def test_parse_and_create_pillow_block(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        res = bridge.interpret_and_execute("Palier à semelle pour arbre Ø25")
        assert res.success is True
        assert res.command_type == AICommandType.CREATE_PILLOW_BLOCK
        assert len(doc.bodies) == 1

    def test_parse_and_create_pulley(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        res = bridge.interpret_and_execute("Poulie à gorge diamètre 100")
        assert res.success is True
        assert res.command_type == AICommandType.CREATE_PULLEY
        assert len(doc.bodies) == 1

    def test_clear_scene(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        bridge.interpret_and_execute("Crée un cube de 30x30x30")
        res = bridge.interpret_and_execute("Nettoie la scène")
        assert res.success is True
        assert len(doc.bodies) == 0


class TestCADAIServerMCP:
    """Vérifie les protocoles REST, diagnostic de clashs et JSON-RPC 2.0 MCP."""

    def test_server_mcp_and_extended_endpoints(self) -> None:
        doc = CADDocument("Test Server MCP Doc")
        bridge = CADAIBridge(doc)
        port = 8771
        server = CADAIServer(bridge, host="127.0.0.1", port=port)
        server.start()

        try:
            # 1. Test MCP initialize (JSON-RPC 2.0)
            url_mcp = f"http://127.0.0.1:{port}/mcp"
            init_payload = json.dumps({
                "jsonrpc": "2.0",
                "id": 10,
                "method": "initialize",
                "params": {}
            }).encode("utf-8")
            req_init = urllib.request.Request(url_mcp, data=init_payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req_init, timeout=3.0) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["result"]["serverInfo"]["name"] == "cad-studio-mcp"

            # 2. Test MCP tools/list
            tools_payload = json.dumps({
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/list",
                "params": {}
            }).encode("utf-8")
            req_tools = urllib.request.Request(url_mcp, data=tools_payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req_tools, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                tools = data["result"]["tools"]
                assert len(tools) >= 8

            # 3. Test MCP tools/call (create_primitive)
            call_payload = json.dumps({
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {
                    "name": "create_primitive",
                    "arguments": {"primitive_type": "box"}
                }
            }).encode("utf-8")
            req_call = urllib.request.Request(url_mcp, data=call_payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req_call, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert data["result"]["isError"] is False
                assert len(doc.bodies) == 1

            # 4. Test POST /api/cad/script (Code-as-CAD)
            url_script = f"http://127.0.0.1:{port}/api/cad/script"
            script_payload = json.dumps({
                "code": "s = cad.cylinder(12.0, 40.0)\ncad.add(s, 'Axe_Moteur')"
            }).encode("utf-8")
            req_script = urllib.request.Request(url_script, data=script_payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req_script, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert data["success"] is True
                assert len(doc.bodies) == 2

            # 5. Test GET /api/cad/clashes
            url_clashes = f"http://127.0.0.1:{port}/api/cad/clashes"
            req_clashes = urllib.request.Request(url_clashes, method="GET")
            with urllib.request.urlopen(req_clashes, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert "clashes_count" in data

        finally:
            server.stop()


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestAICopilotWidget:
    """Valide l'interface graphique du copilote IA (dock widget Qt)."""

    def test_widget_creation_and_quick_chip(self, qapp: QApplication) -> None:
        from src.ui.ai_copilot_dock import AICopilotWidget
        doc = CADDocument("Widget Test Doc")
        widget = AICopilotWidget(doc)

        results: List[CADAIExecutionResult] = []
        widget.geometry_generated.connect(lambda res: results.append(res))

        # Test onglet prompt
        widget.input_field.setText("Cube 30x30x10")
        widget.btn_send.click()

        assert len(results) == 1
        assert results[0].success is True
        assert len(doc.bodies) == 1

        # Test onglet script python
        widget.script_edit.setPlainText("part = cad.box(20.0, 20.0, 20.0)\ncad.add(part, 'PetitCube')")
        widget._on_run_python_script()
        assert len(doc.bodies) == 2

        # Test diagnostic
        widget._on_run_diagnostics()

        new_doc = CADDocument("New Replaced Doc")
        widget.set_document(new_doc)
        assert widget.doc is new_doc
