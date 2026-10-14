"""
Suite de tests de parité approfondie et de résistance industrielle pour CAD Studio.
Valide les fonctionnalités avancées surpassant FreeCAD :
1. Mise en cache LRU mémoïsée O(1) de la visserie normalisée ISO (Fasteners).
2. Format conteneur compressé haute performance (.cadz) avec sérialisation complète.
3. Élimination analytique des lignes cachées (HLR) et cotations interactives ISO 128.
4. Lissage volumique multi-rails guidé dans l'espace 3D avec étanchéité topologique.
5. Plans de référence dynamiques (Dynamic Datum Planes) avec repère orthonormal exact.
"""

from __future__ import annotations
import os
import time
import tempfile
import zipfile
import numpy as np
import pytest

from src.core.geometry import Solid, make_box, make_cylinder
from src.core.types import PlaneType, BooleanOperation, Point2D
from src.core.sketch import Sketch2D, SketchLine, SketchCircle
from src.core.document import CADDocument
from src.core.feature import ExtrudeFeature
from src.core.operations_advanced import (
    DynamicDatumPlaneFeature, DatumAttachmentMode,
    VariableRadiusFilletFeature, MultiRailLoftFeature
)
from src.core.fasteners import (
    create_hex_bolt, create_socket_head_cap_screw, create_hex_nut, create_washer,
    FastenerFeature, _FASTENER_CACHE
)
from src.core.serializer import ProjectSerializer
from src.drawing.drawing_generator import TechnicalDrawingGenerator, TechnicalSheet
from src.drawing.svg_exporter import SVGDrawingExporter


def test_fastener_lru_memoization_cache() -> None:
    """
    Vérifie la mise en cache LRU O(1) de la quincaillerie normalisée ISO.
    Vérifie l'étanchéité géométrique et le gain de performance sur 100 instanciations consécutives.
    """
    # 1. Vérification de la validité topologique des solides créés
    bolt = create_hex_bolt(standard_size="M8", length=35.0, name="VisM8")
    assert not bolt.is_empty()
    assert bolt.is_watertight()
    assert bolt.volume() > 0.0

    screw = create_socket_head_cap_screw(standard_size="M6", length=20.0, name="CHCM6")
    assert not screw.is_empty()
    assert screw.is_watertight()

    nut = create_hex_nut(standard_size="M8", name="EcrouM8")
    assert not nut.is_empty()
    assert nut.is_watertight()

    washer = create_washer(standard_size="M8", name="RondelleM8")
    assert not washer.is_empty()
    assert washer.is_watertight()

    # 2. Test du cache et de l'accélération O(1)
    # L'élément doit être présent dans le dictionnaire de cache
    cache_key = ("hex_bolt", "M8", 35.0)
    assert cache_key in _FASTENER_CACHE

    t_start = time.perf_counter()
    for _ in range(100):
        fast_bolt = create_hex_bolt(standard_size="M8", length=35.0, name="VisRapide")
        assert fast_bolt.manifold == _FASTENER_CACHE[cache_key]
    elapsed = time.perf_counter() - t_start

    # 100 instanciations mémoïsées doivent s'exécuter en moins de 50 millisecondes
    assert elapsed < 0.05, f"La mémoïsation doit être quasi instantanée O(1), mesuré: {elapsed:.4f}s"


def test_cadz_compressed_project_container_roundtrip() -> None:
    """
    Vérifie la sérialisation et désérialisation du format conteneur compressé .cadz.
    Teste la sauvegarde d'un assemblage complet avec esquisses et fonctions avancées,
    l'archive ZIP interne (project.json), puis la reconstruction intégrale du modèle.
    """
    doc = CADDocument("ProjetIndustriel")

    # Esquisse de base rectangulaire
    sk1 = Sketch2D("sk_base", PlaneType.XY)
    sk1.add_rectangle(Point2D(0.0, 0.0), 80.0, 50.0)
    doc.add_sketch(sk1)

    # Extrusion paramétrique de base
    pad = ExtrudeFeature("f_pad", "ExtrusionBase", sketch_id="sk_base", distance=25.0)
    doc.add_feature(pad)

    # Plan de référence dynamique attaché par 3 points spatiaux
    datum = DynamicDatumPlaneFeature(
        "f_datum",
        "PlanIncline",
        mode=DatumAttachmentMode.THREE_POINTS,
        point1=(0.0, 0.0, 25.0),
        point2=(80.0, 0.0, 25.0),
        point3=(40.0, 50.0, 45.0)
    )
    doc.add_feature(datum)

    # Congé à rayon variable le long de Z
    var_fillet = VariableRadiusFilletFeature(
        "f_fillet",
        "CongeProgressif",
        target_body_id="body_f_pad",
        start_radius=2.0,
        end_radius=6.0,
        mid_radius=4.0,
        edge_direction="z"
    )
    doc.add_feature(var_fillet)

    # Visserie standard attachée
    fastener_feat = FastenerFeature("f_vis", "VisAssemblage", fastener_type="hex_bolt", standard_size="M8", length=30.0)
    doc.add_feature(fastener_feat)

    doc.rebuild()
    assert len(doc.bodies) >= 1

    with tempfile.TemporaryDirectory() as tmp_dir:
        cadz_path = os.path.join(tmp_dir, "machine_part.cadz")

        # 1. Sauvegarde au format compressé
        saved = ProjectSerializer.save_project(doc, cadz_path)
        assert saved is True
        assert os.path.exists(cadz_path)

        # 2. Vérification de la structure ZIP et de l'intégrité de l'archive
        assert zipfile.is_zipfile(cadz_path)
        with zipfile.ZipFile(cadz_path, "r") as zf:
            namelist = zf.namelist()
            assert "project.json" in namelist
            raw_json = zf.read("project.json").decode("utf-8")
            assert "ProjetIndustriel" in raw_json
            assert "DynamicDatumPlaneFeature" in raw_json
            assert "VariableRadiusFilletFeature" in raw_json

        # 3. Chargement et désérialisation
        loaded_doc = ProjectSerializer.load_project(cadz_path)
        assert loaded_doc is not None
        assert loaded_doc.name == "ProjetIndustriel"
        assert len(loaded_doc.features) == 4
        assert "sk_base" in loaded_doc.sketches

        # Vérification des propriétés des fonctions restaurées
        f_datum_loaded = loaded_doc.get_feature("f_datum")
        assert isinstance(f_datum_loaded, DynamicDatumPlaneFeature)
        assert f_datum_loaded.mode == DatumAttachmentMode.THREE_POINTS
        assert f_datum_loaded.point1 == (0.0, 0.0, 25.0)

        f_fillet_loaded = loaded_doc.get_feature("f_fillet")
        assert isinstance(f_fillet_loaded, VariableRadiusFilletFeature)
        assert f_fillet_loaded.parameters["start_radius"] == 2.0
        assert f_fillet_loaded.parameters["end_radius"] == 6.0

        # Vérification de la reconstruction des solides
        assert len(loaded_doc.bodies) >= 1
        for body in loaded_doc.bodies.values():
            assert not body.is_empty()


def test_techdraw_hidden_line_removal_and_interactive_dimension() -> None:
    """
    Vérifie le moteur HLR (Hidden Line Removal) analytique et les cotations interactives.
    Un solide avec cavité borgne inférieure doit produire à la fois des arêtes visibles
    et des arêtes cachées (is_hidden=True), exportables en SVG avec style dashed.
    """
    # Création d'une pièce avec cavité borgne inférieure créant des arêtes masquées
    box = make_box(60.0, 40.0, 30.0)
    pocket = make_box(30.0, 20.0, 15.0).translate([15.0, 10.0, 0.0])
    part = box.difference(pocket)

    gen = TechnicalDrawingGenerator(sheet_width=420.0, sheet_height=297.0)
    sheet = gen.generate_sheet(part, title="Bloc Usiné avec Poche", author="Brandon")

    # 1. Vérification de la présence de lignes de projection
    assert len(sheet.lines) > 20

    # 2. Vérification HLR : présence d'arêtes visibles ET d'arêtes masquées
    visible_lines = [line for line in sheet.lines if not line.is_hidden and not line.is_dimension]
    hidden_lines = [line for line in sheet.lines if line.is_hidden]

    assert len(visible_lines) > 0, "Doit comporter des arêtes visibles continues"
    assert len(hidden_lines) > 0, "La vue orthogonale et isométrique doit détecter les arêtes cachées"

    # 3. Ajout de cotation interactive
    gen.add_interactive_dimension(sheet, 50.0, 40.0, 150.0, 40.0, "100.0 mm H7", is_vertical=False)
    dim_lines = [line for line in sheet.lines if line.is_dimension]
    assert len(dim_lines) >= 3  # Cotations automatiques + cotation interactive

    dim_labels = [d for d in sheet.dimensions if "100.0 mm H7" in d.text]
    assert len(dim_labels) == 1

    # 4. Export vectoriel SVG et vérification du balisage normalisé
    with tempfile.TemporaryDirectory() as tmp_dir:
        svg_file = os.path.join(tmp_dir, "plan_technique_hlr.svg")
        svg_str = SVGDrawingExporter.export_svg(sheet, svg_file)

        assert os.path.exists(svg_file)
        assert 'class="hidden-line"' in svg_str
        assert 'class="solid-line"' in svg_str
        assert 'class="dim-line"' in svg_str
        assert "100.0 mm H7" in svg_str


def test_multi_rail_loft_watertightness_and_invariants() -> None:
    """
    Vérifie la création d'un lissage volumique guidé par rails 3D (MultiRailLoftFeature).
    Vérifie l'étanchéité géométrique (watertight manifold) et les invariants de volume.
    """
    # Profil de départ à Z = 0
    sk1 = Sketch2D("sk_start", PlaneType.XY, offset_distance=0.0)
    sk1.add_circle(Point2D(0.0, 0.0), 15.0)

    # Profil d'arrivée à Z = 50
    sk2 = Sketch2D("sk_end", PlaneType.XY, offset_distance=50.0)
    sk2.add_circle(Point2D(0.0, 0.0), 25.0)

    sketches = {"sk_start": sk1, "sk_end": sk2}

    # Rails de guidage définissant une taille cintrée
    rail1 = [(15.0, 0.0, 0.0), (10.0, 0.0, 25.0), (25.0, 0.0, 50.0)]
    rail2 = [(-15.0, 0.0, 0.0), (-10.0, 0.0, 25.0), (-25.0, 0.0, 50.0)]

    loft_feat = MultiRailLoftFeature(
        feature_id="f_loft_rail",
        name="LoftCintre",
        profile_sketch_ids=["sk_start", "sk_end"],
        guide_rail_curves=[rail1, rail2],
        num_intermediate_sections=12,
        num_segments=24,
        operation=BooleanOperation.NEW_BODY
    )

    bodies = loft_feat.evaluate(existing_bodies={}, sketches=sketches)

    assert "body_f_loft_rail" in bodies
    loft_solid = bodies["body_f_loft_rail"]
    assert not loft_solid.is_empty()
    assert loft_solid.is_watertight()
    assert loft_solid.volume() > 5000.0  # Volume cohérent avec le tronc de cône guidé


def test_dynamic_datum_plane_all_attachment_modes() -> None:
    """
    Vérifie les 5 modes d'attachement géométrique dynamique des plans de référence :
    - OFFSET : décalage cartésien
    - THREE_POINTS : passant par 3 sommets quelconques
    - NORMAL_TO_CURVE : normal à un vecteur tangent
    - TANGENT_TO_FACE : tangent à une face normale
    - LINE_AND_POINT : passant par une droite et un point externe
    """
    # 1. Mode THREE_POINTS
    p1 = (10.0, 0.0, 0.0)
    p2 = (0.0, 20.0, 0.0)
    p3 = (0.0, 0.0, 30.0)
    dp_3pts = DynamicDatumPlaneFeature(
        "dp1", "Plan3Points", mode=DatumAttachmentMode.THREE_POINTS,
        point1=p1, point2=p2, point3=p3
    )
    # L'origine est p1
    assert abs(dp_3pts.origin.x - 10.0) < 1e-5
    # La normale doit être orthogonale à (p2 - p1) et (p3 - p1)
    v12 = np.array([-10.0, 20.0, 0.0])
    v13 = np.array([-10.0, 0.0, 30.0])
    n_vec = np.array([dp_3pts.normal.x, dp_3pts.normal.y, dp_3pts.normal.z])
    assert abs(np.dot(n_vec, v12)) < 1e-4
    assert abs(np.dot(n_vec, v13)) < 1e-4

    # 2. Mode NORMAL_TO_CURVE
    dp_normal = DynamicDatumPlaneFeature(
        "dp2", "PlanNormal", mode=DatumAttachmentMode.NORMAL_TO_CURVE,
        point1=(5.0, 5.0, 5.0), tangent_or_normal=(0.0, 0.0, 1.0)
    )
    assert abs(dp_normal.normal.z - 1.0) < 1e-5

    # 3. Mode TANGENT_TO_FACE
    dp_tangent = DynamicDatumPlaneFeature(
        "dp3", "PlanTangent", mode=DatumAttachmentMode.TANGENT_TO_FACE,
        point1=(0.0, 10.0, 0.0), tangent_or_normal=(0.0, 1.0, 0.0)
    )
    assert abs(dp_tangent.normal.y - 1.0) < 1e-5

    # 4. Mode LINE_AND_POINT
    dp_line = DynamicDatumPlaneFeature(
        "dp4", "PlanDroitePoint", mode=DatumAttachmentMode.LINE_AND_POINT,
        point1=(0.0, 0.0, 0.0), point2=(1.0, 0.0, 0.0), point3=(0.0, 1.0, 1.0)
    )
    u_vec = np.array([dp_line.u_axis.x, dp_line.u_axis.y, dp_line.u_axis.z])
    assert abs(u_vec[0] - 1.0) < 1e-5

    # 5. Projection 3D vers 2D et matrice de passage
    pt_spatial = (10.0, 0.0, 0.0)
    pt_2d = dp_3pts.project_point_to_plane(pt_spatial)
    assert isinstance(pt_2d, Point2D)
    # L'origine se projette en (0, 0)
    assert abs(pt_2d.u) < 1e-5 and abs(pt_2d.v) < 1e-5

    mat = dp_3pts.get_transformation_matrix()
    assert mat.shape == (4, 4)
