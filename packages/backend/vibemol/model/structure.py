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
