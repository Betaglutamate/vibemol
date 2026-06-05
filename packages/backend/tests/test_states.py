"""Tests for multi-model parsing, set_state, and state round-tripping."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from vibemol.commands import Context, dispatch
from vibemol.io.pdb import parse_pdb_text
from vibemol.model.scene import Scene
from vibemol.session import load_session, save_session

_TWO_MODEL = """MODEL        1
HETATM    1  C1  LIG A   1       0.000   0.000   0.000  1.00  0.00           C
HETATM    2  C2  LIG A   1       1.500   0.000   0.000  1.00  0.00           C
ENDMDL
MODEL        2
HETATM    1  C1  LIG A   1       0.000   0.000   5.000  1.00  0.00           C
HETATM    2  C2  LIG A   1       1.500   0.000   5.000  1.00  0.00           C
ENDMDL
"""


def test_parses_multiple_models_as_states() -> None:
    s = parse_pdb_text(_TWO_MODEL, name="multi")
    assert s.n_atoms == 2
    assert s.n_states == 2
    assert s.states.shape == (2, 2, 3)
    # coords start at state 0 (z = 0).
    assert float(s.coords[0, 2]) == 0.0


def test_set_state_switches_coordinates() -> None:
    s = parse_pdb_text(_TWO_MODEL)
    s.set_state(1)
    assert float(s.coords[0, 2]) == 5.0
    s.set_state(2)  # wraps back to state 0
    assert float(s.coords[0, 2]) == 0.0


def test_set_state_command() -> None:
    ctx = Context(Scene())
    ctx.add_structure(parse_pdb_text(_TWO_MODEL, name="multi"))
    dispatch(ctx, "set_state 2")
    assert float(ctx.scene.objects["multi"].structure.coords[0, 2]) == 5.0


def test_states_round_trip_in_session(tmp_path: Path) -> None:
    ctx = Context(Scene())
    ctx.add_structure(parse_pdb_text(_TWO_MODEL, name="multi"))
    dispatch(ctx, "set_state 2")
    path = tmp_path / "s.vibe"
    save_session(ctx.scene, path)
    loaded = load_session(path)
    obj = loaded.objects["multi"]
    assert obj.structure.n_states == 2
    assert np.array_equal(obj.structure.states, ctx.scene.objects["multi"].structure.states)
