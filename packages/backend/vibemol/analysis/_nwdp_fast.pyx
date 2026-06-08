# cython: boundscheck=False, wraparound=False, cdivision=True
"""Cython-accelerated DP and scoring for TM-align."""

import numpy as np
cimport numpy as cnp
from libc.math cimport sqrt

cnp.import_array()


def score_matrix(cnp.ndarray[double, ndim=2] mob, cnp.ndarray[double, ndim=2] tgt, double d0):
    """TM-score weight matrix with d01 = d0 + 1.5 cutoff.

    Returns an (n, m) float64 array.  Pairs beyond d01 are 0.
    """
    cdef int n = mob.shape[0]
    cdef int m = tgt.shape[0]
    cdef cnp.ndarray[double, ndim=2] out = np.zeros((n, m), dtype=np.float64)
    cdef double d01 = d0 + 1.5
    cdef double d01_sq = d01 * d01
    cdef double dx, dy, dz, d2, inv_d01_sq
    cdef int i, j

    inv_d01_sq = 1.0 / d01_sq

    for i in range(n):
        for j in range(m):
            dx = mob[i, 0] - tgt[j, 0]
            dy = mob[i, 1] - tgt[j, 1]
            dz = mob[i, 2] - tgt[j, 2]
            d2 = dx * dx + dy * dy + dz * dz
            if d2 <= d01_sq:
                out[i, j] = 1.0 / (1.0 + d2 * inv_d01_sq)

    return out


def nwdp(cnp.ndarray[double, ndim=2] score):
    """Needleman-Wunsch DP with free end gaps and gap penalty = 0.

    Returns a list of aligned (i, j) index pairs.
    """
    cdef int n = score.shape[0]
    cdef int m = score.shape[1]
    cdef cnp.ndarray[double, ndim=2] h = np.zeros((n + 1, m + 1), dtype=np.float64)
    cdef cnp.ndarray[cnp.int8_t, ndim=2] tb = np.zeros((n + 1, m + 1), dtype=np.int8)
    cdef double diag, up, left_val, cand, left_cand, s
    cdef int i, j
    cdef cnp.int8_t direction

    for i in range(1, n + 1):
        left_val = 0.0  # free leading gap
        for j in range(1, m + 1):
            s = score[i - 1, j - 1]
            diag = h[i - 1, j - 1] + s
            up = h[i - 1, j]  # gap = 0
            left_cand = left_val  # gap = 0

            if diag >= up:
                cand = diag
                direction = 0  # diagonal
            else:
                cand = up
                direction = 1  # up

            if left_cand > cand:
                cand = left_cand
                direction = 2  # left

            h[i, j] = cand
            tb[i, j] = direction
            left_val = cand

    # Traceback from best cell on last row / last column (free trailing gap).
    cdef double best_score = -1e30
    cdef int best_i = n, best_j = m

    for j in range(m + 1):
        if h[n, j] > best_score:
            best_score = h[n, j]
            best_i = n
            best_j = j
    for i in range(n + 1):
        if h[i, m] > best_score:
            best_score = h[i, m]
            best_i = i
            best_j = m

    pairs = []
    i = best_i
    j = best_j
    while i > 0 and j > 0:
        direction = tb[i, j]
        if direction == 0:
            i -= 1
            j -= 1
            pairs.append((i, j))
        elif direction == 1:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs
