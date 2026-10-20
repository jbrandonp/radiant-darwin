"""Suite de tests unitaires pour l'outillage et les scripts des compétences d'agent (v1.0).

Vérifie le bon fonctionnement déterministe des 7 scripts utilitaires de compétences :
1. zero-alloc-systems-craftsman (profile_zero_alloc)
2. test-time-program-synthesizer (synthesize_and_verify)
3. loopcraft-harness-engineer (run_loopcraft_cycle)
4. brep-kernel-architect (verify_brep_invariants)
5. neurosymbolic-cad-copilot (validate_cad_prompt_ast)
6. spec-driven-cad-architect (audit_feature_contract)
7. cad-studio-engineer (verify_mesh_manifold)

100% typage statique strict (zéro Any, zéro object), complexité cognitive <= 15.
"""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import Dict, Final, List, Tuple
import pytest
import numpy as np


def _load_skill_module(module_name: str, rel_path: str) -> ModuleType:
    """Charge dynamiquement un module de compétence depuis un chemin contenant des tirets."""
    root_dir = Path(__file__).resolve().parent.parent
    full_path = root_dir / rel_path
    spec = importlib.util.spec_from_file_location(module_name, str(full_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Impossible de charger le module {module_name} à {full_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Chargement dynamique des 7 modules d'outillage
mod_zero_alloc: Final[ModuleType] = _load_skill_module(
    "profile_zero_alloc",
    ".agents/skills/zero-alloc-systems-craftsman/scripts/profile_zero_alloc.py",
)
mod_mesh_manifold: Final[ModuleType] = _load_skill_module(
    "verify_mesh_manifold",
    ".agents/skills/cad-studio-engineer/scripts/verify_mesh_manifold.py",
)
mod_test_time: Final[ModuleType] = _load_skill_module(
    "synthesize_and_verify",
    ".agents/skills/test-time-program-synthesizer/scripts/synthesize_and_verify.py",
)
mod_brep: Final[ModuleType] = _load_skill_module(
    "verify_brep_invariants",
    ".agents/skills/brep-kernel-architect/scripts/verify_brep_invariants.py",
)
mod_copilot: Final[ModuleType] = _load_skill_module(
    "validate_cad_prompt_ast",
    ".agents/skills/neurosymbolic-cad-copilot/scripts/validate_cad_prompt_ast.py",
)
mod_spec: Final[ModuleType] = _load_skill_module(
    "audit_feature_contract",
    ".agents/skills/spec-driven-cad-architect/scripts/audit_feature_contract.py",
)
mod_loopcraft: Final[ModuleType] = _load_skill_module(
    "run_loopcraft_cycle",
    ".agents/skills/loopcraft-harness-engineer/scripts/run_loopcraft_cycle.py",
)


class TestAgentSkillsTooling:
    """Banc de test formel pour tous les outils de compétences de l'agent."""

    def test_zero_alloc_profiler_contiguity_and_benchmark(self) -> None:
        """Vérifie que le profiler détecte correctement la contiguïté et la zéro-allocation."""
        arr_c: np.ndarray = np.ones((10, 3), dtype=np.float32)
        assert mod_zero_alloc.audit_array_contiguity(arr_c) is True

        # Tranche non-contiguë (stride step 2)
        arr_non_c: np.ndarray = arr_c[::2, :]
        assert mod_zero_alloc.audit_array_contiguity(arr_non_c) is False

        # Vérification du benchmark sur 10 000 sommets
        result = mod_zero_alloc.benchmark_zero_alloc_transformation(10_000)
        assert result.is_c_contiguous is True
        assert result.is_zero_allocation is True
        assert result.allocated_delta_bytes == 0

    def test_mesh_manifold_verifier_cube_and_degenerate(self) -> None:
        """Vérifie le calcul d'Euler, d'étanchéité et de volume sur le maillage."""
        # Cube valide
        assert mod_mesh_manifold.run_benchmark_cube() == 0

        # Solide dégénéré (moins de 4 sommets)
        degenerate = mod_mesh_manifold.analyze_triangular_mesh([(0.0, 0.0, 0.0)], [])
        assert degenerate.is_watertight is False
        assert degenerate.vertex_count == 1
        assert degenerate.face_count == 0

    def test_test_time_program_synthesizer_ast_and_oracles(self) -> None:
        """Vérifie le filtrage de sécurité AST et l'évaluation des oracles CAO."""
        # Code sain
        safe_code: Final[str] = "def make_part(r: float) -> float:\n    return r * 2.0\n"
        is_safe, err = mod_test_time.audit_program_ast(safe_code)
        assert is_safe is True
        assert err is None

        # Code hostile (import interdit)
        hostile_code: Final[str] = "import subprocess\nsubprocess.run(['dir'])\n"
        is_hostile, hostile_err = mod_test_time.audit_program_ast(hostile_code)
        assert is_hostile is False
        assert hostile_err is not None
        assert "subprocess" in hostile_err

        # Oracles formels
        verdict = mod_test_time.evaluate_cad_oracles(
            vertex_count=8,
            edge_count=18,
            face_count=12,
            volume=100.0,
            bounding_box_max_span=50.0,
            is_watertight=True,
        )
        assert verdict.final_passed is True

    def test_brep_invariants_validator(self) -> None:
        """Vérifie les invariants de demi-arêtes et la formule d'Euler-Poincaré."""
        HalfEdge = mod_brep.HalfEdge
        BRepTopologyValidator = mod_brep.BRepTopologyValidator

        # Construction d'un demi-graphe avec erreur de twin
        he_broken = {
            0: HalfEdge(id=0, origin_vertex=0, twin_id=1, next_id=0, face_id=0),
            1: HalfEdge(id=1, origin_vertex=1, twin_id=999, next_id=1, face_id=0),  # Twin invalide
        }
        val_broken = BRepTopologyValidator(vertices=[0, 1], half_edges=he_broken, faces=[0])
        assert val_broken.check_twin_reciprocity() is False

    def test_neurosymbolic_cad_copilot_validator(self) -> None:
        """Vérifie la validation des appels d'API CAO autorisés et le blocage des méthodes privées."""
        valid_script: Final[str] = "box = doc.add_box(10.0, 10.0, 10.0)\nhole = doc.add_cylinder(2.0, 15.0)\n"
        v_ok = mod_copilot.validate_copilot_script(valid_script)
        assert v_ok.is_valid is True
        assert v_ok.allowed_api_calls == 2

        # Script avec méthode privée interdite
        banned_script: Final[str] = "doc._internal_destroy()\n"
        v_banned = mod_copilot.validate_copilot_script(banned_script)
        assert v_banned.is_valid is False
        assert len(v_banned.violations) > 0

    def test_spec_driven_cad_contract_auditor(self) -> None:
        """Vérifie l'audit des 4 quadrants de spécification formelle."""
        full_spec: Final[str] = (
            "# Feature Spec\n"
            "## Invariant: Euler chi = 2 et variété fermée\n"
            "## Pré-conditions: Rayon r > 1e-4 avec garde epsilon\n"
            "## Post-conditions: Volume positif et topologie préservée\n"
            "## Tests de Caractérisation: Suite pytest complète\n"
        )
        verdict_full = mod_spec.audit_spec_document_text(full_spec)
        assert verdict_full.is_conforming is True
        assert verdict_full.score_percentage == 100.0

        # Spécification incomplète
        incomplete_spec: Final[str] = "Juste une fonction pour faire un chanfrein"
        verdict_inc = mod_spec.audit_spec_document_text(incomplete_spec)
        assert verdict_inc.is_conforming is False
        assert verdict_inc.score_percentage < 50.0

    def test_loopcraft_harness_execution(self) -> None:
        """Vérifie que l'orchestrateur Loopcraft s'exécute et valide les barrières de qualité."""
        report = mod_loopcraft.execute_loopcraft_harness()
        assert len(report.steps) >= 3
        # Toutes les barrières doivent être au vert suite au durcissement SAST
        assert report.all_passed is True
