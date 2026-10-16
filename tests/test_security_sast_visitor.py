"""
Tests unitaires complets pour le Scanner SAST de Sécurité CAO/FAO 3D (scripts/security_sast_visitor.py).
Vérifie les 5 axes majeurs :
1. Détection des vulnérabilités Zip Slip sur les archives de projet .cadz (vérification de commonpath).
2. Détection des injections de chemins (Path Traversal) dans les exporteurs et importateurs STL, STEP et DXF.
3. Détection des risques d'épuisement mémoire et de blocage CPU (Geometric ReDoS) sur les maillages à triangles effilés et le parsing Regex de STEP.
4. Contrôle de l'intégrité des appels OpenGL natifs (glDrawElements count vs buffer size) et ctypes.
5. Validation que le scanner fonctionne à 100% sans dépendance externe et avec zéro Any/object.
"""

from __future__ import annotations
import ast
import os
import sys
import tempfile
import pytest

from scripts.security_sast_visitor import (
    SecuritySeverity,
    SecurityCategory,
    SecurityFinding,
    SecuritySASTVisitor,
    audit_python_code_security,
    audit_python_file_security,
    validate_safe_cadz_path,
    validate_cad_filepath,
    analyze_regex_redos_risk,
    is_sliver_triangle,
    validate_opengl_draw_elements_bounds,
    format_security_report,
    main as sast_main,
)


# ==============================================================================
# 1. Tests Zip Slip sur archives .cadz et commonpath
# ==============================================================================

def test_zip_slip_cadz_unsafe_extraction() -> None:
    """Vérifie que l'extraction directe d'une archive .cadz via extractall() est détectée comme CRITICAL."""
    code_cadz_unsafe = """
import zipfile

def unpack_cadz_project(cadz_archive_path: str, destination_dir: str) -> None:
    # Vulnérabilité critique Zip Slip sans commonpath
    with zipfile.ZipFile(cadz_archive_path, 'r') as zf:
        zf.extractall(destination_dir)
"""
    findings = audit_python_code_security(code_cadz_unsafe, filename="test_cadz_unpack.py")
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_CADZ_ARCHIVE_UNSAFE_EXTRACTION" in rule_ids

    crit_findings = [f for f in findings if f.rule_id == "SEC_CADZ_ARCHIVE_UNSAFE_EXTRACTION"]
    assert crit_findings[0].severity == SecuritySeverity.CRITICAL
    assert crit_findings[0].category == SecurityCategory.PATH_TRAVERSAL


def test_zip_slip_manual_loop_without_commonpath() -> None:
    """Vérifie qu'une boucle manuelle d'extraction d'archive sans commonpath est détectée."""
    code_manual = """
import os
import zipfile

def extract_archive_members(archive_path: str, target_folder: str) -> None:
    with zipfile.ZipFile(archive_path, 'r') as zf:
        for name in zf.namelist():
            dest = os.path.join(target_folder, name)
            with open(dest, 'wb') as f:
                f.write(zf.read(name))
"""
    findings = audit_python_code_security(code_manual, filename="archive_handler.py")
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_ZIP_SLIP_MANUAL_EXTRACTION" in rule_ids


def test_zip_slip_safe_extraction_with_commonpath() -> None:
    """Vérifie qu'une routine d'extraction utilisant os.path.commonpath n'est pas faussement signalée."""
    code_safe = """
import os
import zipfile

def safe_extract_cadz(archive_path: str, dest_dir: str) -> None:
    abs_dest = os.path.abspath(dest_dir)
    with zipfile.ZipFile(archive_path, 'r') as zf:
        for member in zf.namelist():
            target = os.path.abspath(os.path.join(abs_dest, member))
            if os.path.commonpath([abs_dest, target]) != abs_dest:
                raise ValueError("Tentative de Zip Slip détectée")
            with open(target, 'wb') as f:
                f.write(zf.read(member))
"""
    findings = audit_python_code_security(code_safe, filename="safe_cadz_loader.py")
    # Aucune alerte Zip Slip ne doit être émise
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_CADZ_ARCHIVE_UNSAFE_EXTRACTION" not in rule_ids
    assert "SEC_ZIP_SLIP_MANUAL_EXTRACTION" not in rule_ids


def test_runtime_validate_safe_cadz_path() -> None:
    """Vérifie la fonction utilitaire d'assainissement runtime validate_safe_cadz_path."""
    target_dir = os.path.abspath("temp_projects")

    # Chemin sécurisé
    safe_path = validate_safe_cadz_path(target_dir, "models/part1.step")
    expected = os.path.abspath(os.path.join(target_dir, "models", "part1.step"))
    assert safe_path == expected

    # Tentative d'évasion Zip Slip avec traversée relative
    with pytest.raises(ValueError, match="Zip Slip"):
        validate_safe_cadz_path(target_dir, "../../Windows/System32/evil.dll")

    # Tentative avec slash initial absolu
    with pytest.raises(ValueError, match="Zip Slip"):
        validate_safe_cadz_path(target_dir, "../evil.bat")


# ==============================================================================
# 2. Tests Path Traversal dans Exportateurs/Importateurs STL, STEP, DXF
# ==============================================================================

def test_cad_path_traversal_unsafe_exporter() -> None:
    """Vérifie la détection de Path Traversal et de manque de validation d'extension dans export_stl."""
    code_exporter = """
import os

class CADExporter:
    @staticmethod
    def export_stl(bodies: dict, filepath: str) -> bool:
        # Pas de vérification d'extension ni de confinement de dossier
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            f.write("solid")
        return True
"""
    findings = audit_python_code_security(code_exporter, filename="cad_exporter.py")
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_CAD_MISSING_EXTENSION_VALIDATION" in rule_ids
    assert "SEC_CAD_PATH_TRAVERSAL_SINK" in rule_ids


def test_cad_path_traversal_unsafe_step_importer() -> None:
    """Vérifie la détection de Path Traversal dans une routine d'import STEP."""
    code_importer = """
import os

class STEPImporter:
    def import_step(self, filepath: str) -> str:
        with open(filepath, 'r') as f:
            return f.read(1024)
"""
    findings = audit_python_code_security(code_importer, filename="step_importer.py")
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_CAD_MISSING_EXTENSION_VALIDATION" in rule_ids
    assert "SEC_CAD_PATH_TRAVERSAL_SINK" in rule_ids


def test_cad_exporter_safe_with_validation() -> None:
    """Vérifie qu'un exportateur sécurisé avec vérification d'extension et commonpath ne produit pas de fausses alertes."""
    code_safe = """
import os

def export_dxf(entities: list, filepath: str, allowed_base_dir: str) -> bool:
    if not filepath.lower().endswith(".dxf"):
        raise ValueError("Extension attendue : .dxf")
    abs_path = os.path.abspath(filepath)
    abs_base = os.path.abspath(allowed_base_dir)
    if os.path.commonpath([abs_base, abs_path]) != abs_base:
        raise ValueError("Traversée interdite")
    with open(abs_path, 'w') as f:
        f.write("0\\nSECTION\\n")
    return True
"""
    findings = audit_python_code_security(code_safe, filename="safe_dxf_exporter.py")
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_CAD_MISSING_EXTENSION_VALIDATION" not in rule_ids
    assert "SEC_CAD_PATH_TRAVERSAL_SINK" not in rule_ids


def test_runtime_validate_cad_filepath() -> None:
    """Vérifie l'utilitaire d'assainissement runtime validate_cad_filepath."""
    base_dir = os.path.abspath("exports")

    # Extension valide
    valid_res = validate_cad_filepath("exports/gear.stl", allowed_extensions=(".stl", ".step", ".dxf"), base_directory=base_dir)
    assert valid_res.lower().endswith("gear.stl")

    # Extension non autorisée
    with pytest.raises(ValueError, match="Extension de fichier CAD non autorisée"):
        validate_cad_filepath("exports/malicious.exe", allowed_extensions=(".stl", ".step", ".dxf"))

    # Traversée de répertoire hors de base_dir
    with pytest.raises(ValueError, match="Path Traversal CAD"):
        validate_cad_filepath("../etc/shadow.stl", allowed_extensions=(".stl", ".step", ".dxf"), base_directory=base_dir)


# ==============================================================================
# 3. Tests Geometric ReDoS, Slivers et Parsing STEP
# ==============================================================================

def test_step_regex_nested_quantifier_redos() -> None:
    """Vérifie la détection formelle de l'expression régulière ReDoS de split STEP (nested quantifiers)."""
    code_step_redos = """
import re

def parse_step_records(raw_args: str) -> list:
    # Pattern avec répétitions imbriquées causant du ReDoS exponentiel
    pattern = r",(?=(?:[^']*'[^']*')*[^']*$)"
    return re.split(pattern, raw_args)
"""
    findings = audit_python_code_security(code_step_redos, filename="step_importer.py")
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_STEP_REDOS_NESTED_QUANTIFIER" in rule_ids

    f = next(item for item in findings if item.rule_id == "SEC_STEP_REDOS_NESTED_QUANTIFIER")
    assert f.severity == SecuritySeverity.CRITICAL
    assert f.category == SecurityCategory.REGEX_DOS


def test_step_regex_dotall_unbounded() -> None:
    """Vérifie la détection d'expressions re.DOTALL avec joker glouton .* sans limite."""
    code_dotall = r"""
import re

def extract_step_data_section(content: str) -> str:
    match = re.search(r"DATA\s*;(.*)ENDSEC\s*;", content, flags=re.DOTALL)
    return match.group(1) if match else ""
"""
    findings = audit_python_code_security(code_dotall, filename="step_data_reader.py")
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_STEP_REDOS_DOTALL_UNBOUNDED" in rule_ids


def test_geometric_division_by_zero_sliver_detection() -> None:
    """Vérifie la détection des divisions géométriques non protégées par un seuil epsilon."""
    code_sliver_div = """
def compute_triangle_face_normal(cross_product, norm):
    # Division directe sans vérification norm > epsilon
    return cross_product / norm
"""
    findings = audit_python_code_security(code_sliver_div, filename="mesh_normals.py")
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_GEOMETRIC_SLIVER_DIVISION_BY_ZERO" in rule_ids


def test_geometric_division_with_epsilon_is_safe() -> None:
    """Vérifie qu'une division géométrique protégée par un seuil epsilon ne déclenche pas d'alerte."""
    code_safe_div = """
def compute_triangle_face_normal_safe(cross_product, norm):
    if norm < 1e-9:
        return [0.0, 0.0, 1.0]
    return cross_product / norm
"""
    findings = audit_python_code_security(code_safe_div, filename="safe_mesh_normals.py")
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_GEOMETRIC_SLIVER_DIVISION_BY_ZERO" not in rule_ids


def test_geometric_unbounded_subdivision_while_loop() -> None:
    """Vérifie la détection des boucles de raffinement de maillage infinies sans compteur max."""
    code_unbounded_subdiv = """
def refine_sliver_triangles(mesh_faces):
    while has_degeneracies(mesh_faces):
        mesh_faces = split_longest_edges(mesh_faces)
"""
    findings = audit_python_code_security(code_unbounded_subdiv, filename="mesh_refinement.py")
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_GEOMETRIC_UNBOUNDED_SUBDIVISION" in rule_ids


def test_runtime_analyze_regex_redos_risk() -> None:
    """Vérifie l'analyseur déterministe runtime de regex ReDoS."""
    # Motifs vulnérables
    assert analyze_regex_redos_risk(r",(?=(?:[^']*'[^']*')*[^']*$)")[0] is True
    assert analyze_regex_redos_risk(r"(a+)+")[0] is True
    assert analyze_regex_redos_risk(r"(\w+)+")[0] is True
    assert analyze_regex_redos_risk(r"([0-9]+){2,}")[0] is True

    # Motifs sécurisés
    assert analyze_regex_redos_risk(r"^[a-zA-Z0-9_-]+$")[0] is False
    assert analyze_regex_redos_risk(r"(a|b)*")[0] is False
    assert analyze_regex_redos_risk(r"#(\d+)\s*=\s*([A-Za-z0-9_]+)\s*\((.*?)\)\s*;")[0] is False


def test_runtime_is_sliver_triangle() -> None:
    """Vérifie le calcul géométrique runtime du ratio d'aspect des triangles effilés."""
    # Triangle équilatéral parfait : ratio d'aspect idéal ~ 1.0
    eq_p0 = (0.0, 0.0, 0.0)
    eq_p1 = (1.0, 0.0, 0.0)
    eq_p2 = (0.5, 0.86602540378, 0.0)
    assert is_sliver_triangle(eq_p0, eq_p1, eq_p2, aspect_ratio_threshold=10.0) is False

    # Sliver triangle extrême (quasi colinéaire, base 1.0 et hauteur 1e-6)
    sliver_p0 = (0.0, 0.0, 0.0)
    sliver_p1 = (1.0, 0.0, 0.0)
    sliver_p2 = (0.5, 1e-6, 0.0)
    assert is_sliver_triangle(sliver_p0, sliver_p1, sliver_p2, aspect_ratio_threshold=100.0) is True

    # Triangle totalement dégénéré (aire nulle)
    deg_p0 = (0.0, 0.0, 0.0)
    deg_p1 = (1.0, 1.0, 1.0)
    deg_p2 = (2.0, 2.0, 2.0)
    assert is_sliver_triangle(deg_p0, deg_p1, deg_p2) is True


# ==============================================================================
# 4. Tests OpenGL natif (glDrawElements count vs buffer size) et ctypes
# ==============================================================================

def test_opengl_invalid_count_detection() -> None:
    """Vérifie la détection d'appels glDrawElements ou glDrawArrays avec count invalide (<= 0)."""
    code_gl_invalid = """
import OpenGL.GL as GL

def draw_wireframe(indices, vertices):
    GL.glDrawElements(GL.GL_TRIANGLES, -1, GL.GL_UNSIGNED_INT, indices)
    GL.glDrawArrays(GL.GL_LINES, -5, 0)
"""
    findings = audit_python_code_security(code_gl_invalid, filename="gl_viewport.py")
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_OPENGL_INVALID_COUNT" in rule_ids


def test_opengl_buffer_overflow_detection() -> None:
    """Vérifie la détection d'appels glDrawElements sans vérification de taille du tampon d'indices."""
    code_gl_overflow = """
import OpenGL.GL as GL

def render_unverified_buffer(indices, count):
    # Appel direct avec count sans vérifier len(indices) ni si le buffer est vide
    GL.glDrawElements(GL.GL_TRIANGLES, count, GL.GL_UNSIGNED_INT, indices)
"""
    findings = audit_python_code_security(code_gl_overflow, filename="gl_draw.py")
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_OPENGL_BUFFER_OVERFLOW" in rule_ids


def test_opengl_safe_call_with_bounds_check() -> None:
    """Vérifie qu'un tracé OpenGL avec vérification de non-vacuité et taille ne déclenche pas d'alerte."""
    code_gl_safe = """
import OpenGL.GL as GL

def render_safe_mesh(buffer):
    if buffer.is_empty():
        return
    count = len(buffer.faces) * 3
    GL.glDrawElements(GL.GL_TRIANGLES, count, GL.GL_UNSIGNED_INT, buffer.faces)
"""
    findings = audit_python_code_security(code_gl_safe, filename="gl_safe_draw.py")
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_OPENGL_BUFFER_OVERFLOW" not in rule_ids
    assert "SEC_OPENGL_INVALID_COUNT" not in rule_ids


def test_ctypes_raw_memory_and_arbitrary_address() -> None:
    """Vérifie la détection de manipulations de mémoire brute et de pointeurs bruts ctypes."""
    code_ctypes = """
import ctypes

def copy_raw_buffer(src, dst):
    ctypes.memmove(dst, src, 1024)
    ptr = ctypes.c_void_p(0xDEADBEEF)
"""
    findings = audit_python_code_security(code_ctypes, filename="native_bridge.py")
    rule_ids = [f.rule_id for f in findings]
    assert "SEC_CTYPES_RAW_MEMORY" in rule_ids
    assert "SEC_CTYPES_ARBITRARY_ADDRESS" in rule_ids


def test_runtime_validate_opengl_draw_elements_bounds() -> None:
    """Vérifie l'utilitaire de validation de bornes OpenGL validate_opengl_draw_elements_bounds."""
    # Bornes valides
    assert validate_opengl_draw_elements_bounds(count=300, buffer_element_count=300) is True
    assert validate_opengl_draw_elements_bounds(count=150, buffer_element_count=300) is True

    # Dépassement de tampon (Buffer Overflow)
    assert validate_opengl_draw_elements_bounds(count=301, buffer_element_count=300) is False

    # Nombre d'éléments négatif ou nul
    assert validate_opengl_draw_elements_bounds(count=0, buffer_element_count=300) is False
    assert validate_opengl_draw_elements_bounds(count=-10, buffer_element_count=300) is False


# ==============================================================================
# 5. Validation 100% Autonome, Zéro Any et Zéro object
# ==============================================================================

def test_sast_scanner_strict_typing_zero_any_zero_object() -> None:
    """
    Examine formellement l'AST de scripts/security_sast_visitor.py pour certifier :
    - Zéro import de Any ou object
    - Zéro type Any ou object dans les annotations de fonctions et variables
    - 100% conformité aux règles d'excellence de typage.
    """
    script_path = os.path.join("scripts", "security_sast_visitor.py")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    tree = ast.parse(content, filename=script_path)
    forbidden_imports: list[str] = []
    forbidden_annotations: list[str] = []

    # Vérification des imports
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in ("Any", "object"):
                    forbidden_imports.append(f"Import '{alias.name}' interdit trouvé à la ligne {node.lineno}")

    # Vérification des annotations de typage
    for node in ast.walk(tree):
        if isinstance(node, (ast.AnnAssign, ast.arg, ast.FunctionDef, ast.AsyncFunctionDef)):
            ann = getattr(node, "annotation", None) or getattr(node, "returns", None)
            if ann is not None:
                ann_str = ast.unparse(ann)
                if "Any" in ann_str:
                    forbidden_annotations.append(f"Type interdit 'Any' dans '{ann_str}' à la ligne {node.lineno}")
                if "object" in ann_str:
                    forbidden_annotations.append(f"Type interdit 'object' dans '{ann_str}' à la ligne {node.lineno}")

    assert len(forbidden_imports) == 0, f"Imports interdits détectés : {forbidden_imports}"
    assert len(forbidden_annotations) == 0, f"Annotations interdites détectées : {forbidden_annotations}"


def test_sast_scanner_zero_external_dependencies() -> None:
    """Vérifie que scripts/security_sast_visitor.py n'importe aucune dépendance externe à Python."""
    script_path = os.path.join("scripts", "security_sast_visitor.py")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    tree = ast.parse(content, filename=script_path)
    imported_modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module.split(".")[0])

    # Seuls les modules de la bibliothèque standard Python et __future__ sont tolérés
    allowed_stdlib = sys.stdlib_module_names
    for mod in imported_modules:
        if mod == "__future__":
            continue
        assert mod in allowed_stdlib, f"Module externe non autorisé importé dans le scanner SAST : '{mod}'"


def test_report_formatting_and_cli() -> None:
    """Vérifie la mise en forme du rapport SAST et l'exécution du point d'entrée CLI main()."""
    findings_map = {
        "test_file.py": [
            SecurityFinding(
                rule_id="SEC_ZIP_SLIP_EXTRACTALL",
                category=SecurityCategory.PATH_TRAVERSAL,
                severity=SecuritySeverity.HIGH,
                line_number=10,
                column_offset=4,
                message="Extraction sans commonpath.",
                recommendation="Utiliser os.path.commonpath.",
                code_snippet="zf.extractall(dest)"
            )
        ]
    }
    report = format_security_report(findings_map)
    assert "RAPPORT D'AUDIT SAST DE SÉCURITÉ CAO/FAO 3D" in report
    assert "SEC_ZIP_SLIP_EXTRACTALL" in report

    # Test de main() sur un fichier temporaire propre
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write("def add(a: int, b: int) -> int:\n    return a + b\n")
        tmp_name = tmp.name

    try:
        exit_code = sast_main([tmp_name])
        assert exit_code == 0
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
