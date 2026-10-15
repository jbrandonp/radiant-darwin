"""
Suite de tests déterministes pour l'Auditeur Supply Chain, SBOM CycloneDX v1.5 et OpenSSF Scorecard.
Typage statique strict : zéro Any et zéro object.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Dict, List, Optional, Set, Tuple, Union
import pytest

from scripts.supply_chain_auditor import (
    LicenseCategory,
    LicenseCompatibility,
    VulnerabilitySeverity,
    ScorecardCheckStatus,
    ComponentHash,
    DependencyComponent,
    VulnerabilityFinding,
    OpenSSFScorecardItem,
    OpenSSFScorecardReport,
    SupplyChainAuditReport,
    LicenseRegistry,
    CycloneDXSBOMGenerator,
    OSVClient,
    OpenSSFScorecardEvaluator,
    SupplyChainAuditor,
)


class TestLicenseRegistry:
    """Banc de tests pour le registre et la classification SPDX des licences."""

    def test_normalize_permissive_classifiers(self) -> None:
        """Vérifie la normalisation des licences permissives usuelles."""
        assert LicenseRegistry.normalize_to_spdx("", ["License :: OSI Approved :: MIT License"]) == "MIT"
        assert LicenseRegistry.normalize_to_spdx("", ["License :: OSI Approved :: Apache Software License"]) == "Apache-2.0"
        assert LicenseRegistry.normalize_to_spdx("", ["License :: OSI Approved :: BSD License"]) == "BSD-3-Clause"

    def test_normalize_raw_strings(self) -> None:
        """Vérifie la normalisation à partir des chaînes brutes de métadonnées."""
        assert LicenseRegistry.normalize_to_spdx("MIT License", []) == "MIT"
        assert LicenseRegistry.normalize_to_spdx("Apache 2.0", []) == "Apache-2.0"
        assert LicenseRegistry.normalize_to_spdx("GPLv3", []) == "GPL-3.0-only"
        assert LicenseRegistry.normalize_to_spdx("AGPLv3+", []) == "AGPL-3.0-only"
        assert LicenseRegistry.normalize_to_spdx("LGPL-3.0", []) == "LGPL-3.0-only"

    def test_classify_permissive(self) -> None:
        """Valide la classification des licences permissives compatibles."""
        cat, comp = LicenseRegistry.classify("MIT")
        assert cat == LicenseCategory.PERMISSIVE
        assert comp == LicenseCompatibility.COMPLIANT

        cat2, comp2 = LicenseRegistry.classify("Apache-2.0")
        assert cat2 == LicenseCategory.PERMISSIVE
        assert comp2 == LicenseCompatibility.COMPLIANT

    def test_classify_weak_copyleft(self) -> None:
        """Valide la détection des licences à copyleft faible (LGPL, MPL)."""
        cat, comp = LicenseRegistry.classify("LGPL-3.0-only")
        assert cat == LicenseCategory.WEAK_COPYLEFT
        assert comp == LicenseCompatibility.WARNING

        cat2, comp2 = LicenseRegistry.classify("MPL-2.0")
        assert cat2 == LicenseCategory.WEAK_COPYLEFT
        assert comp2 == LicenseCompatibility.WARNING

    def test_classify_strong_copyleft_contaminating(self) -> None:
        """Valide l'alerte de contamination virale pour les licences GPL et AGPL."""
        cat, comp = LicenseRegistry.classify("GPL-3.0-only")
        assert cat == LicenseCategory.STRONG_COPYLEFT
        assert comp == LicenseCompatibility.INCOMPATIBLE_CONTAMINATING

        cat2, comp2 = LicenseRegistry.classify("AGPL-3.0-only")
        assert cat2 == LicenseCategory.STRONG_COPYLEFT
        assert comp2 == LicenseCompatibility.INCOMPATIBLE_CONTAMINATING


class TestCycloneDXSBOMGenerator:
    """Banc de tests pour le générateur SBOM CycloneDX v1.5 JSON."""

    def test_cyclonedx_schema_and_metadata(self) -> None:
        """Valide la conformité du format CycloneDX v1.5 généré."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pyproj = tmp_path / "pyproject.toml"
            pyproj.write_text(
                """
                [project]
                name = "test-project"
                version = "1.0.0"
                dependencies = ["numpy>=1.26.0"]
                [project.optional-dependencies]
                dev = ["pytest>=8.0.0"]
                """,
                encoding="utf-8"
            )

            generator = CycloneDXSBOMGenerator(tmp_path)
            assert "numpy" in generator.direct_deps
            assert "pytest" in generator.direct_deps

            comp = DependencyComponent(
                name="numpy",
                version="2.0.0",
                purl="pkg:pypi/numpy@2.0.0",
                bom_ref="pkg:pypi/numpy@2.0.0",
                is_direct=True,
                scope="required",
                license_declared="BSD-3-Clause",
                spdx_id="BSD-3-Clause",
                license_category=LicenseCategory.PERMISSIVE,
                license_status=LicenseCompatibility.COMPLIANT,
                summary="NumPy numeric library",
                author="Travis Oliphant",
                dependencies=[],
                hashes=[ComponentHash(algorithm="SHA-256", value="abcdef123456")]
            )

            sbom = generator.generate_cyclonedx_sbom(
                components=[comp],
                dependency_graph={"numpy": []},
                root_name="test-project",
                root_version="1.0.0"
            )

            assert sbom["$schema"] == "http://cyclonedx.org/schema/bom-1.5.json"
            assert sbom["bomFormat"] == "CycloneDX"
            assert sbom["specVersion"] == "1.5"
            assert isinstance(sbom["serialNumber"], str)
            assert str(sbom["serialNumber"]).startswith("urn:uuid:")

            metadata = sbom["metadata"]
            assert isinstance(metadata, dict)
            assert metadata["component"]["name"] == "test-project"

            comps = sbom["components"]
            assert isinstance(comps, list)
            assert len(comps) == 1
            c_dict = comps[0]
            assert c_dict["name"] == "numpy"
            assert c_dict["version"] == "2.0.0"
            assert c_dict["purl"] == "pkg:pypi/numpy@2.0.0"
            assert c_dict["licenses"][0]["license"]["id"] == "BSD-3-Clause"

            deps = sbom["dependencies"]
            assert isinstance(deps, list)
            assert len(deps) == 2  # racine + numpy


class TestOSVClient:
    """Banc de tests pour le connecteur OSV (Open Source Vulnerabilities)."""

    def test_offline_vulnerability_detection(self) -> None:
        """Valide la détection et la classification de vulnérabilités via la base hors-ligne."""
        client = OSVClient(allow_network=False)
        client.add_offline_vulnerability(
            package_name="vulnerable-pkg",
            vuln_id="GHSA-test-1234",
            severity="CRITICAL",
            cvss_score=9.8,
            summary="Remote Code Execution vulnerability in vulnerable-pkg",
            fixed_version="2.1.0",
            aliases=["CVE-2024-99999"]
        )

        findings = client.query_package_vulnerabilities("vulnerable-pkg", "1.0.0")
        assert len(findings) == 1
        finding = findings[0]
        assert finding.id == "GHSA-test-1234"
        assert finding.severity == VulnerabilitySeverity.CRITICAL
        assert finding.cvss_score == 9.8
        assert finding.fixed_version == "2.1.0"
        assert "CVE-2024-99999" in finding.aliases

    def test_batch_query_offline(self) -> None:
        """Valide le fonctionnement des requêtes batch avec cache local."""
        client = OSVClient(allow_network=False)
        client.add_offline_vulnerability(
            package_name="bad-lib",
            vuln_id="PYSEC-2024-11",
            severity="HIGH",
            cvss_score=7.5,
            summary="SQL injection risk",
            fixed_version="3.0.0"
        )

        comps = [
            DependencyComponent(
                name="safe-lib",
                version="1.0.0",
                purl="pkg:pypi/safe-lib@1.0.0",
                bom_ref="pkg:pypi/safe-lib@1.0.0",
                is_direct=True,
                scope="required",
                license_declared="MIT",
                spdx_id="MIT",
                license_category=LicenseCategory.PERMISSIVE,
                license_status=LicenseCompatibility.COMPLIANT,
                summary="",
                author="",
            ),
            DependencyComponent(
                name="bad-lib",
                version="1.0.0",
                purl="pkg:pypi/bad-lib@1.0.0",
                bom_ref="pkg:pypi/bad-lib@1.0.0",
                is_direct=True,
                scope="required",
                license_declared="MIT",
                spdx_id="MIT",
                license_category=LicenseCategory.PERMISSIVE,
                license_status=LicenseCompatibility.COMPLIANT,
                summary="",
                author="",
            )
        ]

        batch_findings = client.query_batch(comps)
        assert len(batch_findings) == 1
        assert batch_findings[0].package_name == "bad-lib"
        assert batch_findings[0].severity == VulnerabilitySeverity.HIGH


class TestOpenSSFScorecardEvaluator:
    """Banc de tests pour les contrôles OpenSSF Scorecard."""

    def test_dependency_pinning_with_lockfile(self) -> None:
        """Valide que la présence d'un lockfile accorde la note maximale 10/10."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            lockfile = tmp_path / "requirements.lock"
            lockfile.write_text("numpy==2.0.0\nscipy==1.14.0\n", encoding="utf-8")

            evaluator = OpenSSFScorecardEvaluator(tmp_path)
            item = evaluator.check_dependency_pinning()
            assert item.status == ScorecardCheckStatus.PASS
            assert item.score == 10.0

    def test_dependency_pinning_loose_ranges(self) -> None:
        """Valide que les versions flottantes sans lockfile déclenchent une alerte."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pyproj = tmp_path / "pyproject.toml"
            pyproj.write_text(
                """
                [project]
                name = "demo"
                dependencies = [
                    "numpy>=1.26.0",
                    "scipy>=1.12.0"
                ]
                """,
                encoding="utf-8"
            )

            evaluator = OpenSSFScorecardEvaluator(tmp_path)
            item = evaluator.check_dependency_pinning()
            assert item.status == ScorecardCheckStatus.FAIL
            assert item.score == 0.0

    def test_hostile_install_scripts_detection(self) -> None:
        """Valide la détection de scripts d'installation hostiles contenant de l'obfuscation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            setup_py = tmp_path / "setup.py"
            setup_py.write_text(
                """
                from setuptools import setup
                import base64
                eval(base64.b64decode('cHJpbnQoImhhY2tlZCIp'))
                setup(name="malicious-pkg")
                """,
                encoding="utf-8"
            )

            evaluator = OpenSSFScorecardEvaluator(tmp_path)
            item = evaluator.check_hostile_install_scripts()
            assert item.status == ScorecardCheckStatus.FAIL
            assert item.score < 6.0
            assert any("base64.b64decode" in d for d in item.details)

    def test_typosquatting_detection(self) -> None:
        """Valide la détection de packages trompeurs simulant des standards PyPI."""
        evaluator = OpenSSFScorecardEvaluator(Path.cwd())
        # 'reqeusts' au lieu de 'requests' -> distance 1 (transposition/faute)
        # 'pydanticc' -> distance 1
        item = evaluator.check_typosquatting(["reqeusts", "numpy", "pydanticc"])
        assert item.status == ScorecardCheckStatus.FAIL
        assert len(item.details) >= 1


class TestSupplyChainAuditorIntegration:
    """Banc de tests d'intégration du moteur complet d'audit Supply Chain."""

    def test_full_audit_execution(self) -> None:
        """Vérifie l'exécution complète de l'audit et l'intégrité du rapport consolidé."""
        auditor = SupplyChainAuditor(project_root=Path.cwd(), allow_network=True)
        report = auditor.run_full_audit()

        assert report.total_components > 0
        assert report.direct_components > 0
        assert report.openssf_scorecard.overall_score >= 6.5
        assert report.passed_quality_gate is True
        assert len(report.contaminating_licenses) == 0

    def test_requirements_lock_generation(self) -> None:
        """Vérifie la génération du fichier requirements.lock avec versions figées."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            lock_path = tmp_path / "test_requirements.lock"

            auditor = SupplyChainAuditor(project_root=Path.cwd(), allow_network=False)
            generated_path = auditor.generate_requirements_lock(lock_path)

            assert generated_path.exists()
            content = generated_path.read_text(encoding="utf-8")
            assert "numpy==" in content
            assert "scipy==" in content
            assert "trimesh==" in content
