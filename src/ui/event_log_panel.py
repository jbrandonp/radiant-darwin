"""
Panneau de Journalisation et d'Événements Unifié (Event Log Panel).
Affiche en temps réel les événements du bus applicatif (EventBus), les alertes de modélisation
et les diagnostics du moteur géométrique avec filtrage par sévérité.
Conforme aux standards de typage strict et SonarQube (complexité cognitive <= 25).
"""

from __future__ import annotations
import datetime
from enum import Enum
from typing import List, Tuple, Optional, Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QPushButton, QComboBox, QLineEdit, QLabel
)
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor, QCloseEvent
from PySide6.QtCore import Qt

from src.core.event_bus import global_event_bus, CADEvent, TimelineRollbackEvent


class LogSeverity(str, Enum):
    """Niveaux de sévérité des messages de journal."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class CADEventLogPanel(QWidget):
    """Widget de journal d'événements dockable avec filtrage et recherche."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._records: List[Tuple[LogSeverity, str]] = []
        self._unsubscribe_token: Optional[Callable[[], None]] = None
        self._init_ui()
        self._connect_event_bus()

    def _init_ui(self) -> None:
        """Initialise les composants visuels du panneau."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Barre d'outils supérieure : Filtre, Recherche, Effacer
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        toolbar.addWidget(QLabel("Niveau :"))
        self.combo_level = QComboBox()
        self.combo_level.addItems(["TOUS", "INFO", "WARNING", "ERROR", "DEBUG"])
        self.combo_level.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.combo_level)

        toolbar.addWidget(QLabel("Recherche :"))
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("Filtrer les messages...")
        self.txt_filter.textChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.txt_filter)

        self.btn_clear = QPushButton("Effacer")
        self.btn_clear.clicked.connect(self.clear_logs)
        toolbar.addWidget(self.btn_clear)

        layout.addLayout(toolbar)

        # Zone d'affichage des logs
        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        font = QFont("Consolas, monospace", 9)
        self.log_display.setFont(font)
        self.log_display.setStyleSheet(
            "QPlainTextEdit { background-color: #181818; color: #CCCCCC; border: 1px solid #2D2D2D; }"
        )
        layout.addWidget(self.log_display)

    def _connect_event_bus(self) -> None:
        """S'abonne au bus d'événements global."""
        self._unsubscribe_token = global_event_bus.subscribe(CADEvent, self._on_event_received)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Désabonne le panneau lors de la fermeture de la fenêtre."""
        if self._unsubscribe_token is not None:
            self._unsubscribe_token()
            self._unsubscribe_token = None
        super().closeEvent(event)

    def _on_event_received(self, event: CADEvent) -> None:
        """Réceptionne un événement du bus et l'ajoute au journal."""
        evt_name = type(event).__name__
        now = datetime.datetime.now().strftime("%H:%M:%S")
        msg = f"[{now}] [{evt_name}] {str(event)}"

        severity = LogSeverity.INFO
        if getattr(event, "is_success", True) is False:
            severity = LogSeverity.ERROR
        elif isinstance(event, TimelineRollbackEvent):
            severity = LogSeverity.WARNING

        self.append_log(severity, msg)

    def append_log(self, severity: LogSeverity, message: str) -> None:
        """Ajoute une ligne de log avec coloration adaptée et mise en mémoire."""
        self._records.append((severity, message))
        if self._matches_filter(severity, message):
            self._render_log_line(severity, message)

    def _matches_filter(self, severity: LogSeverity, message: str) -> bool:
        """Vérifie si une entrée de log satisfait les critères actuels."""
        target_lvl = self.combo_level.currentText()
        if target_lvl != "TOUS" and severity.value != target_lvl:
            return False
        search_query = self.txt_filter.text().strip().lower()
        if search_query and search_query not in message.lower():
            return False
        return True

    def _render_log_line(self, severity: LogSeverity, message: str) -> None:
        """Formate et insère une ligne de log colorée dans le widget."""
        cursor = self.log_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        fmt = QTextCharFormat()
        if severity == LogSeverity.ERROR:
            fmt.setForeground(QColor("#FF5252"))
        elif severity == LogSeverity.WARNING:
            fmt.setForeground(QColor("#FFB74D"))
        elif severity == LogSeverity.DEBUG:
            fmt.setForeground(QColor("#9E9E9E"))
        else:
            fmt.setForeground(QColor("#81C784"))

        cursor.insertText(f"[{severity.value}] {message}\n", fmt)
        self.log_display.moveCursor(QTextCursor.MoveOperation.End)

    def clear_logs(self) -> None:
        """Efface l'historique affiché et le tampon d'enregistrements."""
        self._records.clear()
        self.log_display.clear()

    def _on_filter_changed(self) -> None:
        """Réapplique les filtres de niveau et de recherche sur l'historique."""
        self.log_display.clear()
        for severity, message in self._records:
            if self._matches_filter(severity, message):
                self._render_log_line(severity, message)
