"""
Console Interactive Python Embarquée (Pillar UI & Scripting).
Permet l'exécution dynamique de commandes et scripts Python directement au sein de CAD Studio.
Fournit l'historique de commandes (Haut/Bas), l'invite interactive (>>>), et la capture des flux stdout/stderr.
Conforme aux standards de typage strict et SonarQube (complexité cognitive <= 25).
"""

from __future__ import annotations
import sys
import io
from typing import List, Dict, Optional, Callable, Sequence
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QTextEdit
from PySide6.QtGui import QTextCursor, QFont, QColor, QTextCharFormat, QKeyEvent
from PySide6.QtCore import Qt, Signal

from src.core.document import CADDocument


class CADPythonConsole(QPlainTextEdit):
    """Widget de console interactive Python avec invite, historique et évaluation sécurisée."""

    command_executed = Signal(str)

    PROMPT: str = ">>> "
    CONTINUATION_PROMPT: str = "... "

    def __init__(self, parent: Optional[QWidget] = None, document: Optional[CADDocument] = None) -> None:
        super().__init__(parent)
        self.document: Optional[CADDocument] = document
        self._history: List[str] = []
        self._history_index: int = 0
        self._execution_context: Dict[str, object] = {}
        self._init_ui()
        self._init_context()
        self._insert_prompt()

    def _init_ui(self) -> None:
        """Configure l'apparence et le rendu de la console."""
        font = QFont("Consolas, 'Courier New', monospace", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setStyleSheet(
            "QPlainTextEdit {"
            "  background-color: #1E1E1E;"
            "  color: #D4D4D4;"
            "  selection-background-color: #264F78;"
            "  border: 1px solid #333333;"
            "}"
        )
        self.appendPlainText("# CAD Studio Python Interactive Console (v2.4)\n# Tapez 'help()' ou utilisez 'doc' pour manipuler le modèle 3D.\n")

    def _init_context(self) -> None:
        """Initialise le dictionnaire d'exécution local."""
        import math
        import numpy as np
        self._execution_context = {
            "math": math,
            "np": np,
            "doc": self.document,
        }

    def set_document(self, doc: CADDocument) -> None:
        """Associe un nouveau document actif à la console."""
        self.document = doc
        self._execution_context["doc"] = doc

    def _insert_prompt(self) -> None:
        """Insère l'invite de commande interactive."""
        self.insertPlainText(self.PROMPT)
        self.moveCursor(QTextCursor.MoveOperation.End)

    def _get_current_line_text(self) -> str:
        """Extrait la commande saisie sur la ligne active en omettant l'invite."""
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        line = cursor.selectedText()
        if line.startswith(self.PROMPT):
            return line[len(self.PROMPT):]
        if line.startswith(self.CONTINUATION_PROMPT):
            return line[len(self.CONTINUATION_PROMPT):]
        return line

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Gère les touches Entrée, Flèches Haut/Bas (historique) et Retour arrière."""
        key = event.key()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cmd = self._get_current_line_text()
            self.moveCursor(QTextCursor.MoveOperation.End)
            self.insertPlainText("\n")
            self._execute_line(cmd)
            return

        if key == Qt.Key.Key_Up:
            self._navigate_history(-1)
            return

        if key == Qt.Key.Key_Down:
            self._navigate_history(1)
            return

        if key == Qt.Key.Key_Backspace:
            cursor = self.textCursor()
            if cursor.positionInBlock() <= len(self.PROMPT):
                return

        super().keyPressEvent(event)

    def _navigate_history(self, delta: int) -> None:
        """Parcourt l'historique des commandes saisies."""
        if not self._history:
            return

        new_idx = self._history_index + delta
        if 0 <= new_idx < len(self._history):
            self._history_index = new_idx
            cmd = self._history[new_idx]
            cursor = self.textCursor()
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.insertText(f"{self.PROMPT}{cmd}")
            self.setTextCursor(cursor)

    def _execute_line(self, cmd_line: str) -> None:
        """Exécute une ligne de commande avec capture de sortie."""
        clean_cmd = cmd_line.strip()
        if not clean_cmd:
            self._insert_prompt()
            return

        self._history.append(clean_cmd)
        self._history_index = len(self._history)

        # Exécution sécurisée via le moteur de script CAD (CADScriptEngine)
        from src.ai.cad_script_engine import CADScriptEngine
        from src.core.document import CADDocument

        doc = self._doc if self._doc is not None else CADDocument(name="ConsoleSession")
        res = CADScriptEngine.execute_script(doc, clean_cmd)

        if res.success:
            if res.message and res.message != "Script exécuté avec succès.":
                self.insertPlainText(f"{res.message}\n")
        else:
            self._print_error(res.message)

        self.command_executed.emit(clean_cmd)
        self._insert_prompt()

    def _print_error(self, message: str) -> None:
        """Affiche un message d'erreur en rouge."""
        cursor = self.textCursor()
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#F44336"))
        cursor.insertText(message if message.endswith("\n") else f"{message}\n", fmt)
        self.moveCursor(QTextCursor.MoveOperation.End)
