"""Tests for representation geometry builders and coloring schemes."""

from __future__ import annotations

import importlib.resources as resources

import numpy as np

from vibemol.color import ColorError, color_by_chain, color_spectrum, parse_color
from vibemol.geometry import build_groups
from vibemol.io.pdb import parse_pdb_text
from vibemol.model.scene import MolObject


def demo() -> MolObject:
    text = resources.files("vibemol.data").joinpath("benzene.pdb").read_text()
    obj = MolObject(name="demo", structure=parse_pdb_text(text))
    obj.apply_default_representation()
    return obj


def _by_primitive(groups: list[dict]) -> dict[str, dict]:
    return {g["primitive"]: g for g in groups}


def test_default_representation_is_lines() -> None:
    groups = build_groups(demo())
    prims = _by_primitive(groups)
    assert "lines" in prims
    # Benzene has 12 bonds (6 C-C + 6 C-H); a line segment per bond.
    assert prims["lines"]["count"] == 12
    # 12 segments => 24 endpoints => 24*3 float32 = 288 bytes.
    assert len(prims["lines"]["positions"]) == 24 * 3 * 4


def test_spheres_representation() -> None:
    obj = demo()
    obj.show_as("spheres", np.ones(obj.structure.n_atoms, dtype=bool))
    prims = _by_primitive(build_groups(obj))
    assert set(prims) == {"spheres"}
    assert prims["spheres"]["count"] == 12
    assert len(prims["spheres"]["radii"]) == 12 * 4


def test_sticks_emit_cylinders_and_caps() -> None:
    obj = demo()
    obj.show_as("sticks", np.ones(obj.structure.n_atoms, dtype=bool))
    prims = _by_primitive(build_groups(obj))
    assert prims["cylinders"]["count"] == 12 * 2  # half-bond split
    assert prims["spheres"]["count"] == 12  # capping spheres at all atoms


def test_dots_cloud_scales_with_atoms() -> None:
    obj = demo()
    obj.show_as("dots", np.ones(obj.structure.n_atoms, dtype=bool))
    prims = _by_primitive(build_groups(obj))
    assert prims["points"]["count"] == 12 * 36  # _DOTS_PER_ATOM per atom


def test_color_parsing_and_schemes() -> None:
    assert parse_color("red") == (1.0, 0.2, 0.2)
    assert parse_color("#ff0000") == (1.0, 0.0, 0.0)
    assert parse_color("00ff00") == (0.0, 1.0, 0.0)
    for bad in ("not-a-color", "#xyz"):
        try:
            parse_color(bad)
            raise AssertionError("expected ColorError")
        except ColorError:
            pass

    obj = demo()
    chain_colors = color_by_chain(obj.structure)
    assert chain_colors.shape == (12, 3)
    spec = color_spectrum(obj.structure, by="b")
    assert spec.shape == (12, 3)
