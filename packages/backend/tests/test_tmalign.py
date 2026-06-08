"""Correctness tests for TM-align (the ``usalign`` command).

The point of TM-align over ``align``/``super`` is partial overlap: it should find
and superpose the common core of two structures that share only a substructure,
reporting a high TM-score normalized by the shorter chain and a low core RMSD.
"""

from __future__ import annotations

import numpy as np
from test_superpose import chain_structure  # sibling fixture

from vibemol.analysis import tm_align
from vibemol.commands import Context, dispatch
from vibemol.model.scene import Scene


def _rot_z(deg: float) -> np.ndarray:
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)


def test_tm_align_identity_is_perfect() -> None:
    target = chain_structure("ACDEFGHIKLMNPQRST")  # 17 residues
    moved = target.coords @ _rot_z(50).T + np.array([6.0, -3.0, 2.0], dtype=np.float32)
    mobile = chain_structure("X" * target.n_atoms, coords=moved)  # sequence-independent

    _, _, tm_mob, tm_tgt, rms, n = tm_align(mobile, target)
    assert n == target.n_atoms
    assert rms < 1e-2
    assert tm_tgt > 0.99 and tm_mob > 0.99


def test_tm_align_finds_partial_overlap_core() -> None:
    # Target: a 30-residue helix. Mobile: 12 unrelated residues (displaced far away)
    # followed by a rotated+translated copy of the whole target. Only the 30-residue
    # tail is a true structural match -> usalign should recover exactly that core.
    target = chain_structure("A" * 30)
    moved = target.coords @ _rot_z(65).T + np.array([9.0, 4.0, -5.0], dtype=np.float32)
    junk = chain_structure("A" * 12).coords + np.array([60.0, 60.0, 60.0], dtype=np.float32)
    mobile = chain_structure("G" * 42, coords=np.vstack([junk, moved]))

    rot, trans, tm_mob, tm_tgt, rms, n = tm_align(mobile, target)
    assert n >= 28  # essentially the whole shared core
    assert rms < 0.5
    assert tm_tgt > 0.85  # normalized by the 30-residue target -> near 1
    assert tm_mob < tm_tgt  # normalized by the longer 42-residue mobile -> lower


def test_usalign_command_moves_mobile_and_reports_tmscore() -> None:
    ctx = Context(Scene())
    target = chain_structure("ACDEFGHIKLMNPQR")
    moved = target.coords @ _rot_z(30).T + np.array([10.0, 0.0, 0.0], dtype=np.float32)
    ctx.add_structure(chain_structure("ACDEFGHIKLMNPQR", coords=moved), name="mob")
    ctx.add_structure(target, name="tgt")

    before = ctx.scene.objects["mob"].structure.coords.copy()
    res = dispatch(ctx, "usalign mob, tgt")
    assert "TM-score" in res.log
    after = ctx.scene.objects["mob"].structure.coords
    assert not np.array_equal(after, before)  # mobile moved
    assert np.allclose(after, target.coords, atol=1e-2)  # now superposed
