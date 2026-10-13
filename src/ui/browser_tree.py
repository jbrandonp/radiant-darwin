"""
Navigateur de modèle (Browser Tree) situé à gauche de l'écran.
Affiche la hiérarchie du document : Origine (axes, plans), Corps solides (Bodies)
et Esquisses 2D (Sketches).
"""

from __future__ import annotations
from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel
from PySide6.QtCore import Qt, Signal

from src.core.document import CADDocument


class CADBrowserTree(QWidget):
    """Arborescence du modèle (Model Browser)."""

    body_selected = Signal(str)
    sketch_selected = Signal(str)

    def __init__(self, document: CADDocument, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.document = document

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        header = QLabel("NAVIGATEUR DU MODÈLE")
        header.setStyleSheet("color: #8c93a0; font-weight: bold; font-size: 10px; padding: 2px;")
        layout.addWidget(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree)

        self.document.register_change_listener(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        """Reconstruit l'arbre complet à partir de l'état actuel du document."""
        self.tree.clear()

        # Racine du document
        root_item = QTreeWidgetItem(self.tree, [f"📄 {self.document.name}"])
        root_item.setExpanded(True)

        # Groupe Origine
        origin_item = QTreeWidgetItem(root_item, ["🧭 Origine"])
        QTreeWidgetItem(origin_item, ["• Point Origine (0, 0, 0)"])
        QTreeWidgetItem(origin_item, ["🔴 Axe X"])
        QTreeWidgetItem(origin_item, ["🟢 Axe Y"])
        QTreeWidgetItem(origin_item, ["🔵 Axe Z"])
        QTreeWidgetItem(origin_item, ["📐 Plan XY"])
        QTreeWidgetItem(origin_item, ["📐 Plan XZ"])
        QTreeWidgetItem(origin_item, ["📐 Plan YZ"])
        origin_item.setExpanded(False)

        # Groupe Corps solides (Bodies)
        bodies_group = QTreeWidgetItem(root_item, [f"📦 Corps ({len(self.document.bodies)})"])
        for body_id, solid in self.document.bodies.items():
            vol = solid.volume()
            b_item = QTreeWidgetItem(bodies_group, [f"🔹 {solid.name} ({vol:.1f} mm³)"])
            b_item.setData(0, Qt.ItemDataRole.UserRole, ("body", body_id))
        bodies_group.setExpanded(True)

        # Groupe Esquisses (Sketches)
        sketches_group = QTreeWidgetItem(root_item, [f"✏️ Esquisses ({len(self.document.sketches)})"])
        for s_id, sketch in self.document.sketches.items():
            s_item = QTreeWidgetItem(sketches_group, [f"📐 {sketch.name} [{sketch.plane.value}]"])
            s_item.setData(0, Qt.ItemDataRole.UserRole, ("sketch", s_id))
        sketches_group.setExpanded(True)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Déclenche la sélection d'un corps ou d'une esquisse."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        item_type, item_id = data
        if item_type == "body":
            self.body_selected.emit(item_id)
        elif item_type == "sketch":
            self.sketch_selected.emit(item_id)
