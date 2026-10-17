"""
Barre de chronologie paramétrique inférieure (Timeline) inspirée d'Autodesk Fusion 360.
Affiche chaque étape de conception dans l'ordre chronologique, permet le retour
dans le temps (Rollback) et le rejeu pas-à-pas de l'historique du modèle.
"""

from __future__ import annotations
from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QSlider, QSizePolicy, QMenu
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QContextMenuEvent

from src.core.document import CADDocument
from src.core.feature import Feature


class TimelineStepButton(QPushButton):
    """Pastille représentant une opération paramétrique dans la timeline."""

    reorder_requested = Signal(int, int)  # (from_index, to_index)

    def __init__(self, index: int, feature: Feature, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.feature_index: int = index
        self.feature_id: str = feature.feature_id

        # Icône selon le type de feature
        icon_map = {
            "Box": "📦",
            "Cylinder": "🥫",
            "Sphere": "🔮",
            "Extrude": "⬆️",
            "Combine": "🔀",
        }
        icon = icon_map.get(feature.name.split()[0], "⚙️")
        self.setText(f"{icon} {feature.name}")
        self.setFixedSize(110, 32)
        self.setStyleSheet("""
            QPushButton {
                background-color: #2a2d34;
                color: #e0e2e8;
                border: 1px solid #3d414b;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 500;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #383c46;
                border-color: #00a2ff;
            }
            QPushButton:checked {
                background-color: #007acc;
                border-color: #33aaff;
                color: #ffffff;
                font-weight: bold;
            }
        """)
        self.setCheckable(True)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Menu contextuel pour réorganiser l'opération dans l'arbre paramétrique."""
        menu = QMenu(self)
        act_left = menu.addAction("◀ Déplacer vers la gauche (Avancer)")
        act_right = menu.addAction("▶ Déplacer vers la droite (Reculer)")
        action = menu.exec(event.globalPos())
        if action == act_left and self.feature_index > 0:
            self.reorder_requested.emit(self.feature_index, self.feature_index - 1)
        elif action == act_right:
            self.reorder_requested.emit(self.feature_index, self.feature_index + 1)


class CADTimeline(QWidget):
    """
    Composant de timeline historique (Timeline Bar).
    Situé au bas de l'écran, avec boutons de navigation et affichage séquentiel.
    """

    feature_selected = Signal(str)

    def __init__(self, document: CADDocument, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.document: CADDocument = document
        self.setFixedHeight(65)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(6)

        # Contrôles de lecture (Playback)
        ctrl_box = QHBoxLayout()
        ctrl_box.setSpacing(2)

        btn_ctrl_style = """
            QPushButton {
                background-color: #2a2d34;
                color: #e0e2e8;
                border: 1px solid #3d414b;
                border-radius: 4px;
                font-family: 'Segoe UI Symbol', 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #383c46;
                border-color: #00a2ff;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
        """

        self.btn_first = QPushButton("⏮")
        self.btn_first.setFixedSize(28, 28)
        self.btn_first.setStyleSheet(btn_ctrl_style)
        self.btn_first.setToolTip("Aller au début (|◀)")
        self.btn_first.clicked.connect(self._goto_first)

        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedSize(28, 28)
        self.btn_prev.setStyleSheet(btn_ctrl_style)
        self.btn_prev.setToolTip("Étape précédente (◀)")
        self.btn_prev.clicked.connect(self._step_backward)

        self.btn_play = QPushButton("⏯")
        self.btn_play.setFixedSize(28, 28)
        self.btn_play.setStyleSheet(btn_ctrl_style)
        self.btn_play.setToolTip("Rejouer / Pause (Lecture)")
        self.btn_play.clicked.connect(self._toggle_playback)

        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedSize(28, 28)
        self.btn_next.setStyleSheet(btn_ctrl_style)
        self.btn_next.setToolTip("Étape suivante (▶)")
        self.btn_next.clicked.connect(self._step_forward)

        self.btn_last = QPushButton("⏭")
        self.btn_last.setFixedSize(28, 28)
        self.btn_last.setStyleSheet(btn_ctrl_style)
        self.btn_last.setToolTip("Aller à la fin (▶|)")
        self.btn_last.clicked.connect(self._goto_last)

        ctrl_box.addWidget(self.btn_first)
        ctrl_box.addWidget(self.btn_prev)
        ctrl_box.addWidget(self.btn_play)
        ctrl_box.addWidget(self.btn_next)
        ctrl_box.addWidget(self.btn_last)
        main_layout.addLayout(ctrl_box)

        # Séparateur vertical
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #353841;")
        main_layout.addWidget(sep)

        # Zone de défilement horizontal des étapes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.steps_container = QWidget()
        self.steps_layout = QHBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(4)
        self.steps_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        scroll.setWidget(self.steps_container)
        main_layout.addWidget(scroll, 1)

        # Minuteur pour la lecture animée
        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(700)
        self._playback_timer.timeout.connect(self._playback_tick)
        self._is_playing: bool = False

        self.document.register_change_listener(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        """Met à jour l'affichage des pastilles de la timeline."""
        # Vider les étapes précédentes
        while self.steps_layout.count() > 0:
            item = self.steps_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not self.document.features:
            lbl_empty = QLabel("Aucune opération (Commencez par créer une Boîte, Cylindre ou Esquisse)")
            lbl_empty.setStyleSheet("color: #656c7a; font-style: italic; padding: 6px;")
            self.steps_layout.addWidget(lbl_empty)
            return

        active_idx = self.document.rollback_index
        if active_idx == -1:
            active_idx = len(self.document.features) - 1

        for idx, feat in enumerate(self.document.features):
            btn = TimelineStepButton(idx, feat)
            # Marquer si la feature est active ou grisée par le rollback
            if idx > active_idx:
                btn.setEnabled(False)
                btn.setStyleSheet("background-color: #1e2025; color: #555a64; border: 1px dashed #30333b;")
            btn.clicked.connect(lambda checked=False, f_id=feat.feature_id: self.feature_selected.emit(f_id))
            btn.reorder_requested.connect(self._on_reorder_requested)
            self.steps_layout.addWidget(btn)

    def _on_reorder_requested(self, from_idx: int, to_idx: int) -> None:
        """Réorganise une opération dans l'arbre chronologique du document."""
        self.document.reorder_feature(from_idx, to_idx)

    def _goto_first(self) -> None:
        """Revient au tout début de l'arbre."""
        if self.document.features:
            self.document.set_rollback_index(0)

    def _step_backward(self) -> None:
        """Recule d'une étape dans l'historique."""
        idx = self.document.rollback_index
        if idx == -1:
            idx = len(self.document.features) - 1
        new_idx = max(0, idx - 1)
        self.document.set_rollback_index(new_idx)

    def _step_forward(self) -> None:
        """Avance d'une étape vers le futur."""
        idx = self.document.rollback_index
        if idx == -1:
            idx = len(self.document.features) - 1
        new_idx = min(len(self.document.features) - 1, idx + 1)
        self.document.set_rollback_index(new_idx)

    def _goto_last(self) -> None:
        """Rétablit l'intégralité du modèle à jour."""
        self.document.set_rollback_index(len(self.document.features) - 1)

    def _toggle_playback(self) -> None:
        """Démarre ou arrête la lecture animée de la construction."""
        if self._is_playing:
            self._playback_timer.stop()
            self._is_playing = False
            self.btn_play.setText("▶")
        else:
            self._is_playing = True
            self.btn_play.setText("⏸")
            self.document.set_rollback_index(0)
            self._playback_timer.start()

    def _playback_tick(self) -> None:
        """Fait avancer l'animation d'une étape."""
        idx = self.document.rollback_index
        if idx >= len(self.document.features) - 1:
            self._toggle_playback()
            return
        self.document.set_rollback_index(idx + 1)
