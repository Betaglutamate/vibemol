"""Tests for molecular surface generation (requires SciPy + scikit-image)."""

from __future__ import annotations

import importlib.resources as resources
import importlib.util

import numpy as np
import pytest

from vibemol.io.pdb import parse_pdb_text

_HAS_SKIMAGE = importlib.util.find_spec("skimage") is not None
pytestmark = pytest.mark.skipif(not _HAS_SKIMAGE, reason="requires the [science] extra")


def demo_structure():
    text = resources.files("vibemol.data").joinpath("benzene.pdb").read_text()
    return parse_pdb_text(text)


def test_build_surface_mesh() -> None:
    from vibemol.geometry.surface import build_surface_mesh

    s = demo_structure()
    mesh = build_surface_mesh(s, np.ones(s.n_atoms, dtype=bool), s.cpk_colors_rgb())
    assert mesh is not None
    assert mesh["primitive"] == "mesh"
    assert mesh["count"] > 0  # triangles
    assert mesh["n_vertices"] > 0
    assert len(mesh["positions"]) == mesh["n_vertices"] * 3 * 4
    assert len(mesh["indices"]) == mesh["count"] * 3 * 4


def test_surface_empty_mask_returns_none() -> None:
    from vibemol.geometry.surface import build_surface_mesh

    s = demo_structure()
    assert build_surface_mesh(s, np.zeros(s.n_atoms, dtype=bool), s.cpk_colors_rgb()) is None
