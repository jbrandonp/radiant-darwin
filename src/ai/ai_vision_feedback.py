"""
Moteur de retour visuel multimodal pour les agents IA (Vision-in-the-Loop Feedback).
Permet de capturer et d'encoder en Base64 PNG le rendu 3D du modèle actif afin
que les modèles de langage multimodaux (Claude 3.5 Sonnet, GPT-4o, Gemini 1.5 Pro)
puissent analyser visuellement les formes, congés et proportions de la pièce conçue.
Architecture 100% fortement typée sans Any ni object.
"""

from __future__ import annotations
import base64
import io
import math
from dataclasses import dataclass
from typing import Optional, List, Tuple
import numpy as np

from PySide6.QtGui import QImage, QPainter, QColor, QPen, QBrush, QGuiApplication
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF


from src.core.types import Vector3D, MeshBuffer
from src.core.document import CADDocument


@dataclass
class VisionFeedbackResult:
    """Résultat de la capture visuelle destiné à la consommation par un LLM multimodal."""
    has_image: bool
    base64_png: str
    data_uri: str
    width: int
    height: int
    bounding_diag_mm: float
    description: str


class AIVisionFeedback:
    """Générateur d'instantanés 3D haute fidélité pour vision artificielle d'IA."""

    @staticmethod
    def capture_document_view(
        document: CADDocument,
        width: int = 512,
        height: int = 512,
        yaw_deg: float = 35.0,
        pitch_deg: float = 30.0
    ) -> VisionFeedbackResult:
        """
        Génère un rendu visuel hors-écran déterministe sous forme d'image PNG encodée en Base64.
        Fonctionne avec ou sans contexte GPU matériel (idéal pour serveurs headless ou tests).
        """
        buffers = document.get_all_mesh_buffers()
        if not buffers:
            return AIVisionFeedback._generate_empty_snapshot(width, height)

        # Calculer la boîte englobante globale
        min_pt, max_pt = AIVisionFeedback._compute_global_bounds(document)
        diag = float(math.sqrt((max_pt.x - min_pt.x)**2 + (max_pt.y - min_pt.y)**2 + (max_pt.z - min_pt.z)**2))
        center = Vector3D(
            float(0.5 * (min_pt.x + max_pt.x)),
            float(0.5 * (min_pt.y + max_pt.y)),
            float(0.5 * (min_pt.z + max_pt.z))
        )

        # Dessiner le rendu projeté sur une QImage
        img = QImage(width, height, QImage.Format.Format_ARGB32)
        img.fill(QColor(32, 35, 42))  # Fond studio sombre CAD

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Matrice de projection isométrique
        rad_yaw = math.radians(yaw_deg)
        rad_pitch = math.radians(pitch_deg)
        cos_y, sin_y = math.cos(rad_yaw), math.sin(rad_yaw)
        cos_p, sin_p = math.cos(rad_pitch), math.sin(rad_pitch)

        scale = float(min(width, height) * 0.40 / max(1.0, diag * 0.6))
        half_w, half_h = width / 2.0, height / 2.0

        for buf in buffers:
            if buf.is_empty():
                continue
            AIVisionFeedback._render_buffer_onto_painter(
                buf, painter, center, scale, half_w, half_h,
                cos_y, sin_y, cos_p, sin_p
            )

        # Cadre et libellé d'inspection pour l'IA
        pen_border = QPen(QColor(0, 162, 255, 120), 1.5)
        painter.setPen(pen_border)
        painter.drawRect(2, 2, width - 4, height - 4)

        if QGuiApplication.instance() is not None:
            pen_txt = QPen(QColor(220, 225, 235))
            painter.setPen(pen_txt)
            painter.drawText(12, 24, f"CAD Studio Vision : {document.name} (Diag: {diag:.1f} mm)")

        painter.end()


        # Encodage en Base64 PNG
        b64_str = AIVisionFeedback._qimage_to_base64_png(img)
        data_uri = f"data:image/png;base64,{b64_str}"

        return VisionFeedbackResult(
            has_image=True,
            base64_png=b64_str,
            data_uri=data_uri,
            width=width,
            height=height,
            bounding_diag_mm=diag,
            description=f"Instantané 3D isométrique de '{document.name}' ({len(buffers)} corps, diag: {diag:.1f}mm)."
        )

    @staticmethod
    def _compute_global_bounds(document: CADDocument) -> Tuple[Vector3D, Vector3D]:
        """Calcule les bornes minimales et maximales de la scène entière."""
        min_x, min_y, min_z = 1e9, 1e9, 1e9
        max_x, max_y, max_z = -1e9, -1e9, -1e9

        for body in document.bodies.values():
            if body.is_empty():
                continue
            b_min, b_max = body.bounding_box()
            min_x = min(min_x, b_min.x)
            min_y = min(min_y, b_min.y)
            min_z = min(min_z, b_min.z)
            max_x = max(max_x, b_max.x)
            max_y = max(max_y, b_max.y)
            max_z = max(max_z, b_max.z)

        if min_x > 1e8:
            return Vector3D(-20.0, -20.0, -20.0), Vector3D(20.0, 20.0, 20.0)

        return Vector3D(min_x, min_y, min_z), Vector3D(max_x, max_y, max_z)

    @staticmethod
    def _render_buffer_onto_painter(
        buf: MeshBuffer,
        painter: QPainter,
        center: Vector3D,
        scale: float,
        half_w: float,
        half_h: float,
        cos_y: float,
        sin_y: float,
        cos_p: float,
        sin_p: float
    ) -> None:
        """Projette et dessine les faces et contours d'un maillage 3D sur le canvas QPainter."""
        pen_edge = QPen(QColor(15, 18, 24, 200), 1.0)
        c = buf.color
        brush_face = QBrush(QColor(int(c.r * 255), int(c.g * 255), int(c.b * 255), 235))

        painter.setPen(pen_edge)
        painter.setBrush(brush_face)

        verts = buf.vertices
        faces = buf.faces

        # Projection 3D -> 2D
        proj_pts: List[QPointF] = []
        for v in verts:
            # Centrage relatif
            rx = float(v[0] - center.x)
            ry = float(v[1] - center.y)
            rz = float(v[2] - center.z)

            # Rotation Yaw (axe Z)
            x1 = rx * cos_y - ry * sin_y
            y1 = rx * sin_y + ry * cos_y
            z1 = rz

            # Rotation Pitch (axe X)
            x2 = x1
            y2 = y1 * cos_p - z1 * sin_p

            screen_x = half_w + x2 * scale
            screen_y = half_h - y2 * scale
            proj_pts.append(QPointF(screen_x, screen_y))

        # Dessin des triangles
        max_draw_faces = min(2000, len(faces))
        for i in range(max_draw_faces):
            f = faces[i]
            p0, p1, p2 = proj_pts[f[0]], proj_pts[f[1]], proj_pts[f[2]]
            painter.drawPolygon([p0, p1, p2])

    @staticmethod
    def _qimage_to_base64_png(img: QImage) -> str:
        """Convertit un QImage en chaîne Base64 PNG standard."""
        byte_arr = QByteArray()
        buffer = QBuffer(byte_arr)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buffer, "PNG")
        raw_bytes = bytes(byte_arr.data())
        return base64.b64encode(raw_bytes).decode("ascii")

    @staticmethod
    def _generate_empty_snapshot(width: int, height: int) -> VisionFeedbackResult:
        """Génère un retour visuel pour scène vide."""
        img = QImage(width, height, QImage.Format.Format_ARGB32)
        img.fill(QColor(24, 26, 32))
        painter = QPainter(img)
        if QGuiApplication.instance() is not None:
            painter.setPen(QPen(QColor(120, 128, 145)))
            painter.drawText(width // 4, height // 2, "Scène CAO Vide (Aucun solide)")
        painter.end()


        b64 = AIVisionFeedback._qimage_to_base64_png(img)
        return VisionFeedbackResult(
            has_image=False,
            base64_png=b64,
            data_uri=f"data:image/png;base64,{b64}",
            width=width,
            height=height,
            bounding_diag_mm=0.0,
            description="Scène CAO vide."
        )
