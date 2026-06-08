"""TM-align / US-align structural superposition (native NumPy implementation).

Unlike ``align`` (sequence-based) and ``super`` (ICP), TM-align optimizes the
**TM-score** — a length-normalized similarity that downweights distant pairs and
saturates at ~1 for identical folds. Because the score is normalized by chain
length rather than by the count of matched atoms, it reliably finds the common
core of two structures that only *partially* overlap (different domains, extra
termini, circular permutation of the matched region's endpoints, etc.), which is
exactly what US-align is used for.

Algorithm (faithful to TM-align, Zhang & Skolnick 2005):

  1. Reduce each structure to one trace atom per residue (CA / sugar).
  2. Generate several initial superpositions (seeds): a sequence alignment, a
     gapless-threading sweep, and principal-axis orientations.
  3. For each seed, iterate: superpose -> build a residue x residue TM-score
     matrix -> re-align by dynamic programming (free end gaps) -> superpose on the
     new pairs. Keep the alignment with the highest TM-score.
  4. Report the TM-score normalized by each chain (as US-align does), the RMSD
     over the aligned core, and the rigid transform mapping mobile onto target.

Pure NumPy, no external binaries — runs anywhere the rest of VibeMol runs.
"""

from __future__ import annotations

import numpy as np

from ..model.structure import Structure
from .align import apply_transform, kabsch
from .sequence import needleman_wunsch
from .superpose import _pca_frame, _representative_atoms

_GAP = -0.6  # TM-align's DP gap penalty (scores live in [0, 1])
_MAX_DP_ITER = 8


def _d0(length: int) -> float:
    """TM-score distance scale d0 for a normalization length (clamped >= 0.5)."""
    return max(0.5, 1.24 * float(np.cbrt(length - 15)) - 1.8)


def _score_matrix(mob_t: np.ndarray, tgt: np.ndarray, d0: float) -> np.ndarray:
    """Residue x residue TM-score weights 1/(1 + (d/d0)^2) for transformed mobile."""
    d2 = ((mob_t[:, None, :] - tgt[None, :, :]) ** 2).sum(axis=2)
    return 1.0 / (1.0 + d2 / (d0 * d0))


def _tm(mob_t: np.ndarray, tgt: np.ndarray, d0: float, l_ref: int) -> float:
    """TM-score for already-superposed matched coords, normalized by ``l_ref``."""
    d2 = ((mob_t - tgt) ** 2).sum(axis=1)
    return float((1.0 / (1.0 + d2 / (d0 * d0))).sum() / l_ref)


def _nwdp(score: np.ndarray, gap: float) -> list[tuple[int, int]]:
    """Needleman-Wunsch over a score matrix with **free end gaps**.

    Maximizes the summed score along a monotonic path; leading and trailing gaps
    are unpenalized so a short structure can align to part of a longer one. The
    per-row diagonal/up candidates are vectorized; only the left-gap propagation
    is a scalar scan.
    """
    n, m = score.shape
    h = np.zeros((n + 1, m + 1))
    tb = np.zeros((n + 1, m + 1), dtype=np.int8)  # 0=diag, 1=up (gap in b), 2=left
    for i in range(1, n + 1):
        prev_row = h[i - 1]
        diag = prev_row[:-1] + score[i - 1]  # candidates for j = 1..m
        up = prev_row[1:] + gap
        base = np.where(diag >= up, diag, up)
        base_dir = np.where(diag >= up, 0, 1).astype(np.int8)
        row, tbi = h[i], tb[i]
        left_val = 0.0  # h[i, 0] (free leading gap)
        for j in range(1, m + 1):
            cand = base[j - 1]
            left = left_val + gap
            if cand >= left:
                row[j] = cand
                tbi[j] = base_dir[j - 1]
            else:
                row[j] = left
                tbi[j] = 2
            left_val = row[j]

    # Start traceback from the best cell on the last row/column (free trailing gap).
    last_row, last_col = h[n, :], h[:, m]
    if last_row.max() >= last_col.max():
        i, j = n, int(last_row.argmax())
    else:
        i, j = int(last_col.argmax()), m

    pairs: list[tuple[int, int]] = []
    while i > 0 and j > 0:
        d = tb[i, j]
        if d == 0:
            i, j = i - 1, j - 1
            pairs.append((i, j))
        elif d == 1:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


def _best_superposition(
    mob: np.ndarray, tgt: np.ndarray, d0: float, l_ref: int
) -> tuple[np.ndarray, np.ndarray, float]:
    """Rotation/translation maximizing TM-score for a *fixed* set of matched pairs.

    Mirrors TM-align's score search: superpose, then re-fit on progressively
    tighter inlier subsets, keeping whichever gives the best TM-score.
    """
    rot, trans, _ = kabsch(mob, tgt)
    best_rot, best_trans = rot, trans
    best_tm = _tm(apply_transform(mob, rot, trans), tgt, d0, l_ref)
    for factor in (3.0, 2.0, 1.0, 0.5):
        cur = apply_transform(mob, best_rot, best_trans)
        keep = np.linalg.norm(cur - tgt, axis=1) <= d0 * factor
        if int(keep.sum()) < 3:
            continue
        r, t, _ = kabsch(mob[keep], tgt[keep])
        tm = _tm(apply_transform(mob, r, t), tgt, d0, l_ref)
        if tm > best_tm:
            best_tm, best_rot, best_trans = tm, r, t
    return best_rot, best_trans, best_tm


def _refine(
    m_xyz: np.ndarray, t_xyz: np.ndarray, rot: np.ndarray, trans: np.ndarray,
    d0_search: float, d0: float, l_ref: int,
) -> tuple[float, np.ndarray, np.ndarray, list[tuple[int, int]]] | None:
    """Iterate superpose -> DP re-align from a seed transform; return the best."""
    best: tuple[float, np.ndarray, np.ndarray, list[tuple[int, int]]] | None = None
    prev: list[tuple[int, int]] | None = None
    for _ in range(_MAX_DP_ITER):
        mob_t = apply_transform(m_xyz, rot, trans)
        pairs = _nwdp(_score_matrix(mob_t, t_xyz, d0_search), _GAP)
        if len(pairs) < 3:
            break
        mi = [i for i, _ in pairs]
        tj = [j for _, j in pairs]
        rot, trans, tm = _best_superposition(m_xyz[mi], t_xyz[tj], d0, l_ref)
        if best is None or tm > best[0]:
            best = (tm, rot.copy(), trans.copy(), pairs)
        if pairs == prev:
            break
        prev = pairs
    return best


def _seed_transforms(
    m_xyz: np.ndarray, t_xyz: np.ndarray, m_tok: list[str], t_tok: list[str],
    d0: float, l_ref: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Initial superpositions: sequence alignment, gapless threading, PCA axes."""
    seeds: list[tuple[np.ndarray, np.ndarray]] = []

    # 1. Sequence alignment (when the sequences share enough).
    pairs = needleman_wunsch(m_tok, t_tok)
    if len(pairs) >= 3:
        r, t, _ = kabsch(m_xyz[[i for i, _ in pairs]], t_xyz[[j for _, j in pairs]])
        seeds.append((r, t))

    # 2. Gapless threading: slide mobile along target, keep the best few offsets.
    n, m = len(m_xyz), len(t_xyz)
    step = max(1, min(n, m) // 50)
    threaded: list[tuple[float, np.ndarray, np.ndarray]] = []
    for shift in range(-(n - 3), m - 2, step):
        i0, i1 = max(0, -shift), min(n, m - shift)
        if i1 - i0 < 3:
            continue
        idx = np.arange(i0, i1)
        r, t, _ = kabsch(m_xyz[idx], t_xyz[idx + shift])
        tm = _tm(apply_transform(m_xyz[idx], r, t), t_xyz[idx + shift], d0, l_ref)
        threaded.append((tm, r, t))
    threaded.sort(key=lambda x: -x[0])
    seeds.extend((r, t) for _, r, t in threaded[:3])

    # 3. Principal-axis orientations (sequence-independent), all sign flips.
    mc, mv = _pca_frame(m_xyz)
    tc, tv = _pca_frame(t_xyz)
    for s1 in (1.0, -1.0):
        for s2 in (1.0, -1.0):
            rot = tv @ np.diag([s1, s2, 1.0]) @ mv.T
            if np.linalg.det(rot) < 0:
                rot = tv @ np.diag([s1, s2, -1.0]) @ mv.T
            seeds.append((rot, tc - rot @ mc))
    return seeds


def tm_align(
    mobile: Structure, target: Structure
) -> tuple[np.ndarray, np.ndarray, float, float, float, int]:
    """TM-align superposition of ``mobile`` onto ``target``.

    Returns ``(rot, trans, tm_mobile, tm_target, rmsd, n_aligned)`` where the two
    TM-scores are normalized by the mobile and target chain lengths respectively
    (as US-align reports), and ``rmsd`` is over the aligned core.
    """
    m_xyz, m_tok = _representative_atoms(mobile)
    t_xyz, t_tok = _representative_atoms(target)
    l_mob, l_tgt = len(m_tok), len(t_tok)
    if l_mob < 3 or l_tgt < 3:
        raise ValueError("usalign: need >= 3 backbone residues in each object")

    l_ref = min(l_mob, l_tgt)
    d0 = _d0(l_ref)
    d0_search = min(8.0, max(4.5, d0))  # widen the DP capture radius

    best: tuple[float, np.ndarray, np.ndarray, list[tuple[int, int]]] | None = None
    for rot, trans in _seed_transforms(m_xyz, t_xyz, m_tok, t_tok, d0, l_ref):
        res = _refine(m_xyz, t_xyz, rot, trans, d0_search, d0, l_ref)
        if res is not None and (best is None or res[0] > best[0]):
            best = res
    if best is None:
        raise ValueError("usalign: failed to find a structural superposition")

    _, rot, trans, pairs = best
    mob_p = m_xyz[[i for i, _ in pairs]]
    tgt_p = t_xyz[[j for _, j in pairs]]
    d = np.linalg.norm(apply_transform(mob_p, rot, trans) - tgt_p, axis=1)
    n = len(pairs)
    rmsd_val = float(np.sqrt(np.mean(d**2)))

    d0_mob, d0_tgt = _d0(l_mob), _d0(l_tgt)
    tm_mob = float((1.0 / (1.0 + (d / d0_mob) ** 2)).sum() / l_mob)
    tm_tgt = float((1.0 / (1.0 + (d / d0_tgt) ** 2)).sum() / l_tgt)
    return rot, trans, tm_mob, tm_tgt, rmsd_val, n
