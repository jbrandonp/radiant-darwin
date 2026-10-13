"""
Tests unitaires pour la génération de plans techniques 2D et l'export vectoriel SVG.
"""

import os
import tempfile
import pytest

from src.core.geometry import make_box
from src.drawing.drawing_generator import TechnicalDrawingGenerator
from src.drawing.svg_exporter import SVGDrawingExporter


def test_technical_drawing_generation() -> None:
    """Vérifie la génération des 4 vues orthogonales, cotations et cartouche ISO."""
    box = make_box(50.0, 30.0, 20.0)
    gen = TechnicalDrawingGenerator(sheet_width=420.0, sheet_height=297.0)

    sheet = gen.generate_sheet(box, title="Support Moteur", author="Brandon", material_name="Alu 6061")

    assert sheet.width_mm == 420.0
    assert sheet.height_mm == 297.0
    assert sheet.title_block.project_title == "Support Moteur"
    assert sheet.title_block.author == "Brandon"
    assert len(sheet.lines) > 20  # Lignes de cadre + projections des 4 vues
    assert len(sheet.dimensions) >= 2


def test_svg_export() -> None:
    """Vérifie la production d'un fichier SVG vectoriel valide sur le disque."""
    box = make_box(25.0, 25.0, 15.0)
    gen = TechnicalDrawingGenerator()
    sheet = gen.generate_sheet(box, title="Pièce Test")

    with tempfile.TemporaryDirectory() as tmp_dir:
        svg_path = os.path.join(tmp_dir, "blueprint.svg")
        svg_content = SVGDrawingExporter.export_svg(sheet, svg_path)

        assert os.path.exists(svg_path)
        assert "<svg" in svg_content
        assert "</svg>" in svg_content
        assert "TITRE : Pièce Test" in svg_content
