"""
Passerelle ECAD / MCAD & Intégration de Circuits Imprimés (KiCadStepUp Parity).
Permet de concevoir des cartes électroniques (PCB) multi-couches avec composants 3D (CMS/SMD),
analyser les fichiers Gerber RS-274X et KiCad (.kicad_pcb),
et vérifier les collisions et jeux mécaniques avec les boîtiers électroniques.
Typage statique exhaustif et architecture modulaire sans Any ni object.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import math
import os
import re
from typing import Dict, List, Tuple, Optional, Sequence, Union
import numpy as np

from src.core.nexus_kernel.hybrid_solid import NexusSolid
from src.specialized.ecad_thermal_twin import CopperTrace, SMTComponent, ECADThermalTwin


@dataclass
class GerberAperture:
    """Définition d'aperture normalisée RS-274X."""
    aperture_id: int
    shape: str
    dim_x: float
    dim_y: float = 0.0
    hole_diameter: float = 0.0


@dataclass
class GerberTraceSegment:
    """Segment de piste vectoriel extrait d'un fichier Gerber."""
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    width_mm: float
    aperture_id: int
    layer: str = ""


@dataclass
class GerberFlash:
    """Flash d'aperture (pastille CMS, via, point de test) extrait d'un fichier Gerber."""
    x: float
    y: float
    aperture_id: int
    shape: str
    dim_x: float
    dim_y: float
    layer: str = ""


@dataclass
class GerberLayerData:
    """Conteneur des éléments géométriques extraits d'une couche Gerber."""
    layer_name: str
    traces: List[GerberTraceSegment] = field(default_factory=list)
    flashes: List[GerberFlash] = field(default_factory=list)
    bounds: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    width_mm: float = 0.0
    height_mm: float = 0.0


class RS274XParser:
    """
    Analyseur syntaxique et géométrique exhaustif pour fichiers Gerber RS-274X.
    Prend en charge les formats métrique/impérial, les apertures standard (C, R, O, P),
    les interpolations linéaires (D01), déplacements (D02), et flashs (D03).
    """

    def __init__(self) -> None:
        self.scale_x: float = 100000.0
        self.scale_y: float = 100000.0
        self.unit_factor: float = 1.0
        self.apertures: Dict[int, GerberAperture] = {}
        self.current_aperture_id: int = 10
        self.cur_x: float = 0.0
        self.cur_y: float = 0.0
        self.all_x: List[float] = []
        self.all_y: List[float] = []

    def parse_string(self, content: str, layer_name: str = "Unknown") -> GerberLayerData:
        """Analyse le contenu brut d'un fichier Gerber RS-274X."""
        self._reset_state()
        self._parse_extended_headers(content)

        traces: List[GerberTraceSegment] = []
        flashes: List[GerberFlash] = []

        clean_content = re.sub(r"%[^%]+%", "", content)
        for block in clean_content.split("*"):
            clean_block = block.strip()
            self._process_data_block(clean_block, traces, flashes, layer_name)

        min_x = min(self.all_x) if self.all_x else 0.0
        max_x = max(self.all_x) if self.all_x else 0.0
        min_y = min(self.all_y) if self.all_y else 0.0
        max_y = max(self.all_y) if self.all_y else 0.0

        return GerberLayerData(
            layer_name=layer_name,
            traces=traces,
            flashes=flashes,
            bounds=(min_x, min_y, max_x, max_y),
            width_mm=max(0.0, max_x - min_x),
            height_mm=max(0.0, max_y - min_y)
        )

    def parse_file(self, file_path: str, layer_name: str = "") -> GerberLayerData:
        """Charge et analyse un fichier Gerber sur disque."""
        effective_layer = layer_name or os.path.basename(file_path)
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read(25_000_000)
        return self.parse_string(content, layer_name=effective_layer)

    def _reset_state(self) -> None:
        """Réinitialise l'état du parseur."""
        self.scale_x = 100000.0
        self.scale_y = 100000.0
        self.unit_factor = 1.0
        self.apertures.clear()
        self.current_aperture_id = 10
        self.cur_x = 0.0
        self.cur_y = 0.0
        self.all_x.clear()
        self.all_y.clear()

    def _parse_extended_headers(self, content: str) -> None:
        """Parse les commandes étendues entre pourcentages %...%."""
        matches: List[str] = re.findall(r"%([^%]+)%", content, re.DOTALL)
        for ext in matches:
            for raw_cmd in ext.split("*"):
                cmd = raw_cmd.strip()
                self._dispatch_extended_command(cmd)

    def _dispatch_extended_command(self, cmd: str) -> None:
        """Achemine une commande étendue selon son préfixe."""
        if cmd.startswith("FS"):
            self._parse_format_specification(cmd)
        elif cmd.startswith("MOIN"):
            self.unit_factor = 25.4
        elif cmd.startswith("MOMM"):
            self.unit_factor = 1.0
        elif cmd.startswith("AD"):
            self._parse_aperture_definition(cmd)

    def _parse_format_specification(self, cmd: str) -> None:
        """Extrait l'échelle des coordonnées depuis %FS...%."""
        match = re.search(r"X([0-9])([0-9])Y([0-9])([0-9])", cmd)
        if match:
            dec_x = int(match.group(2))
            dec_y = int(match.group(4))
            self.scale_x = float(10 ** dec_x)
            self.scale_y = float(10 ** dec_y)

    def _parse_aperture_definition(self, cmd: str) -> None:
        """Extrait une aperture standard (C, R, O, P) depuis %ADD...%."""
        match = re.search(r"ADD([0-9]+)([A-Za-z])(?:,([0-9.X]+))?", cmd)
        if not match:
            return

        ap_id = int(match.group(1))
        shape = match.group(2).upper()
        raw_params = match.group(3) or "0.2"
        params = [float(p) for p in raw_params.split("X") if p]

        dim_x = params[0] * self.unit_factor if len(params) > 0 else 0.2
        dim_y = params[1] * self.unit_factor if len(params) > 1 else dim_x
        self.apertures[ap_id] = GerberAperture(
            aperture_id=ap_id,
            shape=shape,
            dim_x=dim_x,
            dim_y=dim_y
        )

    def _parse_coord(self, raw_str: str, scale: float) -> float:
        """Convertit une coordonnée entière ou flottante en millimètres."""
        if "." in raw_str:
            return float(raw_str) * self.unit_factor
        return (float(raw_str) / scale) * self.unit_factor

    def _process_data_block(
        self,
        block: str,
        traces: List[GerberTraceSegment],
        flashes: List[GerberFlash],
        layer_name: str
    ) -> None:
        """Traite une commande d'interpolation ou d'opération géométrique."""
        if not block or block.startswith("G04"):
            return

        ap_match = re.search(r"D([1-9][0-9]+)", block)
        if ap_match:
            self.current_aperture_id = int(ap_match.group(1))

        x_match = re.search(r"X([+-]?[0-9.]+)", block)
        y_match = re.search(r"Y([+-]?[0-9.]+)", block)
        new_x = self._parse_coord(x_match.group(1), self.scale_x) if x_match else self.cur_x
        new_y = self._parse_coord(y_match.group(1), self.scale_y) if y_match else self.cur_y

        op_match = re.search(r"D0?([123])(?![0-9])", block)
        if op_match:
            op_code = op_match.group(1)
            self._apply_operation(op_code, new_x, new_y, traces, flashes, layer_name)

        self.cur_x = new_x
        self.cur_y = new_y

    def _apply_operation(
        self,
        op_code: str,
        new_x: float,
        new_y: float,
        traces: List[GerberTraceSegment],
        flashes: List[GerberFlash],
        layer_name: str
    ) -> None:
        """Applique l'opération D01 (tracer), D02 (déplacer) ou D03 (flasher)."""
        if op_code == "1":
            ap = self.apertures.get(self.current_aperture_id, GerberAperture(self.current_aperture_id, "C", 0.2))
            traces.append(GerberTraceSegment(
                start_x=self.cur_x,
                start_y=self.cur_y,
                end_x=new_x,
                end_y=new_y,
                width_mm=ap.dim_x,
                aperture_id=ap.aperture_id,
                layer=layer_name
            ))
            self.all_x.extend([self.cur_x, new_x])
            self.all_y.extend([self.cur_y, new_y])
        elif op_code == "3":
            ap = self.apertures.get(self.current_aperture_id, GerberAperture(self.current_aperture_id, "C", 0.5))
            flashes.append(GerberFlash(
                x=new_x,
                y=new_y,
                aperture_id=ap.aperture_id,
                shape=ap.shape,
                dim_x=ap.dim_x,
                dim_y=ap.dim_y,
                layer=layer_name
            ))
            self.all_x.append(new_x)
            self.all_y.append(new_y)


@dataclass
class KiCadNode:
    """Nœud de l'arbre d'expressions S-expression de KiCad (.kicad_pcb)."""
    tag: str
    args: List[str] = field(default_factory=list)
    children: List[KiCadNode] = field(default_factory=list)

    def child(self, tag: str) -> Optional[KiCadNode]:
        """Retourne le premier sous-nœud portant le tag spécifié."""
        for ch in self.children:
            if ch.tag == tag:
                return ch
        return None

    def children_named(self, tag: str) -> List[KiCadNode]:
        """Retourne tous les sous-nœuds portant le tag spécifié."""
        return [ch for ch in self.children if ch.tag == tag]


@dataclass
class KiCadPCBData:
    """Structure de données complète issue de l'analyse d'un fichier .kicad_pcb."""
    width_mm: float
    height_mm: float
    thickness_mm: float
    components: List[PCBComponent3D] = field(default_factory=list)
    traces: List[CopperTrace] = field(default_factory=list)
    outline_points: List[Tuple[float, float]] = field(default_factory=list)


class KiCadPCBParser:
    """
    Analyseur de fichiers KiCad PCB (.kicad_pcb) basé sur un moteur S-expression.
    Extrait le contour de carte (Edge.Cuts), les empreintes de composants (footprints / modules),
    et les segments de pistes de cuivre (segments F.Cu / B.Cu).
    """

    def parse_string(self, content: str) -> KiCadPCBData:
        """Analyse le texte brut d'un fichier .kicad_pcb."""
        tokens = self.tokenize(content)
        root = self.parse_tokens(tokens)
        if root is None or root.tag != "kicad_pcb":
            return KiCadPCBData(width_mm=100.0, height_mm=80.0, thickness_mm=1.6)

        thickness_mm = self._extract_thickness(root)
        width_mm, height_mm, outline_points = self._extract_board_dimensions(root)
        components = self._extract_footprints(root)
        traces = self._extract_traces(root)

        return KiCadPCBData(
            width_mm=width_mm,
            height_mm=height_mm,
            thickness_mm=thickness_mm,
            components=components,
            traces=traces,
            outline_points=outline_points
        )

    def parse_file(self, file_path: str) -> KiCadPCBData:
        """Charge et analyse un fichier .kicad_pcb sur disque."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read(25_000_000)
        return self.parse_string(content)

    def tokenize(self, text: str) -> List[str]:
        """Découpe le texte S-expression en une liste de tokens lexicaux."""
        tokens: List[str] = []
        i = 0
        n = len(text)
        backslash = chr(92)
        quote = chr(34)
        delimiters = ("(", ")", quote, chr(13), chr(10))
        while i < n:
            c = text[i]
            if c.isspace():
                i += 1
            elif c in "()":
                tokens.append(c)
                i += 1
            elif c == quote:
                j = i + 1
                while j < n and text[j] != quote:
                    if text[j] == backslash:
                        j += 1
                    j += 1
                tokens.append(text[i + 1:j])
                i = j + 1
            else:
                j = i
                while j < n and not text[j].isspace() and text[j] not in delimiters:
                    j += 1
                tokens.append(text[i:j])
                i = j
        return tokens

    def parse_tokens(self, tokens: List[str]) -> Optional[KiCadNode]:
        """Construit l'arbre syntaxique KiCadNode à partir des jetons lexicaux."""
        stack: List[KiCadNode] = []
        root: Optional[KiCadNode] = None

        idx = 0
        total = len(tokens)
        while idx < total:
            tok = tokens[idx]
            if tok == "(":
                idx += 1
                if idx < total:
                    node = KiCadNode(tag=tokens[idx])
                    if stack:
                        stack[-1].children.append(node)
                    stack.append(node)
            elif tok == ")":
                if stack:
                    popped = stack.pop()
                    if not stack:
                        root = popped
            else:
                if stack:
                    stack[-1].args.append(tok)
            idx += 1

        return root

    def _extract_thickness(self, root: KiCadNode) -> float:
        """Extrait l'épaisseur du substrat depuis (general (thickness ...))."""
        general = root.child("general")
        if general:
            thick_node = general.child("thickness")
            if thick_node and thick_node.args:
                return float(thick_node.args[0])
        return 1.6

    def _extract_board_dimensions(self, root: KiCadNode) -> Tuple[float, float, List[Tuple[float, float]]]:
        """Extrait les dimensions de la carte à partir des éléments du calque Edge.Cuts."""
        pts: List[Tuple[float, float]] = []

        for line in root.children_named("gr_line"):
            layer_node = line.child("layer")
            if layer_node and "Edge.Cuts" in layer_node.args:
                self._collect_start_end(line, pts)

        for rect in root.children_named("gr_rect"):
            layer_node = rect.child("layer")
            if layer_node and "Edge.Cuts" in layer_node.args:
                self._collect_start_end(rect, pts)

        if not pts:
            return 100.0, 80.0, []

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        w = max(xs) - min(xs)
        h = max(ys) - min(ys)
        return float(w), float(h), pts

    def _collect_start_end(self, node: KiCadNode, pts: List[Tuple[float, float]]) -> None:
        """Extrait les points (start) et (end) d'un élément graphique."""
        st = node.child("start")
        en = node.child("end")
        if st and len(st.args) >= 2:
            pts.append((float(st.args[0]), float(st.args[1])))
        if en and len(en.args) >= 2:
            pts.append((float(en.args[0]), float(en.args[1])))

    def _extract_footprints(self, root: KiCadNode) -> List[PCBComponent3D]:
        """Extrait la liste des composants (footprint ou module) de la carte."""
        components: List[PCBComponent3D] = []
        fp_nodes = root.children_named("footprint") + root.children_named("module")

        for fp in fp_nodes:
            pkg_name = fp.args[0] if fp.args else "SMD_Component"
            ref = self._find_footprint_reference(fp)
            pos_x, pos_y, rot = self._find_footprint_pose(fp)
            dim_w, dim_l, dim_h = self._estimate_package_dims(pkg_name)

            components.append(PCBComponent3D(
                designator=ref,
                package=pkg_name,
                pos_x=pos_x,
                pos_y=pos_y,
                width_x=dim_w,
                length_y=dim_l,
                height_z=dim_h,
                rotation_deg=rot
            ))

        return components

    def _find_footprint_reference(self, fp: KiCadNode) -> str:
        """Trouve le désignateur de référence (U1, R12, etc.) d'une empreinte."""
        for prop in fp.children_named("property"):
            if len(prop.args) >= 2 and prop.args[0] == "Reference":
                return prop.args[1]
        for txt in fp.children_named("fp_text"):
            if len(txt.args) >= 2 and txt.args[0] == "reference":
                return txt.args[1]
        return "U?"

    def _find_footprint_pose(self, fp: KiCadNode) -> Tuple[float, float, float]:
        """Extrait la position (x, y) et la rotation d'une empreinte."""
        at_node = fp.child("at")
        if at_node and len(at_node.args) >= 2:
            px = float(at_node.args[0])
            py = float(at_node.args[1])
            rot = float(at_node.args[2]) if len(at_node.args) >= 3 else 0.0
            return px, py, rot
        return 0.0, 0.0, 0.0

    def _estimate_package_dims(self, pkg_name: str) -> Tuple[float, float, float]:
        """Estime la largeur, longueur et hauteur 3D d'un boîtier à partir de son nom normalisé."""
        p = pkg_name.upper()
        if "0805" in p:
            return 2.0, 1.25, 1.0
        if "0603" in p:
            return 1.6, 0.8, 0.8
        if "1206" in p:
            return 3.2, 1.6, 1.2
        if "SOIC" in p or "SO-" in p:
            return 5.0, 4.0, 1.8
        if "QFP" in p:
            return 12.0, 12.0, 2.5
        if "QFN" in p:
            return 6.0, 6.0, 1.0
        if "DPAK" in p or "TO-220" in p:
            return 10.0, 10.0, 4.5
        return 5.0, 5.0, 2.0

    def _extract_traces(self, root: KiCadNode) -> List[CopperTrace]:
        """Extrait les segments de pistes de cuivre du fichier KiCad."""
        traces: List[CopperTrace] = []
        for idx, seg in enumerate(root.children_named("segment")):
            st = seg.child("start")
            en = seg.child("end")
            wd = seg.child("width")
            ly = seg.child("layer")

            if st and en and len(st.args) >= 2 and len(en.args) >= 2:
                x1 = float(st.args[0])
                y1 = float(st.args[1])
                x2 = float(en.args[0])
                y2 = float(en.args[1])
                width = float(wd.args[0]) if wd and wd.args else 0.25
                layer = ly.args[0] if ly and ly.args else "F.Cu"
                length = math.hypot(x2 - x1, y2 - y1)

                traces.append(CopperTrace(
                    trace_id=f"SEG_{idx}",
                    layer_name=layer,
                    length_mm=length,
                    width_mm=width,
                    start_x_mm=x1,
                    start_y_mm=y1,
                    end_x_mm=x2,
                    end_y_mm=y2
                ))

        return traces


@dataclass
class PCBComponent3D:
    """Composant électronique monté sur la carte (CMS / Traversant)."""
    designator: str = "U1"
    ref_des: str = ""
    package: str = "QFP"
    pos_x: float = 0.0
    pos_y: float = 0.0
    height_z: float = 2.0
    width_x: float = 5.0
    length_y: float = 5.0
    pos_x_mm: float = 0.0
    pos_y_mm: float = 0.0
    width_mm: float = 5.0
    length_mm: float = 5.0
    height_mm: float = 2.0
    rotation_deg: float = 0.0

    def __post_init__(self) -> None:
        if not self.ref_des:
            self.ref_des = self.designator
        if not self.designator:
            self.designator = self.ref_des

        if self.pos_x != 0.0 and self.pos_x_mm == 0.0:
            self.pos_x_mm = self.pos_x
        if self.pos_y != 0.0 and self.pos_y_mm == 0.0:
            self.pos_y_mm = self.pos_y
        if self.width_x != 5.0 and self.width_mm == 5.0:
            self.width_mm = self.width_x
        if self.length_y != 5.0 and self.length_mm == 5.0:
            self.length_mm = self.length_y
        if self.height_z != 2.0 and self.height_mm == 2.0:
            self.height_mm = self.height_z


class PCBBoard:
    """Carte de circuit imprimé (PCB) paramétrique avec composants et perçages."""

    def __init__(
        self,
        name: str = "Board",
        board_id: Optional[str] = None,
        width: float = 100.0,
        height: float = 80.0,
        thickness: float = 1.6,
        width_mm: Optional[float] = None,
        height_mm: Optional[float] = None,
        thickness_mm: Optional[float] = None,
        layer_count: int = 4,
        components: Optional[List[PCBComponent3D]] = None,
        traces: Optional[List[CopperTrace]] = None,
        outline_points: Optional[List[Tuple[float, float]]] = None
    ) -> None:
        self.board_id: str = board_id or name
        self.name: str = self.board_id
        self.width_mm: float = float(width_mm if width_mm is not None else width)
        self.height_mm: float = float(height_mm if height_mm is not None else height)
        self.thickness_mm: float = float(thickness_mm if thickness_mm is not None else thickness)
        self.layer_count: int = int(layer_count)
        self.components: List[PCBComponent3D] = components or []
        self.traces: List[CopperTrace] = traces or []
        self.outline_points: List[Tuple[float, float]] = outline_points or []

    def add_component(self, comp: PCBComponent3D) -> None:
        """Ajoute un composant électronique sur la face supérieure de la carte."""
        self.components.append(comp)

    def add_trace(self, trace: CopperTrace) -> None:
        """Ajoute une piste de cuivre conductrice à la carte."""
        self.traces.append(trace)

    def generate_3d_assembly(self) -> NexusSolid:
        """Génère l'assemblage solide volumique étanche de la carte et ses composants."""
        return self.to_solid()

    def to_solid(self) -> NexusSolid:
        """Génère le solide volumique de la carte assemblée avec ses composants."""
        board_solid = NexusSolid.make_box(
            self.width_mm, self.height_mm, self.thickness_mm,
            name=f"Substrate_{self.board_id}"
        )

        for comp in self.components:
            comp_box = NexusSolid.make_box(
                comp.width_mm, comp.length_mm, comp.height_mm,
                name=f"Comp_{comp.ref_des}"
            )
            m_comp = comp_box.internal_manifold.translate([
                comp.pos_x_mm, comp.pos_y_mm, self.thickness_mm
            ])
            comp_solid = NexusSolid(name=f"Comp_{comp.ref_des}", internal_manifold=m_comp)
            board_solid = board_solid.union(comp_solid)

        return board_solid

    def check_enclosure_clearance(
        self,
        enclosure_solid: NexusSolid,
        min_clearance_mm: float = 2.0
    ) -> List[Tuple[str, float]]:
        """Vérifie les interférences entre composants et boîtier mécanique."""
        conflicts: List[Tuple[str, float]] = []
        enc_min, enc_max = enclosure_solid.bounding_box()
        ceiling_z = enc_max[2]

        for comp in self.components:
            top_z = self.thickness_mm + comp.height_mm
            clearance = ceiling_z - top_z
            if clearance < min_clearance_mm:
                conflicts.append((comp.ref_des, float(clearance)))

        return conflicts

    def create_thermal_twin(
        self,
        default_trace_current_amps: float = 1.0,
        default_component_power_w: float = 0.5
    ) -> ECADThermalTwin:
        """Instancie un jumeau numérique thermique synchronisé avec le layout PCB."""
        twin = ECADThermalTwin(
            board_width_mm=self.width_mm,
            board_length_mm=self.height_mm,
            board_thickness_mm=self.thickness_mm,
            layer_count=self.layer_count
        )

        for tr in self.traces:
            if tr.current_amps == 1.0 and default_trace_current_amps != 1.0:
                tr.current_amps = default_trace_current_amps
            twin.add_copper_trace(tr)

        for comp in self.components:
            p_w = default_component_power_w
            pkg = comp.package.upper()
            if "QFP" in pkg or "MCU" in pkg:
                p_w = 1.5
            elif "DPAK" in pkg or "TO-220" in pkg:
                p_w = 2.5
            elif "0805" in pkg or "0603" in pkg:
                p_w = 0.1

            smt_comp = SMTComponent(
                designator=comp.designator,
                package_name=comp.package,
                position_x_mm=comp.pos_x_mm,
                position_y_mm=comp.pos_y_mm,
                power_dissipation_watts=p_w
            )
            twin.add_component(smt_comp)

        return twin

    @classmethod
    def from_gerber(
        cls,
        outline_gerber: str,
        copper_gerber: Optional[str] = None,
        name: str = "GerberBoard",
        thickness_mm: float = 1.6,
        layer_count: int = 2
    ) -> PCBBoard:
        """Instancie un PCB à partir de couches Gerber RS-274X."""
        parser = RS274XParser()
        outline_data = parser.parse_string(outline_gerber, layer_name="Edge.Cuts")

        traces: List[CopperTrace] = []
        if copper_gerber:
            cu_parser = RS274XParser()
            cu_data = cu_parser.parse_string(copper_gerber, layer_name="F.Cu")
            for idx, tr in enumerate(cu_data.traces):
                length = math.hypot(tr.end_x - tr.start_x, tr.end_y - tr.start_y)
                traces.append(CopperTrace(
                    trace_id=f"GERBER_TR_{idx}",
                    layer_name="F.Cu",
                    length_mm=length,
                    width_mm=tr.width_mm,
                    start_x_mm=tr.start_x,
                    start_y_mm=tr.start_y,
                    end_x_mm=tr.end_x,
                    end_y_mm=tr.end_y
                ))

        width = outline_data.width_mm if outline_data.width_mm > 0.0 else 100.0
        height = outline_data.height_mm if outline_data.height_mm > 0.0 else 80.0

        return cls(
            name=name,
            width=width,
            height=height,
            thickness=thickness_mm,
            layer_count=layer_count,
            traces=traces
        )

    @classmethod
    def from_kicad_pcb(cls, content_or_path: str, name: str = "KiCadBoard") -> PCBBoard:
        """Instancie un PCB à partir d'un fichier ou contenu .kicad_pcb."""
        parser = KiCadPCBParser()
        if os.path.isfile(content_or_path):
            data = parser.parse_file(content_or_path)
        else:
            data = parser.parse_string(content_or_path)

        return cls(
            name=name,
            width=data.width_mm,
            height=data.height_mm,
            thickness=data.thickness_mm,
            components=data.components,
            traces=data.traces,
            outline_points=data.outline_points
        )


def verify_enclosure_clearance(
    board: PCBBoard,
    enclosure_max_internal_height: float
) -> bool:
    """Vérifie si tous les composants de la carte s'insèrent dans le boîtier."""
    for comp in board.components:
        top_elevation = board.thickness_mm + comp.height_mm
        if top_elevation > enclosure_max_internal_height:
            return False
    return True


def verify_component_clearance_matrix(
    board: PCBBoard,
    min_spacing_mm: float = 0.5
) -> List[Tuple[str, str, float]]:
    """Détecte les interférences et chevauchements 2D entre composants sur la carte."""
    violations: List[Tuple[str, str, float]] = []
    n = len(board.components)
    for i in range(n):
        c1 = board.components[i]
        for j in range(i + 1, n):
            c2 = board.components[j]
            dx = abs(c1.pos_x_mm - c2.pos_x_mm)
            dy = abs(c1.pos_y_mm - c2.pos_y_mm)
            req_x = (c1.width_mm + c2.width_mm) * 0.5 + min_spacing_mm
            req_y = (c1.length_mm + c2.length_mm) * 0.5 + min_spacing_mm
            if dx < req_x and dy < req_y:
                clearance = min(req_x - dx, req_y - dy)
                violations.append((c1.ref_des, c2.ref_des, float(clearance)))
    return violations
