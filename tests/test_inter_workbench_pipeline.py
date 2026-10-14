"""
Test d'Intégration Bout-en-Bout Multi-Ateliers (Full Lego Inter-Workbench Pipeline).
Vérifie la chaîne industrielle complète : Esquisse 2D -> Solide 3D -> Opérations avancées ->
Métrologie 3x3 -> Simulation FEA von Mises -> FAO Usinage G-Code -> Tôlerie DXF ->
Dessin technique ISO 128 SVG -> Sérialisation JSON .cadproj et reconstruction.
"""

import os
import tempfile
import pytest

from src.core.types import Vector3D, Point2D, PlaneType, BooleanOperation
from src.core.geometry import Solid, make_box, extrude_polygon
from src.core.sketch import Sketch2D
from src.core.feature import ExtrudeFeature, BoxFeature
from src.core.operations_advanced import HoleFeature, HelixFeature, RibFeature
from src.core.document import CADDocument
from src.core.serializer import ProjectSerializer
from src.core.inspector import compute_center_of_mass, compute_inertia_tensor, generate_inspection_report
from src.fea.fea_solver import FEASimulator
from src.cam.cam_engine import CAMEngine
from src.sheetmetal.sheet_metal import SheetMetalPart, SheetMetalRule
from src.sheetmetal.dxf_exporter import DXFExporter
from src.drawing.drawing_generator import TechnicalDrawingGenerator
from src.drawing.svg_exporter import SVGDrawingExporter


def test_full_inter_workbench_industrial_pipeline():
    """Vérifie la traversée continue des 5 ateliers métiers sans rupture de données."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # 1. Esquisse 2D fermée (Plaque rectangulaire 80x50 avec perçage)
        doc = CADDocument("IndustrialPart")
        sketch = Sketch2D("sk1", "BaseSketch", plane=PlaneType.XY)
        sketch.add_rectangle(Point2D(-40.0, -25.0), 80.0, 50.0)
        doc.add_sketch(sketch)

        # 2. Extrusion volumique (Pad 15 mm)
        f_extrude = ExtrudeFeature("f_ext", "BasePad", sketch_id="sk1", height=15.0)
        doc.add_feature(f_extrude)
        assert len(doc.bodies) == 1
        base_body_id = list(doc.bodies.keys())[0]
        base_solid = doc.bodies[base_body_id]
        assert base_solid.volume() > 0.0

        # 3. Ajout de perçage avec lamage CHC (HoleFeature)
        f_hole = HoleFeature(
            "f_hole", "Alésage Lamé", target_body_id=base_body_id,
            pos_x=0.0, pos_y=0.0, diameter=8.0, depth=20.0,
            hole_type="counterbore", cbore_dia=14.0, cbore_depth=6.0
        )
        doc.add_feature(f_hole)
        solid_with_hole = doc.bodies[base_body_id]
        assert solid_with_hole.volume() < base_solid.volume()

        # 4. Métrologie & Tenseur d'inertie 3x3
        report = generate_inspection_report(solid_with_hole, material_name="Acier Carbone C45", density_g_cm3=7.85)
        assert float(report["volume_mm3"]) > 0.0
        assert float(report["mass_grams"]) > 0.0
        inertia = report["inertia"]
        assert inertia.ixx > 0.0 and inertia.iyy > 0.0 and inertia.izz > 0.0

        # 5. Simulation mécanique FEA von Mises
        fea_sim = FEASimulator()
        fea_res = fea_sim.run_static_analysis(solid_with_hole, applied_force_newtons=2500.0)
        assert fea_res is not None
        assert fea_res.max_stress_mpa > 0.0
        heatmap_buf = fea_sim.generate_stress_heatmap_mesh(solid_with_hole, fea_res)
        assert heatmap_buf.vertex_colors is not None
        assert len(heatmap_buf.vertex_colors) > 0

        # 6. FAO / Usinage CNC : Surfaçage + Contournage + G-Code
        cam = CAMEngine()
        op_face = cam.generate_facing_toolpath(-45.0, 45.0, -30.0, 30.0, stock_z=18.0, target_z=15.0)
        op_contour = cam.generate_contour_toolpath(solid_with_hole, depth_mm=15.0)
        gcode_path = os.path.join(tmp_dir, "machining_program.nc")
        gcode_str = cam.export_gcode([op_face, op_contour], gcode_path)
        assert os.path.exists(gcode_path)
        assert "G21" in gcode_str
        assert "M30" in gcode_str

        # 7. Tôlerie pliée K-factor et export DXF
        sm_rule = SheetMetalRule("Inox 1.5mm", thickness_mm=1.5, bend_radius_mm=2.0, k_factor=0.42)
        sm_part = SheetMetalPart(base_width=60.0, base_length=80.0, rule=sm_rule)
        sm_part.add_flange(25.0, angle_deg=90.0)
        flat_pattern = sm_part.generate_flat_pattern()
        assert flat_pattern.total_length_mm > 80.0
        dxf_path = os.path.join(tmp_dir, "flat_pattern.dxf")
        dxf_str = DXFExporter.export_dxf(flat_pattern, dxf_path)
        assert os.path.exists(dxf_path)
        assert "ENTITIES" in dxf_str
        assert "EOF" in dxf_str

        # 8. Dessin Technique ISO 128 avec coupe A-A et symboles GD&T
        drw_gen = TechnicalDrawingGenerator()
        sheet = drw_gen.generate_standard_sheet(solid_with_hole, part_name="Plaque Industrielle", material="Acier C45")
        drw_gen.generate_section_view(solid_with_hole, cut_height=7.5, sheet=sheet)
        drw_gen.add_leader_annotation(0.0, 0.0, 30.0, 40.0, "Ø8 H7 Lamage Ø14", sheet=sheet)
        drw_gen.add_gdt_frame(100.0, 150.0, "⏥", "0.05", datum_primary="A", sheet=sheet)
        drw_gen.add_surface_finish_symbol(150.0, 150.0, roughness="Ra 0.8", sheet=sheet)
        svg_path = os.path.join(tmp_dir, "drawing_plan.svg")
        svg_str = SVGDrawingExporter.export_svg(sheet, svg_path)
        assert os.path.exists(svg_path)
        assert "<svg" in svg_str
        assert "Coupe A-A" in svg_str

        # 9. Sérialisation complète du projet .cadproj et rechargement miroir
        proj_path = os.path.join(tmp_dir, "complete_project.cadproj")
        save_ok = ProjectSerializer.save_project(doc, proj_path)
        assert save_ok
        assert os.path.exists(proj_path)

        loaded_doc = ProjectSerializer.load_project(proj_path)
        assert loaded_doc is not None
        assert len(loaded_doc.features) == len(doc.features)
        assert len(loaded_doc.bodies) == len(doc.bodies)
        loaded_solid = list(loaded_doc.bodies.values())[0]
        # Invariance volumique stricte après sauvegarde et rechargement
        assert pytest.approx(loaded_solid.volume(), rel=1e-3) == solid_with_hole.volume()
