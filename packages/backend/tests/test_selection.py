"""Selection-engine tests: a fixture structure -> expected atom counts.

This is the growth point for selection-language fidelity: add a row here for
every new selector or edge case.
"""

from __future__ import annotations

import numpy as np
import pytest

from vibemol.model.structure import Structure
from vibemol.select import SelectionError, select


def fixture() -> Structure:
    # 2 ALA-ish/GLY residues on chain A near the origin + one water on chain B far away.
    coords = np.array(
        [
            (0, 0, 0), (1, 0, 0), (2, 0, 0), (2, 1, 0), (1, 1, 0),  # A/1 N CA C O CB
            (5, 0, 0), (6, 0, 0), (7, 0, 0), (7, 1, 0),             # A/2 N CA C O
            (20, 0, 0),                                            # B/1 water O
        ],
        dtype=np.float32,
    )
    return Structure(
        name="fix",
        coords=coords,
        elements=["N", "C", "C", "O", "C", "N", "C", "C", "O", "O"],
        atom_names=["N", "CA", "C", "O", "CB", "N", "CA", "C", "O", "O"],
        res_names=["ALA"] * 5 + ["GLY"] * 4 + ["HOH"],
        res_ids=np.array([1, 1, 1, 1, 1, 2, 2, 2, 2, 1], dtype=np.int32),
        chain_ids=["A"] * 9 + ["B"],
        b_factors=np.array([10, 20, 30, 40, 50, 15, 25, 35, 45, 60], dtype=np.float32),
        occupancies=np.ones(10, dtype=np.float32),
        is_hetatm=np.array([False] * 9 + [True]),
    )


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("all", 10),
        ("none", 0),
        ("", 10),  # empty selects all
        ("chain A", 9),
        ("chain B", 1),
        ("resn ALA", 5),
        ("resn ALA+GLY", 9),
        ("resn al*", 5),  # wildcard, case-insensitive
        ("resi 1", 6),  # ALA (5) + water (1) both have resi 1
        ("resi 1 and chain A", 5),
        ("resi 1-2", 10),
        ("resi 2+1", 10),
        ("name CA", 2),
        ("name C*", 5),  # CA, C, CB across the two protein residues
        ("elem O", 3),
        ("elem N", 2),
        ("hetatm", 1),
        ("solvent", 1),
        ("polymer", 9),
        ("not chain A", 1),
        ("chain A and not name CA", 7),
        ("chain A or chain B", 10),
        ("b > 30", 5),
        ("b >= 30", 6),
        ("b < 20", 2),
        ("byres name CA", 9),  # whole ALA + GLY residues, water excluded
        ("within 1.5 of name CB", 5),  # all of residue A/1
        ("name CB around 1.5", 4),  # neighbours of CB, excluding CB itself
        ("not (chain B or hetatm)", 9),
        ("backbone and chain A", 8),  # N/CA/C/O of the two protein residues
    ],
)
def test_selection_counts(expr: str, expected: int) -> None:
    mask = select(fixture(), expr)
    assert int(mask.sum()) == expected, f"{expr!r} -> {int(mask.sum())}, expected {expected}"


@pytest.mark.parametrize("expr", ["resn", "(chain A", "b >", "within of name CA", "bogus"])
def test_selection_errors(expr: str) -> None:
    with pytest.raises(SelectionError):
        select(fixture(), expr)


def test_named_selection_reference() -> None:
    s = fixture()
    # A named selection in scope can be referenced by name and combined.
    named = {"sele": select(s, "elem O")}
    assert int(select(s, "sele", named).sum()) == 3
    assert int(select(s, "sele and chain A", named).sum()) == 2
    assert int(select(s, "not sele", named).sum()) == 7
    # An unknown bareword (no such named selection) is still an error.
    with pytest.raises(SelectionError):
        select(s, "nope", {"sele": named["sele"]})
