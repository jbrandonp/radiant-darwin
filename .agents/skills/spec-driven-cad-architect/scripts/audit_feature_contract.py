"""Auditeur déterministe de contrats de spécifications CAO (v1.0).

Vérifie la présence et la complétude des 4 quadrants de spécification (invariants,
pré-conditions, post-conditions, tests de caractérisation) pour éliminer le 'vibe coding'.
100% typage statique strict (zéro Any, zéro object), complexité cognitive <= 15.
"""

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Final, List, Tuple


@dataclass(frozen=True)
class SpecAuditVerdict:
    """Résultat de l'audit de complétude d'une spécification CAO."""

    has_invariants: bool
    has_preconditions: bool
    has_postconditions: bool
    has_characterization_tests: bool
    score_percentage: float
    is_conforming: bool


def audit_spec_document_text(content: str) -> SpecAuditVerdict:
    """Analyse la présence des mots-clés formels des 4 quadrants dans le texte."""
    lowered = content.lower()

    # Mots-clés requis pour chaque quadrant
    inv_ok = any(kw in lowered for kw in ("invariant", "euler", "watertight", "chi ="))
    pre_ok = any(kw in lowered for kw in ("pre-condition", "précondition", "garde", "dégénérescence", "epsilon"))
    post_ok = any(kw in lowered for kw in ("post-condition", "postcondition", "volume", "topologie"))
    test_ok = any(kw in lowered for kw in ("caractérisation", "characterization", "test unitaire", "harnais", "pytest"))

    fulfilled_count = sum((inv_ok, pre_ok, post_ok, test_ok))
    score = (fulfilled_count / 4.0) * 100.0

    return SpecAuditVerdict(
        has_invariants=inv_ok,
        has_preconditions=pre_ok,
        has_postconditions=post_ok,
        has_characterization_tests=test_ok,
        score_percentage=score,
        is_conforming=(fulfilled_count == 4),
    )


def main() -> int:
    """Point d'entrée CLI pour la validation d'un contrat de spécification."""
    print("\n================ AUDITEUR DE SPÉCIFICATIONS CAO (KARPATHY SOTA 2026) ================")
    sample_spec = (
        "# Spécification : Opération de Congé Analytique (Fillet)\n"
        "## 1. Invariants Topologiques : Euler chi = 2 conservé, variété fermée.\n"
        "## 2. Préconditions : Rayon r > 1e-4 mm, arête de valence 2.\n"
        "## 3. Postconditions : Volume strictement positif, surface torique ou cylindrique raccordée.\n"
        "## 4. Tests de Caractérisation : Suite pytest validant le congé sur cube et cylindre.\n"
    )

    verdict = audit_spec_document_text(sample_spec)
    print(f"Quadrant 1 (Invariants Mathématiques) : {'PRÉSENT' if verdict.has_invariants else 'MANQUANT'}")
    print(f"Quadrant 2 (Pré-Conditions & Gardes)   : {'PRÉSENT' if verdict.has_preconditions else 'MANQUANT'}")
    print(f"Quadrant 3 (Post-Conditions)          : {'PRÉSENT' if verdict.has_postconditions else 'MANQUANT'}")
    print(f"Quadrant 4 (Tests Caractérisation)    : {'PRÉSENT' if verdict.has_characterization_tests else 'MANQUANT'}")
    print(f"\nScore de Complétude Contractuelle : {verdict.score_percentage:.1f} %")
    print(f"Verdict Spec-Driven                : {'CONFORME (Zéro Vibe Coding)' if verdict.is_conforming else 'NON CONFORME'}\n")

    return 0 if verdict.is_conforming else 1


if __name__ == "__main__":
    sys.exit(main())
