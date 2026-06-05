"""Tests for cartoon SS assignment and ribbon mesh generation."""

from __future__ import annotations

import numpy as np

from vibemol.geometry.cartoon import _assign_ss, build_cartoon_mesh, has_protein_backbone
from vibemol.model.structure import Structure


def helix_structure(n: int = 14) -> Structure:
    """An idealized alpha-helix CA trace (radius 2.3 A, 100 deg/residue, 1.5 A rise)."""
    i = np.arange(n)
    theta = np.radians(100.0) * i
    coords = np.stack([2.3 * np.cos(theta), 2.3 * np.sin(theta), 1.5 * i], axis=1).astype(
        np.float32
    )
    return Structure(
        name="helix",
        coords=coords,
        elements=["C"] * n,
        atom_names=["CA"] * n,
        res_names=["ALA"] * n,
        res_ids=np.arange(1, n + 1, dtype=np.int32),
        chain_ids=["A"] * n,
        b_factors=np.zeros(n, dtype=np.float32),
        occupancies=np.ones(n, dtype=np.float32),
        is_hetatm=np.zeros(n, dtype=bool),
    )


def test_has_protein_backbone() -> None:
    assert has_protein_backbone(helix_structure())


def test_ss_assignment_detects_helix() -> None:
    s = helix_structure()
    ss = _assign_ss(s.coords)
    # The bulk of an ideal alpha helix should be classified 'H'.
    assert ss.count("H") >= int(0.6 * len(ss))


def test_build_cartoon_mesh() -> None:
    s = helix_structure()
    mask = np.ones(s.n_atoms, dtype=bool)
    mesh = build_cartoon_mesh(s, mask, s.cpk_colors_rgb())
    assert mesh is not None
    assert mesh["primitive"] == "mesh"
    assert mesh["count"] > 0  # triangles
    assert mesh["n_vertices"] > 0
    # positions/normals/colors are v*3 float32; indices are count*3 uint32.
    assert len(mesh["positions"]) == mesh["n_vertices"] * 3 * 4
    assert len(mesh["normals"]) == mesh["n_vertices"] * 3 * 4
    assert len(mesh["indices"]) == mesh["count"] * 3 * 4


def test_cartoon_skips_non_protein() -> None:
    s = helix_structure(3)
    # No CA in the mask -> no ribbon.
    mesh = build_cartoon_mesh(s, np.zeros(s.n_atoms, dtype=bool), s.cpk_colors_rgb())
    assert mesh is None
