"""Tests for SMILES loading and nucleic-acid cartoon support."""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from vibemol.geometry.cartoon import build_cartoon_mesh, has_cartoon_backbone
from vibemol.model.structure import Structure

_HAS_RDKIT = importlib.util.find_spec("rdkit") is not None


def nucleic_structure(n: int = 8) -> Structure:
    """An idealized B-DNA-ish single strand: one P per residue on a helix."""
    i = np.arange(n)
    theta = np.radians(36.0) * i  # ~36 deg/bp
    xyz = [9.0 * np.cos(theta), 9.0 * np.sin(theta), 3.4 * i]
    coords = np.stack(xyz, axis=1).astype(np.float32)
    return Structure(
        name="dna",
        coords=coords,
        elements=["P"] * n,
        atom_names=["P"] * n,
        res_names=["DA"] * n,
        res_ids=np.arange(1, n + 1, dtype=np.int32),
        chain_ids=["A"] * n,
        b_factors=np.zeros(n, dtype=np.float32),
        occupancies=np.ones(n, dtype=np.float32),
        is_hetatm=np.zeros(n, dtype=bool),
    )


def test_nucleic_has_cartoon_backbone() -> None:
    s = nucleic_structure()
    assert has_cartoon_backbone(s)


def test_nucleic_cartoon_mesh() -> None:
    s = nucleic_structure()
    mesh = build_cartoon_mesh(s, np.ones(s.n_atoms, dtype=bool), s.cpk_colors_rgb())
    assert mesh is not None
    assert mesh["primitive"] == "mesh"
    assert mesh["count"] > 0 and mesh["n_vertices"] > 0


@pytest.mark.skipif(not _HAS_RDKIT, reason="requires the [science] extra (rdkit)")
def test_smiles_loads_with_3d_coords() -> None:
    from vibemol.io import load_text

    s = load_text("CC(=O)Oc1ccccc1C(=O)O", "smiles", name="aspirin")  # aspirin
    assert s.n_atoms == 21  # 13 heavy + 8 H
    assert s.n_bonds > 0
    assert float(np.abs(s.coords).max()) > 0.1  # real 3D conformer, not all-zero
    assert "smiles" in __import__("vibemol.io", fromlist=["SUPPORTED_FORMATS"]).SUPPORTED_FORMATS


@pytest.mark.skipif(not _HAS_RDKIT, reason="requires the [science] extra (rdkit)")
def test_bad_smiles_raises() -> None:
    from vibemol.io import load_text

    with pytest.raises(ValueError):
        load_text("this is not smiles!!!", "smiles")
