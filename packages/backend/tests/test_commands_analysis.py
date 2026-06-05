"""Tests for measurement and alignment commands."""

from __future__ import annotations

import numpy as np
from test_cartoon import helix_structure

from vibemol.analysis import apply_transform
from vibemol.commands import Context, dispatch
from vibemol.model.scene import Scene


def test_distance_and_clear() -> None:
    ctx = Context(Scene())
    s = helix_structure(4)
    ctx.add_structure(s, name="h")
    res = dispatch(ctx, "distance d1, index 1, index 2")
    assert "distance" in res.log
    assert len(ctx.scene.measurements) == 1
    assert ctx.scene.measurements[0].kind == "distance"
    dispatch(ctx, "delete_measurements")
    assert not ctx.scene.measurements


def test_dihedral_records_four_points() -> None:
    ctx = Context(Scene())
    ctx.add_structure(helix_structure(6), name="h")
    dispatch(ctx, "dihedral index 1, index 2, index 3, index 4")
    assert ctx.scene.measurements[0].kind == "dihedral"
    assert len(ctx.scene.measurements[0].points) == 4


def test_align_superposes_objects() -> None:
    ctx = Context(Scene())
    target = helix_structure(12)
    ctx.add_structure(target, name="tgt")

    # A rotated + translated copy of the same helix.
    theta = np.pi / 3
    rot = np.array(
        [[np.cos(theta), -np.sin(theta), 0], [np.sin(theta), np.cos(theta), 0], [0, 0, 1]]
    )
    mobile = helix_structure(12)
    mobile.coords = apply_transform(mobile.coords, rot, np.array([10.0, 4.0, -3.0]))
    ctx.add_structure(mobile, name="mob")

    res = dispatch(ctx, "align mob, tgt")
    assert "RMSD" in res.log
    # After alignment the mobile CA atoms should match the target's closely.
    aligned = ctx.scene.objects["mob"].structure.coords
    assert np.allclose(aligned, target.coords, atol=1e-3)
