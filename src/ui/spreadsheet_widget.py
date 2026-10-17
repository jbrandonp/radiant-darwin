"""
Moteur de tableur paramétrique (Parametric Spreadsheet Engine).
Évalue les formules mathématiques et lie dynamiquement les cellules et alias
aux paramètres du modèle CAO 3D (comme l'atelier Spreadsheet de FreeCAD).
"""

from __future__ import annotations
import ast
from dataclasses import dataclass, field
import math
import re
from typing import Dict, List, Optional, Set, Tuple, Callable, Union

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
        QLineEdit, QLabel, QPushButton, QHeaderView
    )
    PYSIDE_AVAILABLE = True
except ImportError:
    PYSIDE_AVAILABLE = False


def cell_coords_to_name(row: int, col: int) -> str:
    """
    Convertit des coordonnées (row, col) en nom de cellule Excel standard (ex: 1, 0 -> 'A1').
    Row est 1-indexé (1, 2, ...), Col est 0-indexé (0 -> 'A', 1 -> 'B', etc.).
    """
    col_str = ""
    c = col
    while c >= 0:
        col_str = chr(ord('A') + (c % 26)) + col_str
        c = (c // 26) - 1
    return f"{col_str}{row}"


def name_to_cell_coords(cell_name: str) -> Tuple[int, int]:
    """
    Convertit un nom de cellule standard en coordonnées (row, col).
    Ex: 'A1' -> (1, 0), 'B12' -> (12, 1).
    """
    match = re.match(r"^([A-Za-z]+)(\d+)$", cell_name.strip())
    if not match:
        raise ValueError(f"Nom de cellule invalide : {cell_name}")

    col_str, row_str = match.groups()
    col = 0
    for char in col_str.upper():
        col = col * 26 + (ord(char) - ord('A') + 1)
    col -= 1  # 0-indexé
    row = int(row_str)  # 1-indexé
    return (row, col)


@dataclass
class SpreadsheetCell:
    """Représentation d'une cellule du tableur paramétrique."""
    raw_content: str = ""
    computed_value: float = 0.0
    alias: Optional[str] = None
    has_error: bool = False
    error_message: str = ""


class ParametricSpreadsheet:
    """
    Tableur paramétrique bidirectionnel avec graphe de dépendances et évaluation AST sécurisée.
    Permet de piloter toutes les dimensions géométriques via des formules (=A1*2, =Epaisseur+10).
    """

    ALLOWED_MATH_NAMES: Dict[str, Union[float, Callable[..., float]]] = {
        "pi": math.pi,
        "e": math.e,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "abs": abs,
        "min": min,
        "max": max,
        "exp": math.exp,
        "log": math.log,
        "floor": math.floor,
        "ceil": math.ceil,
        "round": round,
    }

    def __init__(self, rows: int = 100, cols: int = 26) -> None:
        """Initialise une grille de tableur vide."""
        self.rows = max(1, rows)
        self.cols = max(1, cols)
        self.cells: Dict[str, SpreadsheetCell] = {}
        self.alias_to_cell: Dict[str, str] = {}
        self.cell_to_alias: Dict[str, str] = {}
        self.parameter_bindings: Dict[str, str] = {}  # param_name -> cell_or_alias
        self.change_listeners: List[Callable[[str, float], None]] = []

    def set_cell(self, cell_ref: str, content: str) -> None:
        """
        Définit le contenu brut d'une cellule (valeur numérique ou formule commençant par '=').
        Recalcule automatiquement les dépendances associées.
        """
        canonical_ref = cell_ref.strip().upper()
        name_to_cell_coords(canonical_ref)  # Validation du format

        if canonical_ref not in self.cells:
            self.cells[canonical_ref] = SpreadsheetCell()

        self.cells[canonical_ref].raw_content = content.strip()
        self.recompute_all()

    def set_alias(self, cell_ref: str, alias: str) -> None:
        """
        Associe un alias nominal à une cellule (ex: B2 -> 'Longueur').
        """
        canonical_ref = cell_ref.strip().upper()
        clean_alias = alias.strip()
        if not clean_alias.isidentifier():
            raise ValueError(f"L'alias '{clean_alias}' n'est pas un identifiant valide.")

        # Supprimer l'ancien alias si existant
        if clean_alias in self.alias_to_cell:
            old_ref = self.alias_to_cell[clean_alias]
            if old_ref in self.cells:
                self.cells[old_ref].alias = None

        self.alias_to_cell[clean_alias] = canonical_ref
        self.cell_to_alias[canonical_ref] = clean_alias

        if canonical_ref not in self.cells:
            self.cells[canonical_ref] = SpreadsheetCell()
        self.cells[canonical_ref].alias = clean_alias

        self.recompute_all()

    def get_alias_value(self, alias: str) -> float:
        """Retourne la valeur calculée associée à un alias."""
        clean_alias = alias.strip()
        if clean_alias not in self.alias_to_cell:
            raise KeyError(f"Alias introuvable : '{clean_alias}'")
        cell_ref = self.alias_to_cell[clean_alias]
        return self.get_cell_value(cell_ref)

    def get_cell_value(self, cell_ref: str) -> float:
        """Retourne la valeur numérique calculée d'une cellule."""
        canonical_ref = cell_ref.strip().upper()
        if canonical_ref in self.cells:
            cell = self.cells[canonical_ref]
            if cell.has_error:
                raise ValueError(f"Erreur dans la cellule {canonical_ref} : {cell.error_message}")
            return cell.computed_value
        return 0.0

    def get_cell_raw(self, cell_ref: str) -> str:
        """Retourne le contenu brut (formule ou texte) d'une cellule."""
        canonical_ref = cell_ref.strip().upper()
        if canonical_ref in self.cells:
            return self.cells[canonical_ref].raw_content
        return ""

    def bind_parameter(self, param_name: str, cell_or_alias: str) -> None:
        """Lie un paramètre de modélisation 3D à une cellule ou un alias."""
        self.parameter_bindings[param_name] = cell_or_alias.strip()

    def get_bound_parameter_value(self, param_name: str) -> float:
        """Résout la valeur numérique d'un paramètre lié."""
        if param_name not in self.parameter_bindings:
            raise KeyError(f"Paramètre non lié : '{param_name}'")
        target = self.parameter_bindings[param_name]
        if target in self.alias_to_cell:
            return self.get_alias_value(target)
        return self.get_cell_value(target)

    def add_listener(self, listener: Callable[[str, float], None]) -> None:
        """Ajoute un écouteur appelé lors des modifications de valeurs calculées."""
        self.change_listeners.append(listener)

    def recompute_all(self) -> None:
        """
        Recalcule l'ensemble des cellules de la feuille en résolvant
        l'ordre topologique des dépendances et en détectant les cycles.
        """
        # Construction du graphe de dépendances
        dep_graph: Dict[str, Set[str]] = {}
        for ref, cell in self.cells.items():
            dep_graph[ref] = self._extract_dependencies(cell.raw_content)

        # Évaluation ordonnée avec détection de cycles
        evaluated: Set[str] = set()
        visiting: Set[str] = set()

        for ref in list(self.cells.keys()):
            self._evaluate_node(ref, dep_graph, evaluated, visiting)

        # Notification des écouteurs
        for ref, cell in self.cells.items():
            if not cell.has_error:
                for callback in self.change_listeners:
                    callback(ref, cell.computed_value)
                if cell.alias:
                    for callback in self.change_listeners:
                        callback(cell.alias, cell.computed_value)

    def _extract_dependencies(self, content: str) -> Set[str]:
        """Extrait toutes les cellules et alias référencés dans une formule."""
        deps: Set[str] = set()
        if not content.startswith("="):
            return deps

        expr = content[1:].strip()
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError:
            return deps

        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                name = node.id
                if name.lower() not in self.ALLOWED_MATH_NAMES:
                    # Est-ce un alias ou une coordonnée de cellule ?
                    if name in self.alias_to_cell:
                        deps.add(self.alias_to_cell[name])
                    else:
                        deps.add(name.upper())
        return deps

    def _evaluate_node(
        self,
        ref: str,
        dep_graph: Dict[str, Set[str]],
        evaluated: Set[str],
        visiting: Set[str]
    ) -> None:
        """Évalue un nœud récursivement avec protection contre les cycles infinis."""
        if ref in evaluated:
            return

        if ref in visiting:
            # Cycle circulaire détecté !
            if ref in self.cells:
                self.cells[ref].has_error = True
                self.cells[ref].error_message = "Référence circulaire détectée (#CYCLE)"
            return

        visiting.add(ref)

        for dep in dep_graph.get(ref, set()):
            if dep in self.cells:
                self._evaluate_node(dep, dep_graph, evaluated, visiting)

        visiting.remove(ref)
        evaluated.add(ref)

        if ref in self.cells:
            self._compute_cell_value(ref)

    def _compute_cell_value(self, ref: str) -> None:
        """Évalue le contenu d'une cellule individuelle de manière sécurisée."""
        cell = self.cells[ref]
        content = cell.raw_content.strip()

        if not content:
            cell.computed_value = 0.0
            cell.has_error = False
            cell.error_message = ""
            return

        if not content.startswith("="):
            # Valeur numérique constante ou texte
            try:
                cell.computed_value = float(content)
                cell.has_error = False
                cell.error_message = ""
            except ValueError:
                cell.computed_value = 0.0
                cell.has_error = False
                cell.error_message = ""
            return

        # Formule mathématique commençant par '='
        expr = content[1:].strip()
        try:
            val = self._safe_eval_expression(expr)
            cell.computed_value = float(val)
            cell.has_error = False
            cell.error_message = ""
        except Exception as err:
            cell.computed_value = 0.0
            cell.has_error = True
            cell.error_message = str(err)

    def _safe_eval_expression(self, expression_str: str) -> float:
        """
        Évalue une expression mathématique via un arbre syntaxique abstrait (AST) sécurisé.
        N'utilise jamais 'eval' direct pour une sécurité absolue.
        """
        try:
            tree = ast.parse(expression_str, mode="eval")
        except SyntaxError as syntax_err:
            raise ValueError(f"Erreur de syntaxe : {syntax_err}")

        return self._eval_ast_node(tree.body)

    def _eval_ast_constant(self, node: ast.Constant) -> float:
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"Constante non numérique : {node.value}")

    def _eval_ast_name(self, node: ast.Name) -> float:
        name = node.id
        if name.lower() in self.ALLOWED_MATH_NAMES:
            val = self.ALLOWED_MATH_NAMES[name.lower()]
            if isinstance(val, (int, float)):
                return float(val)
        if name in self.alias_to_cell:
            target_ref = self.alias_to_cell[name]
            return self.get_cell_value(target_ref)
        upper_name = name.upper()
        if upper_name in self.cells:
            return self.get_cell_value(upper_name)
        raise NameError(f"Identifiant ou cellule inconnue : '{name}'")

    def _eval_ast_unary(self, node: ast.UnaryOp) -> float:
        operand_val = self._eval_ast_node(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +operand_val
        if isinstance(node.op, ast.USub):
            return -operand_val
        raise ValueError("Opérateur unaire non supporté")

    def _eval_ast_binop(self, node: ast.BinOp) -> float:
        left_val = self._eval_ast_node(node.left)
        right_val = self._eval_ast_node(node.right)
        if isinstance(node.op, ast.Add):
            return left_val + right_val
        if isinstance(node.op, ast.Sub):
            return left_val - right_val
        if isinstance(node.op, ast.Mult):
            return left_val * right_val
        if isinstance(node.op, ast.Div):
            if abs(right_val) < 1e-15:
                raise ZeroDivisionError("Division par zéro (#DIV/0)")
            return left_val / right_val
        if isinstance(node.op, ast.Pow):
            return left_val ** right_val
        raise ValueError("Opérateur binaire non supporté")

    def _eval_ast_call(self, node: ast.Call) -> float:
        if isinstance(node.func, ast.Name):
            func_name = node.func.id.lower()
            if func_name in self.ALLOWED_MATH_NAMES:
                func = self.ALLOWED_MATH_NAMES[func_name]
                if callable(func):
                    args = [self._eval_ast_node(arg) for arg in node.args]
                    return float(func(*args))
        raise ValueError(f"Fonction non autorisée ou inconnue : {ast.dump(node.func)}")

    def _eval_ast_node(self, node: ast.AST) -> float:
        """Évalue récursivement les nœuds de l'AST autorisés."""
        if isinstance(node, ast.Constant):
            return self._eval_ast_constant(node)
        if isinstance(node, ast.Name):
            return self._eval_ast_name(node)
        if isinstance(node, ast.UnaryOp):
            return self._eval_ast_unary(node)
        if isinstance(node, ast.BinOp):
            return self._eval_ast_binop(node)
        if isinstance(node, ast.Call):
            return self._eval_ast_call(node)
        raise ValueError(f"Nœud d'expression non supporté : {type(node).__name__}")

    def to_csv(self) -> str:
        """Exporte les cellules du tableur au format CSV standard."""
        lines: List[str] = []
        for ref in sorted(self.cells.keys()):
            cell = self.cells[ref]
            alias_str = cell.alias or ""
            lines.append(f"{ref},{cell.raw_content},{cell.computed_value},{alias_str}")
        return "\n".join(lines)

    def from_csv(self, csv_data: str) -> None:
        """Charge un tableur depuis des données CSV sérialisées."""
        for line in csv_data.strip().splitlines():
            parts = line.split(",")
            if len(parts) >= 2:
                ref = parts[0].strip()
                content = parts[1].strip()
                self.set_cell(ref, content)
                if len(parts) >= 4 and parts[3].strip():
                    self.set_alias(ref, parts[3].strip())


class SpreadsheetWidget:
    """
    Interface graphique pour le tableur paramétrique (FreeCAD Spreadsheet Workbench).
    Fonctionne en mode fenêtré ou headless.
    """

    def __init__(self, spreadsheet: Optional[ParametricSpreadsheet] = None) -> None:
        """Initialise le composant d'interface tableur."""
        self.model = spreadsheet or ParametricSpreadsheet()
        self._qt_widget: Optional[QWidget] = None
        if PYSIDE_AVAILABLE:
            self._init_qt_ui()

    def _init_qt_ui(self) -> None:
        """Initialise les composants Qt si la bibliothèque est présente."""
        self._qt_widget = QWidget()
        layout = QVBoxLayout(self._qt_widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Barre supérieure : Cellule active, Alias, Formule
        top_bar = QHBoxLayout()
        self.cell_label = QLabel("A1 :")
        self.cell_label.setFixedWidth(45)
        self.alias_edit = QLineEdit()
        self.alias_edit.setPlaceholderText("Alias (ex: RayonBase)")
        self.formula_edit = QLineEdit()
        self.formula_edit.setPlaceholderText("Formule ou valeur (ex: =10*2)")
        self.apply_btn = QPushButton("Appliquer")

        top_bar.addWidget(self.cell_label)
        top_bar.addWidget(self.alias_edit)
        top_bar.addWidget(self.formula_edit, 1)
        top_bar.addWidget(self.apply_btn)
        layout.addLayout(top_bar)

        # Grille tabulaire
        self.table = QTableWidget(self.model.rows, self.model.cols)
        col_headers = [cell_coords_to_name(1, c)[:-1] for c in range(self.model.cols)]
        self.table.setHorizontalHeaderLabels(col_headers)
        row_headers = [str(r + 1) for r in range(self.model.rows)]
        self.table.setVerticalHeaderLabels(row_headers)
        layout.addWidget(self.table)

        self._current_cell_ref: str = "A1"
        self.table.currentCellChanged.connect(self._on_cell_selection_changed)
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        self.formula_edit.returnPressed.connect(self._on_apply_clicked)
        self.alias_edit.returnPressed.connect(self._on_apply_clicked)

        self.refresh_table()

    def _on_cell_selection_changed(self, row: int, col: int, _p_row: int, _p_col: int) -> None:
        """Met à jour les champs d'édition lors de la sélection d'une cellule."""
        if row < 0 or col < 0:
            return
        ref = cell_coords_to_name(row + 1, col)
        self._current_cell_ref = ref
        self.cell_label.setText(f"{ref} :")
        self.formula_edit.setText(self.model.get_cell_raw(ref))
        cell = self.model.cells.get(ref)
        self.alias_edit.setText(cell.alias if cell and cell.alias else "")

    def _on_apply_clicked(self) -> None:
        """Applique la formule et l'alias saisis pour la cellule active."""
        ref = self._current_cell_ref
        formula = self.formula_edit.text().strip()
        alias = self.alias_edit.text().strip()

        if formula:
            self.model.set_cell(ref, formula)
        if alias:
            try:
                self.model.set_alias(ref, alias)
            except ValueError:
                pass
        self.refresh_table()

    def refresh_table(self) -> None:
        """Rafraîchit l'affichage de l'ensemble des cellules de la grille."""
        if not PYSIDE_AVAILABLE or self.table is None:
            return
        self.table.blockSignals(True)
        for ref, cell in self.model.cells.items():
            try:
                row, col = name_to_cell_coords(ref)
                r_idx = row - 1
                c_idx = col
                if 0 <= r_idx < self.model.rows and 0 <= c_idx < self.model.cols:
                    item = self.table.item(r_idx, c_idx)
                    if not item:
                        item = QTableWidgetItem()
                        self.table.setItem(r_idx, c_idx, item)
                    if cell.has_error:
                        item.setText(f"#ERR: {cell.error_message}")
                    else:
                        val = cell.computed_value
                        display = f"{val:.2f}" if abs(val - round(val)) > 1e-4 else f"{int(round(val))}"
                        if cell.alias:
                            display += f" [{cell.alias}]"
                        item.setText(display)
            except Exception:
                continue
        self.table.blockSignals(False)

    def get_widget(self) -> Optional[QWidget]:
        """Retourne le widget Qt pour intégration dans la fenêtre principale."""
        return self._qt_widget
