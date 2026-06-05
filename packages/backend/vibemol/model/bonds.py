"""Distance-based bond inference.

Two atoms are bonded when their separation is below the sum of their covalent
radii plus a tolerance. A uniform spatial grid (cell list) keeps this near
O(n) instead of O(n^2) so it scales to large structures.
"""

from __future__ import annotations

import numpy as np

from .elements import covalent_radius

_TOLERANCE = 0.45  # angstroms of slack on the covalent-radii sum


def infer_bonds(coords: np.ndarray, elements: list[str]) -> np.ndarray:
    """Return an (n_bonds, 2) int32 array of bonded atom-index pairs (i < j)."""
    n = coords.shape[0]
    if n < 2:
        return np.empty((0, 2), dtype=np.int32)

    radii = np.array([covalent_radius(e) for e in elements], dtype=np.float32)
    max_bond = float(radii.max() * 2 + _TOLERANCE)
    cell = max(max_bond, 1e-3)

    origin = coords.min(axis=0)
    cell_idx = np.floor((coords - origin) / cell).astype(np.int64)

    # Bucket atoms by cell key.
    grid: dict[tuple[int, int, int], list[int]] = {}
    for i, (cx, cy, cz) in enumerate(cell_idx):
        grid.setdefault((int(cx), int(cy), int(cz)), []).append(i)

    neighbor_offsets = [
        (dx, dy, dz)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        for dz in (-1, 0, 1)
    ]

    bonds: list[tuple[int, int]] = []
    for (cx, cy, cz), atoms in grid.items():
        # Gather candidate atoms from this cell and its 26 neighbors.
        candidates: list[int] = []
        for dx, dy, dz in neighbor_offsets:
            candidates.extend(grid.get((cx + dx, cy + dy, cz + dz), ()))
        for i in atoms:
            for j in candidates:
                if j <= i:
                    continue
                d = float(np.linalg.norm(coords[i] - coords[j]))
                cutoff = radii[i] + radii[j] + _TOLERANCE
                if 0.4 < d <= cutoff:  # lower bound rejects coincident atoms
                    bonds.append((i, j))

    if not bonds:
        return np.empty((0, 2), dtype=np.int32)
    return np.array(sorted(bonds), dtype=np.int32)
