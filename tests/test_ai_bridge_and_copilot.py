"""
Tests unitaires et d'intégration pour le pont d'IA CAO, le synthétiseur de formes
et le serveur autonome REST / JSON-RPC / MCP.
Vérifie la robustesse géométrique, la conformité Manifold et la réactivité en langage naturel.
"""

from __future__ import annotations
import json
import urllib.request
import urllib.error
import pytest
from typing import Dict, List

from src.core.document import CADDocument
from src.core.types import Vector3D
from src.ai.shape_synthesizer import ShapeSynthesizer
from src.ai.cad_ai_bridge import CADAIBridge, CADAIExecutionResult, AICommandType
from src.ai.ai_server import CADAIServer


class TestShapeSynthesizer:
    """Valide la génération paramétrique de formes géométriques complexes industrielles."""

    def test_create_spur_gear(self) -> None:
        """Vérifie la génération d'un engrenage droit à développante avec alésage."""
        gear = ShapeSynthesizer.create_spur_gear(
            num_teeth=16,
            module=2.0,
            pressure_angle_deg=20.0,
            face_width=12.0,
            bore_diameter=12.0
        )
        assert gear is not None
        assert gear.volume() > 0.0
        # Volume théorique approximatif d'un cylindre équivalent : pi * 16^2 * 12 = ~9600 mm3
        assert 5000.0 < gear.volume() < 25000.0
        min_b, max_b = gear.bounding_box()
        assert min_b.z >= 0.0
        assert max_b.z <= 12.01

    def test_create_pipe_flange(self) -> None:
        """Vérifie la génération d'une bride de tuyauterie avec cercle de perçage."""
        flange = ShapeSynthesizer.create_pipe_flange(
            outer_diameter=120.0,
            inner_diameter=40.0,
            flange_thickness=15.0,
            bolt_circle_diameter=90.0,
            num_holes=6,
            hole_diameter=12.0
        )
        assert flange is not None
        vol = flange.volume()
        assert vol > 10000.0
        min_b, max_b = flange.bounding_box()
        assert min_b.x < -45.0
        assert max_b.x > 45.0
        assert max_b.z >= 14.9

    def test_create_heat_sink(self) -> None:
        """Vérifie la génération d'un dissipateur thermique avec semelle et ailettes."""
        sink = ShapeSynthesizer.create_heat_sink(
            base_width=60.0,
            base_length=60.0,
            base_thickness=4.0,
            fin_height=25.0,
            fin_thickness=1.5,
            num_fins=8
        )
        assert sink is not None
        vol = sink.volume()
        assert vol > 0.0
        min_b, max_b = sink.bounding_box()
        assert max_b.z >= 28.0  # base 4 + ailettes 25

    def test_create_electronics_enclosure(self) -> None:
        """Vérifie la génération d'un boîtier électronique évidé avec bossages de fixation."""
        enclosure = ShapeSynthesizer.create_electronics_enclosure(
            width=100.0,
            length=70.0,
            height=35.0,
            wall_thickness=2.5,
            boss_diameter=8.0,
            boss_hole_diameter=3.2
        )
        assert enclosure is not None
        vol = enclosure.volume()
        # Le volume d'une coque évidée doit être strictement inférieur au volume plein (100*70*35 = 245000)
        assert 10000.0 < vol < 245000.0

    def test_create_reinforced_bracket(self) -> None:
        """Vérifie la génération d'une équerre de fixation avec nervure de renfort."""
        bracket = ShapeSynthesizer.create_reinforced_bracket(
            arm_length_1=50.0,
            arm_length_2=50.0,
            width=30.0,
            thickness=5.0,
            rib_thickness=4.0,
            hole_diameter=6.0
        )
        assert bracket is not None
        assert bracket.volume() > 2000.0

    def test_create_stepped_shaft(self) -> None:
        """Vérifie la génération d'un arbre étagé concentrique."""
        diameters = [20.0, 35.0, 25.0]
        lengths = [25.0, 50.0, 30.0]
        shaft = ShapeSynthesizer.create_stepped_shaft(diameters, lengths)
        assert shaft is not None
        min_b, max_b = shaft.bounding_box()
        assert max_b.z >= 104.9  # Somme des longueurs = 105 mm


class TestCADAIBridge:
    """Vérifie la compréhension en langage naturel et l'exécution dans le document."""

    def test_parse_and_create_box(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        res = bridge.interpret_and_execute("Crée un cube de 40x30x20")
        assert res.success is True
        assert res.command_type == AICommandType.CREATE_PRIMITIVE
        assert len(doc.bodies) == 1
        body = list(doc.bodies.values())[0]
        assert abs(body.volume() - (40.0 * 30.0 * 20.0)) < 1.0

    def test_parse_and_create_cylinder(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        res = bridge.interpret_and_execute("Génère un cylindre de rayon 15 et hauteur 50")
        assert res.success is True
        assert res.command_type == AICommandType.CREATE_PRIMITIVE
        assert len(doc.bodies) == 1
        body = list(doc.bodies.values())[0]
        assert body.volume() > 30000.0

    def test_parse_and_create_sphere(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        res = bridge.interpret_and_execute("Crée une sphère de rayon 20")
        assert res.success is True
        assert res.command_type == AICommandType.CREATE_PRIMITIVE
        assert len(doc.bodies) == 1
        body = list(doc.bodies.values())[0]
        assert body.volume() > 25000.0

    def test_parse_and_create_gear(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        res = bridge.interpret_and_execute("Crée un engrenage de 18 dents rayon 35 épaisseur 10")
        assert res.success is True
        assert res.command_type == AICommandType.SYNTHESIZE_SHAPE
        assert len(doc.bodies) == 1
        assert "Engrenage" in res.message

    def test_parse_and_create_flange(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        res = bridge.interpret_and_execute("Bride de tuyauterie diamètre 100 4 trous")
        assert res.success is True
        assert res.command_type == AICommandType.SYNTHESIZE_SHAPE
        assert len(doc.bodies) == 1
        assert "Bride" in res.message

    def test_parse_and_create_heat_sink(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        res = bridge.interpret_and_execute("Dissipateur thermique 50x50 avec 6 ailettes")
        assert res.success is True
        assert res.command_type == AICommandType.SYNTHESIZE_SHAPE
        assert len(doc.bodies) == 1
        assert "Dissipateur" in res.message

    def test_parse_and_create_bracket(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        res = bridge.interpret_and_execute("Support équerre renforcé 40x40 largeur 25")
        assert res.success is True
        assert res.command_type == AICommandType.SYNTHESIZE_SHAPE
        assert len(doc.bodies) == 1

    def test_parse_and_create_enclosure(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        res = bridge.interpret_and_execute("Boîtier électronique 80x60x30 épaisseur 2")
        assert res.success is True
        assert res.command_type == AICommandType.SYNTHESIZE_SHAPE
        assert len(doc.bodies) == 1

    def test_parse_and_create_stepped_shaft(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        res = bridge.interpret_and_execute("Arbre étagé 3 étages")
        assert res.success is True
        assert res.command_type == AICommandType.SYNTHESIZE_SHAPE
        assert len(doc.bodies) == 1

    def test_parse_drill_hole_boolean(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        # Créer d'abord un cube
        bridge.interpret_and_execute("Crée un cube de 50x50x30")
        vol_before = list(doc.bodies.values())[0].volume()

        # Percer un trou
        res = bridge.interpret_and_execute("Perce un trou de diamètre 16 profondeur 30")
        assert res.success is True
        assert res.command_type == AICommandType.BOOLEAN_OPERATION
        vol_after = list(doc.bodies.values())[0].volume()
        assert vol_after < vol_before

    def test_clear_scene(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        bridge.interpret_and_execute("Crée un cube de 30x30x30")
        assert len(doc.bodies) == 1
        res = bridge.interpret_and_execute("Nettoie la scène")
        assert res.success is True
        assert res.command_type == AICommandType.CLEAR_SCENE
        assert len(doc.bodies) == 0

    def test_unknown_command_help(self) -> None:
        doc = CADDocument("Test AI Doc")
        bridge = CADAIBridge(doc)
        res = bridge.interpret_and_execute("Fais de la pizza")
        assert res.success is False
        assert res.command_type == AICommandType.UNKNOWN
        assert "non reconnue" in res.message
        assert len(res.suggested_prompts) > 0


class TestCADAIServer:
    """Vérifie le fonctionnement du serveur REST HTTP en arrière-plan."""

    def test_server_status_and_prompt_endpoints(self) -> None:
        doc = CADDocument("Test Server Doc")
        bridge = CADAIBridge(doc)
        port = 8769
        server = CADAIServer(bridge, host="127.0.0.1", port=port)
        server.start()

        try:
            # 1. Test GET /api/cad/status
            url_status = f"http://127.0.0.1:{port}/api/cad/status"
            req_status = urllib.request.Request(url_status, method="GET")
            with urllib.request.urlopen(req_status, timeout=3.0) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["status"] == "ok"
                assert data["active_bodies"] == 0

            # 2. Test POST /api/cad/prompt
            url_prompt = f"http://127.0.0.1:{port}/api/cad/prompt"
            post_data = json.dumps({"prompt": "Crée un cube de 25x25x25"}).encode("utf-8")
            req_prompt = urllib.request.Request(
                url_prompt,
                data=post_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req_prompt, timeout=3.0) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["success"] is True
                assert len(doc.bodies) == 1

            # 3. Test GET status après création
            with urllib.request.urlopen(req_status, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert data["active_bodies"] == 1
                assert data["total_volume_mm3"] > 15000.0

            # 4. Test POST JSON invalide
            invalid_post = b"not-a-json"
            req_invalid = urllib.request.Request(
                url_prompt,
                data=invalid_post,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req_invalid, timeout=3.0)
            assert exc_info.value.code == 400

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

        # Simuler un prompt utilisateur
        widget.input_field.setText("Cube 30x30x10")
        widget.btn_send.click()

        assert len(results) == 1
        assert results[0].success is True
        assert len(doc.bodies) == 1

        # Tester la mise à jour de document
        new_doc = CADDocument("New Replaced Doc")
        widget.set_document(new_doc)
        assert widget.doc is new_doc
        assert widget.bridge.doc is new_doc
