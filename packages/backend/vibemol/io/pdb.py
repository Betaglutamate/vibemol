"""A self-contained PDB reader.

Phase 0 deliberately avoids heavy parsing dependencies so ``vibemol serve``
works on a bare install. Phase 1 adds Gemmi/RDKit-backed parsers (mmCIF, SDF,
MOL2, …) behind the ``[science]`` extra; they will produce the same
:class:`~vibemol.model.structure.Structure`, so downstream code is unaffected.

Only ATOM/HETATM coordinate records are read here (columns per the PDB v3.3
spec). CONECT records, when present, are merged with distance-based inference.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..model.bonds import infer_bonds
from ..model.structure import Structure


def _guess_element(raw_element: str, atom_name: str) -> str:
    """Resolve an element symbol from columns 77-78, falling back to the name."""
    e = raw_element.strip()
    if e:
        return e.upper()
    # Fall back to the atom name: strip leading digits/spaces, take letters.
    name = atom_name.strip().lstrip("0123456789")
    return (name[:2] if name[:2].isalpha() else name[:1]).upper()


def parse_pdb_text(text: str, name: str = "structure") -> Structure:
    """Parse PDB-format text into a :class:`Structure`."""
    coords: list[tuple[float, float, float]] = []
    elements: list[str] = []
    atom_names: list[str] = []
    res_names: list[str] = []
    res_ids: list[int] = []
    chain_ids: list[str] = []
    b_factors: list[float] = []
    occupancies: list[float] = []
    is_hetatm: list[bool] = []
    ids: list[int] = []
    serial_to_index: dict[int, int] = {}
    conect: list[tuple[int, int]] = []

    for line in text.splitlines():
        record = line[:6]
        if record in ("ATOM  ", "HETATM"):
            # Take only the first model: stop at the first ENDMDL boundary.
            try:
                x = float(line[30:38])
                y = float(line[38:46])
                z = float(line[46:54])
            except ValueError:
                continue
            try:
                serial = int(line[6:11])
            except ValueError:
                serial = len(coords)
            atom_name = line[12:16].strip()
            res_name = line[17:20].strip()
            chain = line[21:22].strip() or "A"
            try:
                res_id = int(line[22:26])
            except ValueError:
                res_id = 0
            occ = float(line[54:60]) if line[54:60].strip() else 1.0
            bf = float(line[60:66]) if line[60:66].strip() else 0.0
            element = _guess_element(line[76:78], atom_name)

            serial_to_index[serial] = len(coords)
            coords.append((x, y, z))
            elements.append(element)
            atom_names.append(atom_name)
            res_names.append(res_name)
            res_ids.append(res_id)
            chain_ids.append(chain)
            b_factors.append(bf)
            occupancies.append(occ)
            is_hetatm.append(record == "HETATM")
            ids.append(serial)
        elif record == "CONECT":
            try:
                a = int(line[6:11])
            except ValueError:
                continue
            for col in (11, 16, 21, 26):
                field = line[col:col + 5].strip()
                if field:
                    conect.append((a, int(field)))
        elif record == "ENDMDL":
            break  # first model only for Phase 0

    coords_arr = np.array(coords, dtype=np.float32).reshape(-1, 3)
    structure = Structure(
        name=name,
        coords=coords_arr,
        elements=elements,
        atom_names=atom_names,
        res_names=res_names,
        res_ids=np.array(res_ids, dtype=np.int32),
        chain_ids=chain_ids,
        b_factors=np.array(b_factors, dtype=np.float32),
        occupancies=np.array(occupancies, dtype=np.float32),
        is_hetatm=np.array(is_hetatm, dtype=bool),
        ids=np.array(ids, dtype=np.int32),
    )

    # Bonds: prefer explicit CONECT, then fill the rest by distance inference.
    explicit: set[tuple[int, int]] = set()
    for a, b in conect:
        if a in serial_to_index and b in serial_to_index:
            i, j = serial_to_index[a], serial_to_index[b]
            explicit.add((min(i, j), max(i, j)))
    inferred = {(int(i), int(j)) for i, j in infer_bonds(coords_arr, elements)}
    all_bonds = sorted(explicit | inferred)
    if all_bonds:
        structure.bonds = np.array(all_bonds, dtype=np.int32)
    return structure


def parse_pdb_file(path: str | Path, name: str | None = None) -> Structure:
    """Parse a PDB file from disk."""
    path = Path(path)
    return parse_pdb_text(path.read_text(), name=name or path.stem)
