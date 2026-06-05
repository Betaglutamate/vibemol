"""Solvent-accessible surface area via the Shrake-Rupley algorithm.

Each atom is expanded by the probe radius (water, 1.4 A) and its sphere sampled
with a Fibonacci point set; a sample is accessible if it lies outside every other
atom's expanded sphere. Pure NumPy with a uniform-grid neighbour search (like
:mod:`vibemol.model.bonds`), so it needs no optional dependencies.
"""

from __future__ import annotations

import numpy as np

from ..model.structure import Structure

_PROBE = 1.4
_N_POINTS = 96


def _fibonacci_sphere(n: int) -> np.ndarray:
    k = np.arange(n)
    phi = np.pi * (3.0 - np.sqrt(5.0))
    y = 1.0 - 2.0 * (k + 0.5) / n
    r = np.sqrt(np.maximum(0.0, 1.0 - y * y))
    theta = phi * k
    return np.stack([np.cos(theta) * r, y, np.sin(theta) * r], axis=1)


def _neighbor_grid(coords: np.ndarray, cell: float) -> dict[tuple[int, int, int], list[int]]:
    grid: dict[tuple[int, int, int], list[int]] = {}
    origin = coords.min(axis=0)
    idx = np.floor((coords - origin) / cell).astype(np.int64)
    for i, (cx, cy, cz) in enumerate(idx):
        grid.setdefault((int(cx), int(cy), int(cz)), []).append(i)
    return grid


def sasa(
    structure: Structure,
    mask: np.ndarray | None = None,
    *,
    probe: float = _PROBE,
    n_points: int = _N_POINTS,
) -> np.ndarray:
    """Per-atom solvent-accessible surface area (A^2).

    Occlusion always considers the whole structure; entries outside ``mask`` (if
    given) are returned as 0.
    """
    n = structure.n_atoms
    out = np.zeros(n, dtype=np.float32)
    if n == 0:
        return out

    coords = structure.coords.astype(np.float64)
    radii = structure.vdw_radii().astype(np.float64) + probe
    sphere = _fibonacci_sphere(n_points)
    want = np.ones(n, dtype=bool) if mask is None else mask

    cell = float(radii.max() * 2.0)
    grid = _neighbor_grid(coords, cell)
    origin = coords.min(axis=0)
    cell_idx = np.floor((coords - origin) / cell).astype(np.int64)
    offsets = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)]

    for i in range(n):
        if not want[i]:
            continue
        cx, cy, cz = cell_idx[i]
        candidates: list[int] = []
        for dx, dy, dz in offsets:
            candidates.extend(grid.get((int(cx) + dx, int(cy) + dy, int(cz) + dz), ()))
        # Neighbours whose expanded spheres can reach atom i's sample shell.
        neighbors = [
            j for j in candidates
            if j != i and float(np.linalg.norm(coords[i] - coords[j])) < radii[i] + radii[j]
        ]
        pts = coords[i] + sphere * radii[i]  # (n_points, 3)
        accessible = np.ones(pts.shape[0], dtype=bool)
        for j in neighbors:
            d2 = ((pts - coords[j]) ** 2).sum(axis=1)
            accessible &= d2 >= radii[j] * radii[j]
        frac = float(accessible.sum()) / n_points
        out[i] = frac * 4.0 * np.pi * radii[i] * radii[i]
    return out
