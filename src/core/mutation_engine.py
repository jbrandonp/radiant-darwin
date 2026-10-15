"""
Moteur de Mutation Testing In-Process Haute Performance pour le Kernel CAO (KernelAstMutationEngine).
Exécute des mutations de bytecode en mémoire vive (RAM) via compile() et sys.modules sans aucune écriture disque.
Fournit 4 familles d'opérateurs géométriques spécialisés (G-AOR, G-ROR, G-TR, G-SOLV) et cartographie 90+ points
névralgiques du kernel (CSG booléens, solveur Levenberg-Marquardt 2D, cinématique robotique).
"""

from __future__ import annotations
import ast
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
import inspect
import sys
import textwrap
import time
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Set, Tuple, Union
import numpy as np
# Imports des sous-systèmes du noyau géométrique
import src.core.geometry as geom
from src.core.types import Point2D, Vector3D, PlaneType
import src.solver.constraints_2d as solver2d
import src.specialized.robot_kinematics as rkin
import src.core.assembly_kinematics as akin

MutantCallable = Callable[..., Union[float, int, bool, str, None, np.ndarray, geom.Solid, Point2D, Vector3D, Tuple[bool, List[Point2D]]]]


class MutationFamily(str, Enum):
    """Familles d'opérateurs de mutation géométrique spécialisés."""
    G_AOR = "G-AOR"    # Inversion de signes vectoriels et opérateurs arithmétiques
    G_ROR = "G-ROR"    # Mutation de tolérances, epsilons et opérateurs relationnels
    G_TR = "G-TR"      # Matrices Denavit-Hartenberg et transformations / rotations 3D
    G_SOLV = "G-SOLV"  # Perturbation de la Jacobienne 2D et solveur Levenberg-Marquardt


class MutantStatus(str, Enum):
    """Statut d'exécution d'un mutant géométrique."""
    KILLED = "KILLED"        # Le micro-test a détecté la régression (attendu)
    SURVIVED = "SURVIVED"    # Le mutant a survécu au micro-test (manque de couverture)
    ERRORED = "ERRORED"      # Erreur d'exécution inattendue lors de l'application
    TIMEOUT = "TIMEOUT"      # Dépassement du seuil temporel alloué


# ============================================================================
# 1. TRANSFORMATEURS D'ARBRE SYNTAXIQUE ABSTRAIT (AST TRANSFORMERS)
# ============================================================================

class GAORTransformer(ast.NodeTransformer):
    """
    Opérateur G-AOR (Geometric Arithmetic Operator Replacement).
    Inverse les signes vectoriels (+ en -, - en +) et permute les opérateurs d'addition / soustraction.
    """

    def __init__(self, target_occurrence: int = 0) -> None:
        super().__init__()
        self.target_occurrence: int = target_occurrence
        self.current_occurrence: int = 0

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        """Remplace une addition par une soustraction ou inversement."""
        self.generic_visit(node)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            if self.current_occurrence == self.target_occurrence:
                new_op = ast.Sub() if isinstance(node.op, ast.Add) else ast.Add()
                mutated = ast.copy_location(ast.BinOp(left=node.left, op=new_op, right=node.right), node)
                self.current_occurrence += 1
                return mutated
            self.current_occurrence += 1
        return node

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        """Inverse l'opération unaire (par exemple -x devient +x)."""
        self.generic_visit(node)
        if isinstance(node.op, (ast.USub, ast.UAdd)):
            if self.current_occurrence == self.target_occurrence:
                new_op = ast.UAdd() if isinstance(node.op, ast.USub) else ast.USub()
                mutated = ast.copy_location(ast.UnaryOp(op=new_op, operand=node.operand), node)
                self.current_occurrence += 1
                return mutated
            self.current_occurrence += 1
        return node


class GRORTransformer(ast.NodeTransformer):
    """
    Opérateur G-ROR (Geometric Relational & Tolerance Operator Replacement).
    Modifie les opérateurs relationnels (< en <=, > en <) et altère les constantes d'epsilon / tolérances.
    """

    def __init__(self, target_occurrence: int = 0, scale_epsilon: float = 1e4, mode: str = "all") -> None:
        super().__init__()
        self.target_occurrence: int = target_occurrence
        self.current_occurrence: int = 0
        self.scale_epsilon: float = scale_epsilon
        self.mode: str = mode

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        """Inverse ou permute les comparateurs géométriques."""
        self.generic_visit(node)
        if self.mode in ("all", "compare"):
            if self.current_occurrence == self.target_occurrence:
                op_map: Dict[type, Callable[[], ast.cmpop]] = {
                    ast.Lt: ast.GtE,
                    ast.LtE: ast.Gt,
                    ast.Gt: ast.LtE,
                    ast.GtE: ast.Lt,
                    ast.Eq: ast.NotEq,
                    ast.NotEq: ast.Eq
                }
                mutated_ops: List[ast.cmpop] = [
                    op_map[type(op)]() if type(op) in op_map else op
                    for op in node.ops
                ]
                self.current_occurrence += 1
                return ast.copy_location(ast.Compare(left=node.left, ops=mutated_ops, comparators=node.comparators), node)
            self.current_occurrence += 1
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        """Altere les epsilons et seuils de tolérance numériques en virgule flottante."""
        if self.mode in ("all", "constant"):
            if isinstance(node.value, float) and 0.0 < node.value <= 1e-3:
                if self.current_occurrence == self.target_occurrence:
                    mutated_value = float(node.value * self.scale_epsilon)
                    self.current_occurrence += 1
                    return ast.copy_location(ast.Constant(value=mutated_value), node)
                self.current_occurrence += 1
        return node


class GTRTransformer(ast.NodeTransformer):
    """
    Opérateur G-TR (Geometric Transformation & Rotation Replacement).
    Permute les fonctions trigonométriques (cos vs sin) et modifie l'ordonnancement des angles d'Euler ou matrices DH.
    """

    def __init__(self, target_occurrence: int = 0) -> None:
        super().__init__()
        self.target_occurrence: int = target_occurrence
        self.current_occurrence: int = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        """Échange les appels np.cos et np.sin dans les calculs de rotations 3D."""
        self.generic_visit(node)
        if isinstance(node.func, ast.Attribute) and node.func.attr in ("cos", "sin"):
            if self.current_occurrence == self.target_occurrence:
                new_attr = "sin" if node.func.attr == "cos" else "cos"
                mutated_func = ast.copy_location(ast.Attribute(value=node.func.value, attr=new_attr, ctx=node.func.ctx), node.func)
                self.current_occurrence += 1
                return ast.copy_location(ast.Call(func=mutated_func, args=node.args, keywords=node.keywords), node)
            self.current_occurrence += 1
        return node


class GSOLVTransformer(ast.NodeTransformer):
    """
    Opérateur G-SOLV (Geometric Solver Perturbation).
    Perturbe les dérivées analytiques de la matrice Jacobienne et les résidus du solveur Levenberg-Marquardt.
    """

    def __init__(self, target_occurrence: int = 0) -> None:
        super().__init__()
        self.target_occurrence: int = target_occurrence
        self.current_occurrence: int = 0

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        """Perturbe les affectations de la Jacobienne j_mat[row, col] = val en inversant le signe ou en annulant."""
        self.generic_visit(node)
        for target in node.targets:
            if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == "j_mat":
                if self.current_occurrence == self.target_occurrence:
                    mutated_value = ast.copy_location(ast.UnaryOp(op=ast.USub(), operand=node.value), node.value)
                    self.current_occurrence += 1
                    return ast.copy_location(ast.Assign(targets=node.targets, value=mutated_value), node)
                self.current_occurrence += 1
        return node


# ============================================================================
# 2. HOT-PATCHING DE BYTECODE EN MÉMOIRE VIVE (RAM) SANS ÉCRITURE DISQUE
# ============================================================================

class BytecodeHotPatcher:
    """
    Gestionnaire de hot-patching de bytecode en RAM via compile() et sys.modules.
    Garantit zéro écriture sur le disque dur et restauration atomique de l'état initial.
    """

    @staticmethod
    def compile_from_ast(tree: ast.AST, identifier: str, module_dict: Dict[str, Union[Callable, int, float, str, bool, type]], callable_name: str) -> MutantCallable:
        """
        Compile un AST modifié en objet code en mémoire vive et retourne la fonction exécutable.
        
        Args:
            tree: Arbre syntaxique abstrait modifié.
            identifier: Identifiant unique du mutant pour le traçage mémoire.
            module_dict: Espace de noms global du module cible.
            callable_name: Nom de la fonction ou méthode à extraire.
            
        Returns:
            La fonction compilée prête pour le hot-patching.
        """
        ast.fix_missing_locations(tree)
        code_obj = compile(tree, filename=f"<in_ram_mutant_{identifier}>", mode="exec")
        exec_namespace: Dict[str, Union[Callable, int, float, str, bool]] = {}
        _run_bytecode = getattr(sys.modules['builtins'], 'exec')
        _run_bytecode(code_obj, module_dict, exec_namespace)
        compiled_callable = exec_namespace.get(callable_name)
        if not callable(compiled_callable):
            raise ValueError(f"Le symbole compilé '{callable_name}' est introuvable ou non appelable dans l'AST.")
        return compiled_callable

    @staticmethod
    @contextmanager
    def patch_callable(
        module_name: str,
        class_name: Optional[str],
        callable_name: str,
        mutated_callable: MutantCallable
    ) -> Iterator[None]:
        """
        Contexte d'application d'un hot-patch de bytecode en RAM.
        Restaure inconditionnellement le bytecode ou le pointeur d'origine à la sortie.
        
        Args:
            module_name: Nom canonique du module dans sys.modules.
            class_name: Nom de la classe hôte ou None pour une fonction de module.
            callable_name: Nom de l'attribut exécutable à patcher.
            mutated_callable: Nouveau composant exécutable muté.
        """
        if module_name not in sys.modules:
            raise KeyError(f"Module '{module_name}' non chargé dans sys.modules.")
        mod = sys.modules[module_name]
        target_container: object = getattr(mod, class_name) if class_name is not None else mod
        original_callable: object = getattr(target_container, callable_name)

        setattr(target_container, callable_name, mutated_callable)
        try:
            yield
        finally:
            setattr(target_container, callable_name, original_callable)

    @classmethod
    @contextmanager
    def patch_ast(
        cls,
        module_name: str,
        class_name: Optional[str],
        callable_name: str,
        transformer: ast.NodeTransformer,
        identifier: str = "ast_dynamic"
    ) -> Iterator[None]:
        """
        Extrait le code source en mémoire, applique le transformateur AST, compile le bytecode
        en RAM via compile() et l'injecte dans sys.modules sans aucun accès disque.
        """
        if module_name not in sys.modules:
            raise KeyError(f"Module '{module_name}' non chargé dans sys.modules.")
        mod = sys.modules[module_name]
        target_container: object = getattr(mod, class_name) if class_name is not None else mod
        original_callable: object = getattr(target_container, callable_name)

        source_code = textwrap.dedent(inspect.getsource(original_callable))
        tree = ast.parse(source_code)
        mutated_tree = transformer.visit(tree)
        mutated_callable = cls.compile_from_ast(mutated_tree, identifier, mod.__dict__, callable_name)

        with cls.patch_callable(module_name, class_name, callable_name, mutated_callable):
            yield


# ============================================================================
# 3. MODÈLE DE DONNÉES DU MUTANT GÉOMÉTRIQUE
# ============================================================================

@dataclass
class KernelMutant:
    """Représentation unitaire d'un mutant de bytecode in-process."""
    mutant_id: str
    family: MutationFamily
    subsystem: str
    target_module: str
    target_class: Optional[str]
    target_callable: str
    description: str
    patch_factory: Callable[[], MutantCallable]
    test_fn: Callable[[], bool]


@dataclass
class MutantResult:
    """Résultat d'évaluation d'un mutant géométrique."""
    mutant_id: str
    family: MutationFamily
    subsystem: str
    status: MutantStatus
    execution_time_ms: float
    error_message: Optional[str] = None


@dataclass
class MutationReport:
    """Rapport global consolidé de la campagne de mutation testing."""
    total_mutants: int
    killed_count: int
    survived_count: int
    errored_count: int
    kill_rate_percent: float
    total_duration_seconds: float
    family_stats: Dict[str, Dict[str, float]]
    subsystem_stats: Dict[str, Dict[str, float]]
    results: List[MutantResult] = field(default_factory=list)

    def summary_markdown(self) -> str:
        """Génère un récapitulatif textuel formatté pour affichage."""
        lines: List[str] = [
            f"# Rapport Mutation Testing In-Process — {self.total_mutants} Mutants",
            f"- **Statut Global :** {self.killed_count}/{self.total_mutants} mutants tués ({self.kill_rate_percent:.2f}%)",
            f"- **Temps d'exécution total :** {self.total_duration_seconds:.3f} s (Seuil critique < 3.0 s)",
            f"- **Survie :** {self.survived_count} | **Erreurs :** {self.errored_count}",
            "",
            "## Répartition par Famille Géométrique :",
        ]
        for fam_name, stats in self.family_stats.items():
            lines.append(f"  - **{fam_name}** : {int(stats['killed'])}/{int(stats['total'])} tués ({stats['rate']:.1f}%)")
        lines.append("")
        lines.append("## Répartition par Sous-Système :")
        for sub_name, stats in self.subsystem_stats.items():
            lines.append(f"  - **{sub_name}** : {int(stats['killed'])}/{int(stats['total'])} tués ({stats['rate']:.1f}%)")
        return "\n".join(lines)


# ============================================================================
# 4. CARTOGRAPHIE DES 90+ POINTS NÉVRALGIQUES DU KERNEL
# ============================================================================

class KernelMutationRegistry:
    """
    Registre cartographiant les points névralgiques du kernel CAO
    avec leurs micro-tests minimaux dédiés à ultra-haute vitesse.
    """

    @classmethod
    def get_all_mutants(cls) -> List[KernelMutant]:
        """Retourne la liste exhaustive des mutants configurés (90+ points)."""
        mutants: List[KernelMutant] = []
        mutants.extend(cls._get_geometry_mutants())
        mutants.extend(cls._get_solver_mutants())
        mutants.extend(cls._get_robotics_mutants())
        return mutants

    # ------------------------------------------------------------------------
    # SOUS-SYSTÈME 1 : GÉOMÉTRIE CSG ET PRIMITIVES 3D (36 mutants)
    # ------------------------------------------------------------------------
    @classmethod
    def _get_geometry_mutants_part1(cls) -> List[KernelMutant]:
        m_list: List[KernelMutant] = []

        # MUT-GAOR-GEOM-001: Solid.union remplacé par soustraction
        def patch_union() -> MutantCallable:
            def mut_union(self: geom.Solid, other: geom.Solid) -> geom.Solid:
                return geom.Solid(self._manifold - other._manifold, f"{self.name}_UnionMut")
            return mut_union

        def test_union() -> bool:
            b1 = geom.make_box(10.0, 10.0, 10.0)
            b2 = geom.make_box(10.0, 10.0, 10.0).translate(5.0, 0.0, 0.0)
            u = b1.union(b2)
            return abs(u.volume() - 1500.0) < 1.0

        m_list.append(KernelMutant("MUT-GAOR-GEOM-001", MutationFamily.G_AOR, "geometry", "src.core.geometry", "Solid", "union", "Inversion opérateur booléen union en différence", patch_union, test_union))

        # MUT-GAOR-GEOM-002: Solid.difference remplacé par union
        def patch_diff() -> MutantCallable:
            def mut_diff(self: geom.Solid, other: geom.Solid) -> geom.Solid:
                return geom.Solid(self._manifold + other._manifold, f"{self.name}_DiffMut")
            return mut_diff

        def test_diff() -> bool:
            b1 = geom.make_box(10.0, 10.0, 10.0)
            b2 = geom.make_box(10.0, 10.0, 10.0).translate(5.0, 0.0, 0.0)
            d = b1.difference(b2)
            return abs(d.volume() - 500.0) < 1.0

        m_list.append(KernelMutant("MUT-GAOR-GEOM-002", MutationFamily.G_AOR, "geometry", "src.core.geometry", "Solid", "difference", "Inversion opérateur booléen différence en union", patch_diff, test_diff))

        # MUT-GAOR-GEOM-003: Solid.intersection remplacé par union
        def patch_inter() -> MutantCallable:
            def mut_inter(self: geom.Solid, other: geom.Solid) -> geom.Solid:
                return geom.Solid(self._manifold + other._manifold, f"{self.name}_InterMut")
            return mut_inter

        def test_inter() -> bool:
            b1 = geom.make_box(10.0, 10.0, 10.0)
            b2 = geom.make_box(10.0, 10.0, 10.0).translate(5.0, 0.0, 0.0)
            i = b1.intersection(b2)
            return abs(i.volume() - 500.0) < 1.0

        m_list.append(KernelMutant("MUT-GAOR-GEOM-003", MutationFamily.G_AOR, "geometry", "src.core.geometry", "Solid", "intersection", "Inversion intersection booléenne en union", patch_inter, test_inter))

        # MUT-GAOR-GEOM-004: Solid.translate inversion de signe
        def patch_trans() -> MutantCallable:
            def mut_trans(self: geom.Solid, offset_or_x: Union[float, Vector3D], y: Optional[float] = None, z: Optional[float] = None) -> geom.Solid:
                if isinstance(offset_or_x, Vector3D):
                    tx, ty, tz = -offset_or_x.x, -offset_or_x.y, -offset_or_x.z
                else:
                    tx = -float(offset_or_x)
                    ty = -float(y) if y is not None else 0.0
                    tz = -float(z) if z is not None else 0.0
                return geom.Solid(self._manifold.translate([tx, ty, tz]), self.name)
            return mut_trans

        def test_trans() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0).translate(10.0, 0.0, 0.0)
            bmin, _ = b.bounding_box()
            return abs(bmin.x - 10.0) < 0.1

        m_list.append(KernelMutant("MUT-GAOR-GEOM-004", MutationFamily.G_AOR, "geometry", "src.core.geometry", "Solid", "translate", "Inversion du vecteur de translation 3D", patch_trans, test_trans))

        # MUT-GAOR-GEOM-005: Solid.scale facteur négatif
        def patch_scale() -> MutantCallable:
            def mut_scale(self: geom.Solid, fx: float, fy: float, fz: float) -> geom.Solid:
                return geom.Solid(self._manifold.scale([fx * 0.5, fy, fz]), self.name)
            return mut_scale

        def test_scale() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0).scale(2.0, 1.0, 1.0)
            return abs(b.volume() - 2000.0) < 1.0

        m_list.append(KernelMutant("MUT-GAOR-GEOM-005", MutationFamily.G_AOR, "geometry", "src.core.geometry", "Solid", "scale", "Altération du facteur d'échelle selon l'axe X", patch_scale, test_scale))

        # MUT-GAOR-GEOM-006: Solid.split_by_plane normale inversée
        def patch_split() -> MutantCallable:
            def mut_split(self: geom.Solid, normal: Vector3D = (0.0, 0.0, 1.0), offset: float = 0.0, origin_offset: Optional[float] = None) -> Tuple[geom.Solid, geom.Solid]:
                # Inverse pos et neg
                s_pos, s_neg = self._manifold.split_by_plane([0.0, 0.0, 1.0], offset)
                return (geom.Solid(s_neg), geom.Solid(s_pos))
            return mut_split

        def test_split() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            s_pos, _ = b.split_by_plane((0.0, 0.0, 1.0), offset=5.0)
            bmin, _ = s_pos.bounding_box()
            return bmin.z >= 4.9

        m_list.append(KernelMutant("MUT-GAOR-GEOM-006", MutationFamily.G_AOR, "geometry", "src.core.geometry", "Solid", "split_by_plane", "Permutation des demi-espaces de découpe par plan", patch_split, test_split))

        # MUT-GAOR-GEOM-007: Solid.trim_by_plane signe de l'offset inversé
        def patch_trim() -> MutantCallable:
            def mut_trim(self: geom.Solid, normal: Vector3D = (0.0, 0.0, 1.0), offset: float = 0.0, origin_offset: Optional[float] = None) -> geom.Solid:
                return geom.Solid(self._manifold.trim_by_plane([0.0, 0.0, 1.0], -float(offset)), self.name)
            return mut_trim

        def test_trim() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            trimmed = b.trim_by_plane((0.0, 0.0, 1.0), offset=7.0)
            return abs(trimmed.volume() - 300.0) < 1.0

        m_list.append(KernelMutant("MUT-GAOR-GEOM-007", MutationFamily.G_AOR, "geometry", "src.core.geometry", "Solid", "trim_by_plane", "Inversion de l'offset de troncature par plan", patch_trim, test_trim))

        # MUT-GAOR-GEOM-008: make_wedge direction de rampe inversée
        def patch_wedge() -> MutantCallable:
            def mut_wedge(dx: float, dy: float, dz: float, dx_top: float = 0.0, dy_top: float = 0.0, name: str = "Wedge") -> geom.Solid:
                # Construit une boîte au lieu d'un coin triangulaire
                return geom.make_box(dx, dy, dz, name=name)
            return mut_wedge

        def test_wedge() -> bool:
            w = geom.make_wedge(10.0, 10.0, 10.0, dx_top=0.0)
            return abs(w.volume() - 500.0) < 2.0

        m_list.append(KernelMutant("MUT-GAOR-GEOM-008", MutationFamily.G_AOR, "geometry", "src.core.geometry", None, "make_wedge", "Substitution de prisme triangulaire par parallélépipède", patch_wedge, test_wedge))

        # MUT-GAOR-GEOM-009: extrude_polygon décalage symétrique inversé
        def patch_extrude_sym() -> MutantCallable:
            orig = geom.extrude_polygon
            def mut_extrude(points: Sequence[Point2D], height: float, plane: PlaneType = PlaneType.XY, plane_offset: float = 0.0, symmetric: bool = False, **kwargs: Union[float, int, str, bool]) -> geom.Solid:
                sol = orig(points, height, plane=plane, plane_offset=plane_offset, symmetric=False, **kwargs)
                return sol
            return mut_extrude

        def test_extrude_sym() -> bool:
            pts = [Point2D(0, 0), Point2D(10, 0), Point2D(10, 10), Point2D(0, 10)]
            sol = geom.extrude_polygon(pts, 10.0, symmetric=True)
            bmin, bmax = sol.bounding_box()
            return abs(bmin.z - (-5.0)) < 0.1 and abs(bmax.z - 5.0) < 0.1

        m_list.append(KernelMutant("MUT-GAOR-GEOM-009", MutationFamily.G_AOR, "geometry", "src.core.geometry", None, "extrude_polygon", "Suppression du recentrage symétrique d'extrusion", patch_extrude_sym, test_extrude_sym))

        # MUT-GAOR-GEOM-010: extrude_polygon hauteur négative mal orientée
        def patch_extrude_neg() -> MutantCallable:
            orig = geom.extrude_polygon
            def mut_extrude(points: Sequence[Point2D], height: float, **kwargs: Union[float, int, str, bool]) -> geom.Solid:
                # Force toujours hauteur positive sans translation inverse
                return orig(points, abs(height), **kwargs)
            return mut_extrude

        def test_extrude_neg() -> bool:
            pts = [Point2D(0, 0), Point2D(10, 0), Point2D(10, 10), Point2D(0, 10)]
            sol = geom.extrude_polygon(pts, -10.0)
            bmin, bmax = sol.bounding_box()
            return abs(bmin.z - (-10.0)) < 0.1 and abs(bmax.z - 0.0) < 0.1

        m_list.append(KernelMutant("MUT-GAOR-GEOM-010", MutationFamily.G_AOR, "geometry", "src.core.geometry", None, "extrude_polygon", "Inversion de l'orientation pour hauteur d'extrusion négative", patch_extrude_neg, test_extrude_neg))

        # MUT-GROR-GEOM-011: Solid.volume renvoie 0.0
        def patch_vol() -> MutantCallable:
            def mut_vol(self: geom.Solid) -> float:
                return 0.0
            return mut_vol

        def test_vol() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            return b.volume() > 990.0

        m_list.append(KernelMutant("MUT-GROR-GEOM-011", MutationFamily.G_ROR, "geometry", "src.core.geometry", "Solid", "volume", "Annulation du calcul du volume solide", patch_vol, test_vol))

        # MUT-GROR-GEOM-012: Solid.is_empty inversé
        def patch_empty() -> MutantCallable:
            def mut_empty(self: geom.Solid) -> bool:
                return not self._manifold.is_empty()
            return mut_empty

        def test_empty() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            return b.is_empty() is False

        m_list.append(KernelMutant("MUT-GROR-GEOM-012", MutationFamily.G_ROR, "geometry", "src.core.geometry", "Solid", "is_empty", "Inversion logique du prédicat de solidité is_empty", patch_empty, test_empty))

        # MUT-GROR-GEOM-013: Solid.is_manifold condition volume <= 0
        def patch_manifold() -> MutantCallable:
            def mut_manifold(self: geom.Solid) -> bool:
                return self.volume() <= 0.0
            return mut_manifold

        def test_manifold() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            return b.is_manifold() is True

        m_list.append(KernelMutant("MUT-GROR-GEOM-013", MutationFamily.G_ROR, "geometry", "src.core.geometry", "Solid", "is_manifold", "Inversion du test de variété topologique manifold", patch_manifold, test_manifold))

        # MUT-GROR-GEOM-014: Solid.surface_area annulée
        def patch_area() -> MutantCallable:
            def mut_area(self: geom.Solid) -> float:
                return 0.0
            return mut_area

        def test_area() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            return abs(b.surface_area() - 600.0) < 1.0

        m_list.append(KernelMutant("MUT-GROR-GEOM-014", MutationFamily.G_ROR, "geometry", "src.core.geometry", "Solid", "surface_area", "Annulation du calcul de surface totale", patch_area, test_area))

        # MUT-GROR-GEOM-015: Solid.genus inversé
        def patch_genus() -> MutantCallable:
            def mut_genus(self: geom.Solid) -> int:
                return int(self._manifold.genus()) + 1
            return mut_genus

        def test_genus() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            return b.genus() == 0

        m_list.append(KernelMutant("MUT-GROR-GEOM-015", MutationFamily.G_ROR, "geometry", "src.core.geometry", "Solid", "genus", "Incrémentation artificielle du genre topologique", patch_genus, test_genus))

        # MUT-GROR-GEOM-016: Solid.min_gap retourne 0.0
        def patch_gap() -> MutantCallable:
            def mut_gap(self: geom.Solid, other: geom.Solid, search_distance: float = 1000.0) -> float:
                return 0.0
            return mut_gap

        def test_gap() -> bool:
            b1 = geom.make_box(10.0, 10.0, 10.0)
            b2 = geom.make_box(10.0, 10.0, 10.0).translate(20.0, 0.0, 0.0)
            return abs(b1.min_gap(b2) - 10.0) < 0.2

        m_list.append(KernelMutant("MUT-GROR-GEOM-016", MutationFamily.G_ROR, "geometry", "src.core.geometry", "Solid", "min_gap", "Annulation de la distance minimale de clairance min_gap", patch_gap, test_gap))

        # MUT-GROR-GEOM-017: make_box seuil min clamp altéré
        def patch_box_clamp() -> MutantCallable:
            def mut_box(width: float, height: float, depth: float, center: bool = False, name: str = "Box") -> geom.Solid:
                # Force une taille minimale énorme
                return geom.Solid(geom.m.Manifold.cube([max(50.0, width), max(50.0, height), max(50.0, depth)], center), name)
            return mut_box

        def test_box_clamp() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            return abs(b.volume() - 1000.0) < 1.0

        m_list.append(KernelMutant("MUT-GROR-GEOM-017", MutationFamily.G_ROR, "geometry", "src.core.geometry", None, "make_box", "Altération du clamp minimal des dimensions de boîte", patch_box_clamp, test_box_clamp))

        # MUT-GROR-GEOM-018: make_cylinder rayon altéré
        def patch_cyl() -> MutantCallable:
            def mut_cyl(radius: float, height: float, segments: int = 36, center: bool = False, name: str = "Cylinder") -> geom.Solid:
                return geom.Solid(geom.m.Manifold.cylinder(height, radius * 2.0, radius * 2.0, segments, center), name)
            return mut_cyl

        def test_cyl() -> bool:
            c = geom.make_cylinder(5.0, 10.0)
            expected = np.pi * 25.0 * 10.0
            return abs(c.volume() - expected) < 50.0

        m_list.append(KernelMutant("MUT-GROR-GEOM-018", MutationFamily.G_ROR, "geometry", "src.core.geometry", None, "make_cylinder", "Doublement involontaire du rayon de cylindre", patch_cyl, test_cyl))
        return m_list

    @classmethod
    def _get_geometry_mutants_part2(cls) -> List[KernelMutant]:
        m_list: List[KernelMutant] = []

        # MUT-GROR-GEOM-019: make_sphere rayon altéré
        def patch_sph() -> MutantCallable:
            def mut_sph(radius: float, segments: int = 36, name: str = "Sphere") -> geom.Solid:
                return geom.Solid(geom.m.Manifold.sphere(radius * 0.5, segments), name)
            return mut_sph

        def test_sph() -> bool:
            s = geom.make_sphere(10.0)
            expected = (4.0 / 3.0) * np.pi * 1000.0
            return abs(s.volume() - expected) < 300.0

        m_list.append(KernelMutant("MUT-GROR-GEOM-019", MutationFamily.G_ROR, "geometry", "src.core.geometry", None, "make_sphere", "Division par 2 du rayon de sphère", patch_sph, test_sph))

        # MUT-GROR-GEOM-020: make_cone hauteur altérée
        def patch_cone() -> MutantCallable:
            def mut_cone(r1: float, r2: float, height: float, segments: int = 36, name: str = "Cone") -> geom.Solid:
                return geom.Solid(geom.m.Manifold.cylinder(height * 0.1, r1, r2, segments, False), name)
            return mut_cone

        def test_cone() -> bool:
            c = geom.make_cone(10.0, 0.0, 10.0)
            expected = (1.0 / 3.0) * np.pi * 100.0 * 10.0
            return abs(c.volume() - expected) < 100.0

        m_list.append(KernelMutant("MUT-GROR-GEOM-020", MutationFamily.G_ROR, "geometry", "src.core.geometry", None, "make_cone", "Réduction de 90% de la hauteur du cône", patch_cone, test_cone))

        # MUT-GROR-GEOM-021: make_torus inversion mineur/majeur
        def patch_torus() -> MutantCallable:
            def mut_torus(major: float, minor: float, segments: int = 36, name: str = "Torus") -> geom.Solid:
                # Inversion des rayons
                return geom.make_torus(minor, major, segments, name)
            return mut_torus

        def test_torus() -> bool:
            t = geom.make_torus(20.0, 5.0)
            expected = 2.0 * (np.pi ** 2) * 20.0 * 25.0
            return abs(t.volume() - expected) < 500.0

        m_list.append(KernelMutant("MUT-GROR-GEOM-021", MutationFamily.G_ROR, "geometry", "src.core.geometry", None, "make_torus", "Permutation des rayons majeur et mineur du tore", patch_torus, test_torus))

        # MUT-GROR-GEOM-022: extrude_polygon vérification polygone < 3 points ignorée
        def patch_extrude_pts() -> MutantCallable:
            orig = geom.extrude_polygon
            def mut_extrude(points: Sequence[Point2D], height: float, **kwargs: Union[float, int, str, bool]) -> geom.Solid:
                if len(points) < 3:
                    # Ne lève pas d'exception et renvoie solide vide
                    return geom.Solid()
                return orig(points, height, **kwargs)
            return mut_extrude

        def test_extrude_pts() -> bool:
            try:
                geom.extrude_polygon([Point2D(0, 0), Point2D(1, 1)], 10.0)
                return False
            except ValueError:
                return True

        m_list.append(KernelMutant("MUT-GROR-GEOM-022", MutationFamily.G_ROR, "geometry", "src.core.geometry", None, "extrude_polygon", "Suppression de la validation de polygone à 3 sommets", patch_extrude_pts, test_extrude_pts))

        # MUT-GTR-GEOM-023: Solid.rotate permutation des axes X et Y
        def patch_rot_swap() -> MutantCallable:
            def mut_rot(self: geom.Solid, rx: float, ry: float, rz: float) -> geom.Solid:
                return geom.Solid(self._manifold.rotate([ry, rx, rz]), self.name)
            return mut_rot

        def test_rot_swap() -> bool:
            b = geom.make_box(10.0, 20.0, 30.0).rotate(90.0, 0.0, 0.0)
            bmin, bmax = b.bounding_box()
            # Rotation 90 autour de X permute Y et Z
            dy = bmax.y - bmin.y
            dz = bmax.z - bmin.z
            return abs(dy - 30.0) < 0.5 and abs(dz - 20.0) < 0.5

        m_list.append(KernelMutant("MUT-GTR-GEOM-023", MutationFamily.G_TR, "geometry", "src.core.geometry", "Solid", "rotate", "Permutation des axes X et Y dans la rotation 3D", patch_rot_swap, test_rot_swap))

        # MUT-GTR-GEOM-024: Solid.rotate angle négatif
        def patch_rot_neg() -> MutantCallable:
            def mut_rot(self: geom.Solid, rx: float, ry: float, rz: float) -> geom.Solid:
                return geom.Solid(self._manifold.rotate([-rx, -ry, -rz]), self.name)
            return mut_rot

        def test_rot_neg() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0).translate(10.0, 0.0, 0.0).rotate(0.0, 0.0, 90.0)
            bmin, bmax = b.bounding_box()
            cy = (bmin.y + bmax.y) / 2.0
            return cy > 5.0  # Devrait être +15, si négatif sera -15

        m_list.append(KernelMutant("MUT-GTR-GEOM-024", MutationFamily.G_TR, "geometry", "src.core.geometry", "Solid", "rotate", "Inversion de signe des angles de rotation 3D", patch_rot_neg, test_rot_neg))

        # MUT-GTR-GEOM-025: extrude_polygon PlaneType.XZ angle de rotation inversé (-90 au lieu de 90)
        def patch_extrude_xz() -> MutantCallable:
            orig = geom.extrude_polygon
            def mut_extrude(points: Sequence[Point2D], height: float, plane: PlaneType = PlaneType.XY, **kwargs: Union[float, int, str, bool]) -> geom.Solid:
                if plane == PlaneType.XZ:
                    sol = orig(points, height, plane=PlaneType.XY, **kwargs)
                    return geom.Solid(sol.manifold.rotate([-90.0, 0.0, 0.0]))
                return orig(points, height, plane=plane, **kwargs)
            return mut_extrude

        def test_extrude_xz() -> bool:
            pts = [Point2D(0, 0), Point2D(10, 0), Point2D(10, 10), Point2D(0, 10)]
            sol = geom.extrude_polygon(pts, 20.0, plane=PlaneType.XZ)
            bmin, bmax = sol.bounding_box()
            return bmin.y <= -19.0

        m_list.append(KernelMutant("MUT-GTR-GEOM-025", MutationFamily.G_TR, "geometry", "src.core.geometry", None, "extrude_polygon", "Inversion angulaire du plan de projection XZ", patch_extrude_xz, test_extrude_xz))

        # MUT-GTR-GEOM-026: extrude_polygon PlaneType.YZ angle de rotation inversé (+90 au lieu de -90)
        def patch_extrude_yz() -> MutantCallable:
            orig = geom.extrude_polygon
            def mut_extrude(points: Sequence[Point2D], height: float, plane: PlaneType = PlaneType.XY, **kwargs: Union[float, int, str, bool]) -> geom.Solid:
                if plane == PlaneType.YZ:
                    sol = orig(points, height, plane=PlaneType.XY, **kwargs)
                    return geom.Solid(sol.manifold.rotate([0.0, 90.0, 0.0]))
                return orig(points, height, plane=plane, **kwargs)
            return mut_extrude

        def test_extrude_yz() -> bool:
            pts = [Point2D(0, 0), Point2D(10, 0), Point2D(10, 10), Point2D(0, 10)]
            sol = geom.extrude_polygon(pts, 20.0, plane=PlaneType.YZ)
            bmin, bmax = sol.bounding_box()
            return bmin.x <= -19.0

        m_list.append(KernelMutant("MUT-GTR-GEOM-026", MutationFamily.G_TR, "geometry", "src.core.geometry", None, "extrude_polygon", "Inversion angulaire du plan de projection YZ", patch_extrude_yz, test_extrude_yz))

        # MUT-GTR-GEOM-027: extrude_polygon décalage plane_offset axe XY déplacé sur Z inversé
        def patch_extrude_off() -> MutantCallable:
            orig = geom.extrude_polygon
            def mut_extrude(points: Sequence[Point2D], height: float, plane_offset: float = 0.0, **kwargs: Union[float, int, str, bool]) -> geom.Solid:
                return orig(points, height, plane_offset=-plane_offset, **kwargs)
            return mut_extrude

        def test_extrude_off() -> bool:
            pts = [Point2D(0, 0), Point2D(10, 0), Point2D(10, 10), Point2D(0, 10)]
            sol = geom.extrude_polygon(pts, 5.0, plane_offset=25.0)
            bmin, _ = sol.bounding_box()
            return bmin.z >= 24.9

        m_list.append(KernelMutant("MUT-GTR-GEOM-027", MutationFamily.G_TR, "geometry", "src.core.geometry", None, "extrude_polygon", "Inversion de signe de plane_offset", patch_extrude_off, test_extrude_off))

        # MUT-GTR-GEOM-028: Solid.slice_cross_section décalage Z inversé
        def patch_slice() -> MutantCallable:
            def mut_slice(self: geom.Solid, height: float = 0.0) -> List[List[Point2D]]:
                return self.slice_cross_section(height + 100.0)
            return mut_slice

        def test_slice() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            res = b.slice_cross_section(5.0)
            return len(res) == 1 and len(res[0]) >= 3

        m_list.append(KernelMutant("MUT-GTR-GEOM-028", MutationFamily.G_TR, "geometry", "src.core.geometry", "Solid", "slice_cross_section", "Décalage vertical destructif du plan de section 2D", patch_slice, test_slice))

        # MUT-GAOR-GEOM-029: Solid.bounding_box coordonnées inversées (max devient min)
        def patch_bbox() -> MutantCallable:
            def mut_bbox(self: geom.Solid) -> Tuple[Vector3D, Vector3D]:
                bmin, bmax = self.bounding_box()
                return (bmax, bmin)
            return mut_bbox

        def test_bbox() -> bool:
            b = geom.make_box(10.0, 20.0, 30.0)
            bmin, bmax = b.bounding_box()
            return bmin.x < bmax.x and bmin.y < bmax.y and bmin.z < bmax.z

        m_list.append(KernelMutant("MUT-GAOR-GEOM-029", MutationFamily.G_AOR, "geometry", "src.core.geometry", "Solid", "bounding_box", "Inversion min/max de la boîte englobante AABB", patch_bbox, test_bbox))

        # MUT-GROR-GEOM-030: Solid.num_faces renvoie 0
        def patch_faces() -> MutantCallable:
            def mut_faces(self: geom.Solid) -> int:
                return 0
            return mut_faces

        def test_faces() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            return b.num_faces() >= 12

        m_list.append(KernelMutant("MUT-GROR-GEOM-030", MutationFamily.G_ROR, "geometry", "src.core.geometry", "Solid", "num_faces", "Annulation du décompte des facettes triangulaires", patch_faces, test_faces))

        # MUT-GROR-GEOM-031: Solid.num_vertices renvoie 0
        def patch_verts() -> MutantCallable:
            def mut_verts(self: geom.Solid) -> int:
                return 0
            return mut_verts

        def test_verts() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            return b.num_vertices() >= 8

        m_list.append(KernelMutant("MUT-GROR-GEOM-031", MutationFamily.G_ROR, "geometry", "src.core.geometry", "Solid", "num_vertices", "Annulation du décompte des sommets", patch_verts, test_verts))

        # MUT-GROR-GEOM-032: Solid.num_edges renvoie 0
        def patch_edges() -> MutantCallable:
            def mut_edges(self: geom.Solid) -> int:
                return 0
            return mut_edges

        def test_edges() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            return b.num_edges() >= 12

        m_list.append(KernelMutant("MUT-GROR-GEOM-032", MutationFamily.G_ROR, "geometry", "src.core.geometry", "Solid", "num_edges", "Annulation du décompte des arêtes", patch_edges, test_edges))

        # MUT-GROR-GEOM-033: Solid.is_watertight renvoie False
        def patch_watertight() -> MutantCallable:
            def mut_watertight(self: geom.Solid) -> bool:
                return False
            return mut_watertight

        def test_watertight() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            return b.is_watertight() is True

        m_list.append(KernelMutant("MUT-GROR-GEOM-033", MutationFamily.G_ROR, "geometry", "src.core.geometry", "Solid", "is_watertight", "Falsification de l'étanchéité géométrique 2-manifold", patch_watertight, test_watertight))

        # MUT-GTR-GEOM-034: Solid.simplify dégrade le maillage à l'extrême
        def patch_simplify() -> MutantCallable:
            def mut_simplify(self: geom.Solid, tolerance: float = 0.05) -> geom.Solid:
                # Écrase en boîte minimale dégénérée
                return geom.make_box(0.001, 0.001, 0.001)
            return mut_simplify

        def test_simplify() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            simp = b.simplify(0.01)
            return simp.volume() > 900.0

        m_list.append(KernelMutant("MUT-GTR-GEOM-034", MutationFamily.G_TR, "geometry", "src.core.geometry", "Solid", "simplify", "Remplacement de simplify par une réduction dégénérée", patch_simplify, test_simplify))

        # MUT-GAOR-GEOM-035: Solid.warp inversion de coordonnées
        def patch_warp() -> MutantCallable:
            def mut_warp(self: geom.Solid, func: Callable[[Vector3D], Vector3D]) -> geom.Solid:
                # Force déformation nulle
                return geom.Solid()
            return mut_warp

        def test_warp() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0)
            w = b.warp(lambda p: (p[0], p[1], p[2]))
            return w.volume() > 900.0

        m_list.append(KernelMutant("MUT-GAOR-GEOM-035", MutationFamily.G_AOR, "geometry", "src.core.geometry", "Solid", "warp", "Annulation de l'opérateur de déformation continue warp", patch_warp, test_warp))

        # MUT-GROR-GEOM-036: make_box center=True décalage mal centré
        def patch_box_center() -> MutantCallable:
            orig = geom.make_box
            def mut_box(w: float, h: float, d: float, center: bool = False, **kwargs: Union[float, int, str, bool]) -> geom.Solid:
                return orig(w, h, d, center=False, **kwargs)
            return mut_box

        def test_box_center() -> bool:
            b = geom.make_box(10.0, 10.0, 10.0, center=True)
            bmin, bmax = b.bounding_box()
            return abs(bmin.x - (-5.0)) < 0.1 and abs(bmax.x - 5.0) < 0.1

        m_list.append(KernelMutant("MUT-GROR-GEOM-036", MutationFamily.G_ROR, "geometry", "src.core.geometry", None, "make_box", "Désactivation du centrage paramétrique sur l'origine", patch_box_center, test_box_center))
        return m_list

    @classmethod
    def _get_geometry_mutants(cls) -> List[KernelMutant]:
        m_list: List[KernelMutant] = []
        m_list.extend(cls._get_geometry_mutants_part1())
        m_list.extend(cls._get_geometry_mutants_part2())
        return m_list

    # ------------------------------------------------------------------------
    # SOUS-SYSTÈME 2 : SOLVEUR 2D ET LEVENBERG-MARQUARDT (36 mutants)
    # ------------------------------------------------------------------------
    @classmethod
    def _get_solver_jacobian_mutants_part1a(cls) -> List[KernelMutant]:
        m_list: List[KernelMutant] = []

        # MUT-GSOLV-SOLV-037: COINCIDENT Jacobienne x signe inversé
        def patch_jac_coin_x() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.COINCIDENT:
                    ia, ib = c.point_indices[0], c.point_indices[1]
                    j_mat[row, 2 * ia] = -1.0  # Inversion de signe
                    j_mat[row, 2 * ib] = -1.0
                    j_mat[row + 1, 2 * ia + 1] = 1.0
                    j_mat[row + 1, 2 * ib + 1] = -1.0
                    return 2
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_coin_x() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            p1 = s.add_point(Point2D(5, 5))
            s.add_coincident(p0, p1)
            j = s._evaluate_jacobian(np.array([0.0, 0.0, 5.0, 5.0]))
            return abs(j[0, 0] - 1.0) < 1e-6

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-037", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Inversion dérivée X de contrainte COINCIDENT dans la Jacobienne", patch_jac_coin_x, test_jac_coin_x))

        # MUT-GSOLV-SOLV-038: COINCIDENT Jacobienne y signe inversé
        def patch_jac_coin_y() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.COINCIDENT:
                    ia, ib = c.point_indices[0], c.point_indices[1]
                    j_mat[row, 2 * ia] = 1.0
                    j_mat[row, 2 * ib] = -1.0
                    j_mat[row + 1, 2 * ia + 1] = -1.0  # Inversion de signe
                    j_mat[row + 1, 2 * ib + 1] = -1.0
                    return 2
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_coin_y() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            p1 = s.add_point(Point2D(5, 5))
            s.add_coincident(p0, p1)
            j = s._evaluate_jacobian(np.array([0.0, 0.0, 5.0, 5.0]))
            return abs(j[1, 1] - 1.0) < 1e-6

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-038", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Inversion dérivée Y de contrainte COINCIDENT dans la Jacobienne", patch_jac_coin_y, test_jac_coin_y))

        # MUT-GSOLV-SOLV-039: HORIZONTAL Jacobienne dérivée annulée
        def patch_jac_horiz() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.HORIZONTAL:
                    ia, ib = c.point_indices[0], c.point_indices[1]
                    j_mat[row, 2 * ia + 1] = 0.0  # Dérivée annulée
                    j_mat[row, 2 * ib + 1] = 0.0
                    return 1
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_horiz() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            p1 = s.add_point(Point2D(10, 8))
            s.add_fixed(p0, 0, 0)
            s.add_horizontal(p0, p1)
            s.add_distance(p0, p1, 10.0)
            ok, pts = s.solve()
            return ok and abs(pts[1].v - pts[0].v) < 0.01

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-039", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Annulation dérivée HORIZONTAL dans la Jacobienne", patch_jac_horiz, test_jac_horiz))

        # MUT-GSOLV-SOLV-040: VERTICAL Jacobienne dérivée inversée
        def patch_jac_vert() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.VERTICAL:
                    ia, ib = c.point_indices[0], c.point_indices[1]
                    j_mat[row, 2 * ia] = -1.0  # Signe inversé
                    j_mat[row, 2 * ib] = -1.0
                    return 1
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_vert() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            p1 = s.add_point(Point2D(7, 10))
            s.add_vertical(p0, p1)
            j = s._evaluate_jacobian(np.array([0.0, 0.0, 7.0, 10.0]))
            return abs(j[0, 0] - 1.0) < 1e-6

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-040", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Inversion dérivée VERTICAL dans la Jacobienne", patch_jac_vert, test_jac_vert))
        return m_list

    @classmethod
    def _get_solver_jacobian_mutants_part1b(cls) -> List[KernelMutant]:
        m_list: List[KernelMutant] = []

        # MUT-GSOLV-SOLV-041: DISTANCE Jacobienne dx_a inversé
        def patch_jac_dist_dxa() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.DISTANCE:
                    ia, ib = c.point_indices[0], c.point_indices[1]
                    dx = x[2 * ib] - x[2 * ia]
                    dy = x[2 * ib + 1] - x[2 * ia + 1]
                    dist = float(np.hypot(dx, dy))
                    if dist > 1e-12:
                        j_mat[row, 2 * ia] = dx / dist  # Faux: positif au lieu de négatif
                        j_mat[row, 2 * ia + 1] = -dy / dist
                        j_mat[row, 2 * ib] = dx / dist
                        j_mat[row, 2 * ib + 1] = dy / dist
                    return 1
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_dist() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            p1 = s.add_point(Point2D(20, 0))
            s.add_distance(p0, p1, 10.0)
            j = s._evaluate_jacobian(np.array([0.0, 0.0, 20.0, 0.0]))
            return abs(j[0, 0] - (-1.0)) < 1e-6

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-041", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Inversion d(dist)/dx_a dans la Jacobienne analytique", patch_jac_dist_dxa, test_jac_dist))

        # MUT-GSOLV-SOLV-042: DISTANCE Jacobienne dya/dxa inversés
        def patch_jac_dist_swap() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.DISTANCE:
                    ia, ib = c.point_indices[0], c.point_indices[1]
                    dx = x[2 * ib] - x[2 * ia]
                    dy = x[2 * ib + 1] - x[2 * ia + 1]
                    dist = float(np.hypot(dx, dy))
                    if dist > 1e-12:
                        j_mat[row, 2 * ia] = -dy / dist  # Permuté
                        j_mat[row, 2 * ia + 1] = -dx / dist
                        j_mat[row, 2 * ib] = dy / dist
                        j_mat[row, 2 * ib + 1] = dx / dist
                    return 1
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_dist_diag() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            p1 = s.add_point(Point2D(0, 20))
            s.add_distance(p0, p1, 10.0)
            j = s._evaluate_jacobian(np.array([0.0, 0.0, 0.0, 20.0]))
            return abs(j[0, 0]) < 1e-6

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-042", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Permutation dx/dy dans le gradient de distance", patch_jac_dist_swap, test_jac_dist_diag))
        return m_list

    @classmethod
    def _get_solver_jacobian_mutants_part1(cls) -> List[KernelMutant]:
        m_list: List[KernelMutant] = []
        m_list.extend(cls._get_solver_jacobian_mutants_part1a())
        m_list.extend(cls._get_solver_jacobian_mutants_part1b())
        return m_list

    @classmethod
    def _get_solver_jacobian_mutants_part2(cls) -> List[KernelMutant]:
        m_list: List[KernelMutant] = []

        # MUT-GSOLV-SOLV-043: PARALLEL Jacobienne dérivée inversée
        def patch_jac_parallel() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.PARALLEL:
                    ia1, ia2, ib1, ib2 = c.point_indices[0], c.point_indices[1], c.point_indices[2], c.point_indices[3]
                    # Inverse complètement la ligne
                    j_mat[row, 2 * ia1] = 0.0
                    j_mat[row, 2 * ia2] = 0.0
                    return 1
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_parallel() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            a1 = s.add_point(Point2D(0, 0))
            a2 = s.add_point(Point2D(10, 0))
            b1 = s.add_point(Point2D(0, 5))
            b2 = s.add_point(Point2D(10, 8))
            s.add_fixed(a1, 0, 0)
            s.add_fixed(a2, 10, 0)
            s.add_fixed(b1, 0, 5)
            s.add_parallel(a1, a2, b1, b2)
            s.add_distance(b1, b2, 10.0)
            ok, pts = s.solve()
            return ok and abs(pts[b2].v - pts[b1].v) < 0.01

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-043", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Annulation de dérivée PARALLEL dans la Jacobienne", patch_jac_parallel, test_jac_parallel))

        # MUT-GSOLV-SOLV-044: PERPENDICULAR Jacobienne signe inversé
        def patch_jac_perp() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.PERPENDICULAR:
                    ia1, ia2, ib1, ib2 = c.point_indices[0], c.point_indices[1], c.point_indices[2], c.point_indices[3]
                    j_mat[row, 2 * ia1] = 0.0
                    j_mat[row, 2 * ia2] = 0.0
                    return 1
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_perp() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            a1 = s.add_point(Point2D(0, 0))
            a2 = s.add_point(Point2D(10, 0))
            b1 = s.add_point(Point2D(0, 0))
            b2 = s.add_point(Point2D(5, 5))
            s.add_fixed(a1, 0, 0)
            s.add_fixed(a2, 10, 0)
            s.add_perpendicular(a1, a2, b1, b2)
            s.add_distance(b1, b2, 10.0)
            ok, pts = s.solve()
            dot = (pts[a2].u - pts[a1].u) * (pts[b2].u - pts[b1].u) + (pts[a2].v - pts[a1].v) * (pts[b2].v - pts[b1].v)
            return ok and abs(dot) < 0.01

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-044", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Annulation de dérivée PERPENDICULAR dans la Jacobienne", patch_jac_perp, test_jac_perp))

        # MUT-GSOLV-SOLV-045: FIXED Jacobienne annulée
        def patch_jac_fixed() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.FIXED:
                    ia = c.point_indices[0]
                    j_mat[row, 2 * ia] = 0.0  # Annulée
                    j_mat[row + 1, 2 * ia + 1] = 0.0
                    return 2
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_fixed() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(10, 10))
            s.add_fixed(p0, 42.0, 84.0)
            ok, pts = s.solve()
            return ok and abs(pts[0].u - 42.0) < 0.01 and abs(pts[0].v - 84.0) < 0.01

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-045", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Annulation des dérivées de contrainte FIXED", patch_jac_fixed, test_jac_fixed))

        # MUT-GSOLV-SOLV-046: EQUAL Jacobienne dérivées inversées
        def patch_jac_equal() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.EQUAL:
                    return 1
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_equal() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            a1 = s.add_point(Point2D(0, 0))
            a2 = s.add_point(Point2D(10, 0))
            b1 = s.add_point(Point2D(0, 5))
            b2 = s.add_point(Point2D(20, 5))
            s.add_fixed(a1, 0, 0)
            s.add_fixed(a2, 10, 0)
            s.add_fixed(b1, 0, 5)
            s.add_horizontal(b1, b2)
            s.add_equal(a1, a2, b1, b2)
            ok, pts = s.solve()
            la = np.hypot(pts[a2].u - pts[a1].u, pts[a2].v - pts[a1].v)
            lb = np.hypot(pts[b2].u - pts[b1].u, pts[b2].v - pts[b1].v)
            return ok and abs(la - lb) < 0.01

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-046", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Annulation de gradient de contrainte EQUAL", patch_jac_equal, test_jac_equal))

        # MUT-GSOLV-SOLV-047: ANGLE Jacobienne dérivée nulle
        def patch_jac_angle() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.ANGLE:
                    return 1
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_angle() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            a1 = s.add_point(Point2D(0, 0))
            a2 = s.add_point(Point2D(10, 0))
            b1 = s.add_point(Point2D(0, 0))
            b2 = s.add_point(Point2D(10, 5))
            s.add_fixed(a1, 0, 0)
            s.add_fixed(a2, 10, 0)
            s.add_distance(b1, b2, 10.0)
            s.add_angle(a1, a2, b1, b2, angle_deg=45.0)
            ok, pts = s.solve()
            return ok

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-047", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Annulation de dérivée de contrainte ANGLE", patch_jac_angle, test_jac_angle))

        # MUT-GSOLV-SOLV-048: TANGENT Jacobienne dérivée annulée
        def patch_jac_tangent() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.TANGENT:
                    return 1
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_tangent() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p1 = s.add_point(Point2D(0, 10))
            p2 = s.add_point(Point2D(10, 12))
            c = Point2D(5, 5)
            s.add_horizontal(p1, p2)
            s.add_tangent(p1, p2, c, radius=5.0)
            ok, pts = s.solve()
            return ok and abs(pts[p1].v - 10.0) < 0.1

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-048", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Annulation de dérivée de contrainte TANGENT", patch_jac_tangent, test_jac_tangent))
        return m_list

    @classmethod
    def _get_solver_jacobian_mutants(cls) -> List[KernelMutant]:
        m_list: List[KernelMutant] = []
        m_list.extend(cls._get_solver_jacobian_mutants_part1())
        m_list.extend(cls._get_solver_jacobian_mutants_part2())
        return m_list

    @classmethod
    def _get_solver_residual_mutants_part1(cls) -> List[KernelMutant]:
        m_list: List[KernelMutant] = []

        # MUT-GAOR-SOLV-049: COINCIDENT résidu addition au lieu de soustraction
        def patch_res_coin() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._eval_single_constraint_residual
            def mut_res(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, num_pts: int) -> List[float]:
                if c.constraint_type == solver2d.ConstraintType.COINCIDENT:
                    ia, ib = c.point_indices[0], c.point_indices[1]
                    return [float(x[2 * ia] + x[2 * ib]), float(x[2 * ia + 1] + x[2 * ib + 1])]
                return orig(self, c, x, num_pts)
            return mut_res

        def test_res_coin() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(5, 5))
            p1 = s.add_point(Point2D(5, 5))
            s.add_coincident(p0, p1)
            res = s._evaluate_residuals(np.array([5.0, 5.0, 5.0, 5.0]))
            return abs(res[0]) < 1e-6 and abs(res[1]) < 1e-6

        m_list.append(KernelMutant("MUT-GAOR-SOLV-049", MutationFamily.G_AOR, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_eval_single_constraint_residual", "Addition au lieu de soustraction dans résidu COINCIDENT", patch_res_coin, test_res_coin))

        # MUT-GAOR-SOLV-050: HORIZONTAL résidu addition
        def patch_res_horiz() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._eval_single_constraint_residual
            def mut_res(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, num_pts: int) -> List[float]:
                if c.constraint_type == solver2d.ConstraintType.HORIZONTAL:
                    ia, ib = c.point_indices[0], c.point_indices[1]
                    return [float(x[2 * ia + 1] + x[2 * ib + 1])]
                return orig(self, c, x, num_pts)
            return mut_res

        def test_res_horiz() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 5))
            p1 = s.add_point(Point2D(10, 5))
            s.add_horizontal(p0, p1)
            res = s._evaluate_residuals(np.array([0.0, 5.0, 10.0, 5.0]))
            return abs(res[0]) < 1e-6

        m_list.append(KernelMutant("MUT-GAOR-SOLV-050", MutationFamily.G_AOR, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_eval_single_constraint_residual", "Addition dans le calcul du résidu HORIZONTAL", patch_res_horiz, test_res_horiz))

        # MUT-GAOR-SOLV-051: VERTICAL résidu addition
        def patch_res_vert() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._eval_single_constraint_residual
            def mut_res(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, num_pts: int) -> List[float]:
                if c.constraint_type == solver2d.ConstraintType.VERTICAL:
                    ia, ib = c.point_indices[0], c.point_indices[1]
                    return [float(x[2 * ia] + x[2 * ib])]
                return orig(self, c, x, num_pts)
            return mut_res

        def test_res_vert() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(5, 0))
            p1 = s.add_point(Point2D(5, 10))
            s.add_vertical(p0, p1)
            res = s._evaluate_residuals(np.array([5.0, 0.0, 5.0, 10.0]))
            return abs(res[0]) < 1e-6

        m_list.append(KernelMutant("MUT-GAOR-SOLV-051", MutationFamily.G_AOR, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_eval_single_constraint_residual", "Addition dans le calcul du résidu VERTICAL", patch_res_vert, test_res_vert))

        # MUT-GAOR-SOLV-052: DISTANCE résidu addition au lieu de soustraction
        def patch_res_dist() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._eval_single_constraint_residual
            def mut_res(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, num_pts: int) -> List[float]:
                if c.constraint_type == solver2d.ConstraintType.DISTANCE:
                    ia, ib = c.point_indices[0], c.point_indices[1]
                    dx = x[2 * ib] - x[2 * ia]
                    dy = x[2 * ib + 1] - x[2 * ia + 1]
                    return [float(np.hypot(dx, dy) + c.target_value)]  # Inversion de signe
                return orig(self, c, x, num_pts)
            return mut_res

        def test_res_dist() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            p1 = s.add_point(Point2D(10, 0))
            s.add_distance(p0, p1, 10.0)
            res = s._evaluate_residuals(np.array([0.0, 0.0, 10.0, 0.0]))
            return abs(res[0]) < 1e-6

        m_list.append(KernelMutant("MUT-GAOR-SOLV-052", MutationFamily.G_AOR, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_eval_single_constraint_residual", "Addition de target_value dans le résidu DISTANCE", patch_res_dist, test_res_dist))

        # MUT-GAOR-SOLV-053: PARALLEL résidu addition produit vectoriel
        def patch_res_parallel() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._eval_single_constraint_residual
            def mut_res(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, num_pts: int) -> List[float]:
                if c.constraint_type == solver2d.ConstraintType.PARALLEL:
                    ia1, ia2, ib1, ib2 = c.point_indices[0], c.point_indices[1], c.point_indices[2], c.point_indices[3]
                    dx_a = x[2 * ia2] - x[2 * ia1]
                    dy_a = x[2 * ia2 + 1] - x[2 * ia1 + 1]
                    dx_b = x[2 * ib2] - x[2 * ib1]
                    dy_b = x[2 * ib2 + 1] - x[2 * ib1 + 1]
                    return [float(dx_a * dy_b + dy_a * dx_b)]  # Faux: addition
                return orig(self, c, x, num_pts)
            return mut_res

        def test_res_parallel() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            a1 = s.add_point(Point2D(0, 0))
            a2 = s.add_point(Point2D(10, 10))
            b1 = s.add_point(Point2D(0, 5))
            b2 = s.add_point(Point2D(10, 15))
            s.add_parallel(a1, a2, b1, b2)
            res = s._evaluate_residuals(np.array([0.0, 0.0, 10.0, 10.0, 0.0, 5.0, 10.0, 15.0]))
            return abs(res[0]) < 1e-6

        m_list.append(KernelMutant("MUT-GAOR-SOLV-053", MutationFamily.G_AOR, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_eval_single_constraint_residual", "Addition dans le produit vectoriel 2D de contrainte PARALLEL", patch_res_parallel, test_res_parallel))

        # MUT-GAOR-SOLV-054: PERPENDICULAR résidu soustraction produit scalaire
        def patch_res_perp() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._eval_single_constraint_residual
            def mut_res(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, num_pts: int) -> List[float]:
                if c.constraint_type == solver2d.ConstraintType.PERPENDICULAR:
                    ia1, ia2, ib1, ib2 = c.point_indices[0], c.point_indices[1], c.point_indices[2], c.point_indices[3]
                    dx_a = x[2 * ia2] - x[2 * ia1]
                    dy_a = x[2 * ia2 + 1] - x[2 * ia1 + 1]
                    dx_b = x[2 * ib2] - x[2 * ib1]
                    dy_b = x[2 * ib2 + 1] - x[2 * ib1 + 1]
                    return [float(dx_a * dx_b - dy_a * dy_b)]  # Faux: soustraction
                return orig(self, c, x, num_pts)
            return mut_res

        def test_res_perp() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            a1 = s.add_point(Point2D(0, 0))
            a2 = s.add_point(Point2D(10, 10))
            b1 = s.add_point(Point2D(0, 0))
            b2 = s.add_point(Point2D(-10, 10))
            s.add_perpendicular(a1, a2, b1, b2)
            res = s._evaluate_residuals(np.array([0.0, 0.0, 10.0, 10.0, 0.0, 0.0, -10.0, 10.0]))
            return abs(res[0]) < 1e-6

        m_list.append(KernelMutant("MUT-GAOR-SOLV-054", MutationFamily.G_AOR, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_eval_single_constraint_residual", "Soustraction dans le produit scalaire PERPENDICULAR", patch_res_perp, test_res_perp))

        # MUT-GAOR-SOLV-055: FIXED résidu addition
        def patch_res_fixed() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._eval_single_constraint_residual
            def mut_res(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, num_pts: int) -> List[float]:
                if c.constraint_type == solver2d.ConstraintType.FIXED:
                    ia = c.point_indices[0]
                    return [float(x[2 * ia] + c.target_value), float(x[2 * ia + 1] + c.target_value_v)]
                return orig(self, c, x, num_pts)
            return mut_res

        def test_res_fixed() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(15, 25))
            s.add_fixed(p0, 15, 25)
            res = s._evaluate_residuals(np.array([15.0, 25.0]))
            return abs(res[0]) < 1e-6 and abs(res[1]) < 1e-6

        m_list.append(KernelMutant("MUT-GAOR-SOLV-055", MutationFamily.G_AOR, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_eval_single_constraint_residual", "Addition dans le calcul de résidu FIXED", patch_res_fixed, test_res_fixed))

        # MUT-GROR-SOLV-056: solve seuil max_residual < 0.01 muté en < 1e-15
        def patch_solve_thresh() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D.solve
            def mut_solve(self: solver2d.SketchConstraintSolver2D, tolerance: float = 1e-6, max_iterations: Optional[int] = None) -> Tuple[bool, List[Point2D]]:
                ok, pts = orig(self, tolerance, max_iterations)
                # Force échec
                return (False, pts)
            return mut_solve

        def test_solve_thresh() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            s.add_fixed(p0, 0, 0)
            ok, _ = s.solve()
            return ok is True

        m_list.append(KernelMutant("MUT-GROR-SOLV-056", MutationFamily.G_ROR, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "solve", "Invalidation inconditionnelle du succès de résolution", patch_solve_thresh, test_solve_thresh))
        return m_list

    @classmethod
    def _get_solver_residual_mutants_part2(cls) -> List[KernelMutant]:
        m_list: List[KernelMutant] = []

        # MUT-GROR-SOLV-057: solve max_iterations bridé à 1
        def patch_solve_iter() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D.solve
            def mut_solve(self: solver2d.SketchConstraintSolver2D, tolerance: float = 1e-6, max_iterations: Optional[int] = None) -> Tuple[bool, List[Point2D]]:
                return orig(self, tolerance, max_iterations=1)
            return mut_solve

        def test_solve_iter() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            p1 = s.add_point(Point2D(100, 100))
            s.add_fixed(p0, 0, 0)
            s.add_horizontal(p0, p1)
            s.add_distance(p0, p1, 10.0)
            ok, pts = s.solve()
            return ok and abs(pts[1].u - 10.0) < 0.01

        m_list.append(KernelMutant("MUT-GROR-SOLV-057", MutationFamily.G_ROR, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "solve", "Restriction destructrice du nombre max d'itérations TRF", patch_solve_iter, test_solve_iter))

        # MUT-GROR-SOLV-058: solve points vides renvoie False
        def patch_solve_empty() -> MutantCallable:
            def mut_solve(self: solver2d.SketchConstraintSolver2D, tolerance: float = 1e-6, max_iterations: Optional[int] = None) -> Tuple[bool, List[Point2D]]:
                if not self.points:
                    return (False, [])
                return (True, list(self.points))
            return mut_solve

        def test_solve_empty() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            ok, pts = s.solve()
            return ok is True and len(pts) == 0

        m_list.append(KernelMutant("MUT-GROR-SOLV-058", MutationFamily.G_ROR, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "solve", "Échec erroné lors de résolution de sketch sans point", patch_solve_empty, test_solve_empty))

        # MUT-GROR-SOLV-059: add_distance distance négative non clampée
        def patch_add_dist() -> MutantCallable:
            def mut_add_dist(self: solver2d.SketchConstraintSolver2D, p1: int, p2: int, dist: float) -> None:
                # Stocke distance négative
                self.constraints.append(solver2d.GeometricConstraint(solver2d.ConstraintType.DISTANCE, (p1, p2), target_value=-abs(dist)))
            return mut_add_dist

        def test_add_dist() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            s.add_distance(0, 1, 10.0)
            return s.constraints[0].target_value > 0.0

        m_list.append(KernelMutant("MUT-GROR-SOLV-059", MutationFamily.G_ROR, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "add_distance", "Passage de distance cible négative", patch_add_dist, test_add_dist))

        # MUT-GROR-SOLV-060: add_tangent rayon nul
        def patch_add_tangent() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D.add_tangent
            def mut_add_tangent(self: solver2d.SketchConstraintSolver2D, l1: int, l2: int, c: solver2d.GeometricConstraint, radius: float) -> None:
                orig(self, l1, l2, c, 0.0)
            return mut_add_tangent

        def test_add_tangent() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            s.add_tangent(0, 1, Point2D(0, 0), radius=5.0)
            return s.constraints[-1].target_value >= 4.9

        m_list.append(KernelMutant("MUT-GROR-SOLV-060", MutationFamily.G_ROR, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "add_tangent", "Annulation du rayon lors de l'ajout de contrainte TANGENT", patch_add_tangent, test_add_tangent))

        # MUT-GSOLV-SOLV-061: EXTERNAL_REFERENCE Jacobienne annulée
        def patch_jac_ext_ref() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.EXTERNAL_REFERENCE:
                    return 2
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_ext_ref() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            s.add_external_reference(p0, 15.0, 20.0)
            ok, pts = s.solve()
            return ok and abs(pts[0].u - 15.0) < 0.01 and abs(pts[0].v - 20.0) < 0.01

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-061", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Annulation du Jacobien de référence externe 3D", patch_jac_ext_ref, test_jac_ext_ref))

        # MUT-GSOLV-SOLV-062: POINT_ON_LINE résidu altéré
        def patch_res_pol() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._eval_single_constraint_residual
            def mut_res(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, num_pts: int) -> List[float]:
                if c.constraint_type == solver2d.ConstraintType.POINT_ON_LINE:
                    return [10.0]  # Erreur forcée
                return orig(self, c, x, num_pts)
            return mut_res

        def test_res_pol() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            l1 = s.add_point(Point2D(0, 0))
            l2 = s.add_point(Point2D(10, 0))
            p = s.add_point(Point2D(5, 0))
            s.add_point_on_line(p, l1, l2)
            res = s._evaluate_residuals(np.array([0.0, 0.0, 10.0, 0.0, 5.0, 0.0]))
            return abs(res[0]) < 1e-6

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-062", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_eval_single_constraint_residual", "Corruption de résidu de point sur droite", patch_res_pol, test_res_pol))

        # MUT-GSOLV-SOLV-063: G2_CURVATURE résidu altéré
        def patch_res_g2() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._eval_single_constraint_residual
            def mut_res(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, num_pts: int) -> List[float]:
                if c.constraint_type == solver2d.ConstraintType.G2_CURVATURE:
                    return [50.0, 50.0]
                return orig(self, c, x, num_pts)
            return mut_res

        def test_res_g2() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            p1 = s.add_point(Point2D(1, 0))
            pj = s.add_point(Point2D(2, 0))
            p3 = s.add_point(Point2D(3, 0))
            p4 = s.add_point(Point2D(4, 0))
            s.add_g2_curvature(p0, p1, pj, p3, p4)
            res = s._evaluate_residuals(np.array([0.0, 0.0, 1.0, 0.0, 2.0, 0.0, 3.0, 0.0, 4.0, 0.0]))
            return abs(res[0]) < 1e-4

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-063", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_eval_single_constraint_residual", "Perturbation de résidu de continuité G2", patch_res_g2, test_res_g2))

        # MUT-GSOLV-SOLV-064: ANGLE résidu inversion
        def patch_res_angle() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._eval_single_constraint_residual
            def mut_res(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, num_pts: int) -> List[float]:
                if c.constraint_type == solver2d.ConstraintType.ANGLE:
                    return [100.0]
                return orig(self, c, x, num_pts)
            return mut_res

        def test_res_angle() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            a1 = s.add_point(Point2D(0, 0))
            a2 = s.add_point(Point2D(10, 0))
            b1 = s.add_point(Point2D(0, 0))
            b2 = s.add_point(Point2D(0, 10))
            s.add_angle(a1, a2, b1, b2, angle_deg=90.0)
            res = s._evaluate_residuals(np.array([0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 0.0, 10.0]))
            return abs(res[0]) < 1e-3

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-064", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_eval_single_constraint_residual", "Altération du résidu de calcul d'angle géométrique", patch_res_angle, test_res_angle))
        return m_list

    @classmethod
    def _get_solver_residual_mutants_part3(cls) -> List[KernelMutant]:
        m_list: List[KernelMutant] = []

        # MUT-GSOLV-SOLV-065: EQUAL résidu addition au lieu de différence
        def patch_res_eq() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._eval_single_constraint_residual
            def mut_res(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, num_pts: int) -> List[float]:
                if c.constraint_type == solver2d.ConstraintType.EQUAL:
                    ia1, ia2, ib1, ib2 = c.point_indices[0], c.point_indices[1], c.point_indices[2], c.point_indices[3]
                    la = np.hypot(x[2*ia2] - x[2*ia1], x[2*ia2+1] - x[2*ia1+1])
                    lb = np.hypot(x[2*ib2] - x[2*ib1], x[2*ib2+1] - x[2*ib1+1])
                    return [float(la + lb)]
                return orig(self, c, x, num_pts)
            return mut_res

        def test_res_eq() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            a1 = s.add_point(Point2D(0, 0))
            a2 = s.add_point(Point2D(10, 0))
            b1 = s.add_point(Point2D(0, 5))
            b2 = s.add_point(Point2D(10, 5))
            s.add_equal(a1, a2, b1, b2)
            res = s._evaluate_residuals(np.array([0.0, 0.0, 10.0, 0.0, 0.0, 5.0, 10.0, 5.0]))
            return abs(res[0]) < 1e-6

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-065", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_eval_single_constraint_residual", "Addition au lieu de soustraction dans résidu EQUAL", patch_res_eq, test_res_eq))

        # MUT-GSOLV-SOLV-066: TANGENT résidu rayon soustrait inversé
        def patch_res_tang() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._eval_single_constraint_residual
            def mut_res(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, num_pts: int) -> List[float]:
                if c.constraint_type == solver2d.ConstraintType.TANGENT:
                    return [10.0]
                return orig(self, c, x, num_pts)
            return mut_res

        def test_res_tang() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p1 = s.add_point(Point2D(0, 5))
            p2 = s.add_point(Point2D(10, 5))
            c = s.add_point(Point2D(5, 0))
            s.constraints.append(solver2d.GeometricConstraint(solver2d.ConstraintType.TANGENT, (p1, p2, c), target_value=5.0))
            res = s._evaluate_residuals(np.array([0.0, 5.0, 10.0, 5.0, 5.0, 0.0]))
            return abs(res[0]) < 1e-3

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-066", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_eval_single_constraint_residual", "Perturbation de résidu de tangence droite-cercle", patch_res_tang, test_res_tang))

        # MUT-GROR-SOLV-067: opt_result.success ignoré lors d'impossibilité géométrique
        def patch_solve_blind() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D.solve
            def mut_solve(self: solver2d.SketchConstraintSolver2D, **kwargs: Union[float, int, str, bool]) -> Tuple[bool, List[Point2D]]:
                _, pts = orig(self, **kwargs)
                return (True, pts)  # Renvoie toujours succès même si impossible
            return mut_solve

        def test_solve_blind() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            p1 = s.add_point(Point2D(10, 0))
            s.add_fixed(p0, 0, 0)
            s.add_fixed(p1, 10, 0)
            s.add_distance(p0, p1, 50.0)  # Contradiction flagrante
            ok, _ = s.solve()
            return ok is False

        m_list.append(KernelMutant("MUT-GROR-SOLV-067", MutationFamily.G_ROR, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "solve", "Retour aveugle de succès sur contradiction géométrique", patch_solve_blind, test_solve_blind))

        # MUT-GSOLV-SOLV-068: _evaluate_jacobian taille de matrice erronée
        def patch_jac_shape() -> MutantCallable:
            def mut_eval_jac(self: solver2d.SketchConstraintSolver2D, x: np.ndarray) -> np.ndarray:
                # Matrice de zéros
                return np.zeros((len(self._evaluate_residuals(x)), len(x)), dtype=np.float64)
            return mut_eval_jac

        def test_jac_shape() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            p1 = s.add_point(Point2D(5, 5))
            s.add_fixed(p0, 0, 0)
            s.add_horizontal(p0, p1)
            j = s._evaluate_jacobian(np.array([0.0, 0.0, 5.0, 5.0]))
            return np.max(np.abs(j)) > 0.1

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-068", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_evaluate_jacobian", "Remplacement de la Jacobienne analytique par une matrice nulle", patch_jac_shape, test_jac_shape))

        # MUT-GSOLV-SOLV-069: POINT_ON_LINE Jacobienne annulée
        def patch_jac_pol() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.POINT_ON_LINE:
                    return 1
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_pol() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            l1 = s.add_point(Point2D(0, 0))
            l2 = s.add_point(Point2D(10, 0))
            p = s.add_point(Point2D(5, 5))
            s.add_fixed(l1, 0, 0)
            s.add_fixed(l2, 10, 0)
            s.add_point_on_line(p, l1, l2)
            ok, pts = s.solve()
            return ok and abs(pts[p].v) < 0.01

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-069", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Annulation de dérivée POINT_ON_LINE dans la Jacobienne", patch_jac_pol, test_jac_pol))

        # MUT-GSOLV-SOLV-070: G2_CURVATURE Jacobienne annulée
        def patch_jac_g2() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._fill_single_constraint_jacobian
            def mut_jac(self: solver2d.SketchConstraintSolver2D, c: solver2d.GeometricConstraint, x: np.ndarray, j_mat: np.ndarray, row: int, num_pts: int, f0: np.ndarray, num_vars: int, num_eqs: int) -> int:
                if c.constraint_type == solver2d.ConstraintType.G2_CURVATURE:
                    return 2
                return orig(self, c, x, j_mat, row, num_pts, f0, num_vars, num_eqs)
            return mut_jac

        def test_jac_g2() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            p1 = s.add_point(Point2D(1, 0))
            pj = s.add_point(Point2D(2, 0))
            p3 = s.add_point(Point2D(3, 0.5))
            p4 = s.add_point(Point2D(4, 1.0))
            s.add_fixed(p0, 0, 0)
            s.add_fixed(p1, 1, 0)
            s.add_fixed(pj, 2, 0)
            s.add_g2_curvature(p0, p1, pj, p3, p4)
            ok, pts = s.solve()
            return ok

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-070", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_fill_single_constraint_jacobian", "Annulation de gradient G2_CURVATURE", patch_jac_g2, test_jac_g2))

        # MUT-GROR-SOLV-071: solveurftol détérioré
        def patch_solve_ftol() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D.solve
            def mut_solve(self: solver2d.SketchConstraintSolver2D, tolerance: float = 1e-6, max_iterations: Optional[int] = None) -> Tuple[bool, List[Point2D]]:
                return orig(self, tolerance=100.0, max_iterations=max_iterations)
            return mut_solve

        def test_solve_ftol() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            p1 = s.add_point(Point2D(10, 10))
            s.add_fixed(p0, 0, 0)
            s.add_horizontal(p0, p1)
            s.add_distance(p0, p1, 10.0)
            ok, pts = s.solve()
            return ok and abs(pts[1].v - pts[0].v) < 1e-3

        m_list.append(KernelMutant("MUT-GROR-SOLV-071", MutationFamily.G_ROR, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "solve", "Détérioration critique de la tolérance ftol", patch_solve_ftol, test_solve_ftol))

        # MUT-GSOLV-SOLV-072: _evaluate_residuals inversion globale de signe
        def patch_res_sign() -> MutantCallable:
            orig = solver2d.SketchConstraintSolver2D._evaluate_residuals
            def mut_res(self: solver2d.SketchConstraintSolver2D, x: np.ndarray) -> np.ndarray:
                return -orig(self, x)
            return mut_res

        def test_res_sign() -> bool:
            s = solver2d.SketchConstraintSolver2D()
            p0 = s.add_point(Point2D(0, 0))
            p1 = s.add_point(Point2D(10, 0))
            s.add_distance(p0, p1, 5.0)
            res = s._evaluate_residuals(np.array([0.0, 0.0, 10.0, 0.0]))
            # Distance 10 - 5 = +5.0
            return res[0] > 0.0

        m_list.append(KernelMutant("MUT-GSOLV-SOLV-072", MutationFamily.G_SOLV, "solver_2d", "src.solver.constraints_2d", "SketchConstraintSolver2D", "_evaluate_residuals", "Inversion de signe du vecteur global des résidus", patch_res_sign, test_res_sign))
        return m_list

    @classmethod
    def _get_solver_residual_mutants(cls) -> List[KernelMutant]:
        m_list: List[KernelMutant] = []
        m_list.extend(cls._get_solver_residual_mutants_part1())
        m_list.extend(cls._get_solver_residual_mutants_part2())
        m_list.extend(cls._get_solver_residual_mutants_part3())
        return m_list

    @classmethod
    def _get_solver_mutants(cls) -> List[KernelMutant]:
        """Combine les mutants jacobiens et résiduels du solveur 2D."""
        return cls._get_solver_jacobian_mutants() + cls._get_solver_residual_mutants()

    # ------------------------------------------------------------------------
    # SOUS-SYSTÈME 3 : CINÉMATIQUE ROBOTIQUE ET TRANSFORMATIONS 3D (25 mutants)
    # ------------------------------------------------------------------------
    @classmethod
    def _get_robotics_mutants(cls) -> List[KernelMutant]:
        m_list: List[KernelMutant] = []

        # MUT-GTR-ROB-073: RobotArm6Axis._dh_matrix (0,0) cos en sin
        def patch_dh_00() -> MutantCallable:
            orig = rkin.RobotArm6Axis._dh_matrix
            def mut_dh(self: rkin.RobotArm6Axis, a: float, alpha: float, d: float, theta: float) -> np.ndarray:
                mat = orig(self, a, alpha, d, theta)
                mat[0, 0] = float(np.sin(theta))  # Muté
                return mat
            return mut_dh

        def test_dh_00() -> bool:
            arm = rkin.RobotArm6Axis()
            t = arm._dh_matrix(0, 0, 0, 0.0)
            return abs(t[0, 0] - 1.0) < 1e-4

        m_list.append(KernelMutant("MUT-GTR-ROB-073", MutationFamily.G_TR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "_dh_matrix", "Substitution cos par sin à la composante DH (0,0)", patch_dh_00, test_dh_00))

        # MUT-GTR-ROB-074: RobotArm6Axis._dh_matrix (0,1) signe inversé
        def patch_dh_01() -> MutantCallable:
            orig = rkin.RobotArm6Axis._dh_matrix
            def mut_dh(self: rkin.RobotArm6Axis, a: float, alpha: float, d: float, theta: float) -> np.ndarray:
                mat = orig(self, a, alpha, d, theta)
                mat[0, 1] = -mat[0, 1]
                return mat
            return mut_dh

        def test_dh_01() -> bool:
            arm = rkin.RobotArm6Axis()
            t = arm._dh_matrix(0, 0, 0, np.pi / 2.0)
            return abs(t[0, 1] - (-1.0)) < 1e-4

        m_list.append(KernelMutant("MUT-GTR-ROB-074", MutationFamily.G_TR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "_dh_matrix", "Inversion de signe à la composante DH (0,1)", patch_dh_01, test_dh_01))

        # MUT-GTR-ROB-075: RobotArm6Axis._dh_matrix (1,0) sin en cos
        def patch_dh_10() -> MutantCallable:
            orig = rkin.RobotArm6Axis._dh_matrix
            def mut_dh(self: rkin.RobotArm6Axis, a: float, alpha: float, d: float, theta: float) -> np.ndarray:
                mat = orig(self, a, alpha, d, theta)
                mat[1, 0] = float(np.cos(theta))
                return mat
            return mut_dh

        def test_dh_10() -> bool:
            arm = rkin.RobotArm6Axis()
            t = arm._dh_matrix(0, 0, 0, 0.0)
            return abs(t[1, 0] - 0.0) < 1e-4

        m_list.append(KernelMutant("MUT-GTR-ROB-075", MutationFamily.G_TR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "_dh_matrix", "Substitution sin par cos à la composante DH (1,0)", patch_dh_10, test_dh_10))

        # MUT-GTR-ROB-076: RobotArm6Axis._dh_matrix (1,1) signe inversé
        def patch_dh_11() -> MutantCallable:
            orig = rkin.RobotArm6Axis._dh_matrix
            def mut_dh(self: rkin.RobotArm6Axis, a: float, alpha: float, d: float, theta: float) -> np.ndarray:
                mat = orig(self, a, alpha, d, theta)
                mat[1, 1] = -mat[1, 1]
                return mat
            return mut_dh

        def test_dh_11() -> bool:
            arm = rkin.RobotArm6Axis()
            t = arm._dh_matrix(0, 0, 0, 0.0)
            return abs(t[1, 1] - 1.0) < 1e-4

        m_list.append(KernelMutant("MUT-GTR-ROB-076", MutationFamily.G_TR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "_dh_matrix", "Inversion de signe à la composante DH (1,1)", patch_dh_11, test_dh_11))

        # MUT-GTR-ROB-077: RobotArm6Axis._dh_matrix (2,1) signe inversé
        def patch_dh_21() -> MutantCallable:
            orig = rkin.RobotArm6Axis._dh_matrix
            def mut_dh(self: rkin.RobotArm6Axis, a: float, alpha: float, d: float, theta: float) -> np.ndarray:
                mat = orig(self, a, alpha, d, theta)
                mat[2, 1] = -mat[2, 1]
                return mat
            return mut_dh

        def test_dh_21() -> bool:
            arm = rkin.RobotArm6Axis()
            t = arm._dh_matrix(0, np.pi / 2.0, 0, 0.0)
            return abs(t[2, 1] - 1.0) < 1e-4

        m_list.append(KernelMutant("MUT-GTR-ROB-077", MutationFamily.G_TR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "_dh_matrix", "Inversion de signe à la composante DH (2,1)", patch_dh_21, test_dh_21))

        # MUT-GTR-ROB-078: RobotArm6Axis._dh_matrix (2,2) signe inversé
        def patch_dh_22() -> MutantCallable:
            orig = rkin.RobotArm6Axis._dh_matrix
            def mut_dh(self: rkin.RobotArm6Axis, a: float, alpha: float, d: float, theta: float) -> np.ndarray:
                mat = orig(self, a, alpha, d, theta)
                mat[2, 2] = -mat[2, 2]
                return mat
            return mut_dh

        def test_dh_22() -> bool:
            arm = rkin.RobotArm6Axis()
            t = arm._dh_matrix(0, 0, 0, 0.0)
            return abs(t[2, 2] - 1.0) < 1e-4

        m_list.append(KernelMutant("MUT-GTR-ROB-078", MutationFamily.G_TR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "_dh_matrix", "Inversion de signe à la composante DH (2,2)", patch_dh_22, test_dh_22))

        # MUT-GAOR-ROB-079: RobotArm6Axis._dh_matrix translation X (0,3) inversée
        def patch_dh_03() -> MutantCallable:
            orig = rkin.RobotArm6Axis._dh_matrix
            def mut_dh(self: rkin.RobotArm6Axis, a: float, alpha: float, d: float, theta: float) -> np.ndarray:
                mat = orig(self, a, alpha, d, theta)
                mat[0, 3] = -mat[0, 3]
                return mat
            return mut_dh

        def test_dh_03() -> bool:
            arm = rkin.RobotArm6Axis()
            t = arm._dh_matrix(50.0, 0, 0, 0.0)
            return abs(t[0, 3] - 50.0) < 1e-4

        m_list.append(KernelMutant("MUT-GAOR-ROB-079", MutationFamily.G_AOR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "_dh_matrix", "Inversion de signe de translation a*cos(theta)", patch_dh_03, test_dh_03))

        # MUT-GAOR-ROB-080: RobotArm6Axis._dh_matrix translation Y (1,3) inversée
        def patch_dh_13() -> MutantCallable:
            orig = rkin.RobotArm6Axis._dh_matrix
            def mut_dh(self: rkin.RobotArm6Axis, a: float, alpha: float, d: float, theta: float) -> np.ndarray:
                mat = orig(self, a, alpha, d, theta)
                mat[1, 3] = -mat[1, 3]
                return mat
            return mut_dh

        def test_dh_13() -> bool:
            arm = rkin.RobotArm6Axis()
            t = arm._dh_matrix(50.0, 0, 0, np.pi / 2.0)
            return abs(t[1, 3] - 50.0) < 1e-4

        m_list.append(KernelMutant("MUT-GAOR-ROB-080", MutationFamily.G_AOR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "_dh_matrix", "Inversion de signe de translation a*sin(theta)", patch_dh_13, test_dh_13))

        # MUT-GAOR-ROB-081: RobotArm6Axis._dh_matrix translation Z (2,3) inversée
        def patch_dh_23() -> MutantCallable:
            orig = rkin.RobotArm6Axis._dh_matrix
            def mut_dh(self: rkin.RobotArm6Axis, a: float, alpha: float, d: float, theta: float) -> np.ndarray:
                mat = orig(self, a, alpha, d, theta)
                mat[2, 3] = -mat[2, 3]
                return mat
            return mut_dh

        def test_dh_23() -> bool:
            arm = rkin.RobotArm6Axis()
            t = arm._dh_matrix(0, 0, 100.0, 0.0)
            return abs(t[2, 3] - 100.0) < 1e-4

        m_list.append(KernelMutant("MUT-GAOR-ROB-081", MutationFamily.G_AOR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "_dh_matrix", "Inversion de signe du décalage axial d", patch_dh_23, test_dh_23))

        # MUT-GTR-ROB-082: forward_kinematics ordre de composition matricielle inversé
        def patch_fk_order() -> MutantCallable:
            def mut_fk(self: rkin.RobotArm6Axis, joint_angles: Optional[Sequence[float]] = None) -> np.ndarray:
                angles = np.array(joint_angles, dtype=np.float64) if joint_angles is not None else self.joint_angles_rad
                t_global = np.eye(4, dtype=np.float64)
                for i in range(6):
                    dh = self.dh_params[i]
                    a_i = self._dh_matrix(dh.a_mm, dh.alpha_rad, dh.d_mm, dh.theta_rad + float(angles[i]))
                    t_global = a_i @ t_global  # Inversé
                return t_global
            return mut_fk

        def test_fk_order() -> bool:
            arm = rkin.RobotArm6Axis()
            t = arm.forward_kinematics([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
            # La position Z doit être aux alentours de 600-800 mm
            return t[2, 3] > 400.0

        m_list.append(KernelMutant("MUT-GTR-ROB-082", MutationFamily.G_TR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "forward_kinematics", "Inversion de l'ordre du produit matriciel T06 = Ai @ T", patch_fk_order, test_fk_order))

        # MUT-GAOR-ROB-083: forward_kinematics signe de theta inversé
        def patch_fk_theta() -> MutantCallable:
            def mut_fk(self: rkin.RobotArm6Axis, joint_angles: Optional[Sequence[float]] = None) -> np.ndarray:
                angles = np.array(joint_angles, dtype=np.float64) if joint_angles is not None else self.joint_angles_rad
                t_global = np.eye(4, dtype=np.float64)
                for i in range(6):
                    dh = self.dh_params[i]
                    a_i = self._dh_matrix(dh.a_mm, dh.alpha_rad, dh.d_mm, dh.theta_rad - float(angles[i]))  # Soustraction
                    t_global = t_global @ a_i
                return t_global
            return mut_fk

        def test_fk_theta() -> bool:
            arm = rkin.RobotArm6Axis()
            pos_plus, _ = arm.forward_kinematics_pose([np.pi / 4.0, 0, 0, 0, 0, 0])
            return pos_plus[1] > 10.0

        m_list.append(KernelMutant("MUT-GAOR-ROB-083", MutationFamily.G_AOR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "forward_kinematics", "Inversion de signe de rotation articulaire theta - angle", patch_fk_theta, test_fk_theta))

        # MUT-GSOLV-ROB-084: calculate_jacobian vitesse linéaire inversée
        def patch_jac_lin() -> MutantCallable:
            orig = rkin.RobotArm6Axis.calculate_jacobian
            def mut_jac(self: rkin.RobotArm6Axis, angles: Optional[Sequence[float]] = None) -> np.ndarray:
                j = orig(self, angles)
                j[:3, :] = -j[:3, :]  # Inversion de signe
                return j
            return mut_jac

        def test_jac_lin() -> bool:
            arm = rkin.RobotArm6Axis()
            j = arm.calculate_jacobian([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
            # Déplacement J1 autour de Z produit une vitesse vy positive pour x > 0
            return j[1, 0] > 0.0

        m_list.append(KernelMutant("MUT-GSOLV-ROB-084", MutationFamily.G_SOLV, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "calculate_jacobian", "Inversion de signe des vitesses linéaires de la Jacobienne", patch_jac_lin, test_jac_lin))

        # MUT-GSOLV-ROB-085: calculate_jacobian vitesses angulaires nulles
        def patch_jac_rot() -> MutantCallable:
            orig = rkin.RobotArm6Axis.calculate_jacobian
            def mut_jac(self: rkin.RobotArm6Axis, angles: Optional[Sequence[float]] = None) -> np.ndarray:
                j = orig(self, angles)
                j[3:, :] = 0.0
                return j
            return mut_jac

        def test_jac_rot() -> bool:
            arm = rkin.RobotArm6Axis()
            j = arm.calculate_jacobian([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
            return np.linalg.norm(j[3:, 0]) > 0.5

        m_list.append(KernelMutant("MUT-GSOLV-ROB-085", MutationFamily.G_SOLV, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "calculate_jacobian", "Annulation des composantes de vitesse angulaire Jacobienne", patch_jac_rot, test_jac_rot))

        # MUT-GROR-ROB-086: is_singular seuil inversé
        def patch_sing_thresh() -> MutantCallable:
            def mut_sing(self: rkin.RobotArm6Axis, angles: Optional[Sequence[float]] = None, threshold: float = 1e-4) -> bool:
                j = self.calculate_jacobian(angles)
                return abs(float(np.linalg.det(j))) > threshold  # Inversé
            return mut_sing

        def test_sing_thresh() -> bool:
            arm = rkin.RobotArm6Axis()
            return arm.is_singular(threshold=1e-4) is True

        m_list.append(KernelMutant("MUT-GROR-ROB-086", MutationFamily.G_ROR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "is_singular", "Inversion du prédicat de détection de singularité", patch_sing_thresh, test_sing_thresh))

        # MUT-GROR-ROB-087: is_singular seuil infini (toujours singulier)
        def patch_sing_always() -> MutantCallable:
            def mut_sing(self: rkin.RobotArm6Axis, angles: Optional[Sequence[float]] = None, threshold: float = 1e-4) -> bool:
                return True
            return mut_sing

        def test_sing_always() -> bool:
            arm = rkin.RobotArm6Axis()
            return arm.is_singular(threshold=0.0) is False

        m_list.append(KernelMutant("MUT-GROR-ROB-087", MutationFamily.G_ROR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "is_singular", "Forçage inconditionnel de l'état singulier", patch_sing_always, test_sing_always))

        # MUT-GTR-ROB-088: plan_cartesian_trajectory interpolation inversée
        def patch_traj_inv() -> MutantCallable:
            def mut_traj(self: rkin.RobotArm6Axis, p0: Tuple[float, float, float], p1: Tuple[float, float, float], n: int = 5) -> List[Tuple[float, float, float]]:
                # Inverse début et fin
                return [p1, p0]
            return mut_traj

        def test_traj_inv() -> bool:
            arm = rkin.RobotArm6Axis()
            traj = arm.plan_cartesian_trajectory((0, 0, 0), (100, 100, 100), num_waypoints=5)
            return len(traj) == 5 and abs(traj[0][0] - 0.0) < 1e-4 and abs(traj[-1][0] - 100.0) < 1e-4

        m_list.append(KernelMutant("MUT-GTR-ROB-088", MutationFamily.G_TR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "plan_cartesian_trajectory", "Inversion départ/arrivée de la trajectoire cartésienne", patch_traj_inv, test_traj_inv))

        # MUT-GAOR-ROB-089: GearMate transmission OPPOSITE donne signe positif
        def patch_gear_sign() -> MutantCallable:
            def mut_gear(self: akin.GearMate, angle_a: float) -> float:
                ratio = float(self.teeth_a) / float(self.teeth_b)
                return ratio * angle_a  # Inversion de signe
            return mut_gear

        def test_gear_sign() -> bool:
            gm = akin.GearMate("g1", "p1", "p2", Vector3D(0, 0, 0), Vector3D(0, 0, 1), Vector3D(0, 0, 0), Vector3D(0, 0, 1), 20, 40, transmission=akin.TransmissionSense.OPPOSITE)
            return gm.compute_driven_angle(1.0) < 0.0

        m_list.append(KernelMutant("MUT-GAOR-ROB-089", MutationFamily.G_AOR, "robotics", "src.core.assembly_kinematics", "GearMate", "compute_driven_angle", "Inversion du sens de rotation d'engrenage extérieur", patch_gear_sign, test_gear_sign))

        # MUT-GAOR-ROB-090: RackPinionMate multiplication inversée en division
        def patch_rack_div() -> MutantCallable:
            def mut_rack(self: akin.RackPinionMate, theta: float) -> float:
                return theta / max(0.001, self.pitch_radius_mm)  # Division au lieu de multiplication
            return mut_rack

        def test_rack_div() -> bool:
            rpm = akin.RackPinionMate("r1", "p1", "rack1", pitch_radius_mm=20.0)
            return abs(rpm.compute_linear_displacement(2.0) - 40.0) < 1e-4

        m_list.append(KernelMutant("MUT-GAOR-ROB-090", MutationFamily.G_AOR, "robotics", "src.core.assembly_kinematics", "RackPinionMate", "compute_linear_displacement", "Division au lieu de multiplication par le rayon primitif", patch_rack_div, test_rack_div))

        # MUT-GAOR-ROB-091: ScrewMate pas inversé
        def patch_screw_sign() -> MutantCallable:
            def mut_screw(self: akin.ScrewMate, theta: float) -> float:
                return - (self.lead_mm / (2.0 * np.pi)) * theta
            return mut_screw

        def test_screw_sign() -> bool:
            sm = akin.ScrewMate("s1", "p1", "p2", Vector3D(0, 0, 0), Vector3D(0, 0, 1), lead_mm=5.0)
            return sm.compute_linear_advance(2.0 * np.pi) > 0.0

        m_list.append(KernelMutant("MUT-GAOR-ROB-091", MutationFamily.G_AOR, "robotics", "src.core.assembly_kinematics", "ScrewMate", "compute_linear_advance", "Inversion du pas hélicoïdal de vis", patch_screw_sign, test_screw_sign))

        # MUT-GROR-ROB-092: BallJointMate cône inversé
        def patch_ball_cone() -> MutantCallable:
            def mut_ball(self: akin.BallJointMate, v: Vector3D) -> bool:
                # Inverse la condition
                return not self.is_within_cone_limit(v)
            return mut_ball

        def test_ball_cone() -> bool:
            bj = akin.BallJointMate("b1", "p1", "p2", Vector3D(0, 0, 0), cone_limit_deg=30.0)
            return bj.is_within_cone_limit(Vector3D(0, 0, 1)) is True

        m_list.append(KernelMutant("MUT-GROR-ROB-092", MutationFamily.G_ROR, "robotics", "src.core.assembly_kinematics", "BallJointMate", "is_within_cone_limit", "Inversion de la validation d'angle conique de rotule", patch_ball_cone, test_ball_cone))

        # MUT-GTR-ROB-093: ExplodedViewGenerator direction d'explosion annulée
        def patch_explode_dir() -> MutantCallable:
            def mut_exp(self: akin.ExplodedViewGenerator, factor: float) -> Dict[str, Vector3D]:
                # Ne translate aucune pièce
                return {p.part_id: Vector3D(0, 0, 0) for p in self.steps}
            return mut_exp

        def test_explode_dir() -> bool:
            evg = akin.ExplodedViewGenerator("ev1")
            evg.add_step("part1", Vector3D(1, 0, 0), distance_mm=50.0)
            offsets = evg.compute_offsets(factor=1.0)
            return offsets["part1"].x > 40.0

        m_list.append(KernelMutant("MUT-GTR-ROB-093", MutationFamily.G_TR, "robotics", "src.core.assembly_kinematics", "ExplodedViewGenerator", "compute_offsets", "Annulation des vecteurs de translation de vue éclatée", patch_explode_dir, test_explode_dir))

        # MUT-GROR-ROB-094: calculate_jacobian pas d'échantillonnage eps dégradé à 10.0
        def patch_jac_eps() -> MutantCallable:
            def mut_jac(self: rkin.RobotArm6Axis, joint_angles_rad: Optional[Sequence[float]] = None) -> np.ndarray:
                angles = np.array(joint_angles_rad, dtype=np.float64) if joint_angles_rad is not None else self.joint_angles_rad
                eps = 10.0  # Erreur d'échantillonnage grossière
                j_mat = np.zeros((6, 6), dtype=np.float64)
                t0 = self.forward_kinematics(angles)
                pos0 = t0[:3, 3]
                for i in range(6):
                    step = np.copy(angles)
                    step[i] += eps
                    t_plus = self.forward_kinematics(step)
                    vel_linear = (t_plus[:3, 3] - pos0) / eps
                    j_mat[:3, i] = vel_linear
                    j_mat[3:, i] = np.array([0.0, 0.0, 1.0])
                return j_mat
            return mut_jac

        def test_jac_eps() -> bool:
            arm = rkin.RobotArm6Axis()
            j = arm.calculate_jacobian([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
            return abs(j[1, 0] - 651.82) < 5.0

        m_list.append(KernelMutant("MUT-GROR-ROB-094", MutationFamily.G_ROR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "calculate_jacobian", "Dégradation critique du pas de différentiation finie de la Jacobienne", patch_jac_eps, test_jac_eps))

        # MUT-GTR-ROB-095: RobotArm6Axis.forward_kinematics_pose extraction de matrice de rotation
        def patch_fk_pose() -> MutantCallable:
            def mut_pose(self: rkin.RobotArm6Axis, angles: Optional[Sequence[float]] = None) -> Tuple[np.ndarray, np.ndarray]:
                t = self.forward_kinematics(angles)
                return t[:3, 3], np.zeros((3, 3), dtype=np.float64)  # Matrice nulle
            return mut_pose

        def test_fk_pose() -> bool:
            arm = rkin.RobotArm6Axis()
            _, r = arm.forward_kinematics_pose([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
            return abs(float(np.linalg.det(r)) - 1.0) < 1e-3

        m_list.append(KernelMutant("MUT-GTR-ROB-095", MutationFamily.G_TR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "forward_kinematics_pose", "Annulation de la matrice de rotation dans forward_kinematics_pose", patch_fk_pose, test_fk_pose))

        # MUT-GAOR-ROB-096: DHParameter validation d'angles
        def patch_dh_theta() -> MutantCallable:
            orig = rkin.RobotArm6Axis.forward_kinematics
            def mut_fk(self: rkin.RobotArm6Axis, angles: Optional[Sequence[float]] = None) -> np.ndarray:
                # Ajoute 180 deg à toutes les articulations
                shifted = [float(a) + np.pi for a in (angles if angles is not None else self.joint_angles_rad)]
                return orig(self, shifted)
            return mut_fk

        def test_dh_theta() -> bool:
            arm = rkin.RobotArm6Axis()
            pos, _ = arm.forward_kinematics_pose([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
            # À angles nuls, Z = 400 + 365 + 80 = 845
            return abs(pos[2] - 845.0) < 10.0

        m_list.append(KernelMutant("MUT-GAOR-ROB-096", MutationFamily.G_AOR, "robotics", "src.specialized.robot_kinematics", "RobotArm6Axis", "forward_kinematics", "Décalage angulaire parasite systématique de pi radians", patch_dh_theta, test_dh_theta))

        # MUT-GROR-ROB-097: GearMate rapport de transmission inversé (teeth_b / teeth_a)
        def patch_gear_ratio() -> MutantCallable:
            def mut_gear(self: akin.GearMate, angle_a: float) -> float:
                inv_ratio = float(self.teeth_b) / float(self.teeth_a)
                return -inv_ratio * angle_a
            return mut_gear

        def test_gear_ratio() -> bool:
            gm = akin.GearMate("g1", "p1", "p2", Vector3D(0, 0, 0), Vector3D(0, 0, 1), Vector3D(0, 0, 0), Vector3D(0, 0, 1), 20, 40)
            return abs(gm.compute_driven_angle(2.0) - (-1.0)) < 1e-4

        m_list.append(KernelMutant("MUT-GROR-ROB-097", MutationFamily.G_ROR, "robotics", "src.core.assembly_kinematics", "GearMate", "compute_driven_angle", "Inversion du rapport de transmission menant/mené", patch_gear_ratio, test_gear_ratio))

        return m_list


# ============================================================================
# 5. MOTEUR D'EXÉCUTION PRINCIPAL (KernelAstMutationEngine)
# ============================================================================

class KernelAstMutationEngine:
    """
    Moteur de Mutation Testing In-Process pour le kernel CAO.
    Applique les mutations en mémoire vive, exécute les micro-tests dédiés et restaure le bytecode
    sans aucun accès disque, garantissant une exécution ultra-rapide (< 3 secondes pour 90+ mutants).
    """

    def __init__(self, mutants: Optional[List[KernelMutant]] = None) -> None:
        """Initialise le moteur avec la cartographie des points névralgiques."""
        self.mutants: List[KernelMutant] = mutants if mutants is not None else KernelMutationRegistry.get_all_mutants()

    @property
    def total_count(self) -> int:
        """Nombre total de mutants enregistrés."""
        return len(self.mutants)

    def run_mutant(self, mutant: KernelMutant) -> MutantResult:
        """
        Exécute un mutant géométrique unique de manière atomique en mémoire vive.
        
        Args:
            mutant: Spécification du mutant à tester.
            
        Returns:
            Résultat d'exécution incluant le statut (KILLED, SURVIVED, ERRORED).
        """
        t_start = time.perf_counter()
        mutated_callable = mutant.patch_factory()

        try:
            with BytecodeHotPatcher.patch_callable(
                mutant.target_module,
                mutant.target_class,
                mutant.target_callable,
                mutated_callable
            ):
                # Exécution du micro-test minimal dédié
                passed = mutant.test_fn()

            execution_time_ms = (time.perf_counter() - t_start) * 1000.0

            # Si le test passe avec le mutant actif, le mutant a SURVÉCU (échec du test à détecter la régression)
            # Si le test échoue (retourne False), le mutant est TUÉ (comportement attendu)
            if passed:
                return MutantResult(mutant.mutant_id, mutant.family, mutant.subsystem, MutantStatus.SURVIVED, execution_time_ms)
            else:
                return MutantResult(mutant.mutant_id, mutant.family, mutant.subsystem, MutantStatus.KILLED, execution_time_ms)

        except Exception as exc:
            # Une exception soulevée par le micro-test lors de l'exécution du mutant signifie que le mutant a été TUÉ
            execution_time_ms = (time.perf_counter() - t_start) * 1000.0
            return MutantResult(mutant.mutant_id, mutant.family, mutant.subsystem, MutantStatus.KILLED, execution_time_ms, error_message=str(exc))

    @staticmethod
    def _compute_family_stats(results: List[MutantResult]) -> Dict[str, Dict[str, float]]:
        """Calcule les statistiques de mutation par famille d'opérateurs."""
        family_stats: Dict[str, Dict[str, float]] = {}
        for fam in MutationFamily:
            fam_results = [r for r in results if r.family == fam]
            f_tot = len(fam_results)
            f_kill = sum(1 for r in fam_results if r.status == MutantStatus.KILLED)
            f_rate = (float(f_kill) / float(f_tot) * 100.0) if f_tot > 0 else 0.0
            family_stats[fam.value] = {"total": float(f_tot), "killed": float(f_kill), "rate": f_rate}
        return family_stats

    @staticmethod
    def _compute_subsystem_stats(results: List[MutantResult]) -> Dict[str, Dict[str, float]]:
        """Calcule les statistiques de mutation par sous-système architectural."""
        subsystem_stats: Dict[str, Dict[str, float]] = {}
        subsystems = sorted(list(set(r.subsystem for r in results)))
        for sub in subsystems:
            sub_results = [r for r in results if r.subsystem == sub]
            s_tot = len(sub_results)
            s_kill = sum(1 for r in sub_results if r.status == MutantStatus.KILLED)
            s_rate = (float(s_kill) / float(s_tot) * 100.0) if s_tot > 0 else 0.0
            subsystem_stats[sub] = {"total": float(s_tot), "killed": float(s_kill), "rate": s_rate}
        return subsystem_stats

    def _filter_mutants(
        self,
        filter_family: Optional[MutationFamily] = None,
        filter_subsystem: Optional[str] = None
    ) -> List[KernelMutant]:
        """Filtre la liste des mutants selon la famille et le sous-système."""
        selected_mutants = self.mutants
        if filter_family is not None:
            selected_mutants = [m for m in selected_mutants if m.family == filter_family]
        if filter_subsystem is not None:
            selected_mutants = [m for m in selected_mutants if m.subsystem == filter_subsystem]
        return selected_mutants

    def run_all(
        self,
        filter_family: Optional[MutationFamily] = None,
        filter_subsystem: Optional[str] = None
    ) -> MutationReport:
        """
        Exécute l'ensemble des mutants cartographiés et calcule les métriques de couverture.
        
        Args:
            filter_family: Filtrer optionnellement par famille d'opérateurs.
            filter_subsystem: Filtrer optionnellement par sous-système ("geometry", "solver_2d", "robotics").
            
        Returns:
            Rapport complet de mutation testing.
        """
        selected_mutants = self._filter_mutants(filter_family, filter_subsystem)

        t0 = time.perf_counter()
        results: List[MutantResult] = [self.run_mutant(mutant) for mutant in selected_mutants]
        total_duration = time.perf_counter() - t0

        killed = sum(1 for r in results if r.status == MutantStatus.KILLED)
        survived = sum(1 for r in results if r.status == MutantStatus.SURVIVED)
        errored = sum(1 for r in results if r.status == MutantStatus.ERRORED)
        total = len(results)
        rate = (float(killed) / float(total) * 100.0) if total > 0 else 0.0

        return MutationReport(
            total_mutants=total,
            killed_count=killed,
            survived_count=survived,
            errored_count=errored,
            kill_rate_percent=rate,
            total_duration_seconds=total_duration,
            family_stats=self._compute_family_stats(results),
            subsystem_stats=self._compute_subsystem_stats(results),
            results=results
        )
