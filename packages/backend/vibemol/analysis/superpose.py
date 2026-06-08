"""Structural superposition: sequence-based ``align`` and structural ``super``.

Both return a rigid transform (rotation, translation) mapping the mobile
structure onto the target, plus the RMSD and the number of atoms matched.

  * ``align_structures`` — pairs residues by a Needleman-Wunsch sequence
    alignment, then refines with iterative outlier rejection (PyMOL's ``align``).
  * ``super_structures`` — sequence-independent: seeds orientations from the CA
    point clouds' principal axes (and the sequence pairing when available) and
    refines each with ICP + outlier rejection, keeping the best (PyMOL's ``super``).
"""

from __future__ import annotations

import numpy as np

from ..model.structure import Structure
from .align import apply_transform, kabsch
from .sequence import needleman_wunsch

# Per-residue trace atom preference (protein CA, then nucleic sugar/phosphate).
_TRACE_PREF = ("CA", "C3'", "C4'", "P", "C1'")
_CUTOFF = 2.0
_CYCLES = 5


def _representative_atoms(s: Structure) -> tuple[np.ndarray, list[str]]:
    """One backbone atom per residue (in order): coords + residue-name tokens."""
    res_order: list[tuple[str, int]] = []
    res_atoms: dict[tuple[str, int], dict[str, int]] = {}
    for i in range(s.n_atoms):
        nm = s.atom_names[i].upper()
        if nm == "CA" and s.elements[i] != "C":
            continue  # skip calcium ions masquerading as "CA"
        key = (s.chain_ids[i], int(s.res_ids[i]))
        if key not in res_atoms:
            res_atoms[key] = {}
            res_order.append(key)
        res_atoms[key].setdefault(nm, i)

    coords: list[np.ndarray] = []
    tokens: list[str] = []
    for key in res_order:
        names = res_atoms[key]
        idx = next((names[p] for p in _TRACE_PREF if p in names), None)
        if idx is None:
            continue  # non-polymer residue (no backbone trace atom)
        coords.append(s.coords[idx])
        tokens.append(s.res_names[idx])
    return np.array(coords, dtype=np.float64).reshape(-1, 3), tokens


def iterative_fit(
    mobile: np.ndarray, target: np.ndarray, *, cutoff: float = _CUTOFF, cycles: int = _CYCLES
) -> tuple[np.ndarray, np.ndarray, float, int, int]:
    """Fixed-correspondence Kabsch fit with outlier rejection.

    ``mobile[k]`` is paired with ``target[k]``. Each cycle fits, then drops pairs
    deviating > ``cutoff`` A and refits. Returns (rot, trans, rmsd, n_used, cycles).
    """
    keep = np.ones(mobile.shape[0], dtype=bool)
    rot, trans, _ = kabsch(mobile, target)
    used_cycles = 0
    for _ in range(cycles):
        used_cycles += 1
        d = np.linalg.norm(apply_transform(mobile, rot, trans) - target, axis=1)
        # Robust threshold: the median (50%-breakdown) keeps gross outliers from
        # skewing rejection, and tightens toward the absolute cutoff as inliers win.
        thr = max(cutoff, 2.5 * float(np.median(d[keep])))
        new_keep = d <= thr
        if int(new_keep.sum()) < 3 or np.array_equal(new_keep, keep):
            break
        keep = new_keep
        rot, trans, _ = kabsch(mobile[keep], target[keep])

    # Report over the inliers within the absolute cutoff (fall back to keep set).
    d = np.linalg.norm(apply_transform(mobile, rot, trans) - target, axis=1)
    final_keep = d <= cutoff
    if int(final_keep.sum()) >= 3:
        keep = final_keep
    rmsd = float(np.sqrt(np.mean(d[keep] ** 2)))
    return rot, trans, rmsd, int(keep.sum()), used_cycles


def align_structures(
    mobile: Structure, target: Structure
) -> tuple[np.ndarray, np.ndarray, float, int, int]:
    """Sequence-based superposition (Needleman-Wunsch pairing + iterative fit)."""
    m_xyz, m_tok = _representative_atoms(mobile)
    t_xyz, t_tok = _representative_atoms(target)
    if len(m_tok) < 3 or len(t_tok) < 3:
        raise ValueError("align: need >= 3 backbone residues in each object")
    pairs = needleman_wunsch(m_tok, t_tok)
    if len(pairs) < 3:
        raise ValueError("align: sequences share too little to align")
    mob = m_xyz[[i for i, _ in pairs]]
    tgt = t_xyz[[j for _, j in pairs]]
    return iterative_fit(mob, tgt)


def _nearest(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Index of the nearest ``dst`` point for each ``src`` point (chunked)."""
    out = np.empty(src.shape[0], dtype=np.int64)
    block = 1024
    for s in range(0, src.shape[0], block):
        chunk = src[s : s + block]
        d2 = ((chunk[:, None, :] - dst[None, :, :]) ** 2).sum(axis=2)
        out[s : s + block] = d2.argmin(axis=1)
    return out


def _icp(
    mobile: np.ndarray, target: np.ndarray, rot: np.ndarray, trans: np.ndarray,
    *, cutoff: float = _CUTOFF, cycles: int = 20,
) -> tuple[np.ndarray, np.ndarray, float, int]:
    """Iterative closest point: refine a seed transform via nearest-CA pairing."""
    for _ in range(cycles):
        cur = apply_transform(mobile, rot, trans)
        nn = _nearest(cur, target)
        d = np.linalg.norm(cur - target[nn], axis=1)
        keep = d <= cutoff
        if int(keep.sum()) < 3:
            keep = d <= max(cutoff, float(np.median(d)))  # relax if too strict
            if int(keep.sum()) < 3:
                return rot, trans, float("inf"), 0
        new_rot, new_trans, _ = kabsch(mobile[keep], target[nn][keep])
        if np.allclose(new_rot, rot, atol=1e-6) and np.allclose(new_trans, trans, atol=1e-6):
            rot, trans = new_rot, new_trans
            break
        rot, trans = new_rot, new_trans

    cur = apply_transform(mobile, rot, trans)
    nn = _nearest(cur, target)
    d = np.linalg.norm(cur - target[nn], axis=1)
    keep = d <= cutoff
    n = int(keep.sum())
    if n < 3:
        return rot, trans, float("inf"), 0
    return rot, trans, float(np.sqrt(np.mean(d[keep] ** 2))), n


def _pca_frame(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Centroid and principal-axis frame (columns = axes, largest first)."""
    centroid = pts.mean(axis=0)
    x = pts - centroid
    _, vecs = np.linalg.eigh(x.T @ x)
    return centroid, vecs[:, ::-1]


def super_structures(
    mobile: Structure, target: Structure
) -> tuple[np.ndarray, np.ndarray, float, int, int]:
    """Sequence-independent structural superposition (PCA-seeded ICP)."""
    m_xyz, m_tok = _representative_atoms(mobile)
    t_xyz, t_tok = _representative_atoms(target)
    if m_xyz.shape[0] < 3 or t_xyz.shape[0] < 3:
        raise ValueError("super: need >= 3 backbone residues in each object")

    mc, mv = _pca_frame(m_xyz)
    tc, tv = _pca_frame(t_xyz)
    seeds: list[tuple[np.ndarray, np.ndarray]] = []
    for s1 in (1.0, -1.0):
        for s2 in (1.0, -1.0):
            signs = np.diag([s1, s2, 1.0])
            rot = tv @ signs @ mv.T
            if np.linalg.det(rot) < 0:  # enforce a proper rotation
                rot = tv @ np.diag([s1, s2, -1.0]) @ mv.T
            seeds.append((rot, tc - rot @ mc))
    # Add the sequence pairing as a seed when the sequences overlap enough.
    pairs = needleman_wunsch(m_tok, t_tok)
    if len(pairs) >= 3:
        r0, t0, _ = kabsch(m_xyz[[i for i, _ in pairs]], t_xyz[[j for _, j in pairs]])
        seeds.append((r0, t0))

    min_match = max(3, int(0.25 * min(m_xyz.shape[0], t_xyz.shape[0])))
    best: tuple[np.ndarray, np.ndarray, float, int] | None = None
    for rot, trans in seeds:
        r, t, rms, n = _icp(m_xyz, t_xyz, rot, trans)
        if n >= min_match and (best is None or rms < best[2]):
            best = (r, t, rms, n)
    if best is None:
        raise ValueError("super: failed to find a structural superposition")
    rot, trans, rms, n = best
    return rot, trans, rms, n, 1
