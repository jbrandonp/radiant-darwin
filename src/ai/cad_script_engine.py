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
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable, Union

from src.core.document import CADDocument
from src.core.geometry import (
    Solid, make_box, make_cylinder, make_sphere, make_cone, make_torus
)
from src.core.types import Vector3D, Point2D
from src.ai.shape_synthesizer import ShapeSynthesizer

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

    def __init__(self, document: CADDocument) -> None:
        self.doc: CADDocument = document
        self.created_bodies: List[str] = []
        self.last_solid: Optional[Solid] = None

    def box(self, width: float, height: float, depth: float, center: bool = True) -> Solid:
        """Crée un parallélépipède rectangle."""
        return make_box(width, height, depth, center=center)

    def cylinder(self, radius: float, height: float, center: bool = True) -> Solid:
        """Crée un cylindre orienté selon l'axe Z."""
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
        body_id = f"{name}_{len(self.doc.bodies) + 1}"
        self.doc.bodies[body_id] = solid
        self.created_bodies.append(body_id)
        self.last_solid = solid
        self.doc._notify_change()
        return body_id

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


SafeContextVal = Union[CADScriptContext, type, Callable, Dict[str, Callable]]


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
    def execute_script(cls, document: CADDocument, code_str: str) -> ScriptExecutionResult:
        """
        Exécute le script Python dans un contexte contrôlé et ajoute les formes au document.
        """
        security_err = cls.validate_ast(code_str)
        if security_err is not None:
            return ScriptExecutionResult(
                success=False,
                message=f"Rejet de sécurité : {security_err}"
            )

        context = CADScriptContext(document)
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
        try:
            compiled = compile(code_str, "<cad_script>", "exec")
            invoker: Callable = getattr(__builtins__, "exec") if hasattr(__builtins__, "exec") else __builtins__["exec"]
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
            return ScriptExecutionResult(
                success=False,
                message=f"Erreur d'exécution du script CAO : {str(e)}",
                execution_time_ms=t_elapsed_ms
            )
