"""
Ruban d'outils supérieur (Ribbon Bar) inspiré d'Autodesk Fusion 360.
Organisé en 9 ateliers : FICHIER, CONCEPTION, ESQUISSE, TÔLERIE, ASSEMBLAGE, SIMULATION, FABRICATION, DESSIN 2D, AFFICHAGE, EXPORT.
"""

from __future__ import annotations
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QTabWidget, QHBoxLayout, QVBoxLayout,
    QToolButton, QLabel, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal


class RibbonButton(QToolButton):
    """Bouton grand format du ruban d'outils avec icône et libellé."""

    def __init__(self, text: str, emoji_icon: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setText(f"{emoji_icon}\n{text}")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setFixedSize(84, 66)
        self.setStyleSheet("""
            QToolButton {
                background-color: #26282e;
                color: #e0e2e8;
                border: 1px solid #363940;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
                text-align: center;
                padding: 2px 2px;
            }
            QToolButton:hover {
                background-color: #32353d;
                border-color: #00a2ff;
                color: #ffffff;
            }
            QToolButton:pressed {
                background-color: #007acc;
            }
        """)


def _create_ribbon_group(title: str, buttons: list[QToolButton]) -> QWidget:
    """Crée une section d'outils encadrée avec son intitulé en bas."""
    group_widget = QWidget()
    vbox = QVBoxLayout(group_widget)
    vbox.setContentsMargins(4, 2, 4, 2)
    vbox.setSpacing(2)

    btn_row = QHBoxLayout()
    btn_row.setContentsMargins(0, 0, 0, 0)
    btn_row.setSpacing(4)
    for btn in buttons:
        btn_row.addWidget(btn)
    vbox.addLayout(btn_row)

    lbl = QLabel(title.upper())
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet("color: #7b8190; font-size: 9px; font-weight: bold; letter-spacing: 1px;")
    vbox.addWidget(lbl)

    wrapper = QWidget()
    h_wrap = QHBoxLayout(wrapper)
    h_wrap.setContentsMargins(0, 0, 0, 0)
    h_wrap.addWidget(group_widget)

    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setStyleSheet("color: #2f3239;")
    h_wrap.addWidget(sep)

    return wrapper


class CADRibbonBar(QTabWidget):
    """Barre de ruban principale avec tous les ateliers de Fusion 360."""

    # Fichier & Paramètres fx
    save_project_requested = Signal()
    load_project_requested = Signal()
    manage_parameters_requested = Signal()

    # Solide & Conception avancée
    create_box_requested = Signal()
    create_cylinder_requested = Signal()
    create_sphere_requested = Signal()
    create_cone_requested = Signal()
    create_torus_requested = Signal()
    create_wedge_requested = Signal()
    create_pipe_requested = Signal()
    extrude_requested = Signal()
    revolve_requested = Signal()
    loft_requested = Signal()
    sweep_requested = Signal()
    hole_requested = Signal()
    shell_requested = Signal()
    pattern_requested = Signal()
    combine_requested = Signal()
    fillet_requested = Signal()
    chamfer_requested = Signal()
    draft_requested = Signal()
    press_pull_requested = Signal()
    modifier_stack_requested = Signal()

    # Quincaillerie & Visserie ISO (FreeCAD Fasteners Workbench)
    create_fastener_requested = Signal(str)

    # Inspection & Métrologie 3D (FreeCAD Measure & Section Workbench)
    measure_requested = Signal()
    section_cut_requested = Signal()

    # Analyse & Réparation de Maillage (FreeCAD Mesh Workbench)
    mesh_analysis_requested = Signal()

    # Esquisse
    new_sketch_xy_requested = Signal()
    new_sketch_xz_requested = Signal()
    new_sketch_yz_requested = Signal()
    add_sketch_rect_requested = Signal()
    add_sketch_circle_requested = Signal()
    add_sketch_slot_requested = Signal()
    add_sketch_polygon_requested = Signal()
    add_sketch_ellipse_requested = Signal()
    solve_constraints_requested = Signal()
    toggle_sketch_mode_requested = Signal()

    # Tôlerie (Sheet Metal)
    create_sheet_metal_requested = Signal()
    flat_pattern_requested = Signal()
    export_dxf_laser_requested = Signal()

    # Assemblage
    add_joint_requested = Signal()
    check_interference_requested = Signal()

    # Simulation FEA
    run_fea_requested = Signal()
    material_selector_requested = Signal()

    # Rendu Photoréaliste PBR (Render Studio)
    open_render_studio_requested = Signal()

    # CAM / Fabrication
    cam_facing_requested = Signal()
    cam_contour_requested = Signal()
    export_gcode_requested = Signal()

    # Mise en Plan 2D (Drawing)
    generate_drawing_requested = Signal()
    export_drawing_svg_requested = Signal()

    # Affichage
    fit_view_requested = Signal()
    home_view_requested = Signal()
    toggle_ortho_requested = Signal()

    # Export 3D
    export_stl_requested = Signal()
    export_obj_requested = Signal()
    export_ply_requested = Signal()
    export_step_requested = Signal()

    # Métiers Spécialisés (BIM, Aérodynamique, Thermique ECAD)
    bim_generate_requested = Signal()
    aero_analysis_requested = Signal()
    ecad_thermal_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(105)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._init_file_group()
        self._init_solid_tab()
        self._init_sketch_tab()
        self._init_sheet_metal_tab()
        self._init_fasteners_tab()
        self._init_assembly_tab()
        self._init_simulation_tab()
        self._init_render_tab()
        self._init_cam_tab()
        self._init_drawing_tab()
        self._init_inspection_tab()
        self._init_mesh_tab()
        self._init_specialized_tab()
        self._init_tools_tab()
        self._init_export_tab()

    def _init_file_group(self) -> None:
        """Onglet PROJET & PARAMÈTRES FX."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_save = RibbonButton("Sauvegarder", "💾")
        btn_save.clicked.connect(self.save_project_requested.emit)
        btn_open = RibbonButton("Ouvrir", "📂")
        btn_open.clicked.connect(self.load_project_requested.emit)
        layout.addWidget(_create_ribbon_group("Fichier Projet", [btn_save, btn_open]))

        btn_fx = RibbonButton("Paramètres fx", "🧮")
        btn_fx.clicked.connect(self.manage_parameters_requested.emit)
        layout.addWidget(_create_ribbon_group("Équations", [btn_fx]))

        self.addTab(tab, "FICHIER")

    def _init_solid_tab(self) -> None:
        """Onglet CONCEPTION SOLIDE AVANCÉE."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_box = RibbonButton("Boîte", "📦")
        btn_box.clicked.connect(self.create_box_requested.emit)
        btn_cyl = RibbonButton("Cylindre", "🥫")
        btn_cyl.clicked.connect(self.create_cylinder_requested.emit)
        btn_sph = RibbonButton("Sphère", "🔮")
        btn_sph.clicked.connect(self.create_sphere_requested.emit)
        btn_ext = RibbonButton("Extrusion", "⬆️")
        btn_ext.clicked.connect(self.extrude_requested.emit)
        btn_rev = RibbonButton("Révolution", "🔄")
        btn_rev.clicked.connect(self.revolve_requested.emit)
        btn_cone = RibbonButton("Cône", "📐")
        btn_cone.clicked.connect(self.create_cone_requested.emit)
        btn_torus = RibbonButton("Tore", "🍩")
        btn_torus.clicked.connect(self.create_torus_requested.emit)
        btn_wedge = RibbonButton("Coin", "📐")
        btn_wedge.clicked.connect(self.create_wedge_requested.emit)
        btn_pipe = RibbonButton("Tuyau 3D", "🧪")
        btn_pipe.clicked.connect(self.create_pipe_requested.emit)
        btn_loft = RibbonButton("Lissage", "🏺")
        btn_loft.clicked.connect(self.loft_requested.emit)
        btn_swp = RibbonButton("Balayage", "➰")
        btn_swp.clicked.connect(self.sweep_requested.emit)

        layout.addWidget(_create_ribbon_group("Créer (PartDesign)", [btn_box, btn_cyl, btn_sph, btn_cone, btn_torus, btn_wedge, btn_pipe, btn_ext, btn_rev, btn_loft, btn_swp]))

        btn_hole = RibbonButton("Perçage", "🕳️")
        btn_hole.clicked.connect(self.hole_requested.emit)
        btn_shell = RibbonButton("Évidement", "🐚")
        btn_shell.clicked.connect(self.shell_requested.emit)
        btn_fillet = RibbonButton("Congé", "🟢")
        btn_fillet.clicked.connect(self.fillet_requested.emit)
        btn_chamfer = RibbonButton("Chanfrein", "📐")
        btn_chamfer.clicked.connect(self.chamfer_requested.emit)
        btn_draft = RibbonButton("Dépouille", "📐")
        btn_draft.clicked.connect(self.draft_requested.emit)
        btn_pat = RibbonButton("Répétition", "🪞")
        btn_pat.clicked.connect(self.pattern_requested.emit)
        btn_comb = RibbonButton("Combiner", "🔀")
        btn_comb.clicked.connect(self.combine_requested.emit)
        btn_press_pull = RibbonButton("Press-Pull", "🎯")
        btn_press_pull.setToolTip("Modélisation directe Press-Pull Fusion 360 (Q)")
        btn_press_pull.clicked.connect(self.press_pull_requested.emit)
        btn_mod_stack = RibbonButton("Modificateurs", "🧩")
        btn_mod_stack.setToolTip("Pile de modificateurs non-destructifs style Blender")
        btn_mod_stack.clicked.connect(self.modifier_stack_requested.emit)

        layout.addWidget(_create_ribbon_group("Modifier", [btn_hole, btn_shell, btn_fillet, btn_chamfer, btn_draft, btn_pat, btn_comb, btn_press_pull, btn_mod_stack]))
        self.addTab(tab, "CONCEPTION")

    def _init_sketch_tab(self) -> None:
        """Onglet ESQUISSE & CONTRAINTES."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_xy = RibbonButton("Plan XY", "📐")
        btn_xy.clicked.connect(self.new_sketch_xy_requested.emit)
        btn_xz = RibbonButton("Plan XZ", "📐")
        btn_xz.clicked.connect(self.new_sketch_xz_requested.emit)
        btn_yz = RibbonButton("Plan YZ", "📐")
        btn_yz.clicked.connect(self.new_sketch_yz_requested.emit)
        layout.addWidget(_create_ribbon_group("Plans", [btn_xy, btn_xz, btn_yz]))

        btn_rect = RibbonButton("Rectangle", "▭")
        btn_rect.clicked.connect(self.add_sketch_rect_requested.emit)
        btn_circ = RibbonButton("Cercle", "◯")
        btn_circ.clicked.connect(self.add_sketch_circle_requested.emit)
        btn_slot = RibbonButton("Oblong", "💊")
        btn_slot.clicked.connect(self.add_sketch_slot_requested.emit)
        btn_poly = RibbonButton("Polygone", "⬡")
        btn_poly.clicked.connect(self.add_sketch_polygon_requested.emit)
        btn_ell = RibbonButton("Ellipse", "⬭")
        btn_ell.clicked.connect(self.add_sketch_ellipse_requested.emit)
        btn_draw = RibbonButton("Mode Stylet", "✏️")
        btn_draw.clicked.connect(self.toggle_sketch_mode_requested.emit)
        layout.addWidget(_create_ribbon_group("Dessin 2D", [btn_rect, btn_circ, btn_slot, btn_poly, btn_ell, btn_draw]))

        btn_solv = RibbonButton("Résoudre", "⚡")
        btn_solv.clicked.connect(self.solve_constraints_requested.emit)
        layout.addWidget(_create_ribbon_group("Solveur 2D", [btn_solv]))

        self.addTab(tab, "ESQUISSE")

    def _init_sheet_metal_tab(self) -> None:
        """Onglet TÔLERIE INDUSTRIELLE (SHEET METAL)."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_sm = RibbonButton("Tôle Pliée", "📑")
        btn_sm.clicked.connect(self.create_sheet_metal_requested.emit)
        btn_flat = RibbonButton("Mise à Plat", "📄")
        btn_flat.clicked.connect(self.flat_pattern_requested.emit)
        btn_dxf = RibbonButton("Laser DXF", "⚡")
        btn_dxf.clicked.connect(self.export_dxf_laser_requested.emit)

        layout.addWidget(_create_ribbon_group("Tôlerie & Pliage", [btn_sm, btn_flat, btn_dxf]))
        self.addTab(tab, "TÔLERIE")

    def _init_fasteners_tab(self) -> None:
        """Onglet QUINCAILLERIE & VISSERIE NORMALISÉE (FreeCAD Fasteners WB)."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_hex = RibbonButton("Vis Hex", "🔩")
        btn_hex.clicked.connect(lambda: self.create_fastener_requested.emit("hex_bolt"))
        btn_chc = RibbonButton("Vis CHC", "🔩")
        btn_chc.clicked.connect(lambda: self.create_fastener_requested.emit("socket_cap"))
        layout.addWidget(_create_ribbon_group("Vis Métriques ISO", [btn_hex, btn_chc]))

        btn_nut = RibbonButton("Écrou Hex", "⚙️")
        btn_nut.clicked.connect(lambda: self.create_fastener_requested.emit("hex_nut"))
        btn_wsh = RibbonButton("Rondelle", "🔘")
        btn_wsh.clicked.connect(lambda: self.create_fastener_requested.emit("washer"))
        layout.addWidget(_create_ribbon_group("Écrous & Rondelles", [btn_nut, btn_wsh]))

        self.addTab(tab, "QUINCAILLERIE")

    def _init_assembly_tab(self) -> None:
        """Onglet ASSEMBLAGE."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_joint = RibbonButton("Liaison", "🔗")
        btn_joint.clicked.connect(self.add_joint_requested.emit)
        btn_interf = RibbonButton("Collisions", "⚠️")
        btn_interf.clicked.connect(self.check_interference_requested.emit)

        layout.addWidget(_create_ribbon_group("Cinématique & Contrôle", [btn_joint, btn_interf]))
        self.addTab(tab, "ASSEMBLAGE")

    def _init_simulation_tab(self) -> None:
        """Onglet SIMULATION (FEA)."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_mat = RibbonButton("Matériaux", "🧪")
        btn_mat.clicked.connect(self.material_selector_requested.emit)
        btn_fea = RibbonButton("Calcul FEA", "📊")
        btn_fea.clicked.connect(self.run_fea_requested.emit)

        layout.addWidget(_create_ribbon_group("Structure & Contraintes", [btn_mat, btn_fea]))
        self.addTab(tab, "SIMULATION")

    def _init_render_tab(self) -> None:
        """Onglet RENDU RÉALISTE & MATÉRIAUX PBR (RENDER STUDIO)."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_studio = RibbonButton("Studio Rendu", "📸")
        btn_studio.clicked.connect(self.open_render_studio_requested.emit)

        layout.addWidget(_create_ribbon_group("Rendu Photoréaliste PBR", [btn_studio]))
        self.addTab(tab, "RENDU")

    def _init_cam_tab(self) -> None:
        """Onglet FABRICATION (CAM)."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_face = RibbonButton("Surfaçage", "🪒")
        btn_face.clicked.connect(self.cam_facing_requested.emit)
        btn_cont = RibbonButton("Contour 2D", "✂️")
        btn_cont.clicked.connect(self.cam_contour_requested.emit)
        btn_gcode = RibbonButton("G-Code CNC", "💾")
        btn_gcode.clicked.connect(self.export_gcode_requested.emit)

        layout.addWidget(_create_ribbon_group("Usinage CNC", [btn_face, btn_cont, btn_gcode]))
        self.addTab(tab, "FABRICATION")

    def _init_drawing_tab(self) -> None:
        """Onglet MISE EN PLAN 2D (DRAWING ISO)."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_draw = RibbonButton("Plan A3/A4", "📋")
        btn_draw.clicked.connect(self.generate_drawing_requested.emit)
        btn_svg = RibbonButton("Export SVG", "📐")
        btn_svg.clicked.connect(self.export_drawing_svg_requested.emit)

        layout.addWidget(_create_ribbon_group("Mise en Plan ISO 128", [btn_draw, btn_svg]))
        self.addTab(tab, "DESSIN 2D")

    def _init_inspection_tab(self) -> None:
        """Onglet INSPECTION & MÉTROLOGIE (FreeCAD Measure WB)."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_meas = RibbonButton("Mesurer 3D", "📏")
        btn_meas.clicked.connect(self.measure_requested.emit)
        btn_clear = RibbonButton("Jeux & Chocs", "💥")
        btn_clear.clicked.connect(self.measure_requested.emit)
        btn_audit = RibbonButton("Bilan Masse", "📊")
        btn_audit.clicked.connect(self.measure_requested.emit)
        btn_cut = RibbonButton("Coupe 2D", "✂️")
        btn_cut.clicked.connect(self.section_cut_requested.emit)

        layout.addWidget(_create_ribbon_group("Métrologie & Contrôle", [btn_meas, btn_clear, btn_audit, btn_cut]))
        self.addTab(tab, "INSPECTION")

    def _init_mesh_tab(self) -> None:
        """Onglet MAILLAGE & RÉPARATION 3D (FreeCAD Mesh WB)."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_diag = RibbonButton("Diagnostic", "🔬")
        btn_diag.clicked.connect(self.mesh_analysis_requested.emit)
        btn_rep = RibbonButton("Réparation", "🛠️")
        btn_rep.clicked.connect(self.mesh_analysis_requested.emit)
        btn_dec = RibbonButton("Décimation", "📉")
        btn_dec.clicked.connect(self.mesh_analysis_requested.emit)

        layout.addWidget(_create_ribbon_group("Atelier Maillage", [btn_diag, btn_rep, btn_dec]))
        self.addTab(tab, "MAILLAGE")

    def _init_specialized_tab(self) -> None:
        """Onglet MÉTIERS SPÉCIALISÉS (BIM, Aérodynamique, Thermique ECAD)."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_bim = RibbonButton("Générer BIM", "🏛️")
        btn_bim.clicked.connect(self.bim_generate_requested.emit)
        btn_aero = RibbonButton("Aérodynamique", "🌪️")
        btn_aero.clicked.connect(self.aero_analysis_requested.emit)
        btn_ecad = RibbonButton("Thermique ECAD", "⚡")
        btn_ecad.clicked.connect(self.ecad_thermal_requested.emit)

        layout.addWidget(_create_ribbon_group("Ingénierie Avancée", [btn_bim, btn_aero, btn_ecad]))
        self.addTab(tab, "MÉTIERS")

    def _init_tools_tab(self) -> None:
        """Onglet AFFICHAGE & CAMÉRA."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_fit = RibbonButton("Recadrer", "🎯")
        btn_fit.clicked.connect(self.fit_view_requested.emit)
        btn_home = RibbonButton("Vue Home", "🏠")
        btn_home.clicked.connect(self.home_view_requested.emit)
        btn_ortho = RibbonButton("Ortho / Persp", "📐")
        btn_ortho.clicked.connect(self.toggle_ortho_requested.emit)

        layout.addWidget(_create_ribbon_group("Caméra", [btn_fit, btn_home, btn_ortho]))
        self.addTab(tab, "AFFICHAGE")

    def _init_export_tab(self) -> None:
        """Onglet EXPORT 3D."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_stl = RibbonButton("STL (3D)", "🖨️")
        btn_stl.clicked.connect(self.export_stl_requested.emit)
        btn_obj = RibbonButton("Wavefront", "📄")
        btn_obj.clicked.connect(self.export_obj_requested.emit)
        btn_ply = RibbonButton("Polygon PLY", "📊")
        btn_ply.clicked.connect(self.export_ply_requested.emit)
        btn_step = RibbonButton("STEP (ISO)", "📦")
        btn_step.clicked.connect(self.export_step_requested.emit)

        layout.addWidget(_create_ribbon_group("Fichiers 3D", [btn_stl, btn_obj, btn_ply, btn_step]))
        self.addTab(tab, "EXPORT")
