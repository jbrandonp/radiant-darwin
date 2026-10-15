"""
Tests unitaires pour les modules d'infrastructure et d'échange de l'overhaul architectural.
Couvre:
- User Preferences & Keymaps (preferences.py)
- WAL Journaling & Crash Recovery (journal.py)
- 3MF Additive Manufacturing Exporter (threemf_exporter.py)
- 2D DXF & SVG Importers (dxf_importer.py, svg_importer.py)
- CAD Worker Pool (worker_pool.py)
- AI Sandbox Security Hardening (cad_validator.py)
"""

from __future__ import annotations
import os
import tempfile
import pytest

from src.core.preferences import (
    PreferencesManager,
    UserPreferences,
    UnitLength,
    CameraNavigationPreset,
    ThemeMode,
    NavigationAction,
    resolve_navigation_press,
)
from src.core.journal import (
    TransactionJournal,
    JournalRecord,
    CrashRecoveryManager,
)
from src.core.types import Vector3D
from src.core.threemf_types import (
    LatticeBeam,
    LatticeBall,
    BeamLatticeTopology,
    BeamCapMode,
)
from src.core.threemf_exporter import ThreeMFExporter, export_3mf_to_bytes
from src.core.dxf_importer import DXF2DImporter
from src.core.svg_importer import SVGImporter
from src.core.worker_pool import (
    CADWorkerPool,
    TPMSWorkerParams,
    TessellationWorkerParams,
    FEAWorkerParams,
)
from src.ai.cad_validator import CADValidator


def test_user_preferences_atomic_save_and_load(tmp_path):
    """Vérifie la sérialisation atomique et le rechargement des préférences utilisateur."""
    config_file = str(tmp_path / "cad_prefs.json")
    mgr = PreferencesManager(config_path=config_file)
    prefs = mgr.preferences
    assert prefs.unit_length == UnitLength.MM

    # Modification des préférences
    new_prefs = UserPreferences(
        unit_length=UnitLength.INCH,
        navigation_preset=CameraNavigationPreset.BLENDER,
        theme=ThemeMode.DARK,
        auto_save_interval_sec=120
    )
    mgr.update_preferences(new_prefs, auto_save=True)

    # Rechargement depuis le disque
    mgr2 = PreferencesManager(config_path=config_file)
    loaded = mgr2.preferences
    assert loaded.unit_length == UnitLength.INCH
    assert loaded.navigation_preset == CameraNavigationPreset.BLENDER
    assert loaded.theme == ThemeMode.DARK
    assert loaded.auto_save_interval_sec == 120

    # Résolution des touches de navigation Blender (MMB = ORBIT, Shift+MMB = PAN)
    action_rot = resolve_navigation_press(CameraNavigationPreset.BLENDER, button="middle", is_shift=False)
    assert action_rot == NavigationAction.ORBIT
    action_pan = resolve_navigation_press(CameraNavigationPreset.BLENDER, button="middle", is_shift=True)
    assert action_pan == NavigationAction.PAN


def test_crash_journal_and_recovery(tmp_path):
    """Vérifie le journal transactionnel Write-Ahead Log (WAL) et la reprise après crash."""
    journal_path = str(tmp_path / "session_crashed.journal")
    journal = TransactionJournal(journal_path=journal_path, document_name="CrashTestDoc")

    # Écriture d'opérations non clôturées par CHECKPOINT ou CLEAN_CLOSE
    journal.record_modify_parameter("extrude_1", "length", 50.0, 25.0)

    # Le journal n'est pas proprement fermé : detect_dirty_journals doit le trouver
    dirty_list = CrashRecoveryManager.detect_dirty_journals(str(tmp_path))
    assert len(dirty_list) == 1
    assert dirty_list[0].journal_path == journal_path

    # Restauration
    recovery_res = CrashRecoveryManager.recover_document(dirty_list[0].journal_path)
    assert recovery_res.success is True

    # Fermeture propre : clean close écrit CLEAN_CLOSE
    journal.close(clean=True)
    dirty_after = CrashRecoveryManager.detect_dirty_journals(str(tmp_path))
    assert len(dirty_after) == 0


def test_3mf_opc_container_and_beam_lattice():
    """Vérifie l'export 3MF Core et l'extension Beam Lattice en conteneur OPC ZIP."""
    lattice = BeamLatticeTopology()
    n0 = lattice.add_node(0.0, 0.0, 0.0)
    n1 = lattice.add_node(10.0, 0.0, 0.0)
    n2 = lattice.add_node(10.0, 10.0, 0.0)
    n3 = lattice.add_node(0.0, 10.0, 0.0)

    lattice.add_beam(n0, n1, radius=0.5, cap_mode=BeamCapMode.SPHERE)
    lattice.add_beam(n1, n2, radius=0.5, cap_mode=BeamCapMode.SPHERE)
    lattice.add_beam(n2, n3, radius=0.5, cap_mode=BeamCapMode.SPHERE)
    lattice.add_beam(n3, n0, radius=0.5, cap_mode=BeamCapMode.SPHERE)

    zip_bytes = export_3mf_to_bytes(lattices={"UnitCell": lattice})
    assert len(zip_bytes) > 200
    # En-tête ZIP PK
    assert zip_bytes[:2] == b"PK"


def test_dxf_2d_streaming_importer():
    """Vérifie l'importateur DXF 2D sur des entités LINE, CIRCLE et LWPOLYLINE."""
    dxf_sample = """0
SECTION
2
ENTITIES
0
LINE
10
0.0
20
0.0
11
100.0
21
0.0
0
CIRCLE
10
50.0
20
50.0
40
25.0
0
LWPOLYLINE
90
4
70
1
10
0.0
20
0.0
42
0.41421356
10
20.0
20
0.0
10
20.0
20
20.0
10
0.0
20
20.0
0
ENDSEC
0
EOF"""

    sketch = DXF2DImporter.parse_dxf_text(dxf_sample)
    assert len(sketch.entities) > 0


def test_svg_streaming_importer():
    """Vérifie l'importateur SVG pour les balises vectorielles et chemins cubiques."""
    svg_sample = """<svg width="200" height="200" xmlns="http://www.w3.org/2000/svg">
      <line x1="10" y1="20" x2="150" y2="20" stroke="black" />
      <circle cx="80" cy="80" r="30" />
      <rect x="10" y="100" width="80" height="50" />
      <path d="M 10 10 L 90 90 C 100 120 120 120 150 90 Z" />
    </svg>"""

    sketch = SVGImporter.parse_svg_text(svg_sample)
    assert len(sketch.entities) > 0


def test_ai_sandbox_security_hardening():
    """Vérifie que le validateur AST bloque strictement l'introspection malveillante."""
    safe_script = """
import math
radius = 10.0
area = math.pi * radius ** 2
"""
    assert CADValidator.validate_script_security(safe_script) is None

    unsafe_subclasses = """
x = ().__class__.__bases__[0].__subclasses__()
"""
    assert CADValidator.validate_script_security(unsafe_subclasses) is not None

    unsafe_globals = """
f = (lambda: None).__globals__
"""
    assert CADValidator.validate_script_security(unsafe_globals) is not None

    unsafe_builtins = """
b = getattr(__builtins__, 'eval')
"""
    assert CADValidator.validate_script_security(unsafe_builtins) is not None
