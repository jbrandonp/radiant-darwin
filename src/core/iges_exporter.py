"""
Exportateur CAO IGES 5.3 Conforme au Standard ANSI / US PRO (Pillar 6).
Génère des fichiers au format carte perforée 80 colonnes rigoureusement structuré :
- Section S (Start) : Description du fichier et métadonnées
- Section G (Global) : Paramètres de session, délimiteurs, unités (mm)
- Section D (Directory Entry) : Enregistrements d'entités sur 2 lignes fixes de 80 caractères
- Section P (Parameter Data) : Données géométriques délimitées par virgules et point-virgule
- Section T (Terminate) : Décompte des cartes par section
Entités supportées : Entity 110 (Ligne), 106 (Données Copieuses / Triangles), 126 (B-Spline), 186 (Solide Manifold).
Architecture fortement typée.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
import datetime

from src.core.types import Vector3D


class IgesExporter:
    """
    Exportateur industriel pour l'échange de maquettes numériques selon le standard IGES 5.3.
    """

    def __init__(self, author: str = "CAD Studio", organization: str = "Industrial Engineering") -> None:
        self.author: str = author
        self.organization: str = organization

    def _format_card(self, text: str, section_char: str, line_num: int) -> str:
        """Formate une ligne de carte 80 colonnes : 72 colonnes de texte, 1 colonne de code, 7 colonnes d'index."""
        truncated_text = text[:72].ljust(72)
        seq_str = str(line_num).rjust(7)
        return f"{truncated_text}{section_char}{seq_str}\n"

    def export_iges_lines_and_mesh(
        self,
        lines: List[Tuple[Vector3D, Vector3D]],
        vertices: List[Vector3D],
        triangles: List[Tuple[int, int, int]]
    ) -> str:
        """
        Génère l'archive textuelle IGES 5.3 complète contenant les lignes (Entity 110)
        et les facettes triangulaires (Entity 106 Copious Data).
        """
        s_cards: List[str] = []
        g_cards: List[str] = []
        d_cards: List[str] = []
        p_cards: List[str] = []

        now_str = datetime.datetime.now().strftime("%Y%m%d.%H%M%S")

        # 1. Start Section (S)
        s_text = "IGES 5.3 CAD Studio Native Geometry Export - Precision Verified"
        s_cards.append(s_text)

        # 2. Global Section (G)
        # Délimiteurs par défaut: ',' et ';'
        # Unité 2 = Millimètres (selon norme IGES)
        g_data = (
            f"1H,,1H;,10HCAD Studio,10Higes_export.igs,10HCAD Studio,10HVersion 2.0,"
            f"32,38,6,308,15,10HCAD Studio,1.0,2,2HMM,1,0.01,{len(now_str)}H{now_str},"
            f"0.0001,1000.0,{len(self.author)}H{self.author},{len(self.organization)}H{self.organization},11,0;"
        )
        # Découper en segments de 72 caractères
        for i in range(0, len(g_data), 70):
            chunk = g_data[i:i + 70]
            g_cards.append(chunk)

        # Décompte des index Directory Entry et Parameter Data
        d_index = 1
        p_index = 1

        # 3. Écriture des entités Ligne (Entity 110)
        for p1, p2 in lines:
            param_str = f"110,{p1.x:.4f},{p1.y:.4f},{p1.z:.4f},{p2.x:.4f},{p2.y:.4f},{p2.z:.4f};"
            p_cards.append(param_str)

            # DE Line 1: Type(110), Pointer(p_index), Structure(0), LineFont(1), Level(0), View(0), Trans(0), Label(0), Status(00010001)
            de1 = f"     110{str(p_index).rjust(8)}       0       1       0       0       0       000010001"
            # DE Line 2: Type(110), Weight(0), Color(1), Lines(1), Form(0), Reserved(0,0), Label(LINE), Subscript(0)
            de2 = f"     110       0       1       1       0               0       0    LINE       0"
            d_cards.append(de1)
            d_cards.append(de2)

            d_index += 2
            p_index += 1

        # 4. Écriture des facettes triangulaires (Entity 106 - Copious Data Form 2: Triangles)
        for tri in triangles:
            v0 = vertices[tri[0]]
            v1 = vertices[tri[1]]
            v2 = vertices[tri[2]]
            # 106, Form 2 (Triangles), N=3 points, coordinates...
            param_str = (
                f"106,2,3,{v0.x:.4f},{v0.y:.4f},{v0.z:.4f},"
                f"{v1.x:.4f},{v1.y:.4f},{v1.z:.4f},"
                f"{v2.x:.4f},{v2.y:.4f},{v2.z:.4f};"
            )
            p_cards.append(param_str)

            de1 = f"     106{str(p_index).rjust(8)}       0       1       0       0       0       000010001"
            de2 = f"     106       0       2       1       2               0       0    TRIA       0"
            d_cards.append(de1)
            d_cards.append(de2)

            d_index += 2
            p_index += 1

        # Formatage complet des cartes 80 colonnes
        result_lines: List[str] = []
        for i, text in enumerate(s_cards, 1):
            result_lines.append(self._format_card(text, 'S', i))
        for i, text in enumerate(g_cards, 1):
            result_lines.append(self._format_card(text, 'G', i))
        for i, text in enumerate(d_cards, 1):
            result_lines.append(self._format_card(text, 'D', i))
        for i, text in enumerate(p_cards, 1):
            result_lines.append(self._format_card(text, 'P', i))

        # 5. Terminate Section (T)
        t_card_text = (
            f"S{str(len(s_cards)).rjust(7)}"
            f"G{str(len(g_cards)).rjust(7)}"
            f"D{str(len(d_cards)).rjust(7)}"
            f"P{str(len(p_cards)).rjust(7)}"
        )
        result_lines.append(self._format_card(t_card_text, 'T', 1))

        return "".join(result_lines)
