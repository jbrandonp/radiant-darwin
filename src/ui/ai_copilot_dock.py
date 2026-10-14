"""
Panneau d'interaction Copilote IA intégré (AI Copilot Dock Widget SOTA).
Inspiré des interfaces Zoo KCL, CadQuery et ToolCAD.
Combine dialogue en langage naturel, bac à sable Code-as-CAD (Python) et diagnostic topologique fermé.
Architecture fortement typée : strictement zéro Any et zéro object.
"""

from __future__ import annotations
from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QPushButton, QLabel, QFrame, QScrollArea, QTabWidget
)
from PySide6.QtCore import Qt, Signal

from src.core.document import CADDocument
from src.ai.cad_ai_bridge import CADAIBridge, CADAIExecutionResult, AICommandType
from src.ai.cad_validator import CADValidator
from src.ai.cad_script_engine import CADScriptEngine, ScriptExecutionResult


class AICopilotWidget(QWidget):
    """Widget d'orchestration IA multimodal (Prompt naturel + Script Python Code-as-CAD)."""

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
        """Construit l'interface du panneau copilote avec onglets Prompt et Script."""
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(6)

        # 1. En-tête avec statut
        header_row = QHBoxLayout()
        title_lbl = QLabel("🤖 COPILOTE IA CAO SOTA")
        title_lbl.setStyleSheet("color: #00a2ff; font-weight: bold; font-size: 11px; letter-spacing: 1px;")
        header_row.addWidget(title_lbl)

        status_badge = QLabel("MCP & Python Prêts")
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
        self._append_system_message("Copilote IA connecté (Mode Prompt naturel & Code-as-CAD actif). Prêt pour vos ordres géométriques.")
        vbox.addWidget(self.transcript_area, 1)

        # 3. Onglets de saisie : Mode Prompt vs Mode Script Python
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #2e323b; border-radius: 4px; background: #202229; }
            QTabBar::tab { background: #1a1b20; color: #8c93a3; padding: 4px 10px; font-size: 10px; font-weight: bold; }
            QTabBar::tab:selected { background: #202229; color: #00a2ff; border-top: 2px solid #00a2ff; }
        """)

        # Onglet A : Langage naturel
        tab_prompt = QWidget()
        t_layout = QVBoxLayout(tab_prompt)
        t_layout.setContentsMargins(4, 4, 4, 4)
        t_layout.setSpacing(4)

        # Suggestions rapides (chips)
        chips_row_1 = QHBoxLayout()
        chips_row_1.setSpacing(3)
        self._add_chip_button(chips_row_1, "⚙️ Engrenage Z24", "Crée un engrenage de 24 dents module 2 avec alésage 12")
        self._add_chip_button(chips_row_1, "📦 Boîtier 100x70", "Crée un boîtier électronique 100x70x35 épaisseur 2.5")
        self._add_chip_button(chips_row_1, "🔘 Bride DN50", "Bride de tuyauterie diamètre 120 4 trous")
        t_layout.addLayout(chips_row_1)

        chips_row_2 = QHBoxLayout()
        chips_row_2.setSpacing(3)
        self._add_chip_button(chips_row_2, "📐 Équerre M6", "Support équerre renforcé 60x50")
        self._add_chip_button(chips_row_2, "⚙️ Palier Ø25", "Palier à semelle pour arbre Ø25")
        self._add_chip_button(chips_row_2, "🔄 Poulie Ø100", "Poulie à gorge diamètre 100")
        t_layout.addLayout(chips_row_2)

        input_row = QHBoxLayout()
        input_row.setSpacing(4)
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ex: Crée un engrenage de 30 dents module 2.5...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #242730; color: #ffffff;
                border: 1px solid #363b47; border-radius: 4px;
                padding: 5px 8px; font-size: 11px;
            }
            QLineEdit:focus { border-color: #00a2ff; }
        """)
        self.input_field.returnPressed.connect(self._on_submit_prompt)
        input_row.addWidget(self.input_field, 1)

        self.btn_send = QPushButton("⚡ Générer")
        self.btn_send.setStyleSheet("""
            QPushButton {
                background-color: #007acc; color: #ffffff;
                border: 1px solid #0098ff; border-radius: 4px;
                padding: 5px 10px; font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background-color: #008be5; }
        """)
        self.btn_send.clicked.connect(self._on_submit_prompt)
        input_row.addWidget(self.btn_send)
        t_layout.addLayout(input_row)

        self.tabs.addTab(tab_prompt, "💬 Langage Naturel")

        # Onglet B : Code-as-CAD Python (Zoo KCL style)
        tab_script = QWidget()
        s_layout = QVBoxLayout(tab_script)
        s_layout.setContentsMargins(4, 4, 4, 4)
        s_layout.setSpacing(4)

        self.script_edit = QTextEdit()
        self.script_edit.setStyleSheet("""
            QTextEdit {
                background-color: #17181c; color: #38bdf8;
                border: 1px solid #2e323b; border-radius: 4px;
                font-family: 'Consolas', 'Courier New', monospace; font-size: 10px;
            }
        """)
        self.script_edit.setPlainText(
            "# Script Code-as-CAD (Objet contextuel 'cad')\n"
            "b = cad.box(50.0, 50.0, 15.0)\n"
            "c = cad.cylinder(10.0, 30.0)\n"
            "piece = b.difference(c)\n"
            "cad.add(piece, 'Plaque_Percee')\n"
        )
        s_layout.addWidget(self.script_edit, 1)

        btn_run_script = QPushButton("▶ Exécuter Script Python")
        btn_run_script.setStyleSheet("""
            QPushButton {
                background-color: #15803d; color: #ffffff;
                border: 1px solid #22c55e; border-radius: 4px;
                padding: 5px 10px; font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background-color: #16a34a; }
        """)
        btn_run_script.clicked.connect(self._on_run_python_script)
        s_layout.addWidget(btn_run_script)

        self.tabs.addTab(tab_script, "🐍 Code-as-CAD")
        vbox.addWidget(self.tabs)

        # 4. Barre d'outils diagnostic et maintenance
        diag_row = QHBoxLayout()
        diag_row.setSpacing(4)

        btn_diag = QPushButton("🔍 Diagnostic Topologique & Clashes")
        btn_diag.setStyleSheet("background-color: #23262e; color: #38bdf8; border: 1px solid #323642; border-radius: 3px; font-size: 10px; padding: 4px;")
        btn_diag.clicked.connect(self._on_run_diagnostics)
        diag_row.addWidget(btn_diag, 1)

        btn_clear = QPushButton("🧹 Nettoyer")
        btn_clear.setStyleSheet("background-color: #23262e; color: #ef4444; border: 1px solid #323642; border-radius: 3px; font-size: 10px; padding: 4px;")
        btn_clear.clicked.connect(lambda: self._execute_prompt_text("Efface tout"))
        diag_row.addWidget(btn_clear)

        vbox.addLayout(diag_row)

    def _add_chip_button(self, layout: QHBoxLayout, label: str, prompt_text: str) -> None:
        """Ajoute un bouton de suggestion rapide."""
        btn = QPushButton(label)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #23262e; color: #a0a6b5;
                border: 1px solid #323642; border-radius: 3px;
                padding: 2px 5px; font-size: 9px;
            }
            QPushButton:hover { background-color: #2d313b; color: #ffffff; border-color: #00a2ff; }
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
        result = self.bridge.execute_natural_language_prompt(prompt)

        if result.success:
            self.transcript_area.append(f"<span style='color: #22c55e;'><b>✅ Succès:</b> {result.message}</span><br>")
        else:
            self.transcript_area.append(f"<span style='color: #ef4444;'><b>⚠️ Erreur:</b> {result.message}</span><br>")

        self.geometry_generated.emit(result)

    def _on_run_python_script(self) -> None:
        """Exécute le code saisi dans l'onglet Code-as-CAD."""
        code = self.script_edit.toPlainText().strip()
        if not code:
            return

        self._append_user_message("<i>[Exécution Script Code-as-CAD]</i>")
        res: ScriptExecutionResult = CADScriptEngine.execute_script(self.doc, code)

        if res.success:
            self.transcript_area.append(f"<span style='color: #22c55e;'><b>✅ Code Exécuté:</b> {res.message}</span><br>")
            dummy_result = CADAIExecutionResult(
                success=True,
                message=res.message,
                command_executed="execute_script",
                command_type=AICommandType.SYNTHESIZE_SHAPE
            )
            self.geometry_generated.emit(dummy_result)
        else:
            self.transcript_area.append(f"<span style='color: #ef4444;'><b>⚠️ Erreur Script:</b> {res.message}</span><br>")

    def _on_run_diagnostics(self) -> None:
        """Lance l'inspection géométrique, le test de variété et la détection d'interférences."""
        if not self.doc.bodies:
            self._append_system_message("La scène est vide, aucun corps à diagnostiquer.")
            return

        lines: List[str] = [f"<b>Rapport d'audit de la scène ({len(self.doc.bodies)} corps) :</b>"]
        for bid, solid in self.doc.bodies.items():
            rep = CADValidator.validate_solid(solid)
            status_txt = "✅ Étanche 2-Manifold" if rep.is_manifold else "❌ Non-Manifold"
            lines.append(f" - <b>{bid}</b>: {status_txt} | Vol: {rep.volume_mm3:.1f} mm³ | Euler χ={rep.euler_characteristic} | Score: {rep.quality_score_percent:.0f}%")
            if rep.warnings:
                lines.append(f"   <span style='color: #f59e0b;'>⚠️ {'; '.join(rep.warnings)}</span>")

        # Vérification des collisions
        clashes = CADValidator.check_scene_interferences(self.doc.bodies)
        if clashes:
            lines.append(f"<span style='color: #ef4444;'><b>⚠️ {len(clashes)} collision(s) détectée(s) :</b></span>")
            for c in clashes:
                lines.append(f"   - {c.description}")
        else:
            lines.append("<span style='color: #22c55e;'>✅ Aucun clash volumique détecté.</span>")

        self.transcript_area.append("<br>".join(lines) + "<br>")
