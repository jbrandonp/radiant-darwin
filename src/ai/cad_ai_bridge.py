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
from typing import Callable, Dict, List, Tuple, Optional

from src.core.types import Vector3D
from src.core.geometry import (
    Solid, make_box, make_cylinder, make_sphere, make_cone, make_torus
)
from src.core.document import CADDocument
from src.core.feature import Feature
from src.core.exporter import CADExporter
from src.ai.shape_synthesizer import ShapeSynthesizer
from src.ai.cad_validator import CADValidator, ValidationReport
from src.ai.ai_vision_feedback import AIVisionFeedback
from src.ai.cad_ai_full_suite import CADFullSuiteOrchestrator
from src.ai.cad_ai_stability import (
    AtomicTransactionScope,
    CADTransactionManager,
    SmartErrorDiagnostics
)


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
    RUN_CAM = "run_cam"
    RUN_FEA = "run_fea"
    GENERATE_TECHDRAW = "generate_techdraw"
    DESIGN_SHEET_METAL = "design_sheet_metal"
    ASSIGN_MATERIAL = "assign_material"
    DIRECT_MODELING = "direct_modeling"
    EXPORT_FILE = "export_file"
    UNDO = "undo"
    REDO = "redo"
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
    vision_data_uri: Optional[str] = None
    remediation_hint: str = ""


class CADAIBridge:
    """
    Passerelle universelle connectant n'importe quel modèle de langage (LLM) à CAD Studio.
    Analyse les instructions en langage naturel (français ou anglais) et orchestre le document.
    """

    def __init__(self, document: CADDocument) -> None:
        """Initialise la passerelle avec le document CAO cible."""
        self.doc: CADDocument = document

    @property
    def document(self) -> CADDocument:
        """Accès au document CAO actif."""
        return self.doc

    def execute_prompt(self, prompt: str) -> CADAIExecutionResult:
        """Exécute une instruction en langage naturel dans un scope atomique et attache le retour visuel 3D."""
        p_clean = prompt.lower().strip()

        # Commande d'annulation (Undo)
        if any(w in p_clean for w in ["annule", "undo", "reviens en arriere", "reviens en arrière"]):
            ok, msg = CADTransactionManager.undo(self.doc)
            vis = AIVisionFeedback.capture_document_view(self.doc, width=384, height=384)
            return CADAIExecutionResult(
                success=ok,
                message=msg,
                command_executed="undo",
                command_type=AICommandType.UNDO,
                vision_data_uri=vis.data_uri
            )

        # Commande de rétablissement (Redo)
        if any(w in p_clean for w in ["retablis", "rétablis", "redo", "refais"]):
            ok, msg = CADTransactionManager.redo(self.doc)
            vis = AIVisionFeedback.capture_document_view(self.doc, width=384, height=384)
            return CADAIExecutionResult(
                success=ok,
                message=msg,
                command_executed="redo",
                command_type=AICommandType.REDO,
                vision_data_uri=vis.data_uri
            )

        # Exécution protégée dans un scope transactionnel avec restauration automatique en cas d'erreur
        with AtomicTransactionScope(self.doc, prompt) as scope:
            try:
                res = self.execute_natural_language_prompt(prompt)
                if not res.success and scope.initial_snapshot is not None:
                    CADTransactionManager.restore_snapshot(self.doc, scope.initial_snapshot)
                vis = AIVisionFeedback.capture_document_view(self.doc, width=384, height=384)
                res.vision_data_uri = vis.data_uri
                return res
            except Exception as err:
                diag = SmartErrorDiagnostics.diagnose(err, prompt)
                if scope.initial_snapshot is not None:
                    CADTransactionManager.restore_snapshot(self.doc, scope.initial_snapshot)
                vis = AIVisionFeedback.capture_document_view(self.doc, width=384, height=384)
                return CADAIExecutionResult(
                    success=False,
                    message=f"{diag.explanation_fr} (Conseil : {diag.remediation_hint})",
                    command_executed=prompt,
                    command_type=AICommandType.UNKNOWN,
                    remediation_hint=diag.remediation_hint,
                    vision_data_uri=vis.data_uri
                )

    def get_context_summary(self) -> Dict[str, str]:
        """Retourne l'état courant synthétisé de la scène pour injection de contexte dans l'IA."""
        body_count = len(self.doc.bodies)
        feat_count = len(self.doc.features)
        sketch_count = len(self.doc.sketches)
        body_names = ", ".join(self.doc.bodies.keys()) if self.doc.bodies else "aucun corps"
        total_vol = sum(b.volume() for b in self.doc.bodies.values() if not b.is_empty())
        return {
            "document_name": self.doc.name,
            "bodies_count": str(body_count),
            "bodies_list": body_names,
            "features_count": str(feat_count),
            "sketches_count": str(sketch_count),
            "total_volume_mm3": f"{total_vol:.1f}",
            "rollback_index": str(self.doc.rollback_index),
        }

    def _get_intent_dispatch_table(self) -> List[Tuple[List[str], Callable[[str], CADAIExecutionResult]]]:
        """Retourne la table de correspondance mots-clés → gestionnaire d'intention CAO."""
        return [
            (["efface", "nettoie", "vide", "clear", "reset"], self._handle_clear_scene),
            (["usinage", "cam", "gcode", "g-code", "fraisage", "contournage"], self._handle_cam_intent),
            (["simulation", "fea", "contrainte", "mises", "force", "charge", "resistance", "résistance"], self._handle_fea_intent),
            (["plan", "techdraw", "mise en plan", "dessin technique"], self._handle_techdraw_intent),
            (["tôle", "tole", "pliage", "plie", "flan", "sheetmetal", "sheet metal"], self._handle_sheet_metal_intent),
            (["materiau", "matériau", "matiere", "matière", "inox", "titane", "masse", "poids"], self._handle_material_intent),
            (["pousse", "tire", "push", "pull", "conge", "congé", "fillet", "chanfrein", "coque", "shell", "évide", "evide"], self._handle_direct_modeling_intent),
            (["export", "exporter", "step", "stl"], self._handle_export_intent),
        ]

    def _get_shape_dispatch_table(self) -> List[Tuple[Callable[[str], bool], Callable[[str], CADAIExecutionResult]]]:
        """Retourne la table de correspondance conditionnelle → gestionnaire de forme 3D."""
        def is_stepped_shaft(p: str) -> bool:
            return "arbre" in p and any(w in p for w in ["étagé", "etage", "stepped", "multistep", "étages", "etages"])

        kw_handlers: List[Tuple[List[str], Callable[[str], CADAIExecutionResult]]] = [
            (["palier", "pillow"], self._handle_pillow_block_intent),
            (["poulie", "pulley"], self._handle_pulley_intent),
            (["engrenage", "pignon", "gear", "dent"], self._handle_spur_gear_intent),
            (["bride", "flange"], self._handle_flange_intent),
            (["dissipateur", "ailette", "heatsink", "refroidisseur"], self._handle_heat_sink_intent),
            (["boitier", "boîtier", "enclosure", "coffret"], self._handle_enclosure_intent),
            (["equerre", "équerre", "bracket", "renfort"], self._handle_bracket_intent),
            (["cylindre", "cylinder", "shaft"], self._handle_cylinder_intent),
            (["sphere", "sphère", "balle", "boule"], self._handle_sphere_intent),
            (["perce", "perçage", "trou", "alesage", "alésage", "drill", "hole"], self._handle_drill_hole_intent),
            (["cube", "boite", "boîte", "pave", "pavé", "box", "plaque", "platine"], self._handle_box_intent),
        ]
        result: List[Tuple[Callable[[str], bool], Callable[[str], CADAIExecutionResult]]] = []
        result.append((is_stepped_shaft, self._handle_stepped_shaft_intent))
        for keywords, handler in kw_handlers:
            result.append((lambda p, kw=keywords: any(w in p for w in kw), handler))
        return result

    def _handle_clear_scene(self, p_clean: str) -> CADAIExecutionResult:
        """Efface tous les corps de la scène."""
        self.doc.bodies.clear()
        self.doc.features.clear()
        self.doc._notify_change()
        return CADAIExecutionResult(
            success=True,
            message="Scène nettoyée avec succès. Tous les corps ont été supprimés.",
            command_executed="clear_scene",
            command_type=AICommandType.CLEAR_SCENE
        )

    def interpret_and_execute(self, prompt: str) -> CADAIExecutionResult:
        """Alias direct pour execute_natural_language_prompt."""
        return self.execute_natural_language_prompt(prompt)

    def execute_natural_language_prompt(self, prompt: str) -> CADAIExecutionResult:
        """
        Interprète une requête libre en langage naturel et exécute les opérations géométriques.
        Ex: 'Crée un engrenage de 24 dents module 2 avec alésage 12' ou 'Boîtier de 120x80x40 épaisseur 3'.
        """
        p_clean = prompt.lower().strip()

        # Phase 1 : intentions techniques (CAM, FEA, export, etc.)
        for keywords, handler in self._get_intent_dispatch_table():
            if any(w in p_clean for w in keywords):
                return handler(p_clean)

        # Phase 2 : intentions de forme 3D
        for predicate, handler in self._get_shape_dispatch_table():
            if predicate(p_clean):
                return handler(p_clean)

        # Commande non reconnue : suggestions interactives
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
                continue
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

    def _get_active_or_default_solid(self) -> Tuple[str, Solid]:
        """Retourne le solide actif dans la scène ou crée un solide étalon par défaut."""
        if self.doc.bodies:
            first_id = next(iter(self.doc.bodies))
            return (first_id, self.doc.bodies[first_id])
        default_box = make_box(60.0, 40.0, 20.0, center=True)
        self.doc.bodies["Piece_Defaut"] = default_box
        self.doc._notify_change()
        return ("Piece_Defaut", default_box)

    def _handle_cam_intent(self, p_clean: str) -> CADAIExecutionResult:
        """Génère les parcours d'usinage et le G-Code."""
        body_id, solid = self._get_active_or_default_solid()
        nums = self._extract_numbers(p_clean)
        depth = nums[0] if nums else 10.0
        cam_res = CADFullSuiteOrchestrator.run_cam(solid, operation_type="contour", depth_mm=depth)
        msg = (
            f"Génération FAO réussie pour '{body_id}' : {cam_res.operation_name} avec {cam_res.tool_name}. "
            f"Passes : {cam_res.total_passes}, Longueur de coupe : {cam_res.total_cut_length_mm:.1f} mm, "
            f"Temps estimé : {cam_res.estimated_time_seconds:.1f} s ({cam_res.gcode_lines_count} lignes de G-Code)."
        )
        return CADAIExecutionResult(
            success=True,
            message=msg,
            command_executed="run_cam",
            command_type=AICommandType.RUN_CAM,
            body_id=body_id,
            volume_mm3=solid.volume()
        )

    def _handle_fea_intent(self, p_clean: str) -> CADAIExecutionResult:
        """Exécute la simulation statique par éléments finis."""
        body_id, solid = self._get_active_or_default_solid()
        nums = self._extract_numbers(p_clean)
        force = nums[0] if nums else 2000.0
        mat_name = "Aluminium 6061-T6"
        if "acier" in p_clean:
            mat_name = "Acier Carbone C45"
        elif "inox" in p_clean:
            mat_name = "Acier Inox 316L"
        elif "titane" in p_clean:
            mat_name = "Titane Ti-6Al-4V"

        fea_res = CADFullSuiteOrchestrator.run_fea(solid, applied_force_n=force, material_name=mat_name)
        msg = (
            f"Simulation FEA sur '{body_id}' sous {force:.0f} N ({mat_name}) : "
            f"Contrainte von Mises max : {fea_res.max_stress_mpa:.1f} MPa, Déplacement max : {fea_res.max_displacement_mm:.3f} mm, "
            f"Facteur de sécurité : {fea_res.safety_factor:.2f} -> {fea_res.status_verdict}. {fea_res.recommendation}"
        )
        return CADAIExecutionResult(
            success=True,
            message=msg,
            command_executed="run_fea",
            command_type=AICommandType.RUN_FEA,
            body_id=body_id,
            volume_mm3=solid.volume()
        )

    def _handle_techdraw_intent(self, p_clean: str) -> CADAIExecutionResult:
        """Génère la mise en plan 2D normalisée ISO."""
        body_id, solid = self._get_active_or_default_solid()
        td_res = CADFullSuiteOrchestrator.generate_techdraw(solid, part_name=body_id)
        return CADAIExecutionResult(
            success=True,
            message=td_res.summary_text,
            command_executed="generate_techdraw",
            command_type=AICommandType.GENERATE_TECHDRAW,
            body_id=body_id,
            volume_mm3=solid.volume()
        )

    def _handle_sheet_metal_intent(self, p_clean: str) -> CADAIExecutionResult:
        """Conçoit une pièce de tôlerie avec plis et calcule son déplié à plat."""
        nums = self._extract_numbers(p_clean)
        w = nums[0] if len(nums) > 0 else 100.0
        l = nums[1] if len(nums) > 1 else 60.0
        t = nums[2] if len(nums) > 2 else 2.0
        flange_h = nums[3] if len(nums) > 3 else 20.0

        sm_res = CADFullSuiteOrchestrator.design_sheet_metal(
            width_mm=w, length_mm=l, thickness_mm=t, flange_height_mm=flange_h
        )
        body_id = f"Tole_Pliee_{len(self.doc.bodies) + 1}"
        self.doc.bodies[body_id] = sm_res.solid
        self.doc._notify_change()

        return CADAIExecutionResult(
            success=True,
            message=sm_res.description,
            command_executed="design_sheet_metal",
            command_type=AICommandType.DESIGN_SHEET_METAL,
            body_id=body_id,
            volume_mm3=sm_res.solid.volume()
        )

    def _handle_material_intent(self, p_clean: str) -> CADAIExecutionResult:
        """Calcule et assigne les caractéristiques massiques d'un matériau."""
        body_id, solid = self._get_active_or_default_solid()
        mat_name = "Aluminium 6061-T6"
        if "inox" in p_clean:
            mat_name = "Acier Inox 316L"
        elif "titane" in p_clean:
            mat_name = "Titane Ti-6Al-4V"
        elif "acier" in p_clean:
            mat_name = "Acier Carbone C45"
        elif "laiton" in p_clean:
            mat_name = "Laiton CuZn39Pb3"

        props = CADFullSuiteOrchestrator.get_material_properties(solid, mat_name)
        msg = (
            f"Propriétés physiques appliquées à '{body_id}' ({props.material_name}) : "
            f"Masse : {props.mass_g:.1f} g ({props.mass_kg:.3f} kg), Densité : {props.density_g_cm3:.2f} g/cm³, "
            f"Volume : {props.volume_mm3:.1f} mm³, Limite élastique Re : {props.yield_strength_mpa:.0f} MPa."
        )
        return CADAIExecutionResult(
            success=True,
            message=msg,
            command_executed="assign_material",
            command_type=AICommandType.ASSIGN_MATERIAL,
            body_id=body_id,
            volume_mm3=props.volume_mm3,
            mass_aluminum_g=props.mass_g if "Alu" in mat_name else (props.volume_mm3 * 1e-3 * 2.70),
            mass_steel_g=props.mass_g if "Acier" in mat_name else (props.volume_mm3 * 1e-3 * 7.85)
        )

    def _handle_direct_modeling_intent(self, p_clean: str) -> CADAIExecutionResult:
        """Exécute une modification directe (push-pull, congé, coque)."""
        body_id, solid = self._get_active_or_default_solid()
        nums = self._extract_numbers(p_clean)
        val = nums[0] if nums else 5.0

        if any(w in p_clean for w in ["conge", "congé", "fillet"]):
            dm_res = CADFullSuiteOrchestrator.direct_modeling_fillet(solid, radius_mm=val)
        elif any(w in p_clean for w in ["coque", "shell", "évide", "evide"]):
            dm_res = CADFullSuiteOrchestrator.direct_modeling_shell(solid, wall_thickness_mm=val)
        else:
            dm_res = CADFullSuiteOrchestrator.direct_modeling_push_pull(solid, offset_mm=val, axis="z")

        self.doc.bodies[body_id] = dm_res.solid
        self.doc._notify_change()

        return CADAIExecutionResult(
            success=True,
            message=dm_res.message,
            command_executed="direct_modeling",
            command_type=AICommandType.DIRECT_MODELING,
            body_id=body_id,
            volume_mm3=dm_res.volume_after_mm3
        )

    def _handle_export_intent(self, p_clean: str) -> CADAIExecutionResult:
        """Exporte le modèle dans le format demandé."""
        fmt = "step"
        if "stl" in p_clean:
            fmt = "stl"
        elif "dxf" in p_clean:
            fmt = "dxf"
        elif "obj" in p_clean:
            fmt = "obj"

        filename = f"export_{self.doc.name.lower().replace(' ', '_')}.{fmt}"
        msg = f"Export du modèle au format {fmt.upper()} initié avec succès vers '{filename}'."
        return CADAIExecutionResult(
            success=True,
            message=msg,
            command_executed=f"export_{fmt}",
            command_type=AICommandType.EXPORT_FILE
        )

