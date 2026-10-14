"""
Palette de commande IA rapide flottante (AI Command Palette HUD) déclenchée par Ctrl+K.
Inspirée de Raycast, Spotlight et du menu F3 de Blender : permet à l'utilisateur
de piloter le logiciel et de générer des pièces en langage naturel instantanément.
Architecture 100% fortement typée sans Any ni object.
"""

from __future__ import annotations
from typing import Optional, List, Callable
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
    QPushButton, QFrame, QScrollArea, QWidget, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent

from src.core.document import CADDocument
from src.ai.cad_ai_bridge import CADAIBridge, CADAIExecutionResult


class AICommandPalette(QDialog):
    """HUD flottant de commande rapide par IA superposé au viewport."""

    action_completed = Signal(str)

    def __init__(self, bridge: CADAIBridge, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.bridge: CADAIBridge = bridge
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(640)

        # Conteneur principal avec ombre portée et bordure néon
        container = QFrame(self)
        container.setObjectName("paletteContainer")
        container.setStyleSheet("""
            QFrame#paletteContainer {
                background-color: rgba(26, 29, 36, 245);
                border: 1.5px solid #00a2ff;
                border-radius: 10px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 8)
        container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Ligne de saisie principale
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        lbl_icon = QLabel("🤖")
        lbl_icon.setStyleSheet("font-size: 20px;")
        input_row.addWidget(lbl_icon)

        self.txt_prompt = QLineEdit()
        self.txt_prompt.setPlaceholderText("Tapez une action en français (ex: Crée un palier de 25mm avec alésage)...")
        self.txt_prompt.setStyleSheet("""
            QLineEdit {
                background-color: #16181d;
                color: #ffffff;
                border: 1px solid #333842;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: 500;
            }
            QLineEdit:focus {
                border-color: #00a2ff;
            }
        """)
        self.txt_prompt.returnPressed.connect(self._on_submit)
        input_row.addWidget(self.txt_prompt, 1)

        self.btn_run = QPushButton("Exécuter ↵")
        self.btn_run.setFixedHeight(34)
        self.btn_run.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
                padding: 0 14px;
            }
            QPushButton:hover {
                background-color: #0098ff;
            }
        """)
        self.btn_run.clicked.connect(self._on_submit)
        input_row.addWidget(self.btn_run)

        layout.addLayout(input_row)

        # Ligne des puces de suggestion (Quick suggestion chips)
        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        chips = [
            ("🔨 Usinage CAM", "Génère le parcours d'usinage et le G-Code"),
            ("⚡ Simulation FEA", "Simule la résistance sous charge de 2000N"),
            ("📐 Plan 2D", "Génère la mise en plan technique 2D ISO"),
            ("📦 Tôlerie", "Conçois une tôle pliée 100x60 épaisseur 2mm"),
            ("🪨 Inox 316L", "Applique le matériau Inox 316L"),
            ("📏 Push-Pull", "Pousse la face de 10mm"),
        ]

        chip_style = """
            QPushButton {
                background-color: #242730;
                color: #9ca3af;
                border: 1px solid #373b45;
                border-radius: 12px;
                font-size: 10px;
                font-weight: 500;
                padding: 3px 10px;
            }
            QPushButton:hover {
                background-color: #313540;
                color: #00a2ff;
                border-color: #00a2ff;
            }
        """
        for label, prompt in chips:
            btn_chip = QPushButton(label)
            btn_chip.setStyleSheet(chip_style)
            btn_chip.clicked.connect(lambda checked=False, p=prompt: self._on_chip_clicked(p))
            chips_row.addWidget(btn_chip)

        chips_row.addStretch()
        layout.addLayout(chips_row)

        # Zone de résultat / retour d'exécution
        self.lbl_feedback = QLabel("Prêt. Appuyez sur Entrée pour exécuter, Échap pour fermer.")
        self.lbl_feedback.setStyleSheet("color: #6b7280; font-size: 11px; font-style: italic; padding-top: 4px;")
        layout.addWidget(self.lbl_feedback)

        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.addWidget(container)

    def show_centered(self, parent_window: QWidget) -> None:
        """Affiche la palette centrée en haut de la fenêtre parente."""
        p_geom = parent_window.geometry()
        x = p_geom.x() + (p_geom.width() - self.width()) // 2
        y = p_geom.y() + 80
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.txt_prompt.setFocus()
        self.txt_prompt.selectAll()

    def _on_chip_clicked(self, prompt: str) -> None:
        """Remplit le champ de saisie avec la suggestion cliquée et lance l'action."""
        self.txt_prompt.setText(prompt)
        self._on_submit()

    def _on_submit(self) -> None:
        """Exécute l'instruction IA entrée."""
        prompt = self.txt_prompt.text().strip()
        if not prompt:
            return

        self.lbl_feedback.setStyleSheet("color: #00a2ff; font-weight: bold; font-size: 11px;")
        self.lbl_feedback.setText(f"Exécution en cours : '{prompt}'...")
        self.repaint()

        res = self.bridge.execute_prompt(prompt)
        if res.success:
            self.lbl_feedback.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 11px;")
            self.lbl_feedback.setText(f"✓ {res.message}")
            self.action_completed.emit(prompt)
        else:
            self.lbl_feedback.setStyleSheet("color: #f87171; font-weight: bold; font-size: 11px;")
            self.lbl_feedback.setText(f"✕ Erreur : {res.message}")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Ferme la palette lors de l'appui sur Échap."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
