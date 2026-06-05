"""Rigid-body superposition via the Kabsch algorithm.

Given two paired point sets, find the rotation + translation minimizing RMSD.
Used by the ``align``/``super`` commands to superpose one object onto another
(v1 pairs CA atoms positionally; sequence-aware alignment is a later refinement).
"""

from __future__ import annotations

import numpy as np


def kabsch(mobile: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Return (rotation 3x3, translation 3, rmsd) mapping ``mobile`` onto ``target``.

    Applying ``mobile @ R.T + t`` best-fits the mobile points onto the target.
    """
    if mobile.shape != target.shape or mobile.shape[0] < 1:
        raise ValueError("kabsch: point sets must be non-empty and the same shape")

    mob_c = mobile.mean(axis=0)
    tgt_c = target.mean(axis=0)
    p = mobile - mob_c
    q = target - tgt_c

    h = p.T @ q
    u, _, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    diag = np.diag([1.0, 1.0, d])
    rot = vt.T @ diag @ u.T

    aligned = p @ rot.T
    rmsd = float(np.sqrt(np.mean(np.sum((aligned - q) ** 2, axis=1))))
    translation = tgt_c - mob_c @ rot.T
    return rot.astype(np.float64), translation.astype(np.float64), rmsd


def apply_transform(coords: np.ndarray, rot: np.ndarray, translation: np.ndarray) -> np.ndarray:
    """Apply ``coords @ rot.T + translation``."""
    return (coords @ rot.T + translation).astype(np.float32)


def rmsd(a: np.ndarray, b: np.ndarray) -> float:
    """Root-mean-square deviation between two equally-shaped point sets (no fit)."""
    if a.shape != b.shape:
        raise ValueError("rmsd: point sets must be the same shape")
    return float(np.sqrt(np.mean(np.sum((a - b) ** 2, axis=1))))
