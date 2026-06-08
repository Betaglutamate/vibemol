"""Correctness tests for the alignment engine: NW, iterative fit, align, super.

These directly exercise the bug the rewrite fixes — that the old code paired the
first N CA atoms positionally, which is wrong under renumbering / extra residues /
different order.
"""

from __future__ import annotations

import numpy as np

from vibemol.analysis import (
    align_structures,
    iterative_fit,
    needleman_wunsch,
    super_structures,
)
from vibemol.commands import Context, dispatch
from vibemol.model.scene import Scene
from vibemol.model.structure import Structure


def _rot_z(deg: float) -> np.ndarray:
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)


def chain_structure(seq: str, start_resid: int = 1, coords: np.ndarray | None = None) -> Structure:
    """A helix with one CA per residue; residue names are the sequence letters."""
    n = len(seq)
    if coords is None:
        i = np.arange(n)
        theta = np.radians(100.0) * i
        coords = np.stack([2.3 * np.cos(theta), 2.3 * np.sin(theta), 1.5 * i], axis=1)
    return Structure(
        name="s",
        coords=coords.astype(np.float32),
        elements=["C"] * n,
        atom_names=["CA"] * n,
        res_names=list(seq),
        res_ids=np.arange(start_resid, start_resid + n, dtype=np.int32),
        chain_ids=["A"] * n,
        b_factors=np.zeros(n, dtype=np.float32),
        occupancies=np.ones(n, dtype=np.float32),
        is_hetatm=np.zeros(n, dtype=bool),
    )


def test_needleman_wunsch_with_gap() -> None:
    # Target is missing the 'D'; align should gap it, keeping the rest in register.
    assert needleman_wunsch("ACDEF", "ACEF") == [(0, 0), (1, 1), (3, 2), (4, 3)]


def test_iterative_fit_recovers_transform_and_rejects_outliers() -> None:
    rng = np.random.default_rng(1)
    pts = rng.normal(size=(20, 3))
    target = pts @ _rot_z(35).T + np.array([4.0, -1.0, 2.0])

    _, _, rms, n, _ = iterative_fit(pts, target)
    assert rms < 1e-6 and n == 20

    # Corrupt three target points -> they must be rejected, RMSD stays ~0.
    bad = target.copy()
    bad[:3] += 50.0
    _, _, rms2, n2, _ = iterative_fit(pts, bad)
    assert n2 == 17 and rms2 < 1e-6


def test_align_is_robust_to_renumbering_and_extra_residues() -> None:
    target = chain_structure("ACDEFGHIKLMN")  # resid 1..12
    moved = target.coords @ _rot_z(40).T + np.array([7.0, 3.0, -2.0], dtype=np.float32)
    # Mobile: 3 unrelated residues prepended, and renumbered 98.. — positional
    # pairing (the old behavior) would mis-pair and give a large RMSD.
    junk = np.array([[100, 0, 0], [101, 0, 0], [102, 0, 0]], dtype=np.float32)
    mobile = chain_structure(
        "WWWACDEFGHIKLMN", start_resid=98, coords=np.vstack([junk, moved])
    )
    _, _, rms, n, _ = align_structures(mobile, target)
    assert n == 12  # only the real overlap is matched
    assert rms < 1e-3  # and it superposes essentially perfectly


def test_super_is_sequence_and_order_independent() -> None:
    target = chain_structure("ACDEFGHIKLMN")
    rng = np.random.default_rng(2)
    perm = rng.permutation(target.n_atoms)  # shuffle residue order
    moved = (target.coords[perm] @ _rot_z(120).T) + np.array([5.0, -4.0, 6.0], dtype=np.float32)
    mobile = chain_structure("X" * target.n_atoms, coords=moved)  # no usable sequence
    _, _, rms, n, _ = super_structures(mobile, target)
    assert n >= 10 and rms < 0.5


def test_align_command_moves_mobile_and_rms_cur_does_not() -> None:
    ctx = Context(Scene())
    target = chain_structure("ACDEFGHIKLMN")
    moved = target.coords @ _rot_z(30).T + np.array([10.0, 0.0, 0.0], dtype=np.float32)
    ctx.add_structure(chain_structure("ACDEFGHIKLMN", coords=moved), name="mob")
    ctx.add_structure(target, name="tgt")

    before = ctx.scene.objects["mob"].structure.coords.copy()
    rms_res = dispatch(ctx, "rms_cur mob, tgt")
    assert "rms_cur" in rms_res.log
    assert np.array_equal(ctx.scene.objects["mob"].structure.coords, before)  # no move

    dispatch(ctx, "align mob, tgt")
    assert not np.array_equal(ctx.scene.objects["mob"].structure.coords, before)  # moved
    assert np.allclose(
        ctx.scene.objects["mob"].structure.coords, target.coords, atol=1e-2
    )  # now superposed
