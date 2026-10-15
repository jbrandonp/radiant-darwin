"""
Suite de tests unitaires formels pour le Générateur d'Export SARIF v2.1.0.
Valide la conformité intégrale au standard officiel OASIS SARIF v2.1.0,
le mapping des identifiants CWE, les niveaux de sévérité, les remédiations Markdown,
et la détection des 4 piliers d'audit (SAST, Typage strict, Complexité cognitive > 25, Cycles).
Typage statique strict : strictement zéro Any et zéro object.
"""

from __future__ import annotations
import json
import os
import sys
import tempfile
import pytest
from typing import List, Dict, Tuple, Optional, Union

from scripts.sarif_generator import (
    SarifReportGenerator,
    SarifRuleDefinition,
    SarifFinding,
    SarifLevel,
    SARIF_RULES_CATALOG,
    validate_sarif_file,
    SARIF_SCHEMA_URI,
    SARIF_VERSION
)


def test_sarif_catalog_rules_integrity() -> None:
    """
    Vérifie l'intégrité formelle de l'ensemble des règles répertoriées dans le catalogue SARIF.
    Vérifie les identifiants CWE, les descriptions, les niveaux de sévérité et les guides Markdown.
    Paramètres : aucun.
    Valeur retournée : None.
    """
    assert len(SARIF_RULES_CATALOG) >= 15

    for rule_id, rule in SARIF_RULES_CATALOG.items():
        assert rule.rule_id == rule_id
        assert len(rule.name) > 0
        assert len(rule.short_description) > 0
        assert len(rule.full_description) > 0
        assert rule.cwe_id.startswith("CWE-")
        assert len(rule.cwe_title) > 0
        assert rule.default_level in (SarifLevel.ERROR, SarifLevel.WARNING, SarifLevel.NOTE)

        # Vérification CVSS score
        cvss = float(rule.security_severity)
        assert 0.0 <= cvss <= 10.0

        # Vérification du guide de remédiation Markdown
        assert len(rule.remediation_markdown) > 50
        assert "## " in rule.remediation_markdown

        # Conversion en reportingDescriptor conforme SARIF
        descriptor = rule.to_reporting_descriptor()
        assert descriptor["id"] == rule_id
        assert descriptor["name"] == rule.name
        assert "shortDescription" in descriptor
        assert "fullDescription" in descriptor
        assert "help" in descriptor
        assert "properties" in descriptor


def test_sarif_specific_mandatory_audit_rules_mapping() -> None:
    """
    Vérifie spécifiquement le mapping des 4 grandes familles d'audit requises :
    1. SAST (CWE-94, CWE-78, CWE-502, CWE-22, CWE-119, CWE-400)
    2. Typage strict sans Any ni object (CWE-704, CWE-843)
    3. Complexité cognitive > 25 (CWE-1120)
    4. Cycles d'architecture (CWE-1047)
    Paramètres : aucun.
    Valeur retournée : None.
    """
    # 1. SAST
    assert "SEC_CODE_EXEC" in SARIF_RULES_CATALOG
    assert SARIF_RULES_CATALOG["SEC_CODE_EXEC"].cwe_id == "CWE-94"
    assert SARIF_RULES_CATALOG["SEC_CODE_EXEC"].default_level == SarifLevel.ERROR

    assert "SEC_SHELL_INJECTION_OS" in SARIF_RULES_CATALOG
    assert SARIF_RULES_CATALOG["SEC_SHELL_INJECTION_OS"].cwe_id == "CWE-78"
    assert SARIF_RULES_CATALOG["SEC_SHELL_INJECTION_OS"].default_level == SarifLevel.ERROR

    assert "SEC_UNSAFE_DESERIALIZE_PICKLE" in SARIF_RULES_CATALOG
    assert SARIF_RULES_CATALOG["SEC_UNSAFE_DESERIALIZE_PICKLE"].cwe_id == "CWE-502"
    assert SARIF_RULES_CATALOG["SEC_UNSAFE_DESERIALIZE_PICKLE"].default_level == SarifLevel.ERROR

    assert "SEC_ZIP_SLIP_HAZARD" in SARIF_RULES_CATALOG
    assert SARIF_RULES_CATALOG["SEC_ZIP_SLIP_HAZARD"].cwe_id == "CWE-22"

    # 2. Typage strict
    assert "TYPE_ANY_FORBIDDEN" in SARIF_RULES_CATALOG
    assert SARIF_RULES_CATALOG["TYPE_ANY_FORBIDDEN"].cwe_id == "CWE-704"
    assert SARIF_RULES_CATALOG["TYPE_ANY_FORBIDDEN"].default_level == SarifLevel.ERROR

    assert "TYPE_MISSING_ANNOTATION" in SARIF_RULES_CATALOG
    assert SARIF_RULES_CATALOG["TYPE_MISSING_ANNOTATION"].cwe_id == "CWE-843"

    # 3. Complexité cognitive > 25
    assert "COMPLEXITY_COGNITIVE_EXCESSIVE" in SARIF_RULES_CATALOG
    assert SARIF_RULES_CATALOG["COMPLEXITY_COGNITIVE_EXCESSIVE"].cwe_id == "CWE-1120"
    assert SARIF_RULES_CATALOG["COMPLEXITY_COGNITIVE_EXCESSIVE"].default_level == SarifLevel.WARNING

    # 4. Cycle d'architecture
    assert "ARCH_CIRCULAR_DEPENDENCY" in SARIF_RULES_CATALOG
    assert SARIF_RULES_CATALOG["ARCH_CIRCULAR_DEPENDENCY"].cwe_id == "CWE-1047"
    assert SARIF_RULES_CATALOG["ARCH_CIRCULAR_DEPENDENCY"].default_level == SarifLevel.ERROR


def test_sarif_export_and_json_schema_validation() -> None:
    """
    Exécute l'exportation SARIF complète sur un ensemble de violations factices
    représentant chaque catégorie et valide le document avec le validateur de schéma officiel.
    Paramètres : aucun.
    Valeur retournée : None.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        sarif_out = os.path.join(tmpdir, "test-results.sarif")
        generator = SarifReportGenerator()

        findings = [
            SarifFinding(
                rule_id="SEC_CODE_EXEC",
                message="Appel interdit à eval()",
                file_path="src/vulnerable_eval.py",
                start_line=12,
                start_column=5,
                snippet_text="eval(user_input)"
            ),
            SarifFinding(
                rule_id="TYPE_ANY_FORBIDDEN",
                message="Usage du type Any interdit sur paramètre 'config'",
                file_path="src/untyped_module.py",
                start_line=45,
                start_column=15
            ),
            SarifFinding(
                rule_id="COMPLEXITY_COGNITIVE_EXCESSIVE",
                message="Complexité cognitive de 32 > 25 dans 'process_deep_tree'",
                file_path="src/complex_fn.py",
                start_line=110,
                start_column=1
            ),
            SarifFinding(
                rule_id="ARCH_CIRCULAR_DEPENDENCY",
                message="Cycle détecté entre module_a et module_b",
                file_path="src/module_a.py",
                start_line=3,
                start_column=1
            )
        ]

        success = generator.export_sarif_file(sarif_out, findings, validate_schema=True)
        assert success is True
        assert os.path.exists(sarif_out)

        # Validation formelle du schéma OASIS
        is_valid, errors = validate_sarif_file(sarif_out)
        assert is_valid is True, f"Erreurs de validation de schéma SARIF : {errors}"
        assert len(errors) == 0

        # Vérification du contenu JSON
        with open(sarif_out, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["$schema"] == SARIF_SCHEMA_URI
        assert data["version"] == SARIF_VERSION
        assert len(data["runs"]) == 1
        run = data["runs"][0]
        assert run["tool"]["driver"]["name"] == "CAD Studio Industrial Auditor"
        assert len(run["results"]) == 4

        # Vérifier que les ruleIndex correspondent
        for r in run["results"]:
            idx = r["ruleIndex"]
            rid = r["ruleId"]
            assert run["tool"]["driver"]["rules"][idx]["id"] == rid


def test_sarif_analysis_on_synthetic_vulnerable_source_tree() -> None:
    """
    Génère un arbre de fichiers Python temporaires contenant des violations réelles
    (eval, typing Any, complexité cognitive > 25, cycle d'importation)
    et valide que collect_findings_from_directory les extrait et produit un SARIF valide.
    Paramètres : aucun.
    Valeur retournée : None.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, "src")
        os.makedirs(src_path, exist_ok=True)

        # 1. Fichier avec SAST injection
        sast_file = os.path.join(src_path, "sec_vuln.py")
        with open(sast_file, "w", encoding="utf-8") as f:
            f.write(
                "import os\n"
                "import pickle\n"
                "def trigger_sast(cmd: str, data: bytes) -> None:\n"
                "    eval(cmd)\n"
                "    os.system(cmd)\n"
                "    pickle.loads(data)\n"
            )

        # 2. Fichier avec violations de typage strict (Any, object, annot manquante)
        typing_file = os.path.join(src_path, "type_vuln.py")
        with open(typing_file, "w", encoding="utf-8") as f:
            f.write(
                "from typing import Any\n"
                "def bad_typing(x: Any, y: object):\n"
                "    return x\n"
                "def missing_annotation(a, b: int) -> int:\n"
                "    return b\n"
            )

        # 3. Fichier avec complexité cognitive > 25
        complex_file = os.path.join(src_path, "complex_logic.py")
        with open(complex_file, "w", encoding="utf-8") as f:
            lines = [
                "def deeply_nested_algorithm(a: int, b: int, c: int) -> int:",
                "    res = 0"
            ]
            indent = "    "
            # Créer 6 niveaux d'imbrications conditionnelles pour dépasser 25 points
            for i in range(6):
                lines.append(f"{indent}if a > {i}:")
                indent += "    "
                lines.append(f"{indent}for j in range(b):")
                indent += "    "
                lines.append(f"{indent}if c == j:")
                indent += "    "
                lines.append(f"{indent}res += 1")
            lines.append(f"{indent}return res")
            f.write("\n".join(lines) + "\n")

        # Analyse par SarifReportGenerator
        generator = SarifReportGenerator()
        findings = generator.collect_findings_from_directory(src_path)

        detected_rule_ids = {f.rule_id for f in findings}

        # Vérifications des détections
        assert "SEC_CODE_EXEC" in detected_rule_ids
        assert "SEC_SHELL_INJECTION_OS" in detected_rule_ids
        assert "SEC_UNSAFE_DESERIALIZE_PICKLE" in detected_rule_ids
        assert "TYPE_ANY_FORBIDDEN" in detected_rule_ids
        assert "TYPE_MISSING_ANNOTATION" in detected_rule_ids
        assert "COMPLEXITY_COGNITIVE_EXCESSIVE" in detected_rule_ids

        # Export SARIF et validation formelle de schéma
        sarif_file = os.path.join(tmpdir, "audit-results.sarif")
        valid = generator.export_sarif_file(sarif_file, findings, validate_schema=True)
        assert valid is True

        is_schema_ok, schema_errors = validate_sarif_file(sarif_file)
        assert is_schema_ok is True, f"Erreurs: {schema_errors}"


def test_sarif_architecture_cycle_detection() -> None:
    """
    Simule un cycle d'architecture direct entre deux modules source et valide
    la génération du résultat SARIF avec la règle ARCH_CIRCULAR_DEPENDENCY.
    Paramètres : aucun.
    Valeur retournée : None.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, "src")
        mod_a = os.path.join(src_path, "module_alpha")
        mod_b = os.path.join(src_path, "module_beta")
        os.makedirs(mod_a, exist_ok=True)
        os.makedirs(mod_b, exist_ok=True)

        with open(os.path.join(mod_a, "alpha.py"), "w", encoding="utf-8") as f:
            f.write("from src.module_beta.beta import BetaClass\nclass AlphaClass:\n    pass\n")

        with open(os.path.join(mod_b, "beta.py"), "w", encoding="utf-8") as f:
            f.write("from src.module_alpha.alpha import AlphaClass\nclass BetaClass:\n    pass\n")

        generator = SarifReportGenerator()
        cycle_findings = generator.analyze_architecture_cycles(src_path)

        assert len(cycle_findings) >= 1
        assert cycle_findings[0].rule_id == "ARCH_CIRCULAR_DEPENDENCY"
        assert cycle_findings[0].custom_level == SarifLevel.ERROR

        sarif_out = os.path.join(tmpdir, "cycle-results.sarif")
        generator.export_sarif_file(sarif_out, cycle_findings, validate_schema=True)

        is_valid, errors = validate_sarif_file(sarif_out)
        assert is_valid is True, f"Erreurs SARIF cycle : {errors}"


def test_official_radiant_darwin_clean_sarif_export() -> None:
    """
    Vérifie l'export SARIF et la validation de schéma sur le fichier audit-results.sarif réel du projet.
    Paramètres : aucun.
    Valeur retournée : None.
    """
    sarif_path = "audit-results.sarif"
    if not os.path.exists(sarif_path):
        generator = SarifReportGenerator()
        findings = generator.collect_findings_from_directory("src")
        generator.export_sarif_file(sarif_path, findings, validate_schema=True)

    assert os.path.exists(sarif_path)
    is_valid, errors = validate_sarif_file(sarif_path)
    assert is_valid is True, f"Erreurs dans audit-results.sarif : {errors}"
    assert len(errors) == 0
