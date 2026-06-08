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

try:
    from ._nwdp_fast import nwdp as _nwdp_c, score_matrix as _score_matrix_c
except ImportError:
    _nwdp_c = None
    _score_matrix_c = None

_MAX_DP_ITER = 20


def _d0(length: int) -> float:
    """TM-score distance scale d0 for a normalization length (clamped >= 0.5)."""
    return max(0.5, 1.24 * float(np.cbrt(length - 15)) - 1.8)


def _score_matrix(
    mob_t: np.ndarray, tgt: np.ndarray, d0: float,
) -> np.ndarray:
    """Residue x residue TM-score weights with distance cutoff.

    Uses d01 = d0 + 1.5 as both the scoring denominator and the distance
    cutoff, matching TM-align's ``get_score_fast`` in the C implementation.
    Pairs beyond d01 get score 0 so the DP (gap = 0) ignores them.
    """
    if _score_matrix_c is not None:
        return _score_matrix_c(
            np.ascontiguousarray(mob_t, dtype=np.float64),
            np.ascontiguousarray(tgt, dtype=np.float64),
            float(d0),
        )
    d01 = d0 + 1.5
    d01_sq = d01 * d01
    d2 = ((mob_t[:, None, :] - tgt[None, :, :]) ** 2).sum(axis=2)
    scores = 1.0 / (1.0 + d2 / d01_sq)
    scores[d2 > d01_sq] = 0.0
    return scores


def _tm(mob_t: np.ndarray, tgt: np.ndarray, d0: float, l_ref: int) -> float:
    """TM-score for already-superposed matched coords, normalized by ``l_ref``."""
    d2 = ((mob_t - tgt) ** 2).sum(axis=1)
    return float((1.0 / (1.0 + d2 / (d0 * d0))).sum() / l_ref)


def _nwdp_py(score: np.ndarray) -> list[tuple[int, int]]:
    """Pure-Python fallback for the Needleman-Wunsch DP (gap = 0, free end gaps)."""
    n, m = score.shape
    h = np.zeros((n + 1, m + 1))
    tb = np.zeros((n + 1, m + 1), dtype=np.int8)  # 0=diag, 1=up, 2=left
    for i in range(1, n + 1):
        prev_row = h[i - 1]
        diag = prev_row[:-1] + score[i - 1]
        up = prev_row[1:]
        base = np.where(diag >= up, diag, up)
        base_dir = np.where(diag >= up, 0, 1).astype(np.int8)
        row, tbi = h[i], tb[i]
        left_val = 0.0
        for j in range(1, m + 1):
            cand = base[j - 1]
            left = left_val
            if cand >= left:
                row[j] = cand
                tbi[j] = base_dir[j - 1]
            else:
                row[j] = left
                tbi[j] = 2
            left_val = row[j]

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


def _nwdp(score: np.ndarray, gap: float) -> list[tuple[int, int]]:
    """Needleman-Wunsch DP with free end gaps and gap = 0.

    Uses the Cython extension when available, otherwise falls back to Python.
    The ``gap`` parameter is accepted for API compatibility but must be 0.
    """
    if _nwdp_c is not None:
        return _nwdp_c(np.ascontiguousarray(score, dtype=np.float64))
    return _nwdp_py(score)


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
    # TM-align uses finer distance cutoff levels for the inlier search.
    for cutoff in (d0 + 8, d0 + 4, d0 + 2, d0 + 1, d0, d0 - 1, d0 - 2, 0.5):
        if cutoff < 0.5:
            continue
        cur = apply_transform(mob, best_rot, best_trans)
        keep = np.linalg.norm(cur - tgt, axis=1) <= cutoff
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
    """Iterate superpose -> DP re-align from a seed transform; return the best.

    Uses gap = 0 and d01 = d0 + 1.5 cutoff in the score matrix, matching
    TM-align's C implementation.
    """
    best: tuple[float, np.ndarray, np.ndarray, list[tuple[int, int]]] | None = None
    prev: list[tuple[int, int]] | None = None
    for _ in range(_MAX_DP_ITER):
        mob_t = apply_transform(m_xyz, rot, trans)
        pairs = _nwdp(_score_matrix(mob_t, t_xyz, d0_search), 0.0)
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
    step = max(1, min(n, m) // 100)
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
    seeds.extend((r, t) for _, r, t in threaded[:5])

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


def _chains(s: Structure) -> dict[str, list[int]]:
    """Map chain ID → sorted list of atom indices for that chain."""
    chains: dict[str, list[int]] = {}
    for i in range(s.n_atoms):
        chains.setdefault(s.chain_ids[i], []).append(i)
    return chains


def _chain_trace(s: Structure, indices: list[int]) -> tuple[np.ndarray, list[str]]:
    """Representative trace atoms for a single chain (subset of atom indices)."""
    sub = s.subset(np.isin(np.arange(s.n_atoms), indices))
    return _representative_atoms(sub)


def _score_d8(length: int) -> float:
    """Distance cutoff for the reported aligned core (USalign convention)."""
    return 1.5 * float(length ** 0.3) + 3.5


def _align_chain_pair(
    m_xyz: np.ndarray, t_xyz: np.ndarray,
    m_tok: list[str], t_tok: list[str],
) -> tuple[np.ndarray, np.ndarray, float, float, float, int]:
    """Run TM-align on a single chain pair, return (rot, trans, tm_mob, tm_tgt, rmsd, n)."""
    l_mob, l_tgt = len(m_tok), len(t_tok)
    if l_mob < 3 or l_tgt < 3:
        raise ValueError("usalign: need >= 3 backbone residues in each chain")

    # Try optimization normalizing by each chain length independently (as USalign does),
    # keep whichever produces the higher TM-score.
    best_result: tuple[float, np.ndarray, np.ndarray, list[tuple[int, int]]] | None = None
    best_score = -1.0

    for l_ref in sorted(set([l_mob, l_tgt])):
        d0 = _d0(l_ref)
        d0_search = min(8.0, max(4.5, d0))

        candidate: tuple[float, np.ndarray, np.ndarray, list[tuple[int, int]]] | None = None
        for rot, trans in _seed_transforms(m_xyz, t_xyz, m_tok, t_tok, d0, l_ref):
            res = _refine(m_xyz, t_xyz, rot, trans, d0_search, d0, l_ref)
            if res is not None and (candidate is None or res[0] > candidate[0]):
                candidate = res
        if candidate is None:
            continue

        _, rot, trans, pairs = candidate
        mob_p = m_xyz[[i for i, _ in pairs]]
        tgt_p = t_xyz[[j for _, j in pairs]]
        d = np.linalg.norm(apply_transform(mob_p, rot, trans) - tgt_p, axis=1)
        d0_mob, d0_tgt = _d0(l_mob), _d0(l_tgt)
        tm_mob = float((1.0 / (1.0 + (d / d0_mob) ** 2)).sum() / l_mob)
        tm_tgt = float((1.0 / (1.0 + (d / d0_tgt) ** 2)).sum() / l_tgt)
        score = max(tm_mob, tm_tgt)

        if score > best_score:
            best_score = score
            best_result = candidate

    if best_result is None:
        raise ValueError("usalign: failed to find a structural superposition")

    # Filter to the aligned core: only pairs within score_d8 distance,
    # matching USalign's reporting convention.
    _, rot, trans, pairs = best_result
    mob_p = m_xyz[[i for i, _ in pairs]]
    tgt_p = t_xyz[[j for _, j in pairs]]
    d = np.linalg.norm(apply_transform(mob_p, rot, trans) - tgt_p, axis=1)

    d8 = _score_d8(max(l_mob, l_tgt))
    core = d <= d8
    d_core = d[core]
    n_core = int(core.sum())
    if n_core < 1:
        n_core = len(pairs)
        d_core = d

    d0_mob, d0_tgt = _d0(l_mob), _d0(l_tgt)
    tm_mob = float((1.0 / (1.0 + (d_core / d0_mob) ** 2)).sum() / l_mob)
    tm_tgt = float((1.0 / (1.0 + (d_core / d0_tgt) ** 2)).sum() / l_tgt)
    rmsd_val = float(np.sqrt(np.mean(d_core**2)))

    return rot, trans, tm_mob, tm_tgt, rmsd_val, n_core


def tm_align(
    mobile: Structure, target: Structure
) -> tuple[np.ndarray, np.ndarray, float, float, float, int]:
    """TM-align superposition of ``mobile`` onto ``target``.

    Returns ``(rot, trans, tm_mobile, tm_target, rmsd, n_aligned)`` where the two
    TM-scores are normalized by the mobile and target chain lengths respectively
    (as US-align reports), and ``rmsd`` is over the aligned core.

    When either structure has multiple chains, all chain-chain pairings are tried
    and the best one is returned (mirroring USalign's default behaviour).
    """
    mob_chains = _chains(mobile)
    tgt_chains = _chains(target)

    # Single-chain fast path (or structures with no chain annotation).
    if len(mob_chains) <= 1 and len(tgt_chains) <= 1:
        m_xyz, m_tok = _representative_atoms(mobile)
        t_xyz, t_tok = _representative_atoms(target)
        if len(m_tok) < 3 or len(t_tok) < 3:
            raise ValueError("usalign: need >= 3 backbone residues in each object")
        return _align_chain_pair(m_xyz, t_xyz, m_tok, t_tok)

    # Multi-chain: try all chain-chain pairings, pick the best.
    # Pre-compute traces, skip tiny chains (< 10 residues).
    mob_traces: list[tuple[str, np.ndarray, list[str]]] = []
    for mc_id, mc_idx in mob_chains.items():
        m_xyz, m_tok = _chain_trace(mobile, mc_idx)
        if len(m_tok) >= 10:
            mob_traces.append((mc_id, m_xyz, m_tok))
    tgt_traces: list[tuple[str, np.ndarray, list[str]]] = []
    for tc_id, tc_idx in tgt_chains.items():
        t_xyz, t_tok = _chain_trace(target, tc_idx)
        if len(t_tok) >= 10:
            tgt_traces.append((tc_id, t_xyz, t_tok))

    # Fall back to the full structure if no chain has >= 10 residues.
    if not mob_traces or not tgt_traces:
        m_xyz, m_tok = _representative_atoms(mobile)
        t_xyz, t_tok = _representative_atoms(target)
        if len(m_tok) < 3 or len(t_tok) < 3:
            raise ValueError("usalign: need >= 3 backbone residues in each object")
        return _align_chain_pair(m_xyz, t_xyz, m_tok, t_tok)

    best: tuple[np.ndarray, np.ndarray, float, float, float, int] | None = None
    best_score = -1.0
    for mc_id, m_xyz, m_tok in mob_traces:
        for tc_id, t_xyz, t_tok in tgt_traces:
            try:
                result = _align_chain_pair(m_xyz, t_xyz, m_tok, t_tok)
            except ValueError:
                continue
            score = max(result[2], result[3])  # max(tm_mob, tm_tgt)
            if score > best_score:
                best_score = score
                best = result

    if best is None:
        raise ValueError("usalign: failed to find a structural superposition")
    return best
