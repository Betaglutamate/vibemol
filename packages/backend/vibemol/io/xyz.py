"""A reader for the simple XYZ coordinate format.

    <n_atoms>
    <comment>
    <element> <x> <y> <z>
    ...

XYZ carries no topology, so bonds are inferred by distance.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..model.bonds import infer_bonds
from ..model.structure import Structure


def parse_xyz_text(text: str, name: str = "structure") -> Structure:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("empty XYZ file")
    try:
        n = int(lines[0].split()[0])
    except (ValueError, IndexError) as e:
        raise ValueError("XYZ: first line must be the atom count") from e

    elements: list[str] = []
    coords: list[tuple[float, float, float]] = []
    for ln in lines[2 : 2 + n]:  # skip count + comment
        parts = ln.split()
        if len(parts) < 4:
            continue
        elements.append(parts[0].upper())
        coords.append((float(parts[1]), float(parts[2]), float(parts[3])))

    coords_arr = np.array(coords, dtype=np.float32).reshape(-1, 3)
    na = coords_arr.shape[0]
    return Structure(
        name=name,
        coords=coords_arr,
        elements=elements,
        atom_names=list(elements),
        res_names=["UNL"] * na,
        res_ids=np.ones(na, dtype=np.int32),
        chain_ids=["A"] * na,
        b_factors=np.zeros(na, dtype=np.float32),
        occupancies=np.ones(na, dtype=np.float32),
        is_hetatm=np.ones(na, dtype=bool),
        bonds=infer_bonds(coords_arr, elements),
    )


def parse_xyz_file(path: str | Path, name: str | None = None) -> Structure:
    path = Path(path)
    return parse_xyz_text(path.read_text(), name=name or path.stem)
