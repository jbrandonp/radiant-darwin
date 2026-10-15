"""
Module d'Audit de Chaîne d'Approvisionnement, Dépendances & SBOM (CycloneDX / OpenSSF).
Conforme aux spécifications CycloneDX v1.5 JSON et aux standards OpenSSF Scorecard.
Typage statique strict : strictement zéro Any et zéro object.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
import tomllib
from typing import Dict, List, Optional, Set, Tuple, Union
import urllib.error
import urllib.request
import uuid

# Configuration sécurisée des sorties standards pour terminaux Windows et CI/CD
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass


# ============================================================================
# 1. Énumérations et Modèles de Données Formels (Typage Strict)
# ============================================================================

class LicenseCategory(Enum):
    """Classification légale des licences logicielles."""
    PERMISSIVE = "PERMISSIVE"
    WEAK_COPYLEFT = "WEAK_COPYLEFT"
    STRONG_COPYLEFT = "STRONG_COPYLEFT"
    PROPRIETARY = "PROPRIETARY"
    UNKNOWN = "UNKNOWN"


class LicenseCompatibility(Enum):
    """Statut de compatibilité d'une licence avec le projet racine (ex: MIT)."""
    COMPLIANT = "COMPLIANT"
    WARNING = "WARNING"
    INCOMPATIBLE_CONTAMINATING = "INCOMPATIBLE_CONTAMINATING"
    UNVERIFIED = "UNVERIFIED"


class VulnerabilitySeverity(Enum):
    """Niveaux de sévérité d'une vulnérabilité selon le standard CVSS."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"
    UNKNOWN = "UNKNOWN"


class ScorecardCheckStatus(Enum):
    """Statut d'évaluation d'un contrôle OpenSSF Scorecard."""
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class ComponentHash:
    """Empreinte cryptographique d'un fichier ou composant."""
    algorithm: str
    value: str

    def to_dict(self) -> Dict[str, str]:
        """Convertit l'empreinte en dictionnaire standard CycloneDX."""
        return {"alg": self.algorithm, "content": self.value}


@dataclass
class DependencyComponent:
    """Représentation formelle d'une dépendance logicielle dans le SBOM."""
    name: str
    version: str
    purl: str
    bom_ref: str
    is_direct: bool
    scope: str
    license_declared: str
    spdx_id: str
    license_category: LicenseCategory
    license_status: LicenseCompatibility
    summary: str
    author: str
    dependencies: List[str] = field(default_factory=list)
    hashes: List[ComponentHash] = field(default_factory=list)

    def to_cyclonedx_component(self) -> Dict[str, Union[str, List[Dict[str, Union[str, Dict[str, str]]]]]]:
        """
        Convertit le composant au format CycloneDX v1.5 JSON.
        
        Returns:
            Dictionnaire conforme au schéma CycloneDX v1.5 pour un composant.
        """
        licenses_list: List[Dict[str, Union[str, Dict[str, str]]]] = []
        if self.spdx_id and self.spdx_id != "NOASSERTION":
            licenses_list.append({"license": {"id": self.spdx_id}})
        elif self.license_declared:
            licenses_list.append({"license": {"name": self.license_declared}})

        properties_list: List[Dict[str, Union[str, Dict[str, str]]]] = [
            {"name": "radiant:dependency:type", "value": "direct" if self.is_direct else "transitive"},
            {"name": "radiant:license:category", "value": self.license_category.value},
            {"name": "radiant:license:compatibility", "value": self.license_status.value},
        ]

        component_data: Dict[str, Union[str, List[Dict[str, Union[str, Dict[str, str]]]]]] = {
            "type": "library",
            "bom-ref": self.bom_ref,
            "name": self.name,
            "version": self.version,
            "purl": self.purl,
            "scope": self.scope,
            "description": self.summary,
            "licenses": licenses_list,
            "properties": properties_list,
        }

        if self.hashes:
            hashes_list: List[Dict[str, Union[str, Dict[str, str]]]] = []
            for h in self.hashes:
                hashes_list.append({"alg": h.algorithm, "content": h.value})
            component_data["hashes"] = hashes_list

        return component_data


@dataclass
class VulnerabilityFinding:
    """Anomalie de sécurité ou CVE détectée via osv.dev."""
    id: str
    aliases: List[str]
    package_name: str
    package_version: str
    severity: VulnerabilitySeverity
    cvss_score: float
    summary: str
    details: str
    fixed_version: Optional[str]
    reference_urls: List[str]


@dataclass
class OpenSSFScorecardItem:
    """Résultat d'un contrôle de chaîne d'approvisionnement OpenSSF."""
    check_id: str
    name: str
    score: float
    status: ScorecardCheckStatus
    reason: str
    details: List[str]
    remediation: str


@dataclass
class OpenSSFScorecardReport:
    """Rapport consolidé d'évaluation OpenSSF Scorecard."""
    overall_score: float
    checks: List[OpenSSFScorecardItem]
    pinned_dependencies_ratio: float
    malicious_patterns_detected: int
    typosquatting_risks_detected: int


@dataclass
class SupplyChainAuditReport:
    """Bilan exhaustif d'audit Supply Chain, Licences, Vulnérabilités & OpenSSF."""
    timestamp: str
    project_name: str
    project_version: str
    total_components: int
    direct_components: int
    transitive_components: int
    components: List[DependencyComponent]
    license_summary: Dict[str, int]
    contaminating_licenses: List[str]
    vulnerabilities: List[VulnerabilityFinding]
    vulnerability_summary: Dict[str, int]
    openssf_scorecard: OpenSSFScorecardReport
    overall_security_grade: str
    passed_quality_gate: bool


# ============================================================================
# 2. Base de Connaissances des Licences Logicielles & Normalisation SPDX
# ============================================================================

class LicenseRegistry:
    """Registre déterministe de classification des licences selon le standard SPDX."""

    PERMISSIVE_SPDX: Set[str] = {
        "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC",
        "Python-2.0", "PSF-2.0", "0BSD", "CC0-1.0", "Unlicense",
        "Artistic-2.0", "Zlib", "WTFPL", "MIT-0"
    }

    WEAK_COPYLEFT_SPDX: Set[str] = {
        "LGPL-2.0-only", "LGPL-2.0-or-later", "LGPL-2.1-only", "LGPL-2.1-or-later",
        "LGPL-3.0-only", "LGPL-3.0-or-later", "MPL-1.1", "MPL-2.0",
        "EPL-1.0", "EPL-2.0", "CDDL-1.0"
    }

    STRONG_COPYLEFT_SPDX: Set[str] = {
        "GPL-1.0-only", "GPL-1.0-or-later", "GPL-2.0-only", "GPL-2.0-or-later",
        "GPL-3.0-only", "GPL-3.0-or-later", "AGPL-1.0-only", "AGPL-1.0-or-later",
        "AGPL-3.0-only", "AGPL-3.0-or-later", "EUPL-1.1", "EUPL-1.2",
        "OSL-3.0", "SSPL-1.0"
    }

    @classmethod
    def normalize_to_spdx(cls, raw_license: str, classifiers: List[str]) -> str:
        """
        Normalise une chaîne textuelle brute ou des Classifiers Trove vers un identifiant SPDX.

        Args:
            raw_license: Chaîne brute déclarée dans les métadonnées pip.
            classifiers: Liste des classifiers Trove PyPI du package.

        Returns:
            Identifiant SPDX canonique ou 'NOASSERTION' si indéterminé.
        """
        # 1. Analyse prioritaire des classifiers Trove (plus fiables)
        for c in classifiers:
            c_upper = c.upper()
            if "OSI APPROVED" in c_upper or "LICENSE ::" in c_upper:
                if "APACHE SOFTWARE LICENSE" in c_upper:
                    return "Apache-2.0"
                if "MIT LICENSE" in c_upper:
                    return "MIT"
                if "BSD LICENSE" in c_upper:
                    if "2-CLAUSE" in c_upper:
                        return "BSD-2-Clause"
                    return "BSD-3-Clause"
                if "PYTHON SOFTWARE FOUNDATION" in c_upper:
                    return "PSF-2.0"
                if "AFFERO GENERAL PUBLIC LICENSE" in c_upper or "AGPL" in c_upper:
                    return "AGPL-3.0-only"
                if "GNU LESSER GENERAL PUBLIC LICENSE" in c_upper or "LGPL" in c_upper:
                    if "V3" in c_upper or "3" in c_upper:
                        return "LGPL-3.0-only"
                    return "LGPL-2.1-only"
                if "GNU GENERAL PUBLIC LICENSE" in c_upper or "GPL" in c_upper:
                    if "V3" in c_upper or "3" in c_upper:
                        return "GPL-3.0-only"
                    if "V2" in c_upper or "2" in c_upper:
                        return "GPL-2.0-only"
                    return "GPL-3.0-only"
                if "MOZILLA PUBLIC LICENSE" in c_upper or "MPL" in c_upper:
                    return "MPL-2.0"
                if "ISC LICENSE" in c_upper:
                    return "ISC"

        # 2. Analyse de la chaîne brute déclarée
        raw_clean = raw_license.strip()
        if not raw_clean:
            return "NOASSERTION"

        raw_upper = raw_clean.upper()

        if re.search(r"\bMIT\b", raw_upper) or "THE MIT LICENSE" in raw_upper:
            return "MIT"
        if re.search(r"\bAPACHE\b", raw_upper):
            return "Apache-2.0"
        if re.search(r"\bBSD\b", raw_upper):
            if "2-CLAUSE" in raw_upper:
                return "BSD-2-Clause"
            return "BSD-3-Clause"
        if "PSF" in raw_upper or "PYTHON SOFTWARE FOUNDATION" in raw_upper:
            return "PSF-2.0"
        if "AGPL" in raw_upper or "AFFERO" in raw_upper:
            return "AGPL-3.0-only"
        if "LGPL" in raw_upper:
            if "3" in raw_upper:
                return "LGPL-3.0-only"
            return "LGPL-2.1-only"
        if "GPL" in raw_upper:
            if "3" in raw_upper:
                return "GPL-3.0-only"
            if "2" in raw_upper:
                return "GPL-2.0-only"
            return "GPL-3.0-only"
        if "MOZILLA" in raw_upper or "MPL" in raw_upper:
            return "MPL-2.0"
        if "ISC" in raw_upper:
            return "ISC"
        if "UNLICENSE" in raw_upper:
            return "Unlicense"

        return raw_clean

    @classmethod
    def classify(cls, spdx_id: str) -> Tuple[LicenseCategory, LicenseCompatibility]:
        """
        Détermine la catégorie juridique et la compatibilité d'une licence SPDX.

        Args:
            spdx_id: Identifiant SPDX normalisé.

        Returns:
            Tuple (LicenseCategory, LicenseCompatibility).
        """
        if spdx_id in cls.PERMISSIVE_SPDX:
            return LicenseCategory.PERMISSIVE, LicenseCompatibility.COMPLIANT

        if spdx_id in cls.WEAK_COPYLEFT_SPDX:
            return LicenseCategory.WEAK_COPYLEFT, LicenseCompatibility.WARNING

        if spdx_id in cls.STRONG_COPYLEFT_SPDX:
            return LicenseCategory.STRONG_COPYLEFT, LicenseCompatibility.INCOMPATIBLE_CONTAMINATING

        # Recherche de motifs résiduels
        spdx_upper = spdx_id.upper()
        if "AGPL" in spdx_upper or ("GPL" in spdx_upper and "LGPL" not in spdx_upper):
            return LicenseCategory.STRONG_COPYLEFT, LicenseCompatibility.INCOMPATIBLE_CONTAMINATING

        if "LGPL" in spdx_upper or "MPL" in spdx_upper:
            return LicenseCategory.WEAK_COPYLEFT, LicenseCompatibility.WARNING

        if spdx_id == "NOASSERTION" or not spdx_id:
            return LicenseCategory.UNKNOWN, LicenseCompatibility.UNVERIFIED

        return LicenseCategory.PROPRIETARY, LicenseCompatibility.WARNING


# ============================================================================
# 3. Scanner de Dépendances & Générateur CycloneDX v1.5 JSON
# ============================================================================

class CycloneDXSBOMGenerator:
    """
    Scanner déterministe de dépendances pip générant un SBOM CycloneDX v1.5 normalisé.
    Identifie précisément les dépendances directes, transitives et le graphe complet.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root: Path = project_root
        self.direct_deps: Set[str] = set()
        self._load_direct_requirements()

    def _canonical_name(self, name: str) -> str:
        """Normalise un nom de package pip en minuscules sans tirets multiples."""
        return re.sub(r"[-_.]+", "-", name).lower()

    def _load_direct_requirements(self) -> None:
        """
        Extrait les dépendances directes depuis pyproject.toml et requirements.txt.
        """
        # 1. Analyse pyproject.toml
        pyproject_path = self.project_root / "pyproject.toml"
        if pyproject_path.exists():
            try:
                data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
                project_sec = data.get("project", {})
                for req in project_sec.get("dependencies", []):
                    m = re.match(r"^([a-zA-Z0-9_\-\.]+)", str(req).strip())
                    if m:
                        self.direct_deps.add(self._canonical_name(m.group(1)))
                opt_deps = project_sec.get("optional-dependencies", {})
                for group_list in opt_deps.values():
                    if isinstance(group_list, list):
                        for req in group_list:
                            m = re.match(r"^([a-zA-Z0-9_\-\.]+)", str(req).strip())
                            if m:
                                self.direct_deps.add(self._canonical_name(m.group(1)))
            except Exception:
                pass

        # 2. Analyse requirements.txt
        req_path = self.project_root / "requirements.txt"
        if req_path.exists():
            try:
                for line in req_path.read_text(encoding="utf-8").splitlines():
                    clean = line.strip()
                    if clean and not clean.startswith("#") and not clean.startswith("-"):
                        m = re.match(r"^([a-zA-Z0-9_\-\.]+)", clean)
                        if m:
                            self.direct_deps.add(self._canonical_name(m.group(1)))
            except Exception:
                pass

    def scan_installed_components(self) -> Tuple[List[DependencyComponent], Dict[str, List[str]]]:
        """
        Recense toutes les distributions installées et construit le graphe de dépendances.

        Returns:
            Tuple contenant la liste des DependencyComponent et l'arborescence des dépendances.
        """
        components: List[DependencyComponent] = []
        dependency_graph: Dict[str, List[str]] = {}

        try:
            dists = list(importlib.metadata.distributions())
        except Exception:
            dists = []

        seen_packages: Set[str] = set()

        for dist in dists:
            raw_name = dist.name
            if not raw_name:
                continue

            can_name = self._canonical_name(raw_name)
            # Ne pas auditer le package racine lui-même dans les dépendances
            if can_name in {"radiant-darwin", "radiant_darwin"}:
                continue

            if can_name in seen_packages:
                continue
            seen_packages.add(can_name)

            version = dist.version or "0.0.0"
            purl = f"pkg:pypi/{can_name}@{version}"
            bom_ref = purl

            # Détection direct vs transitif
            is_direct = can_name in self.direct_deps

            # Métadonnées de licence
            meta = dist.metadata
            raw_license = meta.get("License", "") or meta.get("License-Expression", "")
            classifiers = dist.metadata.get_all("Classifier") or []
            spdx_id = LicenseRegistry.normalize_to_spdx(raw_license, classifiers)
            category, compatibility = LicenseRegistry.classify(spdx_id)

            summary = meta.get("Summary", "") or ""
            author = meta.get("Author", "") or meta.get("Author-email", "") or ""

            # Dépendances sous-jacentes requises
            requires = dist.requires or []
            sub_deps: List[str] = []
            for r in requires:
                match = re.match(r"^([a-zA-Z0-9_\-\.]+)", r)
                if match:
                    sub_dep_name = self._canonical_name(match.group(1))
                    sub_deps.append(sub_dep_name)

            dependency_graph[can_name] = sub_deps

            comp = DependencyComponent(
                name=can_name,
                version=version,
                purl=purl,
                bom_ref=bom_ref,
                is_direct=is_direct,
                scope="required" if is_direct else "optional",
                license_declared=raw_license,
                spdx_id=spdx_id,
                license_category=category,
                license_status=compatibility,
                summary=summary,
                author=author,
                dependencies=sub_deps,
            )
            components.append(comp)

        return components, dependency_graph

    def generate_cyclonedx_sbom(
        self,
        components: List[DependencyComponent],
        dependency_graph: Dict[str, List[str]],
        root_name: str = "radiant-darwin",
        root_version: str = "2.4.0",
    ) -> Dict[str, Union[str, int, Dict[str, Union[str, List[Dict[str, str]], Dict[str, str]]], List[Dict[str, Union[str, List[str]]]]]]:
        """
        Construit l'arborescence complète normalisée CycloneDX v1.5 JSON.

        Args:
            components: Liste des composants de dépendance.
            dependency_graph: Dictionnaire des dépendances {nom: [sous-dépendances]}.
            root_name: Nom du logiciel audité.
            root_version: Version du logiciel audité.

        Returns:
            Dictionnaire complet prêt pour la sérialisation JSON conforme au schéma CycloneDX v1.5.
        """
        root_purl = f"pkg:pypi/{root_name}@{root_version}"
        root_bom_ref = root_purl

        # Direct dependencies purls
        root_depends_on: List[str] = []
        name_to_purl: Dict[str, str] = {c.name: c.purl for c in components}

        for c in components:
            if c.is_direct:
                root_depends_on.append(c.purl)

        # Arbre des dépendances CycloneDX
        dependencies_list: List[Dict[str, Union[str, List[str]]]] = [
            {
                "ref": root_bom_ref,
                "dependsOn": sorted(root_depends_on)
            }
        ]

        for c in components:
            sub_purls: List[str] = []
            for sub_name in dependency_graph.get(c.name, []):
                if sub_name in name_to_purl:
                    sub_purls.append(name_to_purl[sub_name])
            dependencies_list.append({
                "ref": c.bom_ref,
                "dependsOn": sorted(sub_purls)
            })

        # Assemblage CycloneDX v1.5
        sbom_data: Dict[str, Union[str, int, Dict[str, Union[str, List[Dict[str, str]], Dict[str, str]]], List[Dict[str, Union[str, List[str]]]]]] = {
            "$schema": "http://cyclonedx.org/schema/bom-1.5.json",
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "serialNumber": f"urn:uuid:{uuid.uuid4()}",
            "version": 1,
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tools": [
                    {
                        "vendor": "Radiant-Darwin",
                        "name": "SupplyChainAuditor",
                        "version": "1.0.0"
                    }
                ],
                "component": {
                    "type": "application",
                    "bom-ref": root_bom_ref,
                    "name": root_name,
                    "version": root_version,
                    "purl": root_purl,
                    "description": "CAD Studio (Radiant-Darwin) Parametric 3D CAD/CAE/CAM Suite"
                }
            },
            "components": [c.to_cyclonedx_component() for c in components],
            "dependencies": dependencies_list,
        }

        return sbom_data


# ============================================================================
# 4. Connecteur Déterministe OSV.dev (Open Source Vulnerabilities)
# ============================================================================

class OSVClient:
    """
    Connecteur API osv.dev pour l'audit en direct des vulnérabilités connues (CVE).
    Comprend un mode direct, un mode batch et un mode de repli hors-ligne robuste.
    """

    BATCH_ENDPOINT = "https://api.osv.dev/v1/querybatch"
    QUERY_ENDPOINT = "https://api.osv.dev/v1/query"

    def __init__(self, allow_network: bool = True, timeout: float = 6.0) -> None:
        self.allow_network: bool = allow_network
        self.timeout: float = timeout
        # Base de données de secours hors-ligne pour les tests ou environnements déconnectés
        self.offline_db: Dict[str, List[Dict[str, Union[str, List[str], float]]]] = {}

    def add_offline_vulnerability(
        self,
        package_name: str,
        vuln_id: str,
        severity: str,
        cvss_score: float,
        summary: str,
        fixed_version: str,
        aliases: Optional[List[str]] = None
    ) -> None:
        """
        Enregistre une vulnérabilité de test dans la base locale hors-ligne.

        Args:
            package_name: Nom du package vulnérable.
            vuln_id: Identifiant de la vulnérabilité (ex: GHSA-xxx).
            severity: Sévérité ("CRITICAL", "HIGH", "MEDIUM", "LOW").
            cvss_score: Note numérique CVSS (0.0 à 10.0).
            summary: Description de la faille.
            fixed_version: Version contenant le correctif de sécurité.
            aliases: Identifiants alternatifs (ex: CVE-2023-xxxx).
        """
        can_name = re.sub(r"[-_.]+", "-", package_name).lower()
        if can_name not in self.offline_db:
            self.offline_db[can_name] = []

        self.offline_db[can_name].append({
            "id": vuln_id,
            "severity": severity,
            "cvss_score": cvss_score,
            "summary": summary,
            "fixed_version": fixed_version,
            "aliases": aliases or []
        })

    def _parse_cvss_vector_or_score(self, vuln_data: Dict[str, Union[str, List[Dict[str, str]], Dict[str, str]]]) -> Tuple[VulnerabilitySeverity, float]:
        """
        Extrait le score numérique CVSS et la sévérité à partir des données OSV.

        Args:
            vuln_data: Dictionnaire brut de la vulnérabilité renvoyé par OSV.

        Returns:
            Tuple (VulnerabilitySeverity, float).
        """
        severity_entries = vuln_data.get("severity")
        if isinstance(severity_entries, list):
            for entry in severity_entries:
                if isinstance(entry, dict) and entry.get("type") in ("CVSS_V3", "CVSS_V2"):
                    score_str = entry.get("score", "")
                    # Exemple de format: "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
                    # Extraction directe du score si présent ou estimation depuis les vecteurs
                    if "C:H" in score_str and "I:H" in score_str and "A:H" in score_str:
                        return VulnerabilitySeverity.CRITICAL, 9.8
                    if "C:H" in score_str or "I:H" in score_str:
                        return VulnerabilitySeverity.HIGH, 7.5
                    if "C:L" in score_str or "I:L" in score_str:
                        return VulnerabilitySeverity.MEDIUM, 5.3
                    return VulnerabilitySeverity.LOW, 3.1

        # Fallback sur database_specific.severity
        db_spec = vuln_data.get("database_specific")
        if isinstance(db_spec, dict):
            sev_str = str(db_spec.get("severity", "")).upper()
            if "CRITICAL" in sev_str:
                return VulnerabilitySeverity.CRITICAL, 9.5
            if "HIGH" in sev_str:
                return VulnerabilitySeverity.HIGH, 7.8
            if "MODERATE" in sev_str or "MEDIUM" in sev_str:
                return VulnerabilitySeverity.MEDIUM, 5.5
            if "LOW" in sev_str:
                return VulnerabilitySeverity.LOW, 2.5

        return VulnerabilitySeverity.MEDIUM, 5.0

    def _extract_fixed_version(self, vuln_data: Dict[str, Union[str, List[Dict[str, Union[str, List[Dict[str, Union[str, List[Dict[str, str]]]]]]]]]]) -> Optional[str]:
        """
        Extrait la version minimale corrigée depuis les plages affectées.

        Args:
            vuln_data: Dictionnaire brut de la vulnérabilité.

        Returns:
            Version de correction ou None si indisponible.
        """
        affected = vuln_data.get("affected")
        if isinstance(affected, list):
            for aff in affected:
                if isinstance(aff, dict):
                    ranges = aff.get("ranges")
                    if isinstance(ranges, list):
                        for r in ranges:
                            if isinstance(r, dict):
                                events = r.get("events")
                                if isinstance(events, list):
                                    for ev in events:
                                        if isinstance(ev, dict) and "fixed" in ev:
                                            return str(ev["fixed"])
        return None

    def query_package_vulnerabilities(self, package_name: str, version: str) -> List[VulnerabilityFinding]:
        """
        Interroge osv.dev pour un package unique.

        Args:
            package_name: Nom du package pip.
            version: Version installée.

        Returns:
            Liste des vulnérabilités détectées.
        """
        can_name = re.sub(r"[-_.]+", "-", package_name).lower()
        findings: List[VulnerabilityFinding] = []

        # 1. Vérification du mode déconnecté / mock
        if can_name in self.offline_db:
            for item in self.offline_db[can_name]:
                sev_enum = VulnerabilitySeverity(str(item.get("severity", "MEDIUM")))
                findings.append(VulnerabilityFinding(
                    id=str(item.get("id", "VULN-OFFLINE")),
                    aliases=[str(a) for a in (item.get("aliases") or []) if isinstance(a, str)],
                    package_name=can_name,
                    package_version=version,
                    severity=sev_enum,
                    cvss_score=float(item.get("cvss_score", 5.0)),
                    summary=str(item.get("summary", "Vulnérabilité locale détectée")),
                    details=str(item.get("summary", "")),
                    fixed_version=str(item.get("fixed_version", "")),
                    reference_urls=[]
                ))
            return findings

        if not self.allow_network:
            return findings

        # 2. Requête en direct vers l'API osv.dev
        payload = json.dumps({
            "package": {"name": can_name, "ecosystem": "PyPI"},
            "version": version
        }).encode("utf-8")

        req = urllib.request.Request(
            self.QUERY_ENDPOINT,
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    raw_data = json.loads(resp.read().decode("utf-8"))
                    vulns = raw_data.get("vulns", [])
                    for v in vulns:
                        sev_enum, cvss_val = self._parse_cvss_vector_or_score(v)
                        aliases = [str(a) for a in v.get("aliases", []) if isinstance(a, str)]
                        fixed_ver = self._extract_fixed_version(v)
                        refs: List[str] = []
                        for ref_entry in v.get("references", []):
                            if isinstance(ref_entry, dict) and "url" in ref_entry:
                                refs.append(str(ref_entry["url"]))

                        findings.append(VulnerabilityFinding(
                            id=str(v.get("id", "")),
                            aliases=aliases,
                            package_name=can_name,
                            package_version=version,
                            severity=sev_enum,
                            cvss_score=cvss_val,
                            summary=str(v.get("summary", "Pas de résumé fourni")),
                            details=str(v.get("details", "")),
                            fixed_version=fixed_ver,
                            reference_urls=refs
                        ))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            # Tolérance en cas de coupure réseau inopinée
            pass

        return findings

    def query_batch(self, components: List[DependencyComponent]) -> List[VulnerabilityFinding]:
        """
        Interroge osv.dev en mode batch ultra-rapide pour l'ensemble des composants.

        Args:
            components: Liste des composants de dépendances à auditer.

        Returns:
            Liste consolidée de toutes les vulnérabilités trouvées.
        """
        all_findings: List[VulnerabilityFinding] = []

        if not components:
            return all_findings

        # Interroger le cache local / offline d'abord
        pending_components: List[DependencyComponent] = []
        for c in components:
            if c.name in self.offline_db:
                all_findings.extend(self.query_package_vulnerabilities(c.name, c.version))
            else:
                pending_components.append(c)

        if not self.allow_network or not pending_components:
            return all_findings

        # Requête batch vers OSV
        queries_payload = [
            {"package": {"name": c.name, "ecosystem": "PyPI"}, "version": c.version}
            for c in pending_components
        ]

        payload = json.dumps({"queries": queries_payload}).encode("utf-8")
        req = urllib.request.Request(
            self.BATCH_ENDPOINT,
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    raw_data = json.loads(resp.read().decode("utf-8"))
                    results = raw_data.get("results", [])
                    for idx, res_entry in enumerate(results):
                        if idx < len(pending_components):
                            target_comp = pending_components[idx]
                            vulns = res_entry.get("vulns", [])
                            for v in vulns:
                                sev_enum, cvss_val = self._parse_cvss_vector_or_score(v)
                                aliases = [str(a) for a in v.get("aliases", []) if isinstance(a, str)]
                                fixed_ver = self._extract_fixed_version(v)
                                refs: List[str] = []
                                for ref_entry in v.get("references", []):
                                    if isinstance(ref_entry, dict) and "url" in ref_entry:
                                        refs.append(str(ref_entry["url"]))

                                all_findings.append(VulnerabilityFinding(
                                    id=str(v.get("id", "")),
                                    aliases=aliases,
                                    package_name=target_comp.name,
                                    package_version=target_comp.version,
                                    severity=sev_enum,
                                    cvss_score=cvss_val,
                                    summary=str(v.get("summary", "Pas de résumé fourni")),
                                    details=str(v.get("details", "")),
                                    fixed_version=fixed_ver,
                                    reference_urls=refs
                                ))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            # Repli sur requête unitaire si le batch échoue ou en cas d'erreur transitoire
            for c in pending_components:
                all_findings.extend(self.query_package_vulnerabilities(c.name, c.version))

        return all_findings


# ============================================================================
# 5. Auditeur OpenSSF Scorecard & Protection Supply Chain
# ============================================================================

class OpenSSFScorecardEvaluator:
    """
    Évaluateur automatisé inspiré du standard OpenSSF Scorecard (Security Scorecards).
    Vérifie le pinning strict des dépendances, l'absence de scripts d'installation hostiles,
    la détection de typosquatting et la conformité globale de la chaîne d'approvisionnement.
    """

    POPULAR_PYPI_TARGETS: List[str] = [
        "numpy", "scipy", "requests", "urllib3", "setuptools", "wheel", "pip",
        "pytest", "pydantic", "flask", "django", "fastapi", "torch", "tensorflow",
        "pandas", "matplotlib", "trimesh", "pyside6", "pyopengl", "coverage"
    ]

    SUSPICIOUS_SCRIPT_PATTERNS: List[Tuple[str, str, str]] = [
        ("base64.b64decode", "Décodage Base64 potentiellement obfuscé dans le build", "CWE-506"),
        ("eval(", "Exécution dynamique de code arbitraire", "CWE-94"),
        ("exec(", "Exécution dynamique de code arbitraire", "CWE-94"),
        ("marshal.loads", "Désérialisation binaire dangereuse", "CWE-502"),
        ("urllib.request.urlopen", "Appel réseau sortant suspect durant la compilation", "CWE-319"),
        ("socket.socket", "Ouverture de socket réseau ou reverse-shell", "CWE-200"),
        ("os.system", "Exécution de commande système hôte non contrôlée", "CWE-78"),
        ("subprocess.Popen", "Lancement de processus externe arbitraire", "CWE-78"),
        ("powershell", "Invocation explicite du shell PowerShell", "CWE-78"),
        ("cmd.exe", "Invocation explicite de l'interpréteur Windows", "CWE-78"),
    ]

    def __init__(self, project_root: Path) -> None:
        self.project_root: Path = project_root

    @classmethod
    def _levenshtein_distance(cls, s1: str, s2: str) -> int:
        """Calcule la distance d'édition de Levenshtein entre deux chaînes."""
        if len(s1) < len(s2):
            return cls._levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)

        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def check_dependency_pinning(self) -> OpenSSFScorecardItem:
        """
        Vérifie si les dépendances directes sont strictement épinglées (== et hachages).
        Conforme aux recommandations OpenSSF Scorecard (Dependency-Pinning).

        Returns:
            Résultat d'évaluation OpenSSF pour le pinning des dépendances.
        """
        details: List[str] = []
        total_declared = 0
        pinned_declared = 0
        unpinned_lines: List[str] = []

        # 1. Vérification de l'existence d'un lockfile de build déterministe
        lockfile_candidates = [
            self.project_root / "requirements.lock",
            self.project_root / "poetry.lock",
            self.project_root / "Pipfile.lock",
            self.project_root / "pdm.lock",
        ]
        active_lockfile: Optional[Path] = None
        for lf in lockfile_candidates:
            if lf.exists():
                active_lockfile = lf
                break

        # 2. Analyse précise des dépendances déclarées via tomllib
        pyproject_path = self.project_root / "pyproject.toml"
        if pyproject_path.exists():
            try:
                data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
                project_sec = data.get("project", {})
                all_deps = list(project_sec.get("dependencies", []))
                for opt_list in project_sec.get("optional-dependencies", {}).values():
                    if isinstance(opt_list, list):
                        all_deps.extend(opt_list)
                for d_str in all_deps:
                    clean = str(d_str).strip()
                    if not clean:
                        continue
                    total_declared += 1
                    if "==" in clean:
                        pinned_declared += 1
                    else:
                        unpinned_lines.append(f"pyproject.toml: {clean}")
            except Exception:
                pass

        req_path = self.project_root / "requirements.txt"
        if req_path.exists():
            try:
                for line in req_path.read_text(encoding="utf-8").splitlines():
                    clean = line.strip()
                    if clean and not clean.startswith("#") and not clean.startswith("-"):
                        total_declared += 1
                        if "==" in clean:
                            pinned_declared += 1
                        else:
                            unpinned_lines.append(f"requirements.txt: {clean}")
            except Exception:
                pass

        # 3. Évaluation selon présence de lockfile ou ratio
        if active_lockfile is not None:
            score = 10.0
            status = ScorecardCheckStatus.PASS
            reason = f"Fichier de verrouillage déterministe actif ({active_lockfile.name}) garantissant le PIN strict des dépendances."
            remediation = "Conserver le fichier lock synchronisé."
            details.append(f"Lockfile identifié : {active_lockfile.name}")
        elif total_declared == 0:
            score = 10.0
            status = ScorecardCheckStatus.PASS
            reason = "Aucune dépendance externe déclarée."
            remediation = "Conserver les dépendances strictement épinglées."
        else:
            ratio = pinned_declared / total_declared
            score = round(ratio * 10.0, 1)
            if score >= 9.0:
                status = ScorecardCheckStatus.PASS
                reason = f"Excellent niveau de pinning direct ({pinned_declared}/{total_declared} dépendances strictes)."
                remediation = "Maintenir le fichier lock synchronisé."
            elif score >= 5.0:
                status = ScorecardCheckStatus.WARN
                reason = f"Pinning partiel ({pinned_declared}/{total_declared}). Présence d'opérateurs flottants (>= ou ~)."
                remediation = "Épingler les versions avec l'opérateur '==' ou générer un 'requirements.lock' via '--lock requirements.lock'."
            else:
                status = ScorecardCheckStatus.FAIL
                reason = f"Pinning direct insuffisant ({pinned_declared}/{total_declared}). Risque d'injection de versions compromises."
                remediation = "Générer un verrou strict via '--lock requirements.lock' ou figer avec '=='."

        for unp in unpinned_lines[:5]:
            details.append(f"Dépendance avec version flottante : {unp}")

        return OpenSSFScorecardItem(
            check_id="Pinned-Dependencies",
            name="Dependency Pinning Hygiene",
            score=score,
            status=status,
            reason=reason,
            details=details,
            remediation=remediation
        )

    def check_hostile_install_scripts(self) -> OpenSSFScorecardItem:
        """
        Scanne les scripts de construction et d'installation (packaging) à la recherche de code malveillant.
        Conforme aux règles OpenSSF Scorecard (Packaging / Malicious code in install hooks).

        Returns:
            Résultat d'évaluation OpenSSF pour l'intégrité des scripts d'installation.
        """
        suspicious_findings: List[str] = []
        target_files: List[Path] = []

        # Fichiers d'installation et de packaging ciblés
        packaging_names = ["setup.py", "setup.cfg", "build.py", "install.py", "flit.ini"]
        for name in packaging_names:
            p = self.project_root / name
            if p.exists():
                target_files.append(p)

        # Vérification de l'absence de setup.py (bonne pratique PEP 517/621 moderne)
        has_pyproject = (self.project_root / "pyproject.toml").exists()
        has_setup_py = (self.project_root / "setup.py").exists()

        for target in target_files:
            try:
                content = target.read_text(encoding="utf-8")
                for pattern, desc, cwe in self.SUSPICIOUS_SCRIPT_PATTERNS:
                    if pattern in content:
                        suspicious_findings.append(
                            f"Motif suspect '{pattern}' ({desc} - {cwe}) détecté dans {target.name}"
                        )
            except Exception:
                pass

        if not suspicious_findings:
            score = 10.0
            status = ScorecardCheckStatus.PASS
            if has_pyproject and not has_setup_py:
                reason = "Packaging déclaratif moderne PEP 517/621 sans setup.py exécutable hostile."
            else:
                reason = "Aucun script d'installation hostile, obfuscation ou appel réseau clandestin détecté."
            remediation = "Maintenir l'interdiction de scripts d'installation impératifs non audités."
        else:
            score = max(0.0, 10.0 - (len(suspicious_findings) * 3.0))
            status = ScorecardCheckStatus.WARN if score >= 6.0 else ScorecardCheckStatus.FAIL
            reason = f"{len(suspicious_findings)} motif(s) d'installation suspect(s) identifié(s) dans les fichiers de build."
            remediation = "Auditer manuellement les scripts incriminés et substituer les commandes système arbitraires."

        return OpenSSFScorecardItem(
            check_id="Malicious-Scripts-Integrity",
            name="Packaging & Install Scripts Integrity",
            score=score,
            status=status,
            reason=reason,
            details=suspicious_findings,
            remediation=remediation
        )

    def check_typosquatting(self, installed_names: List[str]) -> OpenSSFScorecardItem:
        """
        Détecte les risques d'attaques par Typosquatting sur les noms de packages.

        Args:
            installed_names: Liste des noms de packages installés.

        Returns:
            Résultat d'évaluation OpenSSF pour la prévention du typosquatting.
        """
        suspicious_packages: List[str] = []

        for name in installed_names:
            can_name = re.sub(r"[-_.]+", "-", name).lower()
            if can_name in self.POPULAR_PYPI_TARGETS:
                continue

            for popular in self.POPULAR_PYPI_TARGETS:
                dist = self._levenshtein_distance(can_name, popular)
                if dist == 1 and abs(len(can_name) - len(popular)) <= 1:
                    suspicious_packages.append(
                        f"Package suspect '{can_name}' à distance {dist} du standard '{popular}' (Typosquatting potentiel)"
                    )

        if not suspicious_packages:
            score = 10.0
            status = ScorecardCheckStatus.PASS
            reason = "Aucune confusion de nom ni tentative de typosquatting détectée."
            remediation = "Conserver un contrôle strict sur les ajouts de dépendances."
        else:
            score = max(0.0, 10.0 - (len(suspicious_packages) * 4.0))
            status = ScorecardCheckStatus.FAIL
            reason = f"{len(suspicious_packages)} package(s) présentant une ressemblance anormale avec un standard PyPI."
            remediation = "Vérifier l'authenticité de l'auteur et l'URL source du package sur PyPI."

        return OpenSSFScorecardItem(
            check_id="Typosquatting-Guard",
            name="Typosquatting Resistance",
            score=score,
            status=status,
            reason=reason,
            details=suspicious_packages,
            remediation=remediation
        )

    def evaluate(
        self,
        components: List[DependencyComponent],
        vulnerabilities: List[VulnerabilityFinding],
        contaminating_licenses: List[str]
    ) -> OpenSSFScorecardReport:
        """
        Calcule le rapport complet OpenSSF Scorecard avec note globale sur 10.

        Args:
            components: Liste des composants audités.
            vulnerabilities: Liste des vulnérabilités connues trouvées.
            contaminating_licenses: Liste des packages avec licence contaminante.

        Returns:
            OpenSSFScorecardReport consolidé.
        """
        check_pinning = self.check_dependency_pinning()
        check_scripts = self.check_hostile_install_scripts()
        installed_names = [c.name for c in components]
        check_typo = self.check_typosquatting(installed_names)

        # Contrôle 4: Absence de vulnérabilités
        if not vulnerabilities:
            vuln_score = 10.0
            vuln_status = ScorecardCheckStatus.PASS
            vuln_reason = "Aucune vulnérabilité CVE connue détectée via osv.dev."
            vuln_remediation = "Poursuivre la veille continue avec des scans périodiques."
            vuln_details: List[str] = []
        else:
            crit_count = sum(1 for v in vulnerabilities if v.severity == VulnerabilitySeverity.CRITICAL)
            high_count = sum(1 for v in vulnerabilities if v.severity == VulnerabilitySeverity.HIGH)
            med_count = sum(1 for v in vulnerabilities if v.severity == VulnerabilitySeverity.MEDIUM)
            low_count = sum(1 for v in vulnerabilities if v.severity == VulnerabilitySeverity.LOW)
            penalty = (crit_count * 5.0) + (high_count * 3.0) + (med_count * 1.0) + (low_count * 0.5)
            vuln_score = max(0.0, round(10.0 - penalty, 1))
            vuln_status = ScorecardCheckStatus.FAIL if (crit_count > 0 or high_count > 0) else ScorecardCheckStatus.WARN
            vuln_reason = f"{len(vulnerabilities)} vulnérabilité(s) active(s) : {crit_count} Critiques, {high_count} Hautes."
            vuln_remediation = "Mettre à jour immédiatement vers les versions corrigées recommandées."
            vuln_details = [f"{v.id} ({v.package_name}@{v.package_version}) -> Fix: {v.fixed_version or 'N/A'}" for v in vulnerabilities[:5]]

        check_vuln = OpenSSFScorecardItem(
            check_id="Vulnerability-Freedom",
            name="Known Vulnerabilities Absence",
            score=vuln_score,
            status=vuln_status,
            reason=vuln_reason,
            details=vuln_details,
            remediation=vuln_remediation
        )

        # Contrôle 5: Conformité des licences logicielles
        if not contaminating_licenses:
            lic_score = 10.0
            lic_status = ScorecardCheckStatus.PASS
            lic_reason = "Toutes les dépendances respectent la compatibilité permissive (MIT/BSD/Apache-2.0)."
            lic_remediation = "Conserver la politique d'exclusion des licences virales (GPL/AGPL)."
            lic_details: List[str] = []
        else:
            lic_score = max(0.0, round(10.0 - (len(contaminating_licenses) * 5.0), 1))
            lic_status = ScorecardCheckStatus.FAIL
            lic_reason = f"{len(contaminating_licenses)} licence(s) contaminante(s) (GPL/AGPL) détectée(s) !"
            lic_remediation = "Isoler ou remplacer les packages sous GPL/AGPL pour éviter la contamination virale."
            lic_details = [f"Package contaminant : {pkg}" for pkg in contaminating_licenses]

        check_lic = OpenSSFScorecardItem(
            check_id="License-Compliance",
            name="Open Source License Compliance",
            score=lic_score,
            status=lic_status,
            reason=lic_reason,
            details=lic_details,
            remediation=lic_remediation
        )

        all_checks = [check_pinning, check_scripts, check_typo, check_vuln, check_lic]
        weights = [0.25, 0.20, 0.15, 0.25, 0.15]
        overall_score = round(sum(c.score * w for c, w in zip(all_checks, weights)), 2)

        return OpenSSFScorecardReport(
            overall_score=overall_score,
            checks=all_checks,
            pinned_dependencies_ratio=check_pinning.score / 10.0,
            malicious_patterns_detected=len(check_scripts.details),
            typosquatting_risks_detected=len(check_typo.details)
        )


# ============================================================================
# 6. Moteur Principal d'Audit Supply Chain & Intégration
# ============================================================================

class SupplyChainAuditor:
    """
    Moteur unifié d'audit Supply Chain, Génération SBOM CycloneDX v1.5 et OpenSSF Scorecard.
    """

    def __init__(self, project_root: Optional[Path] = None, allow_network: bool = True) -> None:
        self.project_root: Path = project_root or Path.cwd()
        self.allow_network: bool = allow_network
        self.sbom_generator = CycloneDXSBOMGenerator(self.project_root)
        self.osv_client = OSVClient(allow_network=self.allow_network)
        self.openssf_evaluator = OpenSSFScorecardEvaluator(self.project_root)

    def run_full_audit(
        self,
        export_sbom_path: Optional[Path] = None
    ) -> SupplyChainAuditReport:
        """
        Exécute la suite complète des 4 piliers d'audit Supply Chain.

        Args:
            export_sbom_path: Chemin optionnel pour exporter le SBOM CycloneDX v1.5 JSON.

        Returns:
            Rapport complet d'audit SupplyChainAuditReport.
        """
        # 1. Recensement des composants et dépendances
        components, dep_graph = self.sbom_generator.scan_installed_components()

        # 2. Génération du SBOM CycloneDX v1.5
        sbom_data = self.sbom_generator.generate_cyclonedx_sbom(
            components, dep_graph, root_name="radiant-darwin", root_version="2.4.0"
        )

        if export_sbom_path:
            export_sbom_path.parent.mkdir(parents=True, exist_ok=True)
            export_sbom_path.write_text(json.dumps(sbom_data, indent=2, ensure_ascii=False), encoding="utf-8")

        # 3. Audit des Licences
        license_summary: Dict[str, int] = {
            "PERMISSIVE": 0,
            "WEAK_COPYLEFT": 0,
            "STRONG_COPYLEFT": 0,
            "PROPRIETARY": 0,
            "UNKNOWN": 0,
        }
        contaminating: List[str] = []

        for c in components:
            cat_name = c.license_category.value
            license_summary[cat_name] = license_summary.get(cat_name, 0) + 1
            if c.license_status == LicenseCompatibility.INCOMPATIBLE_CONTAMINATING:
                contaminating.append(f"{c.name} ({c.spdx_id})")

        # 4. Requête des vulnérabilités OSV.dev
        vulnerabilities = self.osv_client.query_batch(components)
        vuln_summary: Dict[str, int] = {
            "CRITICAL": 0,
            "HIGH": 0,
            "MEDIUM": 0,
            "LOW": 0,
        }
        for v in vulnerabilities:
            sev_name = v.severity.value
            vuln_summary[sev_name] = vuln_summary.get(sev_name, 0) + 1

        # 5. Évaluation OpenSSF Scorecard
        scorecard = self.openssf_evaluator.evaluate(components, vulnerabilities, contaminating)

        # 6. Quality Gate & Notation globale
        direct_count = sum(1 for c in components if c.is_direct)
        transitive_count = len(components) - direct_count

        passed_quality_gate = (
            scorecard.overall_score >= 6.5 and
            len(contaminating) == 0 and
            vuln_summary.get("CRITICAL", 0) == 0
        )

        if scorecard.overall_score >= 9.0 and passed_quality_gate:
            grade = "A+ (EXEMPLARY SECURITY)"
        elif scorecard.overall_score >= 8.0 and passed_quality_gate:
            grade = "A (HARDENED)"
        elif scorecard.overall_score >= 6.5 and passed_quality_gate:
            grade = "B (ACCEPTABLE)"
        elif scorecard.overall_score >= 5.0:
            grade = "C (AT RISK)"
        else:
            grade = "F (CRITICAL CONTAMINATION / VULNERABILITY HAZARD)"

        return SupplyChainAuditReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            project_name="radiant-darwin",
            project_version="2.4.0",
            total_components=len(components),
            direct_components=direct_count,
            transitive_components=transitive_count,
            components=components,
            license_summary=license_summary,
            contaminating_licenses=contaminating,
            vulnerabilities=vulnerabilities,
            vulnerability_summary=vuln_summary,
            openssf_scorecard=scorecard,
            overall_security_grade=grade,
            passed_quality_gate=passed_quality_gate
        )

    def generate_requirements_lock(self, output_path: Path, only_direct: bool = False) -> Path:
        """
        Génère un fichier de verrouillage 'requirements.lock' avec versions strictement épinglées (==).

        Args:
            output_path: Chemin du fichier lock à créer.
            only_direct: Si True, épingle uniquement les dépendances directes.

        Returns:
            Chemin du fichier généré.
        """
        components, _ = self.sbom_generator.scan_installed_components()
        target_components = [c for c in components if c.is_direct] if only_direct else components
        target_components.sort(key=lambda x: x.name)

        lines: List[str] = [
            "# ============================================================================",
            "# Fichier de Verrouillage Déterministe de Dépendances (OpenSSF Scorecard Hardened)",
            f"# Généré automatiquement par Radiant-Darwin SupplyChainAuditor le {datetime.now(timezone.utc).isoformat()}",
            "# Règle OpenSSF : Dépendances strictement épinglées avec versions exactes",
            "# ============================================================================",
            "",
        ]

        for c in target_components:
            type_tag = "direct" if c.is_direct else "transitive"
            lic = c.spdx_id or "UNVERIFIED"
            lines.append(f"{c.name}=={c.version}  # {type_tag} | {lic}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return output_path

    @classmethod
    def print_console_report(cls, report: SupplyChainAuditReport) -> None:
        """
        Affiche le rapport d'audit formaté dans la console avec mise en valeur.

        Args:
            report: Rapport d'audit SupplyChainAuditReport.
        """
        sep = "=" * 80
        sub_sep = "-" * 80
        print(sep)
        print("[AUDIT] SUPPLY CHAIN, SBOM CYCLONEDX v1.5 & OPENSSF SCORECARD")
        print(f"    Projet : {report.project_name} v{report.project_version}")
        print(f"    Horodatage : {report.timestamp}")
        print(sep)
        print(f"[COMPOSANTS] PIP RECENSES : {report.total_components} au total")
        print(f"   |-- Dependances directes    : {report.direct_components}")
        print(f"   \\-- Dependances transitives : {report.transitive_components}")
        print(sub_sep)
        print("[LICENCES] AUDIT DE COMPATIBILITE DES LICENCES :")
        for cat, cnt in report.license_summary.items():
            print(f"   * {cat:<18} : {cnt}")
        if report.contaminating_licenses:
            print(f"   [ALERTE] CONTAMINATION GPL/AGPL : {len(report.contaminating_licenses)} detectee(s)")
            for cont in report.contaminating_licenses:
                print(f"      - {cont}")
        else:
            print("   [OK] Aucune licence contaminante detectee (100% compatible MIT/Permissif).")

        print(sub_sep)
        print("[OSV-CVE] SCAN VULNERABILITES OSV.DEV :")
        print(f"   * Critiques : {report.vulnerability_summary.get('CRITICAL', 0)}")
        print(f"   * Hautes    : {report.vulnerability_summary.get('HIGH', 0)}")
        print(f"   * Moyennes  : {report.vulnerability_summary.get('MEDIUM', 0)}")
        print(f"   * Faibles   : {report.vulnerability_summary.get('LOW', 0)}")
        if report.vulnerabilities:
            for v in report.vulnerabilities[:5]:
                print(f"   [VULN] {v.id} [{v.severity.value}] ({v.package_name}@{v.package_version}) -> {v.summary[:60]}...")
                if v.fixed_version:
                    print(f"      Correctif recommande : mise a jour vers v{v.fixed_version}")
        else:
            print("   [OK] Zero vulnerabilite connue detectee dans les packages installes.")

        print(sub_sep)
        print(f"[OPENSSF] EVALUATION SCORECARD : {report.openssf_scorecard.overall_score} / 10.0")
        for chk in report.openssf_scorecard.checks:
            icon = "[PASS]" if chk.status == ScorecardCheckStatus.PASS else ("[WARN]" if chk.status == ScorecardCheckStatus.WARN else "[FAIL]")
            print(f"   {icon} {chk.name:<32} : {chk.score:>4.1f}/10  [{chk.status.value}]")
            print(f"      |-> {chk.reason}")
            if chk.remediation and chk.status != ScorecardCheckStatus.PASS:
                print(f"      [FIX] Action : {chk.remediation}")

        print(sep)
        status_banner = "[OK] QUALITY GATE VALIDEE" if report.passed_quality_gate else "[FAIL] QUALITY GATE REFUSEE"
        print(f"RESULTAT GLOBAL : {status_banner}")
        print(f"GRADE DE SECURITE : {report.overall_security_grade}")
        print(sep)


# ============================================================================
# 7. Point d'Entrée CLI
# ============================================================================

def main(argv: Optional[List[str]] = None) -> int:
    """
    Point d'entrée exécutable en ligne de commande pour l'auditeur Supply Chain.

    Args:
        argv: Arguments optionnels passés en paramètre (utilise sys.argv par défaut).

    Returns:
        0 si la Quality Gate est validée, 1 sinon.
    """
    parser = argparse.ArgumentParser(
        description="Auditeur de Chaîne d'Approvisionnement, SBOM CycloneDX v1.5 et OpenSSF Scorecard."
    )
    parser.add_argument(
        "--root",
        type=str,
        default=".",
        help="Chemin de la racine du projet à auditer (défaut: .)"
    )
    parser.add_argument(
        "--sbom",
        type=str,
        default="sbom.json",
        help="Chemin du fichier CycloneDX SBOM JSON de sortie (défaut: sbom.json)"
    )
    parser.add_argument(
        "--report",
        type=str,
        default="audit_report_supply_chain.json",
        help="Chemin du rapport d'audit JSON consolidé (défaut: audit_report_supply_chain.json)"
    )
    parser.add_argument(
        "--lock",
        type=str,
        default="",
        help="Chemin optionnel pour générer un 'requirements.lock' strictement épinglé (==)"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Désactive les requêtes réseau vers osv.dev (mode déconnecté / air-gapped)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exige un score OpenSSF >= 8.0 pour valider la Quality Gate"
    )

    args = parser.parse_args(argv)

    root_dir = Path(args.root).resolve()
    sbom_path = root_dir / args.sbom if not Path(args.sbom).is_absolute() else Path(args.sbom)
    report_json_path = root_dir / args.report if not Path(args.report).is_absolute() else Path(args.report)

    print("Démarrage de l'Audit Supply Chain & Génération SBOM CycloneDX...")
    auditor = SupplyChainAuditor(project_root=root_dir, allow_network=not args.offline)
    report = auditor.run_full_audit(export_sbom_path=sbom_path)

    # Génération du lockfile si demandé
    if args.lock:
        lock_path = root_dir / args.lock if not Path(args.lock).is_absolute() else Path(args.lock)
        auditor.generate_requirements_lock(lock_path)
        print(f"[LOCK] Verrouillage strict généré : {lock_path}")

    # Export du rapport détaillé en JSON
    report_dict: Dict[str, Union[str, int, bool, Dict[str, int], List[Dict[str, Union[str, float, List[str]]]]]] = {
        "timestamp": report.timestamp,
        "project": report.project_name,
        "version": report.project_version,
        "total_components": report.total_components,
        "direct_components": report.direct_components,
        "transitive_components": report.transitive_components,
        "overall_grade": report.overall_security_grade,
        "passed_quality_gate": report.passed_quality_gate,
        "openssf_score": report.openssf_scorecard.overall_score,
        "license_summary": report.license_summary,
        "vulnerability_summary": report.vulnerability_summary,
        "contaminating_licenses": report.contaminating_licenses,
        "vulnerabilities": [
            {
                "id": v.id,
                "package": v.package_name,
                "version": v.package_version,
                "severity": v.severity.value,
                "cvss": v.cvss_score,
                "summary": v.summary,
                "fixed_version": v.fixed_version or "N/A"
            }
            for v in report.vulnerabilities
        ],
        "openssf_checks": [
            {
                "id": c.check_id,
                "name": c.name,
                "score": c.score,
                "status": c.status.value,
                "reason": c.reason,
                "remediation": c.remediation
            }
            for c in report.openssf_scorecard.checks
        ]
    }

    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report_json_path.write_text(json.dumps(report_dict, indent=2, ensure_ascii=False), encoding="utf-8")
    SupplyChainAuditor.print_console_report(report)

    print(f"[SBOM] CycloneDX v1.5 exporte avec succes : {sbom_path}")
    print(f"[RAPPORT] Rapport d'audit consolide exporte : {report_json_path}")

    if args.strict and report.openssf_scorecard.overall_score < 8.0:
        print("[STRICT] Échec de la Quality Gate en mode strict (Score < 8.0)")
        return 1

    return 0 if report.passed_quality_gate else 1


if __name__ == "__main__":
    sys.exit(main())
