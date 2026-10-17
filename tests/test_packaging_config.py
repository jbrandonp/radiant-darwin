"""
Tests unitaires pour la configuration de packaging autonome (cad_studio.spec, scripts/build_standalone_exe.py).
"""

from __future__ import annotations
import os
import pytest

from scripts.build_standalone_exe import (
    verify_packaging_prerequisites,
    generate_build_manifest,
)


def test_packaging_prerequisites_check() -> None:
    """Vérifie que les prérequis de build (spec, main, pyproject) sont tous présents."""
    assert verify_packaging_prerequisites() is True


def test_cad_studio_spec_integrity() -> None:
    """Vérifie que le fichier de spécification cad_studio.spec contient les blocs critiques."""
    spec_path = "cad_studio.spec"
    assert os.path.exists(spec_path)

    with open(spec_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "src/main.py" in content
    assert "CADStudio" in content
    assert "hidden_imports" in content
    assert "PySide6" in content
    assert "manifold3d" in content


def test_manifest_generation() -> None:
    """Vérifie la génération du dictionnaire manifeste de distribution."""
    manifest = generate_build_manifest(dist_dir="dist/CADStudio")
    assert "executable_name" in manifest
    assert "executable_path" in manifest
    assert "platform" in manifest
    assert "python_version" in manifest
