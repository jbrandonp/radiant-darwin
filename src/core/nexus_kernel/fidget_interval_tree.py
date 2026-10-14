"""
Élagage d'Arbres CSG/SDF par Arithmétique d'Intervalles (Architecture type Fidget / Matt Keeter).
Résout le problème critique de la divergence de Warp sur GPU (Compute Shaders WGPU / Metal / CUDA).
Divise l'espace en tuiles spatiales (ex: 8x8x8) et élague les branches inactives de l'arbre CSG
via l'arithmétique d'intervalles [min, max], générant un micro-bytecode ultra-court par tuile.
Typage statique strict et garantie de complexité cognitive <= 15.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Sequence, Tuple
import numpy as np


class CSGOpType(Enum):
    """Opérateurs géométriques d'arbre CSG / SDF."""
    SPHERE = "sphere"
    BOX = "box"
    CYLINDER = "cylinder"
    UNION = "union"
    INTERSECTION = "intersection"
    DIFFERENCE = "difference"
    CONSTANT = "constant"


@dataclass
class SDFInterval:
    """Intervalle mathématique [min_val, max_val] pour l'évaluation rigoureuse des bornes de distance."""
    min_val: float
    max_val: float

    def __post_init__(self) -> None:
        if self.min_val > self.max_val:
            # Réordonnancement automatique en cas d'inversion flottante
            self.min_val, self.max_val = self.max_val, self.min_val

    def add(self, other: SDFInterval) -> SDFInterval:
        return SDFInterval(self.min_val + other.min_val, self.max_val + other.max_val)

    def sub(self, other: SDFInterval) -> SDFInterval:
        return SDFInterval(self.min_val - other.max_val, self.max_val - other.min_val)

    def negate(self) -> SDFInterval:
        return SDFInterval(-self.max_val, -self.min_val)

    def union(self, other: SDFInterval) -> SDFInterval:
        """Minimun de deux intervalles : min(A, B)."""
        return SDFInterval(min(self.min_val, other.min_val), min(self.max_val, other.max_val))

    def intersect(self, other: SDFInterval) -> SDFInterval:
        """Maximum de deux intervalles : max(A, B)."""
        return SDFInterval(max(self.min_val, other.min_val), max(self.max_val, other.max_val))

    def contains_zero(self) -> bool:
        """Indique si la surface frontalière phi = 0 traverse potentiellement cet intervalle."""
        return self.min_val <= 0.0 <= self.max_val


class SDFIntervalTreeNode:
    """
    Nœud d'arbre d'expression implicite SDF supportant l'évaluation par intervalles
    et l'élagage spatial par tuile pour éliminer la divergence de threads GPU.
    """

    def __init__(
        self,
        op: CSGOpType,
        left: Optional[SDFIntervalTreeNode] = None,
        right: Optional[SDFIntervalTreeNode] = None,
        params: Optional[Tuple[float, ...]] = None
    ) -> None:
        self.op: CSGOpType = op
        self.left: Optional[SDFIntervalTreeNode] = left
        self.right: Optional[SDFIntervalTreeNode] = right
        self.params: Tuple[float, ...] = params if params is not None else ()

    def eval_scalar(self, x: float, y: float, z: float) -> float:
        """Évaluation ponctuelle scalaire directe de la distance signée."""
        if self.op == CSGOpType.SPHERE:
            radius = self.params[0] if self.params else 10.0
            cx = self.params[1] if len(self.params) > 1 else 0.0
            cy = self.params[2] if len(self.params) > 2 else 0.0
            cz = self.params[3] if len(self.params) > 3 else 0.0
            dist_center = float(np.sqrt((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2))
            return dist_center - radius

        if self.op == CSGOpType.BOX:
            hx = self.params[0] if self.params else 10.0
            hy = self.params[1] if len(self.params) > 1 else 10.0
            hz = self.params[2] if len(self.params) > 2 else 10.0
            dx = abs(x) - hx
            dy = abs(y) - hy
            dz = abs(z) - hz
            outside_dist = float(np.linalg.norm(np.maximum([dx, dy, dz], 0.0)))
            inside_dist = min(max(dx, max(dy, dz)), 0.0)
            return outside_dist + inside_dist

        if self.op == CSGOpType.CONSTANT:
            return self.params[0] if self.params else 0.0

        val_l = self.left.eval_scalar(x, y, z) if self.left else 0.0
        val_r = self.right.eval_scalar(x, y, z) if self.right else 0.0

        if self.op == CSGOpType.UNION:
            return min(val_l, val_r)
        if self.op == CSGOpType.INTERSECTION:
            return max(val_l, val_r)
        if self.op == CSGOpType.DIFFERENCE:
            return max(val_l, -val_r)

        return 0.0

    def eval_interval(
        self,
        ix: SDFInterval,
        iy: SDFInterval,
        iz: SDFInterval
    ) -> SDFInterval:
        """Évalue l'intervalle de distance signée sur une boîte 3D [ix, iy, iz]."""
        if self.op == CSGOpType.SPHERE:
            radius = self.params[0] if self.params else 10.0
            cx = self.params[1] if len(self.params) > 1 else 0.0
            cy = self.params[2] if len(self.params) > 2 else 0.0
            cz = self.params[3] if len(self.params) > 3 else 0.0
            # Distance minimale et maximale au centre
            dx_min = max(0.0, max(cx - ix.max_val, ix.min_val - cx))
            dy_min = max(0.0, max(cy - iy.max_val, iy.min_val - cy))
            dz_min = max(0.0, max(cz - iz.max_val, iz.min_val - cz))
            min_dist = float(np.sqrt(dx_min ** 2 + dy_min ** 2 + dz_min ** 2)) - radius

            dx_max = max(abs(ix.min_val - cx), abs(ix.max_val - cx))
            dy_max = max(abs(iy.min_val - cy), abs(iy.max_val - cy))
            dz_max = max(abs(iz.min_val - cz), abs(iz.max_val - cz))
            max_dist = float(np.sqrt(dx_max ** 2 + dy_max ** 2 + dz_max ** 2)) - radius
            return SDFInterval(min_dist, max_dist)

        if self.op == CSGOpType.CONSTANT:
            c = self.params[0] if self.params else 0.0
            return SDFInterval(c, c)

        int_l = self.left.eval_interval(ix, iy, iz) if self.left else SDFInterval(0.0, 0.0)
        int_r = self.right.eval_interval(ix, iy, iz) if self.right else SDFInterval(0.0, 0.0)

        if self.op == CSGOpType.UNION:
            return int_l.union(int_r)
        if self.op == CSGOpType.INTERSECTION:
            return int_l.intersect(int_r)
        if self.op == CSGOpType.DIFFERENCE:
            return int_l.intersect(int_r.negate())

        return SDFInterval(0.0, 0.0)

    def prune_for_tile(
        self,
        ix: SDFInterval,
        iy: SDFInterval,
        iz: SDFInterval
    ) -> SDFIntervalTreeNode:
        """
        Élague l'arbre mathématique pour la tuile locale [ix, iy, iz].
        Si l'un des membres d'une opération domine totalement l'autre sur toute la tuile,
        la branche secondaire est éliminée du micro-bytecode.
        """
        if self.op in (CSGOpType.SPHERE, CSGOpType.BOX, CSGOpType.CONSTANT):
            return self

        pruned_left = self.left.prune_for_tile(ix, iy, iz) if self.left else None
        pruned_right = self.right.prune_for_tile(ix, iy, iz) if self.right else None

        if pruned_left is None:
            return pruned_right if pruned_right is not None else self
        if pruned_right is None:
            return pruned_left

        int_l = pruned_left.eval_interval(ix, iy, iz)
        int_r = pruned_right.eval_interval(ix, iy, iz)

        # Règle d'élagage pour l'Union min(L, R) :
        # Si L.max_val < R.min_val, L est strictement plus petit que R sur toute la tuile -> R est supprimé !
        if self.op == CSGOpType.UNION:
            if int_l.max_val < int_r.min_val:
                return pruned_left
            if int_r.max_val < int_l.min_val:
                return pruned_right

        # Règle d'élagage pour l'Intersection max(L, R) :
        if self.op == CSGOpType.INTERSECTION:
            if int_l.min_val > int_r.max_val:
                return pruned_left
            if int_r.min_val > int_l.max_val:
                return pruned_right

        # Règle d'élagage pour la Différence max(L, -R) :
        if self.op == CSGOpType.DIFFERENCE:
            neg_r = int_r.negate()
            if int_l.min_val > neg_r.max_val:
                return pruned_left
            if neg_r.min_val > int_l.max_val:
                return SDFIntervalTreeNode(CSGOpType.CONSTANT, params=(neg_r.min_val,))

        return SDFIntervalTreeNode(self.op, left=pruned_left, right=pruned_right, params=self.params)

    def count_nodes(self) -> int:
        """Compte le nombre total d'instructions machine dans ce micro-arbre."""
        c = 1
        if self.left:
            c += self.left.count_nodes()
        if self.right:
            c += self.right.count_nodes()
        return c
