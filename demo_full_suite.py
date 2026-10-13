"""
Script de démonstration intégrale de CAD Studio (Suite CAO / CAM / CAE / PBR Fusion 360).
Exécute en séquence les 10 ateliers technologiques et génère tous les fichiers de sortie
(G-code CNC, Plan ISO SVG, Découpe Laser DXF, Rendu Photo PNG, Projet .cadproj).
"""

from __future__ import annotations
import os
import sys

from src.core.document import CADDocument
from src.core.types import PlaneType, BooleanOperation, Point2D, Vector3D
from src.core.feature import BoxFeature, CylinderFeature, ExtrudeFeature, BooleanFeature
from src.core.operations_advanced import HoleFeature, ShellFeature, LinearPatternFeature
from src.core.sketch import Sketch2D
from src.core.parameters import ParameterTable
from src.core.serializer import ProjectSerializer
from src.solver.constraints_2d import SketchConstraintSolver2D
from src.sheetmetal.sheet_metal import SheetMetalPart, SheetMetalRule
from src.sheetmetal.dxf_exporter import DXFExporter
from src.assembly.assembly_manager import AssemblyManager, JointType
from src.materials.material_db import MATERIAL_LIBRARY, MaterialCalculator
from src.fea.fea_solver import FEASimulator
from src.cam.cam_engine import CAMEngine
from src.drawing.drawing_generator import TechnicalDrawingGenerator
from src.drawing.svg_exporter import SVGDrawingExporter
from src.render.pbr_material import PBR_LIBRARY
from src.render.raytracer import PBRRaytracer


def run_full_suite_demo() -> None:
    """Exécute l'ensemble des modules d'ingénierie et exporte les artéfacts industriels."""
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    output_dir = os.path.abspath("demo_output")
    os.makedirs(output_dir, exist_ok=True)
    print("=" * 75)
    print("🚀 DÉMARRAGE DU DÉMONSTRATEUR INDUSTRIEL CAD STUDIO (ÉQUIVALENT FUSION 360)")
    print(f"📁 Dossier de sortie des artéfacts : {output_dir}")
    print("=" * 75)

    # 1. Modélisation Paramétrique Solide
    print("\n[1/10] Atelier CONCEPTION SOLIDE (Moteur Manifold3D & Timeline DAG)...")
    doc = CADDocument("Pièce Industrielle Démo")
    box = BoxFeature("feat_1", "Corps Principal", width=80.0, height=50.0, depth=15.0, center=True)
    doc.add_feature(box)
    hole = HoleFeature("feat_2", "Alésage Central Ø20mm", target_body_id=box.body_id, pos_x=0.0, pos_y=0.0, diameter=20.0, depth=30.0)
    doc.add_feature(hole)
    assert len(doc.bodies) == 1
    active_solid = list(doc.bodies.values())[0]
    print(f"  ✅ Solide modélisé : Volume = {active_solid.volume():.1f} mm³, Historique = {len(doc.features)} features")

    # 2. Solveur de Contraintes Géométriques 2D
    print("\n[2/10] Atelier ESQUISSE & SOLVEUR 2D (Moindres Carrés TRF)...")
    solver = SketchConstraintSolver2D()
    p0 = solver.add_point(Point2D(0.0, 0.0))
    p1 = solver.add_point(Point2D(20.0, 5.0))
    p2 = solver.add_point(Point2D(22.0, 28.0))
    solver.add_fixed(p0, 0.0, 0.0)
    solver.add_horizontal(p0, p1)
    solver.add_vertical(p1, p2)
    solver.add_distance(p0, p1, 60.0)
    solver.add_distance(p1, p2, 40.0)
    ok, solved_pts = solver.solve()
    assert ok and len(solved_pts) == 3
    print(f"  ✅ Esquisse résolue : Sommets = {solved_pts}")

    # 3. Moteur d'Équations et Paramètres Globaux (fx)
    print("\n[3/10] Atelier ÉQUATIONS GLOBALES fx (AST Sécurisé)...")
    param_table = ParameterTable()
    param_table.set_parameter("longueur", "120.0", "mm", "Longueur de base")
    param_table.set_parameter("largeur", "longueur / 2", "mm", "Largeur dérivée")
    param_table.set_parameter("entraxe", "sqrt(largeur ** 2 + 30 ** 2)", "mm", "Entraxe géométrique")
    assert param_table.get_value("largeur") == 60.0
    print(f"  ✅ Paramètres résolus : longueur={param_table.get_value('longueur')} mm, largeur={param_table.get_value('largeur')} mm, entraxe={param_table.get_value('entraxe'):.2f} mm")

    # 4. Atelier Tôlerie Industrielle (Sheet Metal) & DXF Laser
    print("\n[4/10] Atelier TÔLERIE INDUSTRIELLE (Facteur K = 0.44 & Déplié)...")
    rule = SheetMetalRule(thickness_mm=2.0, bend_radius_mm=2.0, k_factor=0.44)
    sm_part = SheetMetalPart(base_width=60.0, base_length=100.0, rule=rule)
    bend = sm_part.add_flange(35.0, 90.0)
    flat_pattern = sm_part.generate_flat_pattern()
    dxf_file = os.path.join(output_dir, "patron_decoupe_laser.dxf")
    DXFExporter.export_flat_pattern_dxf(flat_pattern, dxf_file)
    print(f"  ✅ Flan déplié : Longueur développée = {flat_pattern.total_length_mm:.2f} mm (BD = {bend.bend_deduction_mm:.2f} mm)")
    print(f"  ✅ Export AutoCAD DXF généré : {dxf_file}")

    # 5. Atelier Assemblage & Détection de Collisions CSG
    print("\n[5/10] Atelier ASSEMBLAGE MÉCANIQUE (Liaisons & Interférences)...")
    asm_mgr = AssemblyManager()
    asm_mgr.add_joint("j_1", "Pivot Arbre-Moyeu", JointType.REVOLUTE, "corps_A", "corps_B")
    interf = AssemblyManager.check_interference(active_solid, active_solid, "Corps 1", "Corps 2")
    print(f"  ✅ Liaison cinématique ajoutée : Type REVOLUTE (Pivot 1 DOF)")
    print(f"  ✅ Contrôle collision CSG : Volume de chevauchement = {interf.overlap_volume_mm3:.1f} mm³")

    # 6. Atelier Matériaux & Simulation FEA
    print("\n[6/10] Atelier SIMULATION STATIQUE LINÉAIRE (FEA von Mises)...")
    mat_steel = MATERIAL_LIBRARY["Acier Carbone C45"]
    mass_g = MaterialCalculator.calculate_mass_grams(active_solid.volume(), mat_steel)
    fea_sim = FEASimulator(mat_steel)
    fea_res = fea_sim.run_static_analysis(active_solid, applied_force_newtons=2500.0)
    print(f"  ✅ Masse : {mass_g:.1f} g ({mass_g / 1000:.3f} kg), Limite élastique : {mat_steel.yield_strength_mpa} MPa")
    print(f"  ✅ Analyse FEA : Contrainte Max = {fea_res.max_stress_mpa:.2f} MPa, Facteur de sécurité = {fea_res.safety_factor:.2f}")

    # 7. Atelier Fabrication CAM & G-Code CNC
    print("\n[7/10] Atelier FABRICATION CAM (Surfaçage & Contournage CNC)...")
    cam = CAMEngine()
    op_face = cam.generate_facing_toolpath(-40.0, 40.0, -25.0, 25.0, 5.0, 0.0)
    op_cont = cam.generate_contour_toolpath(active_solid, depth_mm=10.0)
    gcode_file = os.path.join(output_dir, "usinage_fraisage.gcode")
    cam.export_gcode([op_face, op_cont], gcode_file)
    print(f"  ✅ Trajectoires outil calculées : {len(op_face.points) + len(op_cont.points)} passes G0/G1")
    print(f"  ✅ Programme ISO/GRBL G-Code généré : {gcode_file}")

    # 8. Atelier Dessin Technique 2D ISO 128
    print("\n[8/10] Atelier MISE EN PLAN 2D ISO 128 (4 Vues Orthogonales)...")
    drawing_gen = TechnicalDrawingGenerator()
    sheet = drawing_gen.generate_sheet(active_solid, title=doc.name, author="Brandon", material_name="Acier C45")
    svg_file = os.path.join(output_dir, "plan_technique_iso128.svg")
    SVGDrawingExporter.export_svg(sheet, svg_file)
    print(f"  ✅ Plan technique A3 généré : Vues Face, Dessus, Droite, Isométrique 3D + Cotations + Cartouche")
    print(f"  ✅ Planche vectorielle SVG générée : {svg_file}")

    # 9. Atelier Rendu Photoréaliste PBR & Raytracing
    print("\n[9/10] Atelier RENDU STUDIO PBR (Fresnel, Éclairage 3-Points & PNG)...")
    raytracer = PBRRaytracer()
    pbr_mat = PBR_LIBRARY["Aluminium Brossé"]
    png_file = os.path.join(output_dir, "rendu_studio_hd.png")
    ok_render = raytracer.export_render_png(active_solid, pbr_mat, png_file, width=640, height=480)
    assert ok_render and os.path.exists(png_file)
    print(f"  ✅ Image de rendu studio générée : {png_file} (Résolution 640x480)")

    # 10. Persistance de Projet (.cadproj JSON)
    print("\n[10/10] ATELIER FICHIER PROJET (Sérialisation .cadproj)...")
    proj_file = os.path.join(output_dir, "projet_demo.cadproj")
    ok_save = ProjectSerializer.save_project(doc, proj_file)
    loaded_doc = ProjectSerializer.load_project(proj_file)
    assert ok_save and loaded_doc is not None and len(loaded_doc.features) == 2
    print(f"  ✅ Projet paramétrique sauvegardé et rechargé avec succès : {proj_file}")

    print("\n" + "=" * 75)
    print("🏆 TOUS LES 10 ATELIERS DE LA SUITE CAO SE SONT EXÉCUTÉS AVEC 100% DE SUCCÈS !")
    print("=" * 75)


if __name__ == "__main__":
    run_full_suite_demo()
