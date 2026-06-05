"""Tests for XYZ parsing, format dispatch, and the optional science parsers."""

from __future__ import annotations

import importlib.util

import pytest

from vibemol.io import load_text, parse_xyz_text

_WATER_XYZ = """3
water
O   0.000   0.000   0.000
H   0.757   0.586   0.000
H  -0.757   0.586   0.000
"""


def test_parse_xyz() -> None:
    s = parse_xyz_text(_WATER_XYZ, name="water")
    assert s.n_atoms == 3
    assert s.elements == ["O", "H", "H"]
    # O-H bonds inferred by distance (~0.96 A); the two H are not bonded.
    assert s.n_bonds == 2


def test_load_text_dispatch() -> None:
    s = load_text(_WATER_XYZ, "xyz", name="w")
    assert s.n_atoms == 3
    with pytest.raises(ValueError):
        load_text("...", "nonsense")


@pytest.mark.skipif(
    importlib.util.find_spec("gemmi") is None,
    reason="requires the [science] extra (gemmi)",
)
def test_mmcif_via_gemmi() -> None:
    from vibemol.io.science import parse_mmcif_text

    # Minimal mmCIF with two atoms.
    cif = """data_test
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.B_iso_or_equiv
ATOM 1 C CA ALA A 1 0.000 0.000 0.000 1.00 10.00
ATOM 2 C CB ALA A 1 1.500 0.000 0.000 1.00 12.00
"""
    s = parse_mmcif_text(cif, name="t")
    assert s.n_atoms == 2
