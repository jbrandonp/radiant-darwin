"""
Tests unitaires pour le studio de rendu photoréaliste PBR (Render Studio).
Vérifie le modèle physique de Fresnel-Schlick, la bibliothèque PBR,
le lancer de rayons avec studio lumineux et l'export d'image PNG.
"""

import os
import tempfile
import pytest
from PySide6.QtGui import QImage

from src.core.geometry import make_box, make_cylinder
from src.core.types import Vector3D
from src.render.pbr_material import PBRMaterial, PBR_LIBRARY
from src.render.raytracer import PBRRaytracer, DirectionalLight, StudioEnvironment, create_default_studio


def test_pbr_material_properties_and_fresnel() -> None:
    """Vérifie le calcul théorique de la réflectance de base F0 selon Fresnel-Schlick."""
    # 1. Isolant pur (Plastique, metallic=0.0, ior=1.5)
    # F0 = ((1.5 - 1) / (1.5 + 1))^2 = (0.5 / 2.5)^2 = 0.2^2 = 0.04
    dielectric = PBRMaterial(name="Plastique", albedo=(1.0, 0.0, 0.0), metallic=0.0, ior=1.5)
    f0_d = dielectric.get_fresnel_f0()
    assert f0_d[0] == pytest.approx(0.04, abs=1e-3)
    assert f0_d[1] == pytest.approx(0.04, abs=1e-3)
    assert f0_d[2] == pytest.approx(0.04, abs=1e-3)

    # 2. Métal pur (Chrome, metallic=1.0) -> F0 est identique à l'albédo
    metal = PBRMaterial(name="Chrome", albedo=(0.95, 0.85, 0.75), metallic=1.0)
    f0_m = metal.get_fresnel_f0()
    assert f0_m[0] == pytest.approx(0.95)
    assert f0_m[1] == pytest.approx(0.85)
    assert f0_m[2] == pytest.approx(0.75)


def test_pbr_library_presets() -> None:
    """Vérifie la complétude de la bibliothèque de matériaux standard."""
    presets = ["Aluminium Brossé", "Chrome Miroir", "Or 24 Carats", "Cuivre Rouge", "Fibre de Carbone"]
    for name in presets:
        assert name in PBR_LIBRARY
        mat = PBR_LIBRARY[name]
        assert 0.0 <= mat.roughness <= 1.0
        assert 0.0 <= mat.metallic <= 1.0
        assert 0.0 <= mat.specular <= 1.0


def test_raytracer_shading() -> None:
    """Vérifie le calcul d'ombrage d'un sommet avec lumière studio."""
    raytracer = PBRRaytracer()
    mat = PBR_LIBRARY["Aluminium Brossé"]

    norm = Vector3D(0.0, 0.0, 1.0)
    view = Vector3D(0.0, 0.0, 1.0)
    rgb = raytracer.shade_vertex(norm, view, mat)

    assert len(rgb) == 3
    assert all(0.0 <= c <= 1.0 for c in rgb)


def test_raytracer_render_solid_and_png_export() -> None:
    """Vérifie la rasterisation d'un solide et l'exportation du fichier PNG haute définition."""
    box = make_box(20.0, 20.0, 20.0, center=True)
    mat = PBR_LIBRARY["Chrome Miroir"]
    raytracer = PBRRaytracer()

    img = raytracer.render_solid_to_image(box, mat, width=200, height=150)
    assert isinstance(img, QImage)
    assert img.width() == 200
    assert img.height() == 150
    assert not img.isNull()

    with tempfile.TemporaryDirectory() as tmpdir:
        png_path = os.path.join(tmpdir, "render_test.png")
        ok = raytracer.export_render_png(box, mat, png_path, width=200, height=150)

        assert ok is True
        assert os.path.exists(png_path)
        assert os.path.getsize(png_path) > 500  # Vérifie que le fichier PNG est bien formé
