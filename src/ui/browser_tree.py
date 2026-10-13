from __future__ import annotations
from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel, QMenu
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QAction

from src.core.document import CADDocument


class CADBrowserTree(QWidget):
    """
    Arborescence du modèle (Model Browser) style Autodesk Fusion 360.
    Gère la hiérarchie Origine, Corps solides, Esquisses et menus contextuels.
    """

    body_selected = Signal(str)
    sketch_selected = Signal(str)
    export_body_requested = Signal(str)
    delete_body_requested = Signal(str)

    def __init__(self, document: CADDocument, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.document = document

        self.setMinimumWidth(260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        header = QLabel("NAVIGATEUR DU MODÈLE")
        header.setStyleSheet("color: #00a2ff; font-weight: bold; font-size: 10px; padding: 2px;")
        layout.addWidget(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        if self.tree.header():
            self.tree.header().setStretchLastSection(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
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
        bodies_group = QTreeWidgetItem(root_item, [f"📦 Corps solides ({len(self.document.bodies)})"])
        for body_id, solid in self.document.bodies.items():
            vol = solid.volume()
            b_item = QTreeWidgetItem(bodies_group, [f"👁️ {solid.name} ({vol:.1f} mm³)"])
            b_item.setData(0, Qt.ItemDataRole.UserRole, ("body", body_id))
            b_item.setToolTip(0, f"Corps solide '{solid.name}' | Volume: {vol:.1f} mm³\nClic droit pour options")
        bodies_group.setExpanded(True)

        # Groupe Esquisses (Sketches)
        sketches_group = QTreeWidgetItem(root_item, [f"✏️ Esquisses 2D ({len(self.document.sketches)})"])
        for s_id, sketch in self.document.sketches.items():
            s_item = QTreeWidgetItem(sketches_group, [f"📐 {sketch.name} [{sketch.plane.value}]"])
            s_item.setData(0, Qt.ItemDataRole.UserRole, ("sketch", s_id))
            s_item.setToolTip(0, f"Esquisse '{sketch.name}' | Plan {sketch.plane.value}")
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

    def _on_context_menu(self, pos: QPoint) -> None:
        """Affiche le menu contextuel au clic droit sur un élément de l'arbre."""
        item = self.tree.itemAt(pos)
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_id = data
        menu = QMenu(self)

        if item_type == "body":
            act_select = menu.addAction("🔍 Sélectionner et inspecter")
            act_select.triggered.connect(lambda: self.body_selected.emit(item_id))

            act_export = menu.addAction("💾 Exporter ce corps en STL...")
            act_export.triggered.connect(lambda: self.export_body_requested.emit(item_id))

            menu.addSeparator()
            act_delete = menu.addAction("🗑️ Supprimer le corps")
            act_delete.triggered.connect(lambda: self.delete_body_requested.emit(item_id))

        elif item_type == "sketch":
            act_edit = menu.addAction("✏️ Éditer l'esquisse")
            act_edit.triggered.connect(lambda: self.sketch_selected.emit(item_id))

        global_pos = self.tree.mapToGlobal(pos)
        menu.exec(global_pos)
