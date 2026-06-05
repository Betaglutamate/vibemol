"""Round-trip tests for .vibe session save/load."""

from __future__ import annotations

import importlib.resources as resources
from pathlib import Path

import numpy as np

from vibemol.commands import Context, dispatch
from vibemol.io.pdb import parse_pdb_text
from vibemol.model.scene import Scene
from vibemol.session import dump_session, load_session, load_session_bytes, save_session


def test_session_round_trip(tmp_path: Path) -> None:
    text = resources.files("vibemol.data").joinpath("benzene.pdb").read_text()
    ctx = Context(Scene())
    ctx.add_structure(parse_pdb_text(text, name="demo"))
    dispatch(ctx, "as sticks")
    dispatch(ctx, "color red, elem C")
    dispatch(ctx, "select carbons, elem C")
    dispatch(ctx, "bg_color white")

    path = tmp_path / "scene.vibe"
    save_session(ctx.scene, path)
    loaded = load_session(path)

    assert list(loaded.objects) == ["demo"]
    orig, new = ctx.scene.objects["demo"], loaded.objects["demo"]
    assert new.structure.n_atoms == orig.structure.n_atoms
    assert np.array_equal(new.structure.coords, orig.structure.coords)
    assert np.array_equal(new.structure.bonds, orig.structure.bonds)
    assert np.array_equal(new.rep_masks["sticks"], orig.rep_masks["sticks"])
    assert np.allclose(new.colors, orig.colors)
    assert loaded.settings["bg_color"] == "#ffffff"
    assert "carbons" in loaded.selections
    assert int(loaded.selections["carbons"]["demo"].sum()) == 6


def test_session_bytes_round_trip() -> None:
    text = resources.files("vibemol.data").joinpath("benzene.pdb").read_text()
    ctx = Context(Scene())
    ctx.add_structure(parse_pdb_text(text, name="demo"))
    dispatch(ctx, "as spheres")
    data = dump_session(ctx.scene)
    assert isinstance(data, bytes) and len(data) > 0
    loaded = load_session_bytes(data)
    assert list(loaded.objects) == ["demo"]
    assert loaded.objects["demo"].rep_masks["spheres"].all()
