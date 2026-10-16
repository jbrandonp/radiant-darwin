"""
Point d'entrée CLI pour la génération du Rapport HTML Interactif et des Badges SVG.
Usage :
    python scripts/generate_audit_report.py
    python scripts/generate_audit_report.py --output docs/audit_report.html --badges-dir docs/badges
"""

from __future__ import annotations
import argparse
import sys
import os

# Assurer l'accès au projet
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.industrial_audit_engine import ProjectIndustrialAuditor


def main() -> int:
    """Exécute l'audit complet et génère les artefacts HTML, SVG et Markdown."""
    parser = argparse.ArgumentParser(description="Générateur de Rapport HTML Interactif et Badges SVG SOTA")
    parser.add_argument("--src", type=str, default="src", help="Dossier des sources (défaut: src)")
    parser.add_argument("--output", type=str, default="docs/audit_report.html", help="Chemin du rapport HTML")
    parser.add_argument("--badges-dir", type=str, default="docs/badges", help="Dossier des badges SVG")
    parser.add_argument("--summary", type=str, default=None, help="Chemin d'export du résumé Markdown")
    parser.add_argument("--cold", action="store_true", help="Forcer un audit complet sans cache")
    args = parser.parse_args()

    auditor = ProjectIndustrialAuditor(args.src)
    res = auditor.run_full_enterprise_audit(force_cold=args.cold, generate_html=True)

    print(f"\n[SUCCES] Rapport d'audit et badges vectoriels générés avec succès.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
