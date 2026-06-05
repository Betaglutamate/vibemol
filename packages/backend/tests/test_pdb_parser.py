"""Tests for the self-contained PDB parser and bond inference."""

from __future__ import annotations

import importlib.resources as resources

from vibemol.io.pdb import parse_pdb_text


def _demo_text() -> str:
    return resources.files("vibemol.data").joinpath("benzene.pdb").read_text()


def test_parses_all_benzene_atoms() -> None:
    s = parse_pdb_text(_demo_text(), name="benzene")
    assert s.n_atoms == 12  # 6 C + 6 H
    assert s.elements.count("C") == 6
    assert s.elements.count("H") == 6
    assert s.coords.shape == (12, 3)


def test_infers_benzene_bonds() -> None:
    s = parse_pdb_text(_demo_text())
    # Benzene: 6 ring C-C bonds + 6 C-H bonds = 12 bonds.
    assert s.n_bonds == 12
    # Every bond pair is ordered (i < j).
    assert all(int(i) < int(j) for i, j in s.bonds)


def test_structure_geometry_helpers() -> None:
    s = parse_pdb_text(_demo_text())
    # Benzene is centered at the origin by construction.
    assert abs(float(s.center()[0])) < 1e-3
    assert abs(float(s.center()[1])) < 1e-3
    assert s.bounding_radius() > 2.0  # outermost H at radius 2.48 A
    assert s.vdw_radii().shape == (12,)
    assert s.cpk_colors_rgb().shape == (12, 3)
