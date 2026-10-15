"""
Moteur d'exécution sécurisé de scripts paramétriques Code-as-CAD (CAD Script Engine).
Inspiré de Zoo KCL, CadQuery et OpenSCAD.
Permet aux ingénieurs et aux agents IA d'écrire des scripts Python déclaratifs
pour concevoir et modifier des assemblages complexes sans passer par l'interface graphique.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
import ast
import math
import time
import types
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable, Union

from src.core.document import CADDocument
from src.core.geometry import (
    Solid, make_box, make_cylinder, make_sphere, make_cone, make_torus
)
from src.core.types import Vector3D, Point2D
from src.ai.shape_synthesizer import ShapeSynthesizer
from src.ai.cad_ai_full_suite import (
    CADFullSuiteOrchestrator,
    CAMAnalysisResult,
    FEAAnalysisResult,
    TechDrawResult,
    SheetMetalResult,
    MaterialPropertiesResult,
    DirectModelingResult
)
from src.ai.cad_ai_stability import (
    AICancellationToken,
    AtomicTransactionScope,
    CADTransactionManager,
    SmartErrorDiagnostics
)


@dataclass
class ScriptExecutionResult:
    """Résultat de l'exécution d'un script Code-as-CAD."""
    success: bool
    message: str
    bodies_created: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    error_line: Optional[int] = None


class CADScriptContext:
    """
    Objet contextuel fluide exposé à l'intérieur des scripts Python de l'IA (variable globale 'cad').
    Fournit une syntaxe compacte et puissante pour toutes les opérations géométriques.
    """

    def __init__(self, document: CADDocument, token: Optional[AICancellationToken] = None) -> None:
        self.doc: CADDocument = document
        self.created_bodies: List[str] = []
        self.last_solid: Optional[Solid] = None
        self._token: Optional[AICancellationToken] = token

    def _check_watchdog(self) -> None:
        """Interrompt immédiatement le calcul si le jeton d'annulation ou le timeout est déclenché."""
        if self._token is not None:
            self._token.check_cancelled()

    def box(self, width: float, height: float, depth: float, center: bool = True) -> Solid:
        """Crée un parallélépipède rectangle."""
        self._check_watchdog()
        return make_box(width, height, depth, center=center)

    def cylinder(self, radius: float, height: float, center: bool = True) -> Solid:
        """Crée un cylindre orienté selon l'axe Z."""
        self._check_watchdog()
        return make_cylinder(radius, height, center=center)

    def sphere(self, radius: float) -> Solid:
        """Crée une sphère centrée à l'origine."""
        return make_sphere(radius)

    def cone(self, radius1: float, radius2: float, height: float) -> Solid:
        """Crée un tronc de cône."""
        return make_cone(radius1, radius2, height)

    def torus(self, major_radius: float, minor_radius: float) -> Solid:
        """Crée un tore."""
        return make_torus(major_radius, minor_radius)

    def spur_gear(
        self,
        num_teeth: int = 20,
        module: float = 2.0,
        face_width: float = 12.0,
        bore_diameter: float = 12.0
    ) -> Solid:
        """Génère un engrenage droit à développante avec alésage."""
        return ShapeSynthesizer.create_spur_gear(
            num_teeth=num_teeth,
            module=module,
            face_width=face_width,
            bore_diameter=bore_diameter
        )

    def pipe_flange(
        self,
        outer_diameter: float = 120.0,
        inner_diameter: float = 50.0,
        num_holes: int = 4
    ) -> Solid:
        """Génère une bride de tuyauterie normalisée avec trous de fixation."""
        return ShapeSynthesizer.create_pipe_flange(
            outer_diameter=outer_diameter,
            inner_diameter=inner_diameter,
            num_holes=num_holes
        )

    def heat_sink(self, width: float = 80.0, length: float = 60.0, num_fins: int = 10) -> Solid:
        """Génère un dissipateur thermique à ailettes minces."""
        return ShapeSynthesizer.create_heat_sink(
            base_width=width,
            base_length=length,
            num_fins=num_fins
        )

    def enclosure(
        self,
        width: float = 100.0,
        length: float = 70.0,
        height: float = 35.0,
        wall_thickness: float = 2.5
    ) -> Solid:
        """Génère un boîtier électronique évidé avec bossages d'angles taraudés."""
        return ShapeSynthesizer.create_electronics_enclosure(
            width=width,
            length=length,
            height=height,
            wall_thickness=wall_thickness
        )

    def bracket(
        self,
        arm_1: float = 60.0,
        arm_2: float = 50.0,
        width: float = 30.0,
        thickness: float = 6.0
    ) -> Solid:
        """Génère une équerre de fixation renforcée avec nervure."""
        return ShapeSynthesizer.create_reinforced_bracket(
            arm_length_1=arm_1,
            arm_length_2=arm_2,
            width=width,
            thickness=thickness
        )

    def stepped_shaft(self, diameters: List[float], lengths: List[float]) -> Solid:
        """Génère un arbre étagé concentrique."""
        return ShapeSynthesizer.create_stepped_shaft(diameters, lengths)

    def add(self, solid: Solid, name: str = "Piece") -> str:
        """Ajoute un solide au document CAO et notifie les observateurs."""
        self._check_watchdog()
        body_id = f"{name}_{len(self.doc.bodies) + 1}"
        self.doc.bodies[body_id] = solid
        self.created_bodies.append(body_id)
        self.last_solid = solid
        self.doc._notify_change()
        return body_id

    def commit(self, solid: Solid, name: str = "Piece") -> str:
        """Alias pour add, valide et enregistre le solide dans le document CAO."""
        return self.add(solid, name)


    def cut_hole(self, target_id: str, diameter: float, depth: float, x: float = 0.0, y: float = 0.0) -> bool:
        """Perce un alésage cylindrique dans le corps spécifié."""
        if target_id not in self.doc.bodies:
            return False
        orig = self.doc.bodies[target_id]
        p_min, p_max = orig.bounding_box()
        mid_z = (p_min.z + p_max.z) / 2.0
        drill = make_cylinder(diameter / 2.0, depth, center=True).translate(x, y, mid_z)
        self.doc.bodies[target_id] = orig.difference(drill)
        self.doc._notify_change()
        return True

    def clear(self) -> None:
        """Efface tous les corps du document."""
        self.doc.bodies.clear()
        self.doc.features.clear()
        self.created_bodies.clear()
        self.doc._notify_change()

    def cam(
        self,
        body_id: str = "",
        operation: str = "contour",
        depth: float = 10.0,
        tool_diameter: float = 6.0
    ) -> CAMAnalysisResult:
        """Génère les parcours d'usinage et le G-code pour une pièce."""
        target_solid = self.doc.bodies.get(body_id) or self.last_solid or make_box(50.0, 30.0, 15.0)
        return CADFullSuiteOrchestrator.run_cam(
            target_solid,
            operation_type=operation,
            depth_mm=depth,
            tool_diameter_mm=tool_diameter
        )

    def fea(
        self,
        body_id: str = "",
        force_n: float = 1500.0,
        material: str = "Aluminium 6061-T6"
    ) -> FEAAnalysisResult:
        """Exécute l'analyse mécanique FEA et renvoie les contraintes von Mises et le facteur de sécurité."""
        target_solid = self.doc.bodies.get(body_id) or self.last_solid or make_box(50.0, 30.0, 15.0)
        return CADFullSuiteOrchestrator.run_fea(
            target_solid,
            applied_force_n=force_n,
            material_name=material
        )

    def techdraw(
        self,
        body_id: str = "",
        material: str = "Aluminium 6061-T6"
    ) -> TechDrawResult:
        """Génère la mise en plan 2D normalisée ISO (4 vues, cartouche et cotations)."""
        target_solid = self.doc.bodies.get(body_id) or self.last_solid or make_box(50.0, 30.0, 15.0)
        return CADFullSuiteOrchestrator.generate_techdraw(
            target_solid,
            part_name=body_id or "Piece_CAO",
            material_name=material
        )

    def sheetmetal(
        self,
        width: float = 120.0,
        length: float = 80.0,
        thickness: float = 2.0,
        flange_height: float = 25.0
    ) -> Solid:
        """Conçoit une pièce de tôlerie avec plis et génère le modèle 3D."""
        res = CADFullSuiteOrchestrator.design_sheet_metal(
            width_mm=width,
            length_mm=length,
            thickness_mm=thickness,
            flange_height_mm=flange_height
        )
        self.last_solid = res.solid
        return res.solid

    def material(
        self,
        body_id: str = "",
        material_name: str = "Aluminium 6061-T6"
    ) -> MaterialPropertiesResult:
        """Calcule les caractéristiques massiques et mécaniques exactes d'une pièce."""
        target_solid = self.doc.bodies.get(body_id) or self.last_solid or make_box(50.0, 30.0, 15.0)
        return CADFullSuiteOrchestrator.get_material_properties(target_solid, material_name)

    def push_pull(self, body_id: str, offset_mm: float, axis: str = "z") -> Solid:
        """Modélisation directe : extrusion ou retrait d'une face d'un corps solide."""
        target_solid = self.doc.bodies.get(body_id) or self.last_solid or make_box(50.0, 30.0, 15.0)
        res = CADFullSuiteOrchestrator.direct_modeling_push_pull(target_solid, offset_mm=offset_mm, axis=axis)
        if body_id in self.doc.bodies:
            self.doc.bodies[body_id] = res.solid
            self.doc._notify_change()
        self.last_solid = res.solid
        return res.solid

    def fillet(self, body_id: str, radius_mm: float) -> Solid:
        """Applique un congé de raccordement sur un solide."""
        target_solid = self.doc.bodies.get(body_id) or self.last_solid or make_box(50.0, 30.0, 15.0)
        res = CADFullSuiteOrchestrator.direct_modeling_fillet(target_solid, radius_mm=radius_mm)
        if body_id in self.doc.bodies:
            self.doc.bodies[body_id] = res.solid
            self.doc._notify_change()
        self.last_solid = res.solid
        return res.solid

    def shell(self, body_id: str, wall_thickness_mm: float) -> Solid:
        """Évide un corps solide pour créer une coque mince."""
        target_solid = self.doc.bodies.get(body_id) or self.last_solid or make_box(50.0, 30.0, 15.0)
        res = CADFullSuiteOrchestrator.direct_modeling_shell(target_solid, wall_thickness_mm=wall_thickness_mm)
        if body_id in self.doc.bodies:
            self.doc.bodies[body_id] = res.solid
            self.doc._notify_change()
        self.last_solid = res.solid
        return res.solid



SafeContextVal = Union[
    CADScriptContext,
    types.ModuleType,
    type,
    Callable[..., None],
    Dict[str, Union[type, Callable[..., None], Callable[..., int], Callable[..., float], Callable[..., str], Callable[..., bool]]]
]


class CADScriptEngine:
    """
    Interpréteur et bac à sable (sandbox) d'exécution de code Python pour la CAO.
    Sécurise l'environnement en interdisant les accès système et les modules dangereux.
    """

    BANNED_MODULES = {"os", "sys", "subprocess", "socket", "urllib", "shutil", "builtins", "requests"}
    BANNED_CALLS = {"eval", "exec", "open", "__import__", "compile", "globals", "locals"}

    @classmethod
    def _check_import_node(cls, node: ast.AST) -> Optional[str]:
        """Vérifie la sécurité des déclarations d'import."""
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in cls.BANNED_MODULES:
                    return f"Module interdit détecté : '{alias.name}'"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.split(".")[0] in cls.BANNED_MODULES:
                return f"Import interdit détecté depuis : '{mod}'"
        return None

    @classmethod
    def _check_call_node(cls, node: ast.AST) -> Optional[str]:
        """Vérifie la sécurité des invocations de fonctions."""
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in cls.BANNED_CALLS:
                return f"Appel système non sécurisé interdit : '{node.func.id}()'"
        return None

    @classmethod
    def validate_ast(cls, code_str: str) -> Optional[str]:
        """
        Analyse l'AST du code pour détecter toute tentative d'injection ou d'importation malveillante.
        """
        try:
            tree = ast.parse(code_str)
        except SyntaxError as e:
            return f"Erreur de syntaxe à la ligne {e.lineno}: {e.msg}"

        for node in ast.walk(tree):
            err = cls._check_import_node(node) or cls._check_call_node(node)
            if err is not None:
                return err

        return None

    @classmethod
    def execute_script(
        cls,
        document: CADDocument,
        code_str: str,
        timeout_seconds: Optional[float] = 10.0
    ) -> ScriptExecutionResult:
        """
        Exécute le script Python dans un contexte contrôlé protégé par transaction atomique.
        """
        security_err = cls.validate_ast(code_str)
        if security_err is not None:
            return ScriptExecutionResult(
                success=False,
                message=f"Rejet de sécurité : {security_err}"
            )

        token = AICancellationToken(timeout_seconds=timeout_seconds)
        context = CADScriptContext(document, token=token)
        safe_globals: Dict[str, SafeContextVal] = {
            "cad": context,
            "math": math,
            "Vector3D": Vector3D,
            "Point2D": Point2D,
            "Solid": Solid,
            "__builtins__": {
                "range": range,
                "len": len,
                "int": int,
                "float": float,
                "str": str,
                "bool": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "min": min,
                "max": max,
                "abs": abs,
                "print": lambda *args: None
            }
        }

        t_start = time.perf_counter()
        with AtomicTransactionScope(document, "Script Code-as-CAD") as scope:
            try:
                compiled = compile(code_str, "<cad_script>", "exec")
                invoker: Callable[[types.CodeType, Dict[str, SafeContextVal]], None] = (
                    getattr(__builtins__, "exec") if hasattr(__builtins__, "exec") else __builtins__["exec"]
                )
                invoker(compiled, safe_globals)
                t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

                n_bodies = len(context.created_bodies)
                msg = f"Script exécuté avec succès en {t_elapsed_ms:.1f} ms. {n_bodies} corps généré(s) : {', '.join(context.created_bodies)}."
                return ScriptExecutionResult(
                    success=True,
                    message=msg,
                    bodies_created=context.created_bodies,
                    execution_time_ms=t_elapsed_ms
                )
            except Exception as e:
                t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0
                diag = SmartErrorDiagnostics.diagnose(e, code_str)
                if scope.initial_snapshot is not None:
                    CADTransactionManager.restore_snapshot(document, scope.initial_snapshot)
                return ScriptExecutionResult(
                    success=False,
                    message=f"{diag.explanation_fr} : {str(e)} (Conseil : {diag.remediation_hint})",
                    execution_time_ms=t_elapsed_ms
                )
