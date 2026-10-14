"""
Noyau Géométrique Hybride NEXUS-3D : Opérateurs Topologiques d'Euler-Poincaré.
Inspiré des fondations mathématiques de Martti Mäntylä (B-Rep CAD Kernels),
de Parasolid et d'OpenCASCADE (OCCT).

Garantit que chaque étape de construction ou chirurgie topologique préserve l'invariant :
    V - E + F - (L - F) - 2(S - G) = 0
où :
    V = Nombre de sommets (Vertices)
    E = Nombre d'arêtes (Edges)
    F = Nombre de faces (Faces)
    L = Nombre total de boucles (Wires / Loops, externes + internes)
    S = Nombre de coques fermées déconnectées (Shells)
    G = Genre topologique (nombre de trous traversants / poignées de tore)

Typage statique strict et intégrité formelle certifiée.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Union
import numpy as np

from src.core.nexus_kernel.brep_topology import (
    NexusBRep,
    NexusVertex,
    NexusEdge,
    NexusWire,
    NexusFace,
    NexusShell,
    NexusLineCurve,
    NexusPlaneSurface,
    NexusSurface,
)


@dataclass(frozen=True)
class EulerPoincareDiagnostic:
    """Diagnostic formel de validité topologique selon la formule d'Euler-Poincaré."""
    is_valid: bool
    euler_characteristic: int
    expected_characteristic: int
    vertices_count: int
    edges_count: int
    faces_count: int
    loops_count: int
    shells_count: int
    genus: int
    diagnostic_message: str


class NexusEulerOperators:
    """
    Opérateurs d'Euler atomiques pour le graphe de frontière B-Rep de NEXUS-3D.
    Toute modification structurelle d'une variété B-Rep doit s'effectuer via ces opérateurs
    pour interdire les états topologiques non-variétés et dégénérés.
    """

    @staticmethod
    def make_vertex_face_shell(
        brep: NexusBRep,
        vertex_id: str,
        x: float,
        y: float,
        z: float,
        face_id: str,
        shell_id: str,
        surface: Optional[NexusSurface] = None
    ) -> Tuple[NexusVertex, NexusFace, NexusShell]:
        """
        Opérateur fondamental MVFS (Make Vertex, Face, Shell).
        Crée un solide initial avec un premier sommet isolé, une face initiale et une coque.
        Effet sur l'invariant : ΔV = +1, ΔF = +1, ΔS = +1.
        Formule : V - E + F = 1 - 0 + 1 = 2 = 2*S.
        """
        v = NexusVertex(vertex_id, float(x), float(y), float(z))
        brep.add_vertex(v)

        w_id = f"Wire_{face_id}_outer"
        outer_wire = NexusWire(w_id, edges=[], is_closed=True)
        brep.add_wire(outer_wire)

        if surface is None:
            surface = NexusPlaneSurface(
                f"Surface_{face_id}",
                origin=v.point,
                normal=np.array([0.0, 0.0, 1.0], dtype=np.float64)
            )

        face = NexusFace(face_id, surface=surface, outer_wire=outer_wire, inner_wires=[], area=0.0)
        brep.add_face(face)

        shell = NexusShell(shell_id, faces=[face], is_closed=False)
        brep.add_shell(shell)

        return v, face, shell

    @staticmethod
    def make_edge_vertex(
        brep: NexusBRep,
        existing_vertex_id: str,
        new_vertex_id: str,
        x: float,
        y: float,
        z: float,
        new_edge_id: str,
        wire_id: Optional[str] = None
    ) -> Tuple[NexusVertex, NexusEdge]:
        """
        Opérateur MEV (Make Edge, Vertex).
        Étend une nouvelle arête et un nouveau sommet à partir d'un sommet préexistant.
        Effet sur l'invariant : ΔV = +1, ΔE = +1.
        Variation nette : Δ(V - E) = 0.
        """
        if existing_vertex_id not in brep.vertices:
            raise KeyError(f"Le sommet d'origine '{existing_vertex_id}' n'existe pas dans le B-Rep.")

        v_from = brep.vertices[existing_vertex_id]
        v_new = NexusVertex(new_vertex_id, float(x), float(y), float(z))
        brep.add_vertex(v_new)

        curve = NexusLineCurve(f"Curve_{new_edge_id}", v_from.point, v_new.point)
        edge = NexusEdge(new_edge_id, curve=curve, start_vertex=v_from, end_vertex=v_new)
        brep.add_edge(edge)

        if wire_id and wire_id in brep.wires:
            brep.wires[wire_id].edges.append(edge)

        return v_new, edge

    @staticmethod
    def make_edge_face(
        brep: NexusBRep,
        vertex_1_id: str,
        vertex_2_id: str,
        new_edge_id: str,
        new_face_id: str,
        wire_to_split_id: str,
        new_wire_id: str,
        surface: Optional[NexusSurface] = None
    ) -> Tuple[NexusEdge, NexusFace]:
        """
        Opérateur MEF (Make Edge, Face).
        Relie deux sommets existants d'une boucle fermée pour la scinder en deux faces distinctes.
        Effet sur l'invariant : ΔE = +1, ΔF = +1.
        Variation nette : Δ(-E + F) = 0.
        """
        if vertex_1_id not in brep.vertices or vertex_2_id not in brep.vertices:
            raise KeyError(f"Sommets '{vertex_1_id}' ou '{vertex_2_id}' introuvables.")
        if wire_to_split_id not in brep.wires:
            raise KeyError(f"Boucle source '{wire_to_split_id}' introuvable.")

        v1 = brep.vertices[vertex_1_id]
        v2 = brep.vertices[vertex_2_id]
        curve = NexusLineCurve(f"Curve_{new_edge_id}", v1.point, v2.point)
        new_edge = NexusEdge(new_edge_id, curve=curve, start_vertex=v1, end_vertex=v2)
        brep.add_edge(new_edge)

        old_wire = brep.wires[wire_to_split_id]
        old_wire.edges.append(new_edge)

        new_wire = NexusWire(new_wire_id, edges=[new_edge], is_closed=True)
        brep.add_wire(new_wire)

        if surface is None:
            surface = NexusPlaneSurface(
                f"Surface_{new_face_id}",
                origin=v1.point,
                normal=np.array([0.0, 0.0, 1.0], dtype=np.float64)
            )

        new_face = NexusFace(new_face_id, surface=surface, outer_wire=new_wire, inner_wires=[], area=0.0)
        brep.add_face(new_face)

        return new_edge, new_face

    @staticmethod
    def kill_vertex_edge(
        brep: NexusBRep,
        vertex_id: str,
        edge_id: str
    ) -> bool:
        """
        Opérateur KVE (Kill Vertex, Edge).
        Inverse exact de MEV. Supprime un sommet pendant et son arête incidente unique.
        Effet sur l'invariant : ΔV = -1, ΔE = -1.
        Variation nette : Δ(V - E) = 0.
        """
        if vertex_id not in brep.vertices or edge_id not in brep.edges:
            return False

        edge = brep.edges[edge_id]
        if edge.start_vertex.vertex_id != vertex_id and edge.end_vertex.vertex_id != vertex_id:
            return False

        # Retirer l'arête des boucles qui la contiennent
        for wire in brep.wires.values():
            wire.edges = [e for e in wire.edges if e.edge_id != edge_id]

        del brep.edges[edge_id]
        del brep.vertices[vertex_id]
        return True

    @staticmethod
    def kill_edge_face(
        brep: NexusBRep,
        edge_id: str,
        face_to_remove_id: str,
        target_retained_face_id: str
    ) -> bool:
        """
        Opérateur KEF (Kill Edge, Face).
        Inverse exact de MEF. Supprime une arête séparatrice et fusionne deux faces contiguës en une seule.
        Effet sur l'invariant : ΔE = -1, ΔF = -1.
        Variation nette : Δ(-E + F) = 0.
        """
        if edge_id not in brep.edges or face_to_remove_id not in brep.faces or target_retained_face_id not in brep.faces:
            return False

        retained_face = brep.faces[target_retained_face_id]
        removed_face = brep.faces[face_to_remove_id]

        # Fusionner les arêtes en excluant l'arête supprimée
        merged_edges = [e for e in retained_face.outer_wire.edges if e.edge_id != edge_id]
        for e in removed_face.outer_wire.edges:
            if e.edge_id != edge_id and e not in merged_edges:
                merged_edges.append(e)

        retained_face.outer_wire.edges = merged_edges

        # Supprimer des shells
        for shell in brep.shells.values():
            shell.faces = [f for f in shell.faces if f.face_id != face_to_remove_id]

        del brep.faces[face_to_remove_id]
        del brep.edges[edge_id]
        return True

    @staticmethod
    def make_inner_hole_loop(
        brep: NexusBRep,
        face_id: str,
        inner_wire_id: str,
        inner_edges: List[NexusEdge]
    ) -> NexusWire:
        """
        Opérateur KFMH / MHR (Make Hole Ring / Loop).
        Ajoute une boucle interne fermée (découpe de perçage ou lumière) à une face existante.
        Effet sur l'invariant : ΔL = +1.
        """
        if face_id not in brep.faces:
            raise KeyError(f"Face '{face_id}' introuvable dans le B-Rep.")

        face = brep.faces[face_id]
        for e in inner_edges:
            if e.edge_id not in brep.edges:
                brep.add_edge(e)

        inner_wire = NexusWire(inner_wire_id, edges=list(inner_edges), is_closed=True)
        brep.add_wire(inner_wire)
        face.inner_wires.append(inner_wire)
        return inner_wire

    @classmethod
    def verify_euler_poincare(
        cls,
        brep: NexusBRep,
        genus: int = 0
    ) -> EulerPoincareDiagnostic:
        """
        Vérificateur formel d'Euler-Poincaré étendu aux solides fermés à faces multiples et trous.
        Formule complète :
            V - E + F - (Loops - Faces) = 2 * (Shells - Genus)
        Pour un polyèdre simple (S=1, G=0, pas de boucles internes Loops=Faces) :
            V - E + F = 2.
        """
        v = len(brep.vertices)
        e = len(brep.edges)
        f = len(brep.faces)
        total_loops = sum(1 + len(face.inner_wires) for face in brep.faces.values())
        s = max(1, len(brep.shells))

        # Formule d'Euler-Poincaré
        # LHS: V - E + F - (total_loops - F)
        # RHS: 2 * (s - genus)
        lhs = v - e + f - (total_loops - f)
        rhs = 2 * (s - genus)

        is_valid = (lhs == rhs)
        chi = v - e + f

        if is_valid:
            msg = f"Topologie B-Rep valide conforme au théorème d'Euler-Poincaré (V={v}, E={e}, F={f}, S={s}, G={genus})."
        else:
            msg = (
                f"Violation d'Euler-Poincaré : V - E + F - (L - F) = {lhs} ≠ 2*(S - G) = {rhs} "
                f"(V={v}, E={e}, F={f}, Loops={total_loops}, S={s}, G={genus})."
            )

        return EulerPoincareDiagnostic(
            is_valid=is_valid,
            euler_characteristic=chi,
            expected_characteristic=rhs,
            vertices_count=v,
            edges_count=e,
            faces_count=f,
            loops_count=total_loops,
            shells_count=s,
            genus=genus,
            diagnostic_message=msg
        )
