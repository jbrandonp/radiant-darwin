"""
Exportateur vectoriel SVG pour plans de dessin technique normalisés ISO.
Produit des fichiers vectoriels prêts pour l'impression haute résolution ou découpeuse laser.
"""

from __future__ import annotations
import os
from src.drawing.drawing_generator import TechnicalSheet


class SVGDrawingExporter:
    """Exportateur SVG pour plans techniques 2D."""

    @staticmethod
    def export_svg(sheet: TechnicalSheet, filepath: str) -> str:
        """Exporte la feuille technique au format SVG vectoriel standard."""
        w, h = sheet.width_mm, sheet.height_mm

        svg_lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}mm" height="{h}mm">',
            f'  <rect width="{w}" height="{h}" fill="#ffffff" stroke="none" />',
            '  <!-- Styles -->',
            '  <style>',
            '    .solid-line { stroke: #1a1a1a; stroke-width: 0.6; stroke-linecap: round; }',
            '    .dim-line { stroke: #0066cc; stroke-width: 0.35; stroke-dasharray: none; }',
            '    .text-title { font-family: "Segoe UI", Arial, sans-serif; font-size: 4px; font-weight: bold; fill: #222222; }',
            '    .text-dim { font-family: "Segoe UI", Arial, sans-serif; font-size: 3.2px; font-weight: 600; fill: #0066cc; }',
            '    .title-box { stroke: #222222; stroke-width: 0.5; fill: #f8f9fa; }',
            '  </style>',
            '  <!-- Géométrie & Projections -->'
        ]

        # Inverser l'axe Y pour l'affichage SVG (origine en haut à gauche)
        for line in sheet.lines:
            cls_name = "dim-line" if line.is_dimension else "solid-line"
            svg_y1 = h - line.y1
            svg_y2 = h - line.y2
            svg_lines.append(
                f'  <line x1="{line.x1:.2f}" y1="{svg_y1:.2f}" x2="{line.x2:.2f}" y2="{svg_y2:.2f}" class="{cls_name}" />'
            )

        # Cotations
        for dim in sheet.dimensions:
            svg_y = h - dim.y
            rotate = ' transform="rotate(-90, ' + f'{dim.x:.2f}, {svg_y:.2f})"' if dim.is_vertical else ''
            svg_lines.append(
                f'  <text x="{dim.x:.2f}" y="{svg_y:.2f}" text-anchor="middle" class="text-dim"{rotate}>{dim.text}</text>'
            )

        # Cartouche ISO en bas à droite (Dimensions : 140 mm x 35 mm)
        tb = sheet.title_block
        bx = w - 150.0
        by = h - 45.0
        bw = 140.0
        bh = 35.0

        svg_lines.extend([
            '  <!-- Cartouche ISO normalisé -->',
            f'  <rect x="{bx}" y="{by}" width="{bw}" height="{bh}" class="title-box" />',
            f'  <line x1="{bx}" y1="{by + 12}" x2="{bx + bw}" y2="{by + 12}" stroke="#222" stroke-width="0.3" />',
            f'  <line x1="{bx}" y1="{by + 24}" x2="{bx + bw}" y2="{by + 24}" stroke="#222" stroke-width="0.3" />',
            f'  <line x1="{bx + 70}" y1="{by}" x2="{bx + 70}" y2="{by + bh}" stroke="#222" stroke-width="0.3" />',
            f'  <text x="{bx + 4}" y="{by + 8}" class="text-title">TITRE : {tb.project_title}</text>',
            f'  <text x="{bx + 74}" y="{by + 8}" class="text-title">AUTEUR : {tb.author}</text>',
            f'  <text x="{bx + 4}" y="{by + 19}" class="text-title">MATIÈRE : {tb.material}</text>',
            f'  <text x="{bx + 74}" y="{by + 19}" class="text-title">ÉCHELLE : {tb.scale}</text>',
            f'  <text x="{bx + 4}" y="{by + 30}" class="text-title">DATE : {tb.date}</text>',
            f'  <text x="{bx + 74}" y="{by + 30}" class="text-title">FEUILLE : {tb.sheet} (ISO 128)</text>',
            '</svg>'
        ])

        svg_content = "\n".join(svg_lines)
        if filepath:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(svg_content)

        return svg_content
