"""The canonical in-memory structure model.

Atoms are stored as a structure-of-arrays (SoA) using NumPy for cache-friendly,
vectorized selection and geometry work. This is the single representation all
parsers produce and all downstream code (selection engine, geometry, commands)
consumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .elements import cpk_color, vdw_radius


@dataclass
class Structure:
    """A parsed molecular structure (one or more states share the topology).

    Per-atom arrays are all length ``n_atoms`` and index-aligned. For Phase 0
    we carry a single coordinate set; multi-state/trajectory support arrives in
    Phase 2 by promoting ``coords`` to shape ``(n_states, n_atoms, 3)``.
    """

    name: str
    coords: np.ndarray            # (n_atoms, 3) float32, angstroms
    elements: list[str]           # element symbol per atom, upper-case
    atom_names: list[str]         # PDB atom name (e.g. "CA")
    res_names: list[str]          # residue name (e.g. "ALA")
    res_ids: np.ndarray           # (n_atoms,) int32 residue sequence number
    chain_ids: list[str]          # chain identifier per atom
    b_factors: np.ndarray         # (n_atoms,) float32
    occupancies: np.ndarray       # (n_atoms,) float32
    is_hetatm: np.ndarray         # (n_atoms,) bool — HETATM vs ATOM
    bonds: np.ndarray = field(    # (n_bonds, 2) int32 atom-index pairs
        default_factory=lambda: np.empty((0, 2), dtype=np.int32)
    )
    ids: np.ndarray = field(      # (n_atoms,) int32 original serial/id ("id" selector)
        default_factory=lambda: np.empty((0,), dtype=np.int32)
    )
    states: np.ndarray | None = None  # (n_states, n_atoms, 3) for trajectories/NMR models
    current_state: int = 0            # index into states that `coords` reflects

    def __post_init__(self) -> None:
        # Default ``ids`` to 1-based atom serials when a parser didn't supply them.
        if self.ids.shape[0] != self.n_atoms:
            self.ids = np.arange(1, self.n_atoms + 1, dtype=np.int32)

    @property
    def n_states(self) -> int:
        return 1 if self.states is None else int(self.states.shape[0])

    def set_state(self, state: int) -> None:
        """Point ``coords`` at multi-state frame ``state`` (clamped, wraps off-end)."""
        if self.states is None or self.states.shape[0] <= 1:
            return
        state = int(state) % self.states.shape[0]
        self.current_state = state
        self.coords = self.states[state]

    @property
    def n_atoms(self) -> int:
        return int(self.coords.shape[0])

    @property
    def n_bonds(self) -> int:
        return int(self.bonds.shape[0])

    def vdw_radii(self) -> np.ndarray:
        """Per-atom van der Waals radii (A) as a float32 array."""
        return np.array([vdw_radius(e) for e in self.elements], dtype=np.float32)

    def cpk_colors_rgb(self) -> np.ndarray:
        """Per-atom CPK colors as (n_atoms, 3) float32 in [0, 1]."""
        out = np.empty((self.n_atoms, 3), dtype=np.float32)
        for i, e in enumerate(self.elements):
            h = cpk_color(e)
            out[i] = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        return out / 255.0

    def center(self) -> np.ndarray:
        """Geometric center of all atoms (A)."""
        if self.n_atoms == 0:
            return np.zeros(3, dtype=np.float32)
        return self.coords.mean(axis=0)

    def bounding_radius(self) -> float:
        """Radius of the bounding sphere around the center (A)."""
        if self.n_atoms == 0:
            return 1.0
        d = np.linalg.norm(self.coords - self.center(), axis=1)
        return float(d.max())

    def subset(self, keep: np.ndarray) -> Structure:
        """Return a new Structure containing only atoms where ``keep`` is True,
        with bonds restricted to surviving atoms and re-indexed."""
        idx = np.flatnonzero(keep)
        remap = np.full(self.n_atoms, -1, dtype=np.int64)
        remap[idx] = np.arange(idx.shape[0])
        if self.n_bonds:
            bsel = keep[self.bonds[:, 0]] & keep[self.bonds[:, 1]]
            bonds = remap[self.bonds[bsel]].astype(np.int32)
        else:
            bonds = np.empty((0, 2), dtype=np.int32)
        return Structure(
            name=self.name,
            coords=self.coords[idx].copy(),
            elements=[self.elements[i] for i in idx],
            atom_names=[self.atom_names[i] for i in idx],
            res_names=[self.res_names[i] for i in idx],
            res_ids=self.res_ids[idx].copy(),
            chain_ids=[self.chain_ids[i] for i in idx],
            b_factors=self.b_factors[idx].copy(),
            occupancies=self.occupancies[idx].copy(),
            is_hetatm=self.is_hetatm[idx].copy(),
            bonds=bonds,
            ids=self.ids[idx].copy(),
        )

    def residue_labels(self) -> np.ndarray:
        """Per-atom integer residue labels, grouping atoms by (chain, res_id).

        Used by the ``byres`` selection modifier to expand a mask to whole
        residues. Returns an (n_atoms,) int array; equal labels share a residue.
        """
        labels = np.empty(self.n_atoms, dtype=np.int64)
        mapping: dict[tuple[str, int], int] = {}
        for i in range(self.n_atoms):
            key = (self.chain_ids[i], int(self.res_ids[i]))
            label = mapping.get(key)
            if label is None:
                label = len(mapping)
                mapping[key] = label
            labels[i] = label
        return labels
