"""Needleman-Wunsch global sequence alignment.

Used by ``align`` to establish a residue correspondence between two structures
from their one-letter sequences before structural superposition. Identity
scoring (match/mismatch/gap) keeps it general across protein and nucleic
sequences; no external dependencies.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

_MATCH = 1.0
_MISMATCH = -1.0
_GAP = -2.0


def needleman_wunsch(
    seq_a: Sequence[object],
    seq_b: Sequence[object],
    *,
    match: float = _MATCH,
    mismatch: float = _MISMATCH,
    gap: float = _GAP,
) -> list[tuple[int, int]]:
    """Globally align two sequences; return aligned index pairs ``(i, j)``.

    Works on strings or token lists (e.g. residue names). Only non-gap columns
    are returned (positions aligned in both sequences), in increasing order —
    exactly the residue pairs to superpose.
    """
    n, m = len(seq_a), len(seq_b)
    if n == 0 or m == 0:
        return []

    # Score matrix with full-gap initial row/column.
    score = np.zeros((n + 1, m + 1), dtype=np.float64)
    score[:, 0] = np.arange(n + 1) * gap
    score[0, :] = np.arange(m + 1) * gap
    # Traceback: 0=diagonal, 1=up (gap in b), 2=left (gap in a).
    trace = np.zeros((n + 1, m + 1), dtype=np.int8)
    trace[1:, 0] = 1
    trace[0, 1:] = 2

    for i in range(1, n + 1):
        a = seq_a[i - 1]
        for j in range(1, m + 1):
            diag = score[i - 1, j - 1] + (match if a == seq_b[j - 1] else mismatch)
            up = score[i - 1, j] + gap
            left = score[i, j - 1] + gap
            best = max(diag, up, left)
            score[i, j] = best
            trace[i, j] = 0 if best == diag else (1 if best == up else 2)

    pairs: list[tuple[int, int]] = []
    i, j = n, m
    while i > 0 or j > 0:
        t = trace[i, j]
        if t == 0:
            i, j = i - 1, j - 1
            pairs.append((i, j))  # aligned column
        elif t == 1:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs
