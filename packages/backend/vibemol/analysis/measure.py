"""Geometric measurements (distance, angle, dihedral) and polar-contact detection."""

from __future__ import annotations

import numpy as np

from ..model.structure import Structure


def distance(a: np.ndarray, b: np.ndarray) -> float:
    """Distance between two points (A)."""
    return float(np.linalg.norm(a - b))


def angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Angle a-b-c in degrees (b is the vertex)."""
    v1 = a - b
    v2 = c - b
    cos = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9))
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


def dihedral(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> float:
    """Dihedral angle a-b-c-d in degrees (range -180..180)."""
    b1, b2, b3 = b - a, c - b, d - c
    n1 = np.cross(b1, b2)
    n2 = np.cross(b2, b3)
    m1 = np.cross(n1, b2 / (np.linalg.norm(b2) + 1e-9))
    x = float(np.dot(n1, n2))
    y = float(np.dot(m1, n2))
    return float(np.degrees(np.arctan2(y, x)))


def polar_contacts(
    structure: Structure, mask: np.ndarray, *, cutoff: float = 3.5
) -> list[tuple[int, int, float]]:
    """Find polar contacts: N/O atom pairs within ``cutoff`` (A), not bonded and
    not in the same residue. Returns (i, j, distance) with i < j."""
    polar = np.array([e in ("N", "O") for e in structure.elements]) & mask
    idx = np.flatnonzero(polar)
    if idx.shape[0] < 2:
        return []

    bonded: set[tuple[int, int]] = set()
    for i, j in structure.bonds:
        bonded.add((int(i), int(j)))
        bonded.add((int(j), int(i)))

    res = structure.residue_labels()
    coords = structure.coords
    out: list[tuple[int, int, float]] = []
    cutoff2 = cutoff * cutoff
    for a in range(idx.shape[0]):
        ia = int(idx[a])
        for b in range(a + 1, idx.shape[0]):
            ib = int(idx[b])
            if res[ia] == res[ib] or (ia, ib) in bonded:
                continue
            diff = coords[ia] - coords[ib]
            d2 = float(diff @ diff)
            if d2 <= cutoff2:
                out.append((ia, ib, float(np.sqrt(d2))))
    return out
