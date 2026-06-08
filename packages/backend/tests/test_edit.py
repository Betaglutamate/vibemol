"""Tests for object-editing/quantitative commands: create/extract/count/com/transform."""

from __future__ import annotations

import importlib.resources as resources

import numpy as np

from vibemol.commands import Context, dispatch
from vibemol.io.pdb import parse_pdb_text
from vibemol.model.scene import Scene


def ctx_with_demo() -> Context:
    text = resources.files("vibemol.data").joinpath("benzene.pdb").read_text()
    ctx = Context(Scene())
    ctx.add_structure(parse_pdb_text(text, name="demo"))
    return ctx


def test_create_copies_without_touching_source() -> None:
    ctx = ctx_with_demo()
    dispatch(ctx, "create ring, elem C")
    assert ctx.scene.objects["ring"].structure.n_atoms == 6  # 6 carbons
    assert ctx.scene.objects["demo"].structure.n_atoms == 12  # source intact
    # The ring's C-C bonds survive the subset.
    assert ctx.scene.objects["ring"].structure.n_bonds == 6


def test_extract_moves_atoms_out_of_source() -> None:
    ctx = ctx_with_demo()
    dispatch(ctx, "extract hydro, elem H")
    assert ctx.scene.objects["hydro"].structure.n_atoms == 6  # the 6 hydrogens
    assert ctx.scene.objects["demo"].structure.n_atoms == 6  # removed from source


def test_count_atoms() -> None:
    ctx = ctx_with_demo()
    assert dispatch(ctx, "count_atoms elem C").log == "count_atoms: 6"
    assert dispatch(ctx, "count_atoms").log == "count_atoms: 12"


def test_centerofmass_near_origin() -> None:
    ctx = ctx_with_demo()  # benzene is built centered on the origin
    log = dispatch(ctx, "centerofmass").log
    coords = [float(x) for x in log.split("[")[1].rstrip("]").split(",")]
    assert all(abs(c) < 1e-2 for c in coords)


def test_translate_and_rotate() -> None:
    ctx = ctx_with_demo()
    dispatch(ctx, "translate [5, 0, 0], demo")
    assert abs(float(ctx.scene.objects["demo"].structure.coords[:, 0].mean()) - 5.0) < 1e-4

    ctx2 = ctx_with_demo()
    # C1 is at (1.39, 0, 0); a +90 deg rotation about z (centered at origin) -> (0, 1.39, 0).
    dispatch(ctx2, "rotate z, 90, demo")
    c1 = ctx2.scene.objects["demo"].structure.coords[0]
    assert np.allclose(c1, [0.0, 1.39, 0.0], atol=1e-2)


def test_get_extent() -> None:
    ctx = ctx_with_demo()
    log = dispatch(ctx, "get_extent").log
    assert "size" in log and "min" in log
