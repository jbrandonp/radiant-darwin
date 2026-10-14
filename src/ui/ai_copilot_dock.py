"""
Panneau d'interaction Copilote IA intégré (AI Copilot Dock Widget).
Permet à l'ingénieur de piloter CAD Studio en langage naturel direct depuis l'interface Qt.
Génère n'importe quelle pièce ou modification géométrique avec retour visuel immédiat dans le viewport.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QPushButton, QLabel, QFrame, QScrollArea
)
from PySide6.QtCore import Qt, Signal

from src.core.document import CADDocument
from src.ai.cad_ai_bridge import CADAIBridge, CADAIExecutionResult


class AICopilotWidget(QWidget):
    """Widget de chat interactif avec l'IA pour la génération CAO directe."""

    # Signal émis à chaque fois qu'une action IA a modifié la géométrie
    geometry_generated = Signal(CADAIExecutionResult)

    def __init__(self, document: CADDocument, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc: CADDocument = document
        self.bridge: CADAIBridge = CADAIBridge(document)

        self._init_ui()

    def set_document(self, document: CADDocument) -> None:
        """Met à jour la référence au document lors du rechargement d'un projet."""
        self.doc = document
        self.bridge.doc = document

    def _init_ui(self) -> None:
        """Construit l'interface du panneau copilote."""
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(6)

        # 1. En-tête avec statut
        header_row = QHBoxLayout()
        title_lbl = QLabel("🤖 COPILOTE IA CAO")
        title_lbl.setStyleSheet("color: #00a2ff; font-weight: bold; font-size: 11px; letter-spacing: 1px;")
        header_row.addWidget(title_lbl)

        status_badge = QLabel("Actif (NEXUS-3D)")
        status_badge.setStyleSheet("background-color: #1e3a2f; color: #4ade80; border: 1px solid #2e5a42; border-radius: 3px; padding: 1px 4px; font-size: 9px; font-weight: bold;")
        header_row.addWidget(status_badge, 0, Qt.AlignmentFlag.AlignRight)
        vbox.addLayout(header_row)

        # 2. Zone de transcription du dialogue
        self.transcript_area = QTextEdit()
        self.transcript_area.setReadOnly(True)
        self.transcript_area.setStyleSheet("""
            QTextEdit {
                background-color: #1a1b20;
                color: #d1d5db;
                border: 1px solid #2e323b;
                border-radius: 4px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                padding: 6px;
            }
        """)
        self._append_system_message("Bienvenue dans le Copilote IA CAD Studio. Décrivez la pièce ou la modification souhaitée en langage naturel.")
        vbox.addWidget(self.transcript_area, 1)

        # 3. Raccourcis rapides de génération (Prompt Chips)
        chips_lbl = QLabel("Suggestions instantanées :")
        chips_lbl.setStyleSheet("color: #7b8190; font-size: 9px; font-weight: bold;")
        vbox.addWidget(chips_lbl)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(4)
        self._add_chip_button(chips_row, "⚙️ Engrenage Z24", "Crée un engrenage de 24 dents module 2 avec alésage de 12 mm")
        self._add_chip_button(chips_row, "📦 Boîtier 100x70", "Crée un boîtier électronique de 100x70x35 mm épaisseur 2.5 mm")
        self._add_chip_button(chips_row, "🔘 Bride DN50", "Crée une bride circulaire de 120 mm alésage 50 avec 4 trous de 12 mm")
        vbox.addLayout(chips_row)

        chips_row_2 = QHBoxLayout()
        chips_row_2.setSpacing(4)
        self._add_chip_button(chips_row_2, "📐 Équerre M6", "Crée une équerre renforcée de 60x50 mm avec nervure et trous M6")
        self._add_chip_button(chips_row_2, "❄️ Dissipateur", "Crée un dissipateur thermique de 80x60 mm avec 10 ailettes")
        self._add_chip_button(chips_row_2, "🧹 Nettoyer", "Efface tout")
        vbox.addLayout(chips_row_2)

        # 4. Ligne de saisie de consigne
        input_row = QHBoxLayout()
        input_row.setSpacing(4)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ex: Crée un engrenage de 30 dents module 2.5...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #242730;
                color: #ffffff;
                border: 1px solid #363b47;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #00a2ff;
            }
        """)
        self.input_field.returnPressed.connect(self._on_submit_prompt)
        input_row.addWidget(self.input_field, 1)

        self.btn_send = QPushButton("⚡ Générer")
        self.btn_send.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: #ffffff;
                border: 1px solid #0098ff;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #008be5;
            }
            QPushButton:pressed {
                background-color: #005f9e;
            }
        """)
        self.btn_send.clicked.connect(self._on_submit_prompt)
        input_row.addWidget(self.btn_send)

        vbox.addLayout(input_row)

    def _add_chip_button(self, layout: QHBoxLayout, label: str, prompt_text: str) -> None:
        """Ajoute un bouton de suggestion rapide."""
        btn = QPushButton(label)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #23262e;
                color: #a0a6b5;
                border: 1px solid #323642;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 9px;
            }
            QPushButton:hover {
                background-color: #2d313b;
                color: #ffffff;
                border-color: #00a2ff;
            }
        """)
        btn.clicked.connect(lambda: self._execute_prompt_text(prompt_text))
        layout.addWidget(btn)

    def _append_system_message(self, text: str) -> None:
        """Affiche un message d'information système dans le chat."""
        self.transcript_area.append(f"<span style='color: #4ade80;'><b>🤖 Assistant IA:</b> {text}</span><br>")

    def _append_user_message(self, text: str) -> None:
        """Affiche le prompt utilisateur."""
        self.transcript_area.append(f"<span style='color: #60a5fa;'><b>👤 Vous:</b> {text}</span>")

    def _on_submit_prompt(self) -> None:
        """Traite le prompt saisi dans le champ texte."""
        txt = self.input_field.text().strip()
        if not txt:
            return
        self.input_field.clear()
        self._execute_prompt_text(txt)

    def _execute_prompt_text(self, prompt: str) -> None:
        """Exécute la requête via le pont IA et propage le signal de rafraîchissement."""
        self._append_user_message(prompt)

        # Exécution directe par le moteur IA
        result = self.bridge.execute_natural_language_prompt(prompt)

        if result.success:
            self.transcript_area.append(f"<span style='color: #22c55e;'><b>✅ Succès:</b> {result.message}</span><br>")
        else:
            self.transcript_area.append(f"<span style='color: #ef4444;'><b>⚠️ Erreur:</b> {result.message}</span><br>")

        # Émission du signal pour mise à jour du viewport et des arbres
        self.geometry_generated.emit(result)
