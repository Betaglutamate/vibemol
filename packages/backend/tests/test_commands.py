"""Tests for the command system against a loaded demo scene."""

from __future__ import annotations

import importlib.resources as resources

import numpy as np
import pytest

from vibemol.color import ColorError
from vibemol.commands import CommandError, Context, dispatch
from vibemol.io.pdb import parse_pdb_text
from vibemol.model.scene import Scene


def ctx_with_demo() -> Context:
    text = resources.files("vibemol.data").joinpath("benzene.pdb").read_text()
    ctx = Context(Scene())
    ctx.add_structure(parse_pdb_text(text, name="demo"))
    return ctx


def obj(ctx: Context):
    return ctx.scene.objects["demo"]


def test_parse_and_unknown_command() -> None:
    ctx = ctx_with_demo()
    with pytest.raises(CommandError):
        dispatch(ctx, "frobnicate stuff")
    # blank lines / comments are no-ops.
    assert dispatch(ctx, "   ").scene_changed is False
    assert dispatch(ctx, "# a comment").scene_changed is False


def test_show_hide_as() -> None:
    ctx = ctx_with_demo()
    dispatch(ctx, "as spheres")
    assert obj(ctx).rep_masks["spheres"].all()
    assert not obj(ctx).rep_masks["lines"].any()  # `as` clears other reps

    dispatch(ctx, "show sticks, elem C")
    assert obj(ctx).rep_masks["sticks"].sum() == 6  # 6 carbons

    dispatch(ctx, "hide spheres, elem H")
    assert obj(ctx).rep_masks["spheres"].sum() == 6  # hydrogens hidden


def test_color_flat_and_scheme() -> None:
    ctx = ctx_with_demo()
    dispatch(ctx, "color red, elem C")
    carbons = np.array([e == "C" for e in obj(ctx).structure.elements])
    assert np.allclose(obj(ctx).colors[carbons], (1.0, 0.2, 0.2))

    res = dispatch(ctx, "color bychain")
    assert res.scene_changed
    with pytest.raises(ColorError):
        dispatch(ctx, "color not-a-color")


def test_select_and_delete_selection() -> None:
    ctx = ctx_with_demo()
    res = dispatch(ctx, "select carbons, elem C")
    assert res.selections_changed and not res.scene_changed
    assert ctx.scene.selections["carbons"]["demo"].sum() == 6
    dispatch(ctx, "deselect carbons")
    assert "carbons" not in ctx.scene.selections


def test_color_a_named_selection() -> None:
    ctx = ctx_with_demo()
    dispatch(ctx, "select ring, elem C")
    dispatch(ctx, "color blue, ring")  # reference the named selection by name
    carbons = np.array([e == "C" for e in obj(ctx).structure.elements])
    assert np.allclose(obj(ctx).colors[carbons], (0.36, 0.36, 1.0))


def test_set_name_renames_selection() -> None:
    ctx = ctx_with_demo()
    dispatch(ctx, "select ring, elem C")
    res = dispatch(ctx, "set_name ring, core")
    assert res.selections_changed
    assert "core" in ctx.scene.selections and "ring" not in ctx.scene.selections
    # The renamed selection is still referenceable.
    dispatch(ctx, "color red, core")
    with pytest.raises(CommandError):
        dispatch(ctx, "set_name nonexistent, x")


def test_set_name_renames_object() -> None:
    ctx = ctx_with_demo()
    dispatch(ctx, "set_name demo, benzene")
    assert "benzene" in ctx.scene.objects and "demo" not in ctx.scene.objects


def test_enable_disable_object() -> None:
    ctx = ctx_with_demo()
    assert obj(ctx).visible is True
    res = dispatch(ctx, "disable demo")
    assert obj(ctx).visible is False and res.scene_changed
    dispatch(ctx, "enable demo")
    assert obj(ctx).visible is True
    dispatch(ctx, "disable all")
    assert obj(ctx).visible is False
    with pytest.raises(CommandError):
        dispatch(ctx, "disable nosuchobject")


def test_bg_color_and_set() -> None:
    ctx = ctx_with_demo()
    dispatch(ctx, "bg_color white")
    assert ctx.scene.settings["bg_color"] == "#ffffff"
    dispatch(ctx, "set stick_radius, 0.3")
    assert ctx.scene.settings["stick_radius"] == "0.3"


def test_zoom_returns_camera() -> None:
    ctx = ctx_with_demo()
    res = dispatch(ctx, "zoom all")
    assert res.camera is not None
    assert res.scene_changed is False
    assert res.camera["radius"] >= 1.0


def test_remove_and_delete_object() -> None:
    ctx = ctx_with_demo()
    dispatch(ctx, "remove elem H")
    assert obj(ctx).structure.n_atoms == 6  # only carbons remain
    assert obj(ctx).structure.n_bonds == 6  # the ring survives, C-H bonds gone
    dispatch(ctx, "delete all")
    assert not ctx.scene.objects


def test_unknown_representation_errors() -> None:
    ctx = ctx_with_demo()
    with pytest.raises(CommandError):
        dispatch(ctx, "show bananas")
