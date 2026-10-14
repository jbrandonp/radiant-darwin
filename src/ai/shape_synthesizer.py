"""
Générateur de formes industrielles complexes pour l'IA (Parametric Shape Synthesizer).
Permet à une IA de matérialiser n'importe quel objet mécanique complexe :
engrenages à développante, brides normalisées, boîtiers électroniques, dissipateurs thermiques,
arbres étagés avec clavettes, équerres renforcées et ressorts hélicoïdaux.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
import math
from typing import List, Tuple, Optional
import numpy as np

from src.core.types import Vector3D, Point2D
from src.core.geometry import (
    Solid, make_box, make_cylinder, make_sphere, make_cone, make_torus, extrude_polygon
)


class ShapeSynthesizer:
    """
    Bibliothèque générative experte permettant à une IA de concevoir
    des composants mécaniques complets sans difficulté.
    """

    @staticmethod
    def create_spur_gear(
        num_teeth: int = 20,
        module: float = 2.0,
        pressure_angle_deg: float = 20.0,
        face_width: float = 12.0,
        bore_diameter: float = 12.0,
        keyway_width: float = 4.0,
        keyway_depth: float = 2.0
    ) -> Solid:
        """
        Génère un engrenage droit cylindrique à développante de cercle normalisé ISO.
        """
        # Dimensions normalisées
        pitch_diameter = num_teeth * module
        pitch_radius = pitch_diameter / 2.0
        addendum = 1.0 * module
        dedendum = 1.25 * module
        outer_radius = pitch_radius + addendum
        root_radius = max(bore_diameter / 2.0 + 2.0, pitch_radius - dedendum)

        # Tracé du contour polygonal d'une dent (profil trapézoïdal approché à développante)
        points_2d: List[Point2D] = []
        angle_per_tooth = 2.0 * math.pi / max(4, num_teeth)
        half_tooth_angle = angle_per_tooth / 4.0

        for i in range(num_teeth):
            theta = i * angle_per_tooth
            # 1. Fond de dent (Root)
            p_root_1 = Point2D(root_radius * math.cos(theta - half_tooth_angle), root_radius * math.sin(theta - half_tooth_angle))
            # 2. Flanc montant (Involute flank)
            p_pitch_1 = Point2D(pitch_radius * math.cos(theta - half_tooth_angle * 0.6), pitch_radius * math.sin(theta - half_tooth_angle * 0.6))
            # 3. Sommet de dent (Tip)
            p_tip_1 = Point2D(outer_radius * math.cos(theta - half_tooth_angle * 0.3), outer_radius * math.sin(theta - half_tooth_angle * 0.3))
            p_tip_2 = Point2D(outer_radius * math.cos(theta + half_tooth_angle * 0.3), outer_radius * math.sin(theta + half_tooth_angle * 0.3))
            # 4. Flanc descendant
            p_pitch_2 = Point2D(pitch_radius * math.cos(theta + half_tooth_angle * 0.6), pitch_radius * math.sin(theta + half_tooth_angle * 0.6))
            p_root_2 = Point2D(root_radius * math.cos(theta + half_tooth_angle), root_radius * math.sin(theta + half_tooth_angle))

            points_2d.extend([p_root_1, p_pitch_1, p_tip_1, p_tip_2, p_pitch_2, p_root_2])

        # Extrusion volumique du corps denté
        gear_blank = extrude_polygon(points_2d, face_width, name=f"SpurGear_Z{num_teeth}_M{module}")

        # Perçage de l'alésage central pour l'arbre
        bore = make_cylinder(bore_diameter / 2.0, face_width * 1.5, center=True)
        gear_with_bore = gear_blank.difference(bore)

        # Rainure de clavette normalisée
        if keyway_width > 0.0 and keyway_depth > 0.0:
            kw_box = make_box(keyway_width, keyway_depth * 2.0, face_width * 1.5, center=True)
            kw_shifted = kw_box.translate(0.0, (bore_diameter / 2.0) + (keyway_depth / 2.0), 0.0)
            return gear_with_bore.difference(kw_shifted)

        return gear_with_bore

    @staticmethod
    def create_pipe_flange(
        outer_diameter: float = 120.0,
        inner_diameter: float = 50.0,
        flange_thickness: float = 14.0,
        hub_diameter: float = 70.0,
        hub_height: float = 18.0,
        bolt_circle_diameter: float = 95.0,
        num_holes: int = 4,
        hole_diameter: float = 12.0
    ) -> Solid:
        """
        Génère une bride de tuyauterie industrielle normalisée avec collet et perçages circulaires.
        """
        # Plateau principal de bride
        base_disc = make_cylinder(outer_diameter / 2.0, flange_thickness, center=False, name="FlangeBase")

        # Collet de soudage (Hub)
        if hub_height > 0.0 and hub_diameter > inner_diameter:
            hub = make_cylinder(hub_diameter / 2.0, hub_height, center=False)
            flange_body = base_disc.union(hub)
        else:
            flange_body = base_disc

        # Alésage intérieur traversant pour passage du fluide
        total_h = flange_thickness + hub_height + 10.0
        through_bore = make_cylinder(inner_diameter / 2.0, total_h, center=True).translate(0.0, 0.0, total_h / 2.0 - 5.0)
        flange_bored = flange_body.difference(through_bore)

        # Réseau circulaire de trous de boulons (Bolt pattern)
        radius_pcd = bolt_circle_diameter / 2.0
        angle_step = 2.0 * math.pi / max(1, num_holes)

        for i in range(num_holes):
            ang = i * angle_step
            hx = radius_pcd * math.cos(ang)
            hy = radius_pcd * math.sin(ang)
            hole = make_cylinder(hole_diameter / 2.0, flange_thickness * 1.5, center=True).translate(hx, hy, flange_thickness / 2.0)
            flange_bored = flange_bored.difference(hole)

        return flange_bored

    @staticmethod
    def create_heat_sink(
        base_width: float = 80.0,
        base_length: float = 60.0,
        base_thickness: float = 5.0,
        fin_thickness: float = 1.5,
        fin_height: float = 25.0,
        num_fins: int = 10
    ) -> Solid:
        """
        Génère un dissipateur thermique à ailettes en peigne pour l'électronique de puissance.
        """
        # Semelle thermique en aluminium
        base = make_box(base_width, base_length, base_thickness, center=False, name="HeatSinkBase")

        if num_fins <= 0:
            return base

        # Calcul du pas entre chaque ailette
        available_space = base_width - (num_fins * fin_thickness)
        pitch = available_space / max(1, num_fins - 1) + fin_thickness

        sink = base
        for i in range(num_fins):
            fx = i * pitch
            fin = make_box(fin_thickness, base_length, fin_height, center=False)
            fin_positioned = fin.translate(fx, 0.0, base_thickness)
            sink = sink.union(fin_positioned)

        return sink

    @staticmethod
    def create_electronics_enclosure(
        width: float = 100.0,
        length: float = 70.0,
        height: float = 35.0,
        wall_thickness: float = 2.5,
        boss_diameter: float = 8.0,
        boss_hole_diameter: float = 3.2 # Taraudage M3 standard
    ) -> Solid:
        """
        Génère un boîtier électronique évidé avec 4 bossages de fixation aux coins.
        """
        # Bloc extérieur
        outer_box = make_box(width, length, height, center=False, name="EnclosureBody")

        # Cavité intérieure évidée
        inner_w = width - 2.0 * wall_thickness
        inner_l = length - 2.0 * wall_thickness
        inner_h = height - wall_thickness + 1.0  # Laisse le fond et débouche sur le dessus
        cavity = make_box(inner_w, inner_l, inner_h, center=False).translate(wall_thickness, wall_thickness, wall_thickness)

        box_shelled = outer_box.difference(cavity)

        # 4 Bossages de fixation d'angle pour vis de couvercle
        boss_r = boss_diameter / 2.0
        hole_r = boss_hole_diameter / 2.0
        boss_positions = [
            (wall_thickness + boss_r, wall_thickness + boss_r),
            (width - wall_thickness - boss_r, wall_thickness + boss_r),
            (width - wall_thickness - boss_r, length - wall_thickness - boss_r),
            (wall_thickness + boss_r, length - wall_thickness - boss_r)
        ]

        for bx, by in boss_positions:
            boss = make_cylinder(boss_r, height - wall_thickness, center=False).translate(bx, by, wall_thickness)
            hole = make_cylinder(hole_r, height, center=False).translate(bx, by, wall_thickness)
            boss_drilled = boss.difference(hole)
            box_shelled = box_shelled.union(boss_drilled)

        return box_shelled

    @staticmethod
    def create_reinforced_bracket(
        arm_length_1: float = 60.0,
        arm_length_2: float = 50.0,
        width: float = 30.0,
        thickness: float = 6.0,
        rib_thickness: float = 4.0,
        hole_diameter: float = 6.5 # Perçage vis M6
    ) -> Solid:
        """
        Génère une équerre de fixation renforcée (L-Bracket) avec nervure de renfort centrale.
        """
        # Aile horizontale 1
        arm1 = make_box(arm_length_1, width, thickness, center=False)
        # Aile verticale 2
        arm2 = make_box(thickness, width, arm_length_2, center=False)
        bracket = arm1.union(arm2)

        # Nervure triangulaire de renfort (Stiffening Rib)
        rib_len_1 = arm_length_1 * 0.7
        rib_len_2 = arm_length_2 * 0.7
        rib_poly = [
            Point2D(thickness, thickness),
            Point2D(rib_len_1, thickness),
            Point2D(thickness, rib_len_2)
        ]
        # Extrusion dans le plan XZ puis rotation/translation
        rib = extrude_polygon(rib_poly, rib_thickness, name="Rib")
        rib_centered = rib.translate(0.0, (width - rib_thickness) / 2.0, 0.0)
        bracket_reinforced = bracket.union(rib_centered)

        # Perçages de fixation
        # Trou sur aile 1
        h1 = make_cylinder(hole_diameter / 2.0, thickness * 2.0, center=True).translate(arm_length_1 * 0.8, width / 2.0, thickness / 2.0)
        # Trou sur aile 2
        h2 = make_cylinder(hole_diameter / 2.0, thickness * 2.0, center=True).rotate(0.0, 90.0, 0.0).translate(thickness / 2.0, width / 2.0, arm_length_2 * 0.8)

        return bracket_reinforced.difference(h1).difference(h2)

    @staticmethod
    def create_stepped_shaft(
        diameters: List[float],
        lengths: List[float],
        center_bore: float = 0.0
    ) -> Solid:
        """
        Génère un arbre mécanique étagé de transmission à plusieurs portées de roulement.
        """
        if not diameters or not lengths or len(diameters) != len(lengths):
            return make_cylinder(10.0, 40.0, center=False)

        current_z = 0.0
        shaft: Optional[Solid] = None

        for d, l in zip(diameters, lengths):
            section = make_cylinder(d / 2.0, l, center=False).translate(0.0, 0.0, current_z)
            if shaft is None:
                shaft = section
            else:
                shaft = shaft.union(section)
            current_z += l

        assert shaft is not None
        if center_bore > 0.0:
            bore = make_cylinder(center_bore / 2.0, current_z * 1.5, center=True).translate(0.0, 0.0, current_z / 2.0)
            return shaft.difference(bore)

        return shaft

    @staticmethod
    def create_pillow_block_bearing(
        base_width: float = 120.0,
        base_depth: float = 35.0,
        base_thickness: float = 14.0,
        bearing_bore: float = 25.0,
        shaft_center_height: float = 36.5,
        bolt_hole_diameter: float = 11.0,
        bolt_center_dist: float = 95.0
    ) -> Solid:
        """
        Génère un palier à semelle auto-aligneur standard (Pillow Block Housing).
        """
        # 1. Semelle de fixation
        base = make_box(base_width, base_depth, base_thickness, center=True).translate(0.0, 0.0, base_thickness / 2.0)

        # 2. Perçages de fixation de la semelle
        h_left = make_cylinder(bolt_hole_diameter / 2.0, base_thickness * 2.0, center=True).translate(-bolt_center_dist / 2.0, 0.0, base_thickness / 2.0)
        h_right = make_cylinder(bolt_hole_diameter / 2.0, base_thickness * 2.0, center=True).translate(bolt_center_dist / 2.0, 0.0, base_thickness / 2.0)
        base_drilled = base.difference(h_left).difference(h_right)

        # 3. Corps vertical du palier (arche centrale)
        housing_radius = bearing_bore * 0.9 + 10.0
        housing_cyl = make_cylinder(housing_radius, base_depth, center=True).rotate(90.0, 0.0, 0.0).translate(0.0, 0.0, shaft_center_height)

        # 4. Bloc montant de liaison entre semelle et cylindre
        support_box = make_box(housing_radius * 1.8, base_depth, shaft_center_height, center=True).translate(0.0, 0.0, shaft_center_height / 2.0)
        housing_body = base_drilled.union(support_box).union(housing_cyl)

        # 5. Alésage central pour bague de roulement
        bore = make_cylinder(bearing_bore / 2.0, base_depth * 1.5, center=True).rotate(90.0, 0.0, 0.0).translate(0.0, 0.0, shaft_center_height)
        return housing_body.difference(bore)

    @staticmethod
    def create_v_belt_pulley(
        outer_diameter: float = 100.0,
        pulley_width: float = 25.0,
        bore_diameter: float = 15.0,
        groove_depth: float = 10.0,
        groove_top_width: float = 12.0
    ) -> Solid:
        """
        Génère une poulie mécanique à gorge trapézoïdale pour courroie en V.
        """
        pulley_blank = make_cylinder(outer_diameter / 2.0, pulley_width, center=True)

        # Alésage pour l'arbre
        bore = make_cylinder(bore_diameter / 2.0, pulley_width * 1.5, center=True)
        pulley_drilled = pulley_blank.difference(bore)

        # Gorge taillée circonférentielle
        groove_cut = make_torus(outer_diameter / 2.0, groove_top_width / 2.0)
        return pulley_drilled.difference(groove_cut)
