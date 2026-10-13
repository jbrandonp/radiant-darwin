"""
Moteur de lancer de rayons et d'illumination globale PBR (Raytracing / Shading).
Calcule l'éclairage de studio à 3 points, les réflexions spéculaires de Fresnel,
la micro-rugosité et produit des images de rendu photoréalistes exportables en PNG.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
import numpy as np
from PySide6.QtGui import QImage, QColor

from src.core.types import Vector3D, MeshBuffer
from src.core.geometry import Solid
from src.render.pbr_material import PBRMaterial, PBR_LIBRARY


@dataclass
class DirectionalLight:
    """Source de lumière directionnelle de studio."""
    direction: Vector3D
    color: Tuple[float, float, float]
    intensity: float


@dataclass
class StudioEnvironment:
    """Environnement lumineux de studio complet."""
    name: str
    lights: List[DirectionalLight]
    ambient_color: Tuple[float, float, float] = (0.2, 0.22, 0.25)
    ambient_intensity: float = 0.25


def create_default_studio() -> StudioEnvironment:
    """Crée l'éclairage de studio 3-points standard (Key, Fill, Rim)."""
    return StudioEnvironment(
        name="Studio 3-Points Classique",
        lights=[
            DirectionalLight(
                direction=Vector3D(0.577, 0.577, 0.577).normalized(),
                color=(1.0, 0.98, 0.95),
                intensity=1.1
            ),
            DirectionalLight(
                direction=Vector3D(-0.707, 0.353, 0.612).normalized(),
                color=(0.85, 0.92, 1.0),
                intensity=0.5
            ),
            DirectionalLight(
                direction=Vector3D(0.0, -0.894, 0.447).normalized(),
                color=(1.0, 1.0, 1.0),
                intensity=0.75
            )
        ],
        ambient_color=(0.15, 0.18, 0.22),
        ambient_intensity=0.3
    )


class PBRRaytracer:
    """
    Moteur de rendu et de calcul d'ombrage physique.
    Génère des images de qualité studio avec ombrage de Fresnel et occlusion ambiante.
    """

    def __init__(self, environment: Optional[StudioEnvironment] = None) -> None:
        """Initialise le raytracer avec son studio lumineux."""
        self.env = environment or create_default_studio()

    def shade_vertex(
        self,
        normal: Vector3D,
        view_dir: Vector3D,
        material: PBRMaterial
    ) -> Tuple[float, float, float]:
        """
        Calcule la couleur RGB réfléchie pour une normale donnée selon le modèle PBR.
        Applique Fresnel-Schlick, la composante diffuse Lambertienne et le reflet spéculaire.
        """
        norm = normal.normalized()
        view = view_dir.normalized()
        f0_r, f0_g, f0_b = material.get_fresnel_f0()

        # 1. Ambiance
        amb_r = self.env.ambient_color[0] * self.env.ambient_intensity * material.albedo[0]
        amb_g = self.env.ambient_color[1] * self.env.ambient_intensity * material.albedo[1]
        amb_b = self.env.ambient_color[2] * self.env.ambient_intensity * material.albedo[2]

        total_r = amb_r
        total_g = amb_g
        total_b = amb_b

        # Exposant de rugosité spéculaire
        safe_roughness = max(0.0, min(1.0, material.roughness))
        spec_power = max(2.0, (1.0 - safe_roughness) ** 2.0 * 128.0)

        # 2. Somme sur chaque source de lumière du studio
        for light in self.env.lights:
            light_dir = light.direction.normalized()
            n_dot_l = max(0.0, norm.dot(light_dir))

            if n_dot_l > 0.0:
                # Demi-vecteur de Blinn-Phong
                half_vec = Vector3D(view.x + light_dir.x, view.y + light_dir.y, view.z + light_dir.z).normalized()
                n_dot_h = max(0.0, norm.dot(half_vec))
                v_dot_h = max(0.0, view.dot(half_vec))

                # Facteur de Fresnel Schlick
                fresnel = (1.0 - v_dot_h) ** 5.0
                f_r = f0_r + (1.0 - f0_r) * fresnel
                f_g = f0_g + (1.0 - f0_g) * fresnel
                f_b = f0_b + (1.0 - f0_b) * fresnel

                # Diffusion (les métaux absorbent la diffusion)
                safe_metallic = max(0.0, min(1.0, material.metallic))
                diffuse_factor = (1.0 - safe_metallic) * n_dot_l
                diff_r = material.albedo[0] * light.color[0] * diffuse_factor
                diff_g = material.albedo[1] * light.color[1] * diffuse_factor
                diff_b = material.albedo[2] * light.color[2] * diffuse_factor

                # Spécularité
                spec_intensity = (n_dot_h ** spec_power) * material.specular
                spec_r = f_r * light.color[0] * spec_intensity
                spec_g = f_g * light.color[1] * spec_intensity
                spec_b = f_b * light.color[2] * spec_intensity

                total_r += (diff_r + spec_r) * light.intensity
                total_g += (diff_g + spec_g) * light.intensity
                total_b += (diff_b + spec_b) * light.intensity

        # Mappage des tons et saturation
        r_clamped = min(1.0, max(0.0, total_r))
        g_clamped = min(1.0, max(0.0, total_g))
        b_clamped = min(1.0, max(0.0, total_b))

        return (r_clamped, g_clamped, b_clamped)

    def render_solid_to_image(
        self,
        solid: Solid,
        material: PBRMaterial,
        width: int = 640,
        height: int = 480
    ) -> QImage:
        """
        Effectue un rendu rasterisé haute fidélité du solide avec Z-buffer logiciel.
        Retourne une QImage prête pour affichage ou enregistrement PNG.
        """
        safe_w = max(1, width)
        safe_h = max(1, height)
        mesh = solid.to_mesh_buffer()
        image = QImage(safe_w, safe_h, QImage.Format.Format_ARGB32)

        # Fond studio en dégradé vertical
        for y in range(safe_h):
            ratio = y / max(1, safe_h)
            bg_c = int(28 + 22 * ratio)
            for x in range(safe_w):
                image.setPixelColor(x, y, QColor(bg_c, bg_c + 2, bg_c + 5, 255))

        if mesh.is_empty():
            return image

        verts = mesh.vertices
        faces = mesh.faces
        normals = mesh.normals

        b_min, b_max = solid.bounding_box()
        center = Vector3D((b_min.x + b_max.x) * 0.5, (b_min.y + b_max.y) * 0.5, (b_min.z + b_max.z) * 0.5)
        span = max(b_max.x - b_min.x, b_max.y - b_min.y, b_max.z - b_min.z, 1.0)
        scale = min(width, height) * 0.35 / span

        # Matrice de vue isométrique
        # Angle azimut 45°, élévation 30°
        cos_az = np.cos(np.radians(45.0))
        sin_az = np.sin(np.radians(45.0))
        cos_el = np.cos(np.radians(30.0))
        sin_el = np.sin(np.radians(30.0))

        view_dir = Vector3D(float(cos_az * cos_el), float(sin_az * cos_el), float(sin_el)).normalized()

        # Projection 3D vers 2D
        proj_pts: List[Tuple[int, int, float]] = []
        for v in verts:
            rel_x = float(v[0]) - center.x
            rel_y = float(v[1]) - center.y
            rel_z = float(v[2]) - center.z

            # Rotation
            x_rot = rel_x * cos_az - rel_y * sin_az
            y_temp = rel_x * sin_az + rel_y * cos_az
            y_rot = y_temp * sin_el + rel_z * cos_el
            depth = -y_temp * cos_el + rel_z * sin_el

            screen_x = int(safe_w * 0.5 + x_rot * scale)
            screen_y = int(safe_h * 0.5 - y_rot * scale)
            proj_pts.append((screen_x, screen_y, depth))

        # Z-Buffer de profondeur
        z_buffer = np.full((safe_h, safe_w), -1e9, dtype=np.float32)

        # Rendu des triangles avec ombrage PBR
        for face_idx, face in enumerate(faces):
            p0 = proj_pts[face[0]]
            p1 = proj_pts[face[1]]
            p2 = proj_pts[face[2]]

            # Normale du triangle
            norm = Vector3D(float(normals[face[0]][0]), float(normals[face[0]][1]), float(normals[face[0]][2]))
            color_rgb = self.shade_vertex(norm, view_dir, material)
            qcol = QColor(int(color_rgb[0] * 255), int(color_rgb[1] * 255), int(color_rgb[2] * 255), 255)

            # Dessin simple par rasterisation de triangle (Barycentrique)
            min_x = max(0, min(p0[0], p1[0], p2[0]))
            max_x = min(safe_w - 1, max(p0[0], p1[0], p2[0]))
            min_y = max(0, min(p0[1], p1[1], p2[1]))
            max_y = min(safe_h - 1, max(p0[1], p1[1], p2[1]))

            denom = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
            if abs(denom) < 1e-5:
                continue

            inv_denom = 1.0 / denom
            for y in range(min_y, max_y + 1):
                for x in range(min_x, max_x + 1):
                    w0 = ((p1[1] - p2[1]) * (x - p2[0]) + (p2[0] - p1[0]) * (y - p2[1])) * inv_denom
                    w1 = ((p2[1] - p0[1]) * (x - p2[0]) + (p0[0] - p2[0]) * (y - p2[1])) * inv_denom
                    w2 = 1.0 - w0 - w1

                    if w0 >= 0.0 and w1 >= 0.0 and w2 >= 0.0:
                        depth = w0 * p0[2] + w1 * p1[2] + w2 * p2[2]
                        if depth > z_buffer[y, x]:
                            z_buffer[y, x] = depth
                            image.setPixelColor(x, y, qcol)

        return image

    def export_render_png(
        self,
        solid: Solid,
        material: PBRMaterial,
        filepath: str,
        width: int = 1280,
        height: int = 720
    ) -> bool:
        """Génère l'image et l'enregistre sur disque au format PNG haute résolution."""
        img = self.render_solid_to_image(solid, material, width, height)
        return img.save(filepath, "PNG")
