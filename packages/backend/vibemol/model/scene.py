"""The scene graph — the backend-owned session state.

This is the PyMOL model, split over a network: the backend owns objects,
per-atom representation visibility, per-atom colors, named selections, and
settings; the client owns only the camera. Commands mutate this scene; geometry
is regenerated from it and streamed to the client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .structure import Structure

# The representations VibeMol can render. Visibility is tracked *per atom per
# kind* (a boolean mask), exactly mirroring PyMOL's show/hide/as semantics.
REP_KINDS: tuple[str, ...] = (
    "lines",
    "sticks",
    "ball_and_stick",
    "spheres",
    "nonbonded",
    "dots",
)


@dataclass
class MolObject:
    """A loaded structure plus its display state (rep masks + per-atom colors)."""

    name: str
    structure: Structure
    visible: bool = True
    rep_masks: dict[str, np.ndarray] = field(default_factory=dict)
    colors: np.ndarray = field(default_factory=lambda: np.empty((0, 3), dtype=np.float32))

    def __post_init__(self) -> None:
        n = self.structure.n_atoms
        for kind in REP_KINDS:
            self.rep_masks.setdefault(kind, np.zeros(n, dtype=bool))
        if self.colors.shape != (n, 3):
            self.colors = self.structure.cpk_colors_rgb()

    def apply_default_representation(self) -> None:
        """PyMOL-like default: lines for bonded atoms, nonbonded points elsewhere."""
        n = self.structure.n_atoms
        bonded = np.zeros(n, dtype=bool)
        if self.structure.n_bonds:
            bonded[self.structure.bonds.reshape(-1)] = True
        self.rep_masks["lines"] = bonded.copy()
        self.rep_masks["nonbonded"] = ~bonded

    def show(self, kind: str, mask: np.ndarray) -> None:
        self.rep_masks[kind] |= mask

    def hide(self, kind: str, mask: np.ndarray) -> None:
        self.rep_masks[kind] &= ~mask

    def show_as(self, kind: str, mask: np.ndarray) -> None:
        """Show ``kind`` for ``mask`` and clear every other kind for those atoms."""
        for other in REP_KINDS:
            if other == kind:
                self.rep_masks[other] |= mask
            else:
                self.rep_masks[other] &= ~mask

    def set_color(self, rgb: tuple[float, float, float], mask: np.ndarray) -> None:
        self.colors[mask] = rgb

    def active_kinds(self) -> list[str]:
        """Representation kinds with at least one shown atom (in REP_KINDS order)."""
        return [k for k in REP_KINDS if bool(self.rep_masks[k].any())]


@dataclass
class Scene:
    """The full session: ordered objects, named selections, and settings."""

    objects: dict[str, MolObject] = field(default_factory=dict)
    # Named selection -> {object_name: boolean mask over that object's atoms}.
    selections: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=lambda: {"bg_color": "#0b0d10"})

    def add_object(self, obj: MolObject, *, default_rep: bool = True) -> MolObject:
        if default_rep:
            obj.apply_default_representation()
        self.objects[obj.name] = obj
        return obj

    def delete_object(self, name: str) -> bool:
        existed = self.objects.pop(name, None) is not None
        # Drop any selection fragments referencing the deleted object.
        for masks in self.selections.values():
            masks.pop(name, None)
        return existed

    def unique_name(self, base: str) -> str:
        """Return ``base`` or ``base_2``/``base_3``/… if already taken."""
        if base not in self.objects:
            return base
        i = 2
        while f"{base}_{i}" in self.objects:
            i += 1
        return f"{base}_{i}"
