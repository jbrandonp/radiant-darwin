"""
Panneau d'interface utilisateur pour la pile de modificateurs inspiré de Blender (Modifier Panel).
Permet d'ajouter, configurer, activer/désactiver, réordonner et appliquer (Bake)
des modificateurs non-destructifs sur le corps sélectionné.
Architecture 100% fortement typée sans Any ni object.
"""

from __future__ import annotations
from typing import Optional, Dict, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QComboBox, QDoubleSpinBox, QCheckBox,
    QGroupBox, QDockWidget, QSizePolicy
)
from PySide6.QtCore import Qt, Signal

from src.core.modifier_stack import (
    ModifierStack, CADModifier, ModifierType,
    MirrorModifier, ArrayModifier, SolidifyModifier, BevelModifier, BooleanModifier
)
from src.core.geometry import Solid


class ModifierCardWidget(QFrame):
    """Carte représentant un modificateur individuel dans la pile (style Blender)."""

    modifier_changed = Signal(str)
    modifier_applied = Signal(str)
    modifier_removed = Signal(str)
    modifier_moved = Signal(str, int)  # modifier_id, direction (-1 ou +1)

    def __init__(self, modifier: CADModifier, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.modifier: CADModifier = modifier
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #2b2e36;
                border: 1px solid #3d414c;
                border-radius: 5px;
                margin-bottom: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # En-tête : Icône, Titre, Visibilité, Monter, Descendre, Appliquer, Supprimer
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)

        self.chk_enabled = QCheckBox()
        self.chk_enabled.setChecked(self.modifier.is_enabled)
        self.chk_enabled.setToolTip("Activer / Désactiver le modificateur")
        self.chk_enabled.toggled.connect(self._on_toggled)
        header.addWidget(self.chk_enabled)

        icon_map = {
            ModifierType.MIRROR: "🪞",
            ModifierType.ARRAY: "🔲",
            ModifierType.SOLIDIFY: "🧱",
            ModifierType.BEVEL: "📐",
            ModifierType.BOOLEAN: "🔀",
            ModifierType.SUBDIVISION: "🌐",
            ModifierType.DISPLACE: "🌊",
        }
        icon = icon_map.get(self.modifier.modifier_type, "⚙️")
        lbl_title = QLabel(f"<b>{icon} {self.modifier.name}</b>")
        lbl_title.setStyleSheet("color: #e4e7ee; font-size: 11px;")
        header.addWidget(lbl_title, 1)

        btn_style = """
            QPushButton {
                background-color: #353942;
                color: #cfd3dc;
                border: 1px solid #484d59;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                padding: 1px 4px;
            }
            QPushButton:hover {
                background-color: #007acc;
                color: #ffffff;
            }
        """

        btn_up = QPushButton("▲")
        btn_up.setFixedSize(20, 20)
        btn_up.setStyleSheet(btn_style)
        btn_up.clicked.connect(lambda: self.modifier_moved.emit(self.modifier.modifier_id, -1))
        header.addWidget(btn_up)

        btn_down = QPushButton("▼")
        btn_down.setFixedSize(20, 20)
        btn_down.setStyleSheet(btn_style)
        btn_down.clicked.connect(lambda: self.modifier_moved.emit(self.modifier.modifier_id, 1))
        header.addWidget(btn_down)

        btn_apply = QPushButton("Bake")
        btn_apply.setFixedHeight(20)
        btn_apply.setStyleSheet(btn_style)
        btn_apply.setToolTip("Appliquer définitivement dans la géométrie de base (Bake)")
        btn_apply.clicked.connect(lambda: self.modifier_applied.emit(self.modifier.modifier_id))
        header.addWidget(btn_apply)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(20, 20)
        btn_del.setStyleSheet("""
            QPushButton {
                background-color: #353942;
                color: #ff6b6b;
                border: 1px solid #484d59;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d32f2f;
                color: #ffffff;
            }
        """)
        btn_del.clicked.connect(lambda: self.modifier_removed.emit(self.modifier.modifier_id))
        header.addWidget(btn_del)

        layout.addLayout(header)

        # Corps des paramètres éditables
        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(4, 2, 4, 2)
        body_layout.setSpacing(3)
        self._build_parameter_inputs(body_layout)
        layout.addLayout(body_layout)

    def _build_parameter_inputs(self, layout: QVBoxLayout) -> None:
        """Crée les champs de saisie spécifiques au type de modificateur."""
        for param_name, param_val in self.modifier.parameters.items():
            row = QHBoxLayout()
            lbl = QLabel(param_name.replace("_", " ").capitalize())
            lbl.setStyleSheet("color: #a0a6b5; font-size: 10px;")
            spin = QDoubleSpinBox()
            spin.setRange(-1000.0, 1000.0)
            spin.setValue(param_val)
            spin.setStyleSheet("background-color: #1e2025; color: #ffffff; border: 1px solid #3d414c;")
            spin.valueChanged.connect(lambda v, p=param_name: self._on_param_changed(p, v))
            row.addWidget(lbl)
            row.addWidget(spin, 1)
            layout.addLayout(row)

    def _on_toggled(self, checked: bool) -> None:
        """Active ou désactive le modificateur."""
        self.modifier.is_enabled = checked
        self.modifier_changed.emit(self.modifier.modifier_id)

    def _on_param_changed(self, param_name: str, val: float) -> None:
        """Met à jour un paramètre numérique."""
        self.modifier.parameters[param_name] = float(val)
        self.modifier_changed.emit(self.modifier.modifier_id)


class ModifierStackDock(QDockWidget):
    """Panneau Dock de gestion de la pile de modificateurs non-destructifs."""

    stack_updated = Signal(str)  # body_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Pile de Modificateurs (Blender)", parent)
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)

        self._active_stack: Optional[ModifierStack] = None
        self._context_bodies: Dict[str, Solid] = {}
        self._target_body_id: str = "body_main"

        container = QWidget()
        self.main_layout = QVBoxLayout(container)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(6)

        # Barre supérieure : sélecteur d'ajout de modificateur
        add_bar = QHBoxLayout()
        self.combo_add = QComboBox()
        self.combo_add.addItems([
            "➕ Ajouter un Modificateur...",
            "Miroir (Mirror)",
            "Réseau (Array)",
            "Épaississement (Solidify)",
            "Biseautage (Bevel)"
        ])
        self.combo_add.setStyleSheet("""
            QComboBox {
                background-color: #2a2d35;
                color: #e4e7ee;
                border: 1px solid #3d414c;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
            }
        """)
        self.combo_add.currentIndexChanged.connect(self._on_add_selected)
        add_bar.addWidget(self.combo_add)
        self.main_layout.addLayout(add_bar)

        # Zone déroulante des cartes de modificateurs
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(4)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self.cards_container)
        self.main_layout.addWidget(scroll, 1)

        self.setWidget(container)

    def set_target_stack(self, stack: ModifierStack, context_bodies: Dict[str, Solid]) -> None:
        """Associe la pile de modificateurs du corps actif au panneau."""
        self._active_stack = stack
        self._context_bodies = context_bodies
        self._target_body_id = stack.body_id
        self.refresh()

    def refresh(self) -> None:
        """Reconstruit l'affichage des cartes de modificateurs."""
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if self._active_stack is None or self._active_stack.count() == 0:
            lbl = QLabel("Aucun modificateur actif.\nSélectionnez 'Ajouter un Modificateur' ci-dessus.")
            lbl.setStyleSheet("color: #7b8190; font-style: italic; padding: 12px; text-align: center;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cards_layout.addWidget(lbl)
            return

        for mod in self._active_stack.modifiers:
            card = ModifierCardWidget(mod)
            card.modifier_changed.connect(self._on_modifier_changed)
            card.modifier_applied.connect(self._on_modifier_applied)
            card.modifier_removed.connect(self._on_modifier_removed)
            card.modifier_moved.connect(self._on_modifier_moved)
            self.cards_layout.addWidget(card)

    def _on_add_selected(self, index: int) -> None:
        """Gère l'ajout d'un nouveau modificateur depuis le menu déroulant."""
        if index <= 0 or self._active_stack is None:
            return

        count = self._active_stack.count() + 1
        mod: Optional[CADModifier] = None

        if index == 1:
            mod = MirrorModifier(f"mod_mirror_{count}", f"Miroir {count}", axis="X")
        elif index == 2:
            mod = ArrayModifier(f"mod_array_{count}", f"Réseau {count}", count=3, offset_x=30.0)
        elif index == 3:
            mod = SolidifyModifier(f"mod_solidify_{count}", f"Coque {count}", thickness=2.0)
        elif index == 4:
            mod = BevelModifier(f"mod_bevel_{count}", f"Biseau {count}", width=1.5)

        if mod is not None:
            self._active_stack.add_modifier(mod)
            self.refresh()
            self.stack_updated.emit(self._target_body_id)

        self.combo_add.setCurrentIndex(0)

    def _on_modifier_changed(self, modifier_id: str) -> None:
        """Notifie que les paramètres d'un modificateur ont changé."""
        self.stack_updated.emit(self._target_body_id)

    def _on_modifier_applied(self, modifier_id: str) -> None:
        """Applique et cuit le modificateur dans la géométrie."""
        if self._active_stack is None or self._target_body_id not in self._context_bodies:
            return
        base_solid = self._context_bodies[self._target_body_id]
        new_solid, ok = self._active_stack.apply_modifier(modifier_id, base_solid, self._context_bodies)
        if ok:
            self._context_bodies[self._target_body_id] = new_solid
            self.refresh()
            self.stack_updated.emit(self._target_body_id)

    def _on_modifier_removed(self, modifier_id: str) -> None:
        """Supprime un modificateur de la pile."""
        if self._active_stack is not None:
            self._active_stack.remove_modifier(modifier_id)
            self.refresh()
            self.stack_updated.emit(self._target_body_id)

    def _on_modifier_moved(self, modifier_id: str, direction: int) -> None:
        """Déplace un modificateur dans la pile."""
        if self._active_stack is not None:
            if self._active_stack.move_modifier(modifier_id, direction):
                self.refresh()
                self.stack_updated.emit(self._target_body_id)
