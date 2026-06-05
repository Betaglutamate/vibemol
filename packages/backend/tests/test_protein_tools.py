"""Tests for the new protein analysis tools: colorings, SASA, interface, export."""

from __future__ import annotations

import importlib.resources as resources

import numpy as np
from test_cartoon import helix_structure

from vibemol.analysis import sasa
from vibemol.color import (
    color_by_charge,
    color_by_hydrophobicity,
    color_by_secondary_structure,
)
from vibemol.commands import Context, dispatch
from vibemol.io.pdb import parse_pdb_text
from vibemol.io.write_pdb import write_pdb
from vibemol.model.scene import Scene
from vibemol.model.structure import Structure


def _two_residue() -> Structure:
    # An acidic (ASP) and a basic (ARG) residue, one atom each, far apart.
    return Structure(
        name="t",
        coords=np.array([[0, 0, 0], [10, 0, 0]], dtype=np.float32),
        elements=["C", "C"],
        atom_names=["CA", "CA"],
        res_names=["ASP", "ARG"],
        res_ids=np.array([1, 2], dtype=np.int32),
        chain_ids=["A", "A"],
        b_factors=np.zeros(2, dtype=np.float32),
        occupancies=np.ones(2, dtype=np.float32),
        is_hetatm=np.zeros(2, dtype=bool),
    )


def test_hydrophobicity_coloring() -> None:
    # ILE (most hydrophobic) -> orange-ish; ARG (most hydrophilic) -> teal-ish.
    s = Structure(
        name="t", coords=np.zeros((2, 3), np.float32), elements=["C", "C"],
        atom_names=["CA", "CA"], res_names=["ILE", "ARG"],
        res_ids=np.array([1, 2], np.int32), chain_ids=["A", "A"],
        b_factors=np.zeros(2, np.float32), occupancies=np.ones(2, np.float32),
        is_hetatm=np.zeros(2, bool),
    )
    c = color_by_hydrophobicity(s)
    assert c[0][0] > c[0][2]  # ILE: more red than blue (orange)
    assert c[1][2] > c[1][0]  # ARG: more blue than red (teal)


def test_charge_coloring() -> None:
    c = color_by_charge(_two_residue())
    assert c[0][0] > c[0][2]  # ASP acidic -> red
    assert c[1][2] > c[1][0]  # ARG basic -> blue


def test_ss_coloring_runs() -> None:
    s = helix_structure(14)
    c = color_by_secondary_structure(s)
    assert c.shape == (14, 3)


def test_sasa_lone_vs_buried() -> None:
    # A lone carbon's SASA ~ 4*pi*(vdw+probe)^2; with a neighbour it drops.
    lone = Structure(
        name="t", coords=np.zeros((1, 3), np.float32), elements=["C"],
        atom_names=["C"], res_names=["UNL"], res_ids=np.array([1], np.int32),
        chain_ids=["A"], b_factors=np.zeros(1, np.float32),
        occupancies=np.ones(1, np.float32), is_hetatm=np.ones(1, bool),
    )
    area = sasa(lone)[0]
    expected = 4 * np.pi * (1.70 + 1.4) ** 2
    assert abs(area - expected) / expected < 0.05  # within 5% of the analytic sphere

    pair = Structure(
        name="t", coords=np.array([[0, 0, 0], [1.0, 0, 0]], np.float32), elements=["C", "C"],
        atom_names=["C", "C"], res_names=["UNL", "UNL"], res_ids=np.array([1, 1], np.int32),
        chain_ids=["A", "A"], b_factors=np.zeros(2, np.float32),
        occupancies=np.ones(2, np.float32), is_hetatm=np.ones(2, bool),
    )
    assert sasa(pair)[0] < area  # an overlapping neighbour occludes part of the surface


def test_sasa_and_interface_commands() -> None:
    text = resources.files("vibemol.data").joinpath("benzene.pdb").read_text()
    ctx = Context(Scene())
    ctx.add_structure(parse_pdb_text(text, name="demo"))
    res = dispatch(ctx, "sasa")
    assert "SASA" in res.log

    ctx2 = Context(Scene())
    ctx2.add_structure(parse_pdb_text(text, name="demo"))
    dispatch(ctx2, "interface elem C, elem H, 1.5")
    assert "interface" in ctx2.scene.selections


def test_color_scheme_commands() -> None:
    text = resources.files("vibemol.data").joinpath("benzene.pdb").read_text()
    ctx = Context(Scene())
    ctx.add_structure(parse_pdb_text(text, name="demo"))
    for scheme in ("hydrophobicity", "charge", "ss"):
        assert dispatch(ctx, f"color {scheme}").scene_changed


def test_write_pdb_round_trips() -> None:
    text = resources.files("vibemol.data").joinpath("benzene.pdb").read_text()
    original = parse_pdb_text(text, name="demo")
    reparsed = parse_pdb_text(write_pdb(original), name="rt")
    assert reparsed.n_atoms == original.n_atoms
    assert reparsed.elements == original.elements
    assert np.allclose(reparsed.coords, original.coords, atol=1e-3)
