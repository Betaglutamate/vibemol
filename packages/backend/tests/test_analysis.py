"""Tests for measurements (distance/angle/dihedral), polar contacts, and Kabsch."""

from __future__ import annotations

import numpy as np

from vibemol.analysis import (
    angle,
    apply_transform,
    dihedral,
    distance,
    kabsch,
    polar_contacts,
    rmsd,
)
from vibemol.model.structure import Structure


def test_distance_angle_dihedral() -> None:
    o = np.array([0.0, 0.0, 0.0])
    x = np.array([1.0, 0.0, 0.0])
    y = np.array([0.0, 1.0, 0.0])
    assert distance(o, x) == 1.0
    assert abs(angle(x, o, y) - 90.0) < 1e-4
    # Classic +90 degree dihedral.
    a = np.array([0.0, 1.0, 0.0])
    b = np.array([0.0, 0.0, 0.0])
    c = np.array([1.0, 0.0, 0.0])
    d = np.array([1.0, 0.0, 1.0])
    assert abs(abs(dihedral(a, b, c, d)) - 90.0) < 1e-4


def test_kabsch_recovers_known_transform() -> None:
    rng = np.random.default_rng(0)
    mobile = rng.normal(size=(20, 3))
    # A known rotation (90 deg about z) + translation.
    theta = np.pi / 2
    true_rot = np.array(
        [[np.cos(theta), -np.sin(theta), 0], [np.sin(theta), np.cos(theta), 0], [0, 0, 1]]
    )
    target = mobile @ true_rot.T + np.array([5.0, -2.0, 1.0])

    rot, trans, err = kabsch(mobile, target)
    assert err < 1e-6
    assert np.allclose(apply_transform(mobile, rot, trans), target, atol=1e-5)


def test_rmsd() -> None:
    a = np.zeros((5, 3))
    b = np.ones((5, 3))
    assert abs(rmsd(a, b) - np.sqrt(3.0)) < 1e-6


def test_polar_contacts() -> None:
    # Two N/O atoms 3.0 A apart on different residues -> one contact;
    # a distant carbon is ignored.
    coords = np.array([[0, 0, 0], [3.0, 0, 0], [20, 0, 0]], dtype=np.float32)
    s = Structure(
        name="t",
        coords=coords,
        elements=["O", "N", "C"],
        atom_names=["O", "N", "C"],
        res_names=["HOH", "ALA", "ALA"],
        res_ids=np.array([1, 2, 2], dtype=np.int32),
        chain_ids=["A", "A", "A"],
        b_factors=np.zeros(3, dtype=np.float32),
        occupancies=np.ones(3, dtype=np.float32),
        is_hetatm=np.array([True, False, False]),
    )
    contacts = polar_contacts(s, np.ones(3, dtype=bool))
    assert len(contacts) == 1
    assert {contacts[0][0], contacts[0][1]} == {0, 1}
    assert abs(contacts[0][2] - 3.0) < 1e-4
