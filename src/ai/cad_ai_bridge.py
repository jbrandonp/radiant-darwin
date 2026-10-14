"""
Passerelle d'automatisation et de commande par Intelligence Artificielle (CAD-AI Bridge).
Permet à une IA de piloter l'intégralité du moteur de CAO par langage naturel ou JSON déclaratif.
Traduit les intentions en opérations géométriques Manifold3D, met à jour la timeline et le document.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Dict, List, Tuple, Optional

from src.core.types import Vector3D
from src.core.geometry import (
    Solid, make_box, make_cylinder, make_sphere, make_cone, make_torus
)
from src.core.document import CADDocument
from src.core.feature import Feature
from src.core.exporter import CADExporter
from src.ai.shape_synthesizer import ShapeSynthesizer
from src.ai.cad_validator import CADValidator, ValidationReport


class AICommandType(Enum):
    """Types de commandes exécutables par l'IA."""
    CREATE_PRIMITIVE = "create_primitive"
    SYNTHESIZE_SHAPE = "synthesize_shape"
    BOOLEAN_OPERATION = "boolean_operation"
    CLEAR_SCENE = "clear_scene"
    EXPORT = "export"
    CREATE_BOX = "create_box"
    CREATE_CYLINDER = "create_cylinder"
    CREATE_SPHERE = "create_sphere"
    CREATE_CONE = "create_cone"
    CREATE_TORUS = "create_torus"
    DRILL_HOLE = "drill_hole"
    FILLET = "fillet"
    CHAMFER = "chamfer"
    CREATE_SPUR_GEAR = "create_spur_gear"
    CREATE_PIPE_FLANGE = "create_pipe_flange"
    CREATE_HEAT_SINK = "create_heat_sink"
    CREATE_ELECTRONICS_ENCLOSURE = "create_electronics_enclosure"
    CREATE_REINFORCED_BRACKET = "create_reinforced_bracket"
    CREATE_STEPPED_SHAFT = "create_stepped_shaft"
    CREATE_PILLOW_BLOCK = "create_pillow_block"
    CREATE_PULLEY = "create_pulley"
    EXPORT_STL = "export_stl"
    EXPORT_STEP = "export_step"
    UNKNOWN = "unknown"


@dataclass
class CADAIExecutionResult:
    """Résultat officiel d'exécution d'une commande par l'IA."""
    success: bool
    message: str
    command_executed: str
    command_type: AICommandType = AICommandType.UNKNOWN
    body_id: Optional[str] = None
    volume_mm3: float = 0.0
    mass_aluminum_g: float = 0.0
    mass_steel_g: float = 0.0
    bounding_box_dims_mm: Optional[Vector3D] = None
    suggested_prompts: List[str] = field(default_factory=list)
    is_manifold: bool = True
    quality_score: float = 100.0


class CADAIBridge:
    """
    Passerelle universelle connectant n'importe quel modèle de langage (LLM) à CAD Studio.
    Analyse les instructions en langage naturel (français ou anglais) et orchestre le document.
    """

    def __init__(self, document: CADDocument) -> None:
        """Initialise la passerelle avec le document CAO cible."""
        self.doc: CADDocument = document

    def interpret_and_execute(self, prompt: str) -> CADAIExecutionResult:
        """Alias direct pour execute_natural_language_prompt."""
        return self.execute_natural_language_prompt(prompt)

    def execute_natural_language_prompt(self, prompt: str) -> CADAIExecutionResult:
        """
        Interprète une requête libre en langage naturel et exécute les opérations géométriques.
        Ex: 'Crée un engrenage de 24 dents module 2 avec alésage 12' ou 'Boîtier de 120x80x40 épaisseur 3'.
        """
        p_clean = prompt.lower().strip()

        # 1. Commande d'effacement / Nettoyage de la scène
        if any(w in p_clean for w in ["efface", "nettoie", "vide", "clear", "reset"]):
            self.doc.bodies.clear()
            self.doc.features.clear()
            self.doc._notify_change()
            return CADAIExecutionResult(
                success=True,
                message="Scène nettoyée avec succès. Tous les corps ont été supprimés.",
                command_executed="clear_scene",
                command_type=AICommandType.CLEAR_SCENE
            )

        # 2. Arbre étagé concentrique
        if "arbre" in p_clean and any(w in p_clean for w in ["étagé", "etage", "stepped", "multistep", "étages", "etages"]):
            return self._handle_stepped_shaft_intent(p_clean)

        # 3. Palier à semelle (Pillow Block)
        if any(w in p_clean for w in ["palier", "pillow"]):
            return self._handle_pillow_block_intent(p_clean)

        # 4. Poulie mécanique
        if any(w in p_clean for w in ["poulie", "pulley"]):
            return self._handle_pulley_intent(p_clean)

        # 5. Engrenage / Pignon
        if any(w in p_clean for w in ["engrenage", "pignon", "gear", "dent"]):
            return self._handle_spur_gear_intent(p_clean)

        # 6. Bride de tuyauterie
        if any(w in p_clean for w in ["bride", "flange"]):
            return self._handle_flange_intent(p_clean)

        # 7. Dissipateur thermique à ailettes
        if any(w in p_clean for w in ["dissipateur", "ailette", "heatsink", "refroidisseur"]):
            return self._handle_heat_sink_intent(p_clean)

        # 8. Boîtier électronique évidé
        if any(w in p_clean for w in ["boitier", "boîtier", "enclosure", "coffret"]):
            return self._handle_enclosure_intent(p_clean)

        # 9. Équerre de fixation
        if any(w in p_clean for w in ["equerre", "équerre", "bracket", "renfort"]):
            return self._handle_bracket_intent(p_clean)

        # 10. Cylindre / Arbre simple
        if any(w in p_clean for w in ["cylindre", "cylinder", "shaft"]):
            return self._handle_cylinder_intent(p_clean)

        # 11. Sphère
        if any(w in p_clean for w in ["sphere", "sphère", "balle", "boule"]):
            return self._handle_sphere_intent(p_clean)

        # 12. Perçage / Alésage sur la pièce active
        if any(w in p_clean for w in ["perce", "perçage", "trou", "alesage", "alésage", "drill", "hole"]):
            return self._handle_drill_hole_intent(p_clean)

        # 13. Pavé / Boîte / Plaque / Cube
        if any(w in p_clean for w in ["cube", "boite", "boîte", "pave", "pavé", "box", "plaque", "platine"]):
            return self._handle_box_intent(p_clean)

        # 14. Commande non reconnue : suggestions interactives
        return CADAIExecutionResult(
            success=False,
            message="Instruction non reconnue. Vous pouvez demander par exemple : 'Crée un engrenage', 'Bride de tuyauterie', 'Palier à semelle', 'Poulie', 'Dissipateur thermique', 'Boîtier électronique', 'Équerre renforcée', 'Arbre étagé', 'Cube 50x50x20', 'Cylindre r=15 h=40', 'Perce un trou Ø10'.",
            command_executed="unknown",
            command_type=AICommandType.UNKNOWN,
            suggested_prompts=[
                "Crée un engrenage de 20 dents module 2.0",
                "Génère une bride de tuyauterie 4 trous",
                "Palier à semelle pour arbre Ø25",
                "Poulie à gorge diamètre 100",
                "Dissipateur thermique 60x60 avec 8 ailettes",
                "Boîtier électronique 100x70x35 épaisseur 2.5",
                "Support équerre renforcé 50x50",
                "Arbre étagé 3 étages",
                "Crée un cube de 50x30x20",
                "Perce un trou de diamètre 12"
            ]
        )

    def _extract_numbers(self, text: str) -> List[float]:
        """Extrait toutes les valeurs numériques (entières et décimales) d'une chaîne."""
        matches = re.findall(r"[-+]?\d*\.?\d+", text)
        res: List[float] = []
        for m in matches:
            try:
                res.append(float(m))
            except ValueError:
                pass
        return res

    def _register_and_build_result(
        self,
        solid: Solid,
        base_name: str,
        cmd_type: str,
        category: AICommandType = AICommandType.SYNTHESIZE_SHAPE
    ) -> CADAIExecutionResult:
        """Enregistre le solide dans le document, recalcule les métriques, valide la topologie et génère le rapport."""
        body_id = f"{base_name}_{len(self.doc.bodies) + 1}"
        self.doc.bodies[body_id] = solid
        self.doc._notify_change()

        vol = solid.volume()
        mass_alu = (vol * 1e-3) * 2.70
        mass_steel = (vol * 1e-3) * 7.85

        p_min, p_max = solid.bounding_box()
        dims = Vector3D(abs(p_max.x - p_min.x), abs(p_max.y - p_min.y), abs(p_max.z - p_min.z))

        val_rep = CADValidator.validate_solid(solid)
        warn_str = f" [Avertissement: {'; '.join(val_rep.warnings)}]" if val_rep.warnings else ""

        msg = (
            f"L'IA a généré '{body_id}' avec succès : "
            f"Volume: {vol:.1f} mm³, Masse Alu: {mass_alu:.1f}g, Encombrement: {dims.x:.1f}x{dims.y:.1f}x{dims.z:.1f} mm "
            f"| Topologie: {'Étanche 2-Manifold' if val_rep.is_manifold else 'Non-Manifold'} (χ={val_rep.euler_characteristic}, Qualité: {val_rep.quality_score_percent:.0f}%){warn_str}."
        )

        return CADAIExecutionResult(
            success=True,
            message=msg,
            command_executed=cmd_type,
            command_type=category,
            body_id=body_id,
            volume_mm3=vol,
            mass_aluminum_g=mass_alu,
            mass_steel_g=mass_steel,
            bounding_box_dims_mm=dims,
            is_manifold=val_rep.is_manifold,
            quality_score=val_rep.quality_score_percent
        )

    def _handle_spur_gear_intent(self, text: str) -> CADAIExecutionResult:
        """Extrait les paramètres d'engrenage et matérialise le composant."""
        nums = self._extract_numbers(text)
        teeth = int(nums[0]) if len(nums) > 0 and nums[0] >= 4 else 24
        mod = float(nums[1]) if len(nums) > 1 and nums[1] > 0 else 2.0
        bore = float(nums[2]) if len(nums) > 2 and nums[2] > 0 else 12.0
        width = float(nums[3]) if len(nums) > 3 and nums[3] > 0 else 15.0

        gear = ShapeSynthesizer.create_spur_gear(num_teeth=teeth, module=mod, bore_diameter=bore, face_width=width)
        return self._register_and_build_result(gear, f"Engrenage_Z{teeth}_M{mod}", "create_spur_gear", AICommandType.SYNTHESIZE_SHAPE)

    def _handle_flange_intent(self, text: str) -> CADAIExecutionResult:
        """Extrait les paramètres de bride de tuyauterie."""
        nums = self._extract_numbers(text)
        od = float(nums[0]) if len(nums) > 0 else 120.0
        bore = float(nums[1]) if len(nums) > 1 else 50.0
        holes = int(nums[2]) if len(nums) > 2 and nums[2] >= 2 else 4

        flange = ShapeSynthesizer.create_pipe_flange(outer_diameter=od, inner_diameter=bore, num_holes=holes)
        return self._register_and_build_result(flange, f"Bride_DN{int(bore)}", "create_pipe_flange", AICommandType.SYNTHESIZE_SHAPE)

    def _handle_heat_sink_intent(self, text: str) -> CADAIExecutionResult:
        """Extrait les paramètres de dissipateur thermique."""
        nums = self._extract_numbers(text)
        w = float(nums[0]) if len(nums) > 0 else 80.0
        l = float(nums[1]) if len(nums) > 1 else 60.0
        fins = int(nums[2]) if len(nums) > 2 and nums[2] >= 2 else 10

        sink = ShapeSynthesizer.create_heat_sink(base_width=w, base_length=l, num_fins=fins)
        return self._register_and_build_result(sink, "Dissipateur_Thermique", "create_heat_sink", AICommandType.SYNTHESIZE_SHAPE)

    def _handle_enclosure_intent(self, text: str) -> CADAIExecutionResult:
        """Extrait les paramètres de boîtier électronique."""
        nums = self._extract_numbers(text)
        w = float(nums[0]) if len(nums) > 0 else 100.0
        l = float(nums[1]) if len(nums) > 1 else 70.0
        h = float(nums[2]) if len(nums) > 2 else 35.0
        thick = float(nums[3]) if len(nums) > 3 and nums[3] > 0 else 2.5

        enc = ShapeSynthesizer.create_electronics_enclosure(width=w, length=l, height=h, wall_thickness=thick)
        return self._register_and_build_result(enc, "Boitier_Electronique", "create_electronics_enclosure", AICommandType.SYNTHESIZE_SHAPE)

    def _handle_bracket_intent(self, text: str) -> CADAIExecutionResult:
        """Extrait les paramètres d'équerre de fixation."""
        nums = self._extract_numbers(text)
        l1 = float(nums[0]) if len(nums) > 0 else 60.0
        l2 = float(nums[1]) if len(nums) > 1 else 50.0
        thick = float(nums[2]) if len(nums) > 2 else 6.0

        brk = ShapeSynthesizer.create_reinforced_bracket(arm_length_1=l1, arm_length_2=l2, thickness=thick)
        return self._register_and_build_result(brk, "Equerre_Renforcee", "create_reinforced_bracket", AICommandType.SYNTHESIZE_SHAPE)

    def _handle_stepped_shaft_intent(self, text: str) -> CADAIExecutionResult:
        """Génère un arbre étagé concentrique."""
        nums = self._extract_numbers(text)
        stages = int(nums[0]) if len(nums) > 0 and 2 <= nums[0] <= 8 else 3
        diameters = [15.0 + i * 10.0 for i in range(stages)]
        lengths = [25.0 + i * 5.0 for i in range(stages)]
        shaft = ShapeSynthesizer.create_stepped_shaft(diameters, lengths)
        return self._register_and_build_result(shaft, "Arbre_Etage", "create_stepped_shaft", AICommandType.SYNTHESIZE_SHAPE)

    def _handle_pillow_block_intent(self, text: str) -> CADAIExecutionResult:
        """Extrait les paramètres de palier à semelle."""
        nums = self._extract_numbers(text)
        w = float(nums[0]) if len(nums) > 0 else 120.0
        bore = float(nums[1]) if len(nums) > 1 else 25.0
        h = float(nums[2]) if len(nums) > 2 else 36.5
        pillow = ShapeSynthesizer.create_pillow_block_bearing(base_width=w, bearing_bore=bore, shaft_center_height=h)
        return self._register_and_build_result(pillow, "Palier_Semelle", "create_pillow_block", AICommandType.CREATE_PILLOW_BLOCK)

    def _handle_pulley_intent(self, text: str) -> CADAIExecutionResult:
        """Extrait les paramètres de poulie mécanique."""
        nums = self._extract_numbers(text)
        dia = float(nums[0]) if len(nums) > 0 else 100.0
        w = float(nums[1]) if len(nums) > 1 else 25.0
        bore = float(nums[2]) if len(nums) > 2 else 15.0
        pulley = ShapeSynthesizer.create_v_belt_pulley(outer_diameter=dia, pulley_width=w, bore_diameter=bore)
        return self._register_and_build_result(pulley, "Poulie_Gorge", "create_pulley", AICommandType.CREATE_PULLEY)

    def _handle_cylinder_intent(self, text: str) -> CADAIExecutionResult:
        """Génère un cylindre ou portée d'arbre."""
        nums = self._extract_numbers(text)
        is_radius = "rayon" in text or "radius" in text
        val1 = float(nums[0]) if len(nums) > 0 else 20.0
        radius = val1 if is_radius else val1 / 2.0
        height = float(nums[1]) if len(nums) > 1 else 40.0

        cyl = make_cylinder(radius, height, center=True)
        return self._register_and_build_result(cyl, "Cylindre", "create_cylinder", AICommandType.CREATE_PRIMITIVE)

    def _handle_sphere_intent(self, text: str) -> CADAIExecutionResult:
        """Génère une sphère."""
        nums = self._extract_numbers(text)
        is_diameter = "diametre" in text or "diamètre" in text or "diameter" in text
        val = float(nums[0]) if len(nums) > 0 else 15.0
        radius = val / 2.0 if is_diameter else val

        sph = make_sphere(radius)
        return self._register_and_build_result(sph, "Sphere", "create_sphere", AICommandType.CREATE_PRIMITIVE)

    def _handle_drill_hole_intent(self, text: str) -> CADAIExecutionResult:
        """Perce un alésage cylindrique dans le dernier corps actif du document."""
        if not self.doc.bodies:
            return CADAIExecutionResult(
                success=False,
                message="Aucun corps solide existant dans la scène pour y percer un trou.",
                command_executed="drill_hole",
                command_type=AICommandType.BOOLEAN_OPERATION
            )

        nums = self._extract_numbers(text)
        hole_dia = float(nums[0]) if len(nums) > 0 else 10.0
        hx = float(nums[1]) if len(nums) > 1 else 0.0
        hy = float(nums[2]) if len(nums) > 2 else 0.0

        last_id = list(self.doc.bodies.keys())[-1]
        active_solid = self.doc.bodies[last_id]

        p_min, p_max = active_solid.bounding_box()
        total_depth = (p_max.z - p_min.z) * 1.5 + 10.0
        mid_z = (p_max.z + p_min.z) / 2.0

        drill = make_cylinder(hole_dia / 2.0, total_depth, center=True).translate(hx, hy, mid_z)
        drilled_solid = active_solid.difference(drill)

        self.doc.bodies[last_id] = drilled_solid
        self.doc._notify_change()

        return CADAIExecutionResult(
            success=True,
            message=f"Alésage Ø{hole_dia:.1f} mm percé avec succès dans '{last_id}' aux coordonnées ({hx:.1f}, {hy:.1f}).",
            command_executed="drill_hole",
            command_type=AICommandType.BOOLEAN_OPERATION,
            body_id=last_id,
            volume_mm3=drilled_solid.volume()
        )

    def _handle_box_intent(self, text: str) -> CADAIExecutionResult:
        """Génère un parallélépipède / boîte / platine standard."""
        nums = self._extract_numbers(text)
        w = float(nums[0]) if len(nums) > 0 else 60.0
        h = float(nums[1]) if len(nums) > 1 else 40.0
        d = float(nums[2]) if len(nums) > 2 else 15.0

        box = make_box(w, h, d, center=True)
        return self._register_and_build_result(box, "Boite", "create_box", AICommandType.CREATE_PRIMITIVE)
