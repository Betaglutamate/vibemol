"""Parsers that depend on the optional ``[science]`` extra (Gemmi, RDKit).

Each function imports its backing library lazily and raises ``ImportError`` with
an actionable message when the extra is not installed, so callers can fall back
(see :func:`vibemol.io.fetch.fetch_pdb`).
"""

from __future__ import annotations

import numpy as np

from ..model.bonds import infer_bonds
from ..model.structure import Structure

_HINT = "install the science extra: pip install 'vibemol[science]'"


def parse_mmcif_text(text: str, name: str = "structure") -> Structure:
    """Parse mmCIF text into a Structure using Gemmi (first model only)."""
    try:
        import gemmi  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise ImportError(f"mmCIF parsing needs Gemmi; {_HINT}") from e

    block = gemmi.cif.read_string(text).sole_block()
    st = gemmi.make_structure_from_block(block)
    st.setup_entities()

    elements: list[str] = []
    coords: list[tuple[float, float, float]] = []
    atom_names: list[str] = []
    res_names: list[str] = []
    res_ids: list[int] = []
    chain_ids: list[str] = []
    b_factors: list[float] = []
    occupancies: list[float] = []
    is_hetatm: list[bool] = []

    model = st[0]
    for chain in model:
        for res in chain:
            het = res.het_flag == "H"
            for atom in res:
                elements.append(atom.element.name.upper())
                coords.append((atom.pos.x, atom.pos.y, atom.pos.z))
                atom_names.append(atom.name)
                res_names.append(res.name)
                res_ids.append(res.seqid.num)
                chain_ids.append(chain.name)
                b_factors.append(atom.b_iso)
                occupancies.append(atom.occ)
                is_hetatm.append(het)

    coords_arr = np.array(coords, dtype=np.float32).reshape(-1, 3)
    return Structure(
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
        bonds=infer_bonds(coords_arr, elements),
    )


def _structure_from_rdkit(mol: object, name: str) -> Structure:
    from rdkit import Chem  # noqa: PLC0415

    rdmol = mol  # typed loosely; rdkit objects aren't statically typed here
    conf = rdmol.GetConformer()  # type: ignore[attr-defined]
    elements, coords, atom_names = [], [], []
    for atom in rdmol.GetAtoms():  # type: ignore[attr-defined]
        pos = conf.GetAtomPosition(atom.GetIdx())
        sym = atom.GetSymbol().upper()
        elements.append(sym)
        coords.append((pos.x, pos.y, pos.z))
        atom_names.append(f"{sym}{atom.GetIdx() + 1}")
    bonds = [
        (b.GetBeginAtomIdx(), b.GetEndAtomIdx())
        for b in rdmol.GetBonds()  # type: ignore[attr-defined]
    ]
    bonds_arr = (
        np.array([(min(i, j), max(i, j)) for i, j in bonds], dtype=np.int32)
        if bonds
        else np.empty((0, 2), dtype=np.int32)
    )
    na = len(elements)
    _ = Chem  # keep import referenced
    return Structure(
        name=name,
        coords=np.array(coords, dtype=np.float32).reshape(-1, 3),
        elements=elements,
        atom_names=atom_names,
        res_names=["UNL"] * na,
        res_ids=np.ones(na, dtype=np.int32),
        chain_ids=["A"] * na,
        b_factors=np.zeros(na, dtype=np.float32),
        occupancies=np.ones(na, dtype=np.float32),
        is_hetatm=np.ones(na, dtype=bool),
        bonds=bonds_arr,
    )


def parse_sdf_text(text: str, name: str = "structure") -> Structure:
    """Parse the first molecule of an SDF/MOL block via RDKit."""
    try:
        from rdkit import Chem  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise ImportError(f"SDF parsing needs RDKit; {_HINT}") from e
    mol = Chem.MolFromMolBlock(text, removeHs=False)
    if mol is None:
        raise ValueError("RDKit could not parse the SDF/MOL block")
    return _structure_from_rdkit(mol, name)


def parse_mol2_text(text: str, name: str = "structure") -> Structure:
    """Parse a MOL2 block via RDKit."""
    try:
        from rdkit import Chem  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise ImportError(f"MOL2 parsing needs RDKit; {_HINT}") from e
    mol = Chem.MolFromMol2Block(text, removeHs=False)
    if mol is None:
        raise ValueError("RDKit could not parse the MOL2 block")
    return _structure_from_rdkit(mol, name)
