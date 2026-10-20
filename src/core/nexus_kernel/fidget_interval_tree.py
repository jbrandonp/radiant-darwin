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
import math
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

    def _eval_sphere_scalar(self, x: float, y: float, z: float) -> float:
        """Distance signée ponctuelle à une sphère."""
        radius = self.params[0] if self.params else 10.0
        cx = self.params[1] if len(self.params) > 1 else 0.0
        cy = self.params[2] if len(self.params) > 2 else 0.0
        cz = self.params[3] if len(self.params) > 3 else 0.0
        dist_center = float(np.sqrt((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2))
        return dist_center - radius

    def _eval_box_scalar(self, x: float, y: float, z: float) -> float:
        """Distance signée ponctuelle à une boîte alignée."""
        hx = self.params[0] if self.params else 10.0
        hy = self.params[1] if len(self.params) > 1 else 10.0
        hz = self.params[2] if len(self.params) > 2 else 10.0
        dx = abs(x) - hx
        dy = abs(y) - hy
        dz = abs(z) - hz
        outside_dist = float(np.linalg.norm(np.maximum([dx, dy, dz], 0.0)))
        inside_dist = min(max(dx, max(dy, dz)), 0.0)
        return outside_dist + inside_dist

    def _eval_cylinder_scalar(self, x: float, y: float, z: float) -> float:
        """Distance signée ponctuelle à un cylindre d'axe Z."""
        radius = self.params[0] if self.params else 10.0
        hz = self.params[1] if len(self.params) > 1 else 10.0
        d_xy = math.hypot(x, y) - radius
        d_z = abs(z) - hz
        outside = math.hypot(max(0.0, d_xy), max(0.0, d_z))
        inside = min(max(d_xy, d_z), 0.0)
        return outside + inside

    def eval_scalar(self, x: float, y: float, z: float) -> float:
        """Évaluation ponctuelle scalaire directe de la distance signée."""
        if self.op == CSGOpType.SPHERE:
            return self._eval_sphere_scalar(x, y, z)

        if self.op == CSGOpType.BOX:
            return self._eval_box_scalar(x, y, z)

        if self.op == CSGOpType.CYLINDER:
            return self._eval_cylinder_scalar(x, y, z)

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

    def _eval_sphere_interval(
        self,
        ix: SDFInterval,
        iy: SDFInterval,
        iz: SDFInterval
    ) -> SDFInterval:
        """Intervalle de distance signée à une sphère."""
        radius = self.params[0] if self.params else 10.0
        cx = self.params[1] if len(self.params) > 1 else 0.0
        cy = self.params[2] if len(self.params) > 2 else 0.0
        cz = self.params[3] if len(self.params) > 3 else 0.0
        dx_min = max(0.0, max(cx - ix.max_val, ix.min_val - cx))
        dy_min = max(0.0, max(cy - iy.max_val, iy.min_val - cy))
        dz_min = max(0.0, max(cz - iz.max_val, iz.min_val - cz))
        min_dist = float(np.sqrt(dx_min ** 2 + dy_min ** 2 + dz_min ** 2)) - radius

        dx_max = max(abs(ix.min_val - cx), abs(ix.max_val - cx))
        dy_max = max(abs(iy.min_val - cy), abs(iy.max_val - cy))
        dz_max = max(abs(iz.min_val - cz), abs(iz.max_val - cz))
        max_dist = float(np.sqrt(dx_max ** 2 + dy_max ** 2 + dz_max ** 2)) - radius
        return SDFInterval(min_dist, max_dist)

    def _eval_box_interval(self, ix: SDFInterval, iy: SDFInterval, iz: SDFInterval) -> SDFInterval:
        """Intervalle de distance signée à une boîte alignée."""
        hx = self.params[0] if self.params else 10.0
        hy = self.params[1] if len(self.params) > 1 else 10.0
        hz = self.params[2] if len(self.params) > 2 else 10.0

        dx_min = max(0.0, max(-hx - ix.max_val, ix.min_val - hx))
        dy_min = max(0.0, max(-hy - iy.max_val, iy.min_val - hy))
        dz_min = max(0.0, max(-hz - iz.max_val, iz.min_val - hz))

        if ix.min_val <= hx and ix.max_val >= -hx and iy.min_val <= hy and iy.max_val >= -hy and iz.min_val <= hz and iz.max_val >= -hz:
            d_in_x = max(abs(ix.min_val) - hx, abs(ix.max_val) - hx)
            d_in_y = max(abs(iy.min_val) - hy, abs(iy.max_val) - hy)
            d_in_z = max(abs(iz.min_val) - hz, abs(iz.max_val) - hz)
            min_dist = min(0.0, max(d_in_x, max(d_in_y, d_in_z)))
        else:
            min_dist = float(np.sqrt(dx_min ** 2 + dy_min ** 2 + dz_min ** 2))

        corners = [
            (ix.min_val, iy.min_val, iz.min_val),
            (ix.max_val, iy.max_val, iz.max_val),
            (ix.min_val, iy.max_val, iz.min_val),
            (ix.max_val, iy.min_val, iz.max_val)
        ]
        max_dist = max(self._eval_box_scalar(cx, cy, cz) for cx, cy, cz in corners)
        return SDFInterval(min_dist, max_dist)

    def _eval_cylinder_interval(self, ix: SDFInterval, iy: SDFInterval, iz: SDFInterval) -> SDFInterval:
        """Intervalle de distance signée à un cylindre d'axe Z."""
        radius = self.params[0] if self.params else 10.0
        hz = self.params[1] if len(self.params) > 1 else 10.0

        dx_min = max(0.0, max(0.0 - ix.max_val, ix.min_val - 0.0))
        dy_min = max(0.0, max(0.0 - iy.max_val, iy.min_val - 0.0))
        r_box_min = float(np.sqrt(dx_min ** 2 + dy_min ** 2))
        dz_min = max(0.0, max(-hz - iz.max_val, iz.min_val - hz))

        d_xy = max(0.0, r_box_min - radius)
        min_dist = float(np.sqrt(d_xy ** 2 + dz_min ** 2))
        if r_box_min < radius and iz.min_val <= hz and iz.max_val >= -hz:
            min_dist = min(0.0, r_box_min - radius)

        corners = [
            (ix.min_val, iy.min_val, iz.min_val),
            (ix.max_val, iy.max_val, iz.max_val),
            (ix.min_val, iy.max_val, iz.min_val),
            (ix.max_val, iy.min_val, iz.max_val)
        ]
        max_dist = max(self._eval_cylinder_scalar(cx, cy, cz) for cx, cy, cz in corners)
        return SDFInterval(min_dist, max_dist)

    def eval_interval(
        self,
        ix: SDFInterval,
        iy: SDFInterval,
        iz: SDFInterval
    ) -> SDFInterval:
        """Évalue l'intervalle de distance signée sur une boîte 3D [ix, iy, iz]."""
        if self.op == CSGOpType.SPHERE:
            return self._eval_sphere_interval(ix, iy, iz)

        if self.op == CSGOpType.BOX:
            return self._eval_box_interval(ix, iy, iz)

        if self.op == CSGOpType.CYLINDER:
            return self._eval_cylinder_interval(ix, iy, iz)

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

    @staticmethod
    def _try_prune_union(
        left: SDFIntervalTreeNode,
        right: SDFIntervalTreeNode,
        int_l: SDFInterval,
        int_r: SDFInterval
    ) -> Optional[SDFIntervalTreeNode]:
        """Règle d'élagage pour l'Union min(L, R)."""
        if int_l.max_val < int_r.min_val:
            return left
        if int_r.max_val < int_l.min_val:
            return right
        return None

    @staticmethod
    def _try_prune_intersection(
        left: SDFIntervalTreeNode,
        right: SDFIntervalTreeNode,
        int_l: SDFInterval,
        int_r: SDFInterval
    ) -> Optional[SDFIntervalTreeNode]:
        """Règle d'élagage pour l'Intersection max(L, R)."""
        if int_l.min_val > int_r.max_val:
            return left
        if int_r.min_val > int_l.max_val:
            return right
        return None

    @staticmethod
    def _try_prune_difference(
        left: SDFIntervalTreeNode,
        right: SDFIntervalTreeNode,
        int_l: SDFInterval,
        int_r: SDFInterval
    ) -> Optional[SDFIntervalTreeNode]:
        """Règle d'élagage pour la Différence max(L, -R)."""
        neg_r = int_r.negate()
        if int_l.min_val > neg_r.max_val:
            return left
        if neg_r.min_val > int_l.max_val:
            return SDFIntervalTreeNode(CSGOpType.CONSTANT, params=(neg_r.min_val,))
        return None

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

        if self.op == CSGOpType.UNION:
            pruned_union = self._try_prune_union(pruned_left, pruned_right, int_l, int_r)
            if pruned_union is not None:
                return pruned_union

        if self.op == CSGOpType.INTERSECTION:
            pruned_inter = self._try_prune_intersection(pruned_left, pruned_right, int_l, int_r)
            if pruned_inter is not None:
                return pruned_inter

        if self.op == CSGOpType.DIFFERENCE:
            pruned_diff = self._try_prune_difference(pruned_left, pruned_right, int_l, int_r)
            if pruned_diff is not None:
                return pruned_diff

        return SDFIntervalTreeNode(self.op, left=pruned_left, right=pruned_right, params=self.params)

    def count_nodes(self) -> int:
        """Compte le nombre total d'instructions machine dans ce micro-arbre."""
        c = 1
        if self.left:
            c += self.left.count_nodes()
        if self.right:
            c += self.right.count_nodes()
        return c
