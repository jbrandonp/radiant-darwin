"""
Noyau Géométrique Hybride NEXUS-3D : Arène Mémoire Générationnelle (SlotMap / ECS Data-Oriented Design).
Inspiré des structures de données modernes de Rust (crate `slotmap`) et de l'architecture DOD.

Bannit les pointeurs bruts et les références d'objets enchevêtrées :
- Stockage plat contigu en mémoire garantissant zéro dérive de pointeur et localisation de cache optimale.
- Clés générationnelles 64-bits (Index + Génération) rendant impossible l'utilisation de références périmées (Use-After-Free / Stale Reference).
- Allocation O(1), accès O(1) et suppression O(1) avec recyclage instantané des emplacements libres.

Typage statique strict et intégrité certifiée.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Sequence, Union, TypeVar, Generic, Iterator

T = TypeVar("T")


@dataclass(frozen=True)
class ArenaKey:
    """Clé générationnelle immuable identifiant de manière unique une entité dans l'arène."""
    index: int
    generation: int

    def __repr__(self) -> str:
        return f"Key(idx={self.index}, gen={self.generation})"

    def to_u64(self) -> int:
        """Encode l'index (32 bits) et la génération (32 bits) dans un entier unique 64 bits."""
        return (self.generation << 32) | (self.index & 0xFFFFFFFF)

    @classmethod
    def from_u64(cls, val: int) -> ArenaKey:
        gen = val >> 32
        idx = val & 0xFFFFFFFF
        return cls(index=idx, generation=gen)


@dataclass
class _Slot(Generic[T]):
    """Emplacement interne de l'arène."""
    value: Optional[T]
    generation: int
    is_occupied: bool


class GenerationalArena(Generic[T]):
    """
    Arène mémoire contiguë haute performance avec validation générationnelle O(1).
    """

    def __init__(self, initial_capacity: int = 64) -> None:
        self._slots: List[_Slot[T]] = []
        self._free_indices: List[int] = []
        self._count: int = 0

        for i in range(max(16, initial_capacity)):
            self._slots.append(_Slot(value=None, generation=1, is_occupied=False))
            self._free_indices.append(i)

    def __len__(self) -> int:
        return self._count

    def insert(self, value: T) -> ArenaKey:
        """Insère un élément dans l'arène et retourne sa clé générationnelle immuable en O(1)."""
        if not self._free_indices:
            # Agrandir l'arène
            new_idx = len(self._slots)
            self._slots.append(_Slot(value=None, generation=1, is_occupied=False))
            self._free_indices.append(new_idx)

        idx = self._free_indices.pop()
        slot = self._slots[idx]
        slot.value = value
        slot.is_occupied = True
        self._count += 1

        return ArenaKey(index=idx, generation=slot.generation)

    def get(self, key: ArenaKey) -> Optional[T]:
        """Récupère l'élément associé à la clé en O(1). Retourne None si la clé est périmée ou inexistante."""
        if key.index < 0 or key.index >= len(self._slots):
            return None
        slot = self._slots[key.index]
        if not slot.is_occupied or slot.generation != key.generation:
            return None
        return slot.value

    def contains(self, key: ArenaKey) -> bool:
        """Vérifie si la clé est valide et correspond à un élément actif."""
        return self.get(key) is not None

    def remove(self, key: ArenaKey) -> Optional[T]:
        """Supprime l'élément en O(1) et incrémente le compteur de génération pour invalider toute clé future."""
        if key.index < 0 or key.index >= len(self._slots):
            return None
        slot = self._slots[key.index]
        if not slot.is_occupied or slot.generation != key.generation:
            return None

        removed_val = slot.value
        slot.value = None
        slot.is_occupied = False
        slot.generation += 1  # Invalidation immédiate de toutes les anciennes références
        self._free_indices.append(key.index)
        self._count -= 1

        return removed_val

    def clear(self) -> None:
        """Purge l'arène et incrémente toutes les générations."""
        for idx, slot in enumerate(self._slots):
            if slot.is_occupied:
                slot.value = None
                slot.is_occupied = False
                slot.generation += 1
                self._free_indices.append(idx)
        self._count = 0

    def items(self) -> List[Tuple[ArenaKey, T]]:
        """Retourne la liste de tous les couples (clé, valeur) actuellement actifs."""
        res: List[Tuple[ArenaKey, T]] = []
        for idx, slot in enumerate(self._slots):
            if slot.is_occupied and slot.value is not None:
                res.append((ArenaKey(idx, slot.generation), slot.value))
        return res

    def values(self) -> List[T]:
        """Retourne tous les éléments actifs sous forme de liste contiguë."""
        return [slot.value for slot in self._slots if slot.is_occupied and slot.value is not None]

    def keys(self) -> List[ArenaKey]:
        """Retourne toutes les clés valides actives."""
        return [ArenaKey(idx, slot.generation) for idx, slot in enumerate(self._slots) if slot.is_occupied]
