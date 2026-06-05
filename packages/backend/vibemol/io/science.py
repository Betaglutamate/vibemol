"""Parsers that depend on the optional ``[science]`` extra (Gemmi, RDKit).

Each function imports its backing library lazily and raises ``ImportError`` with
an actionable message when the extra is not installed, so callers can fall back
(see :func:`vibemol.io.fetch.fetch_pdb`).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..model.bonds import infer_bonds
from ..model.structure import Structure

_HINT = "install the science extra: pip install 'vibemol[science]'"


def parse_mmcif_text(text: str, name: str = "structure") -> Structure:
    """Parse mmCIF text into a Structure by reading the ``_atom_site`` loop with
    Gemmi's CIF tokenizer (first model only). Reading the columns directly is
    robust across gemmi versions and handles minimal/non-standard blocks."""
    try:
        import gemmi  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise ImportError(f"mmCIF parsing needs Gemmi; {_HINT}") from e

    block = gemmi.cif.read_string(text).sole_block()

    def col(tag: str) -> list[str]:
        # as_string strips CIF quoting — e.g. atom names like "C3'" are quoted
        # because they contain a prime; without this they'd keep literal quotes.
        return [gemmi.cif.as_string(v) for v in block.find_loop(f"_atom_site.{tag}")]

    xs, ys, zs = col("Cartn_x"), col("Cartn_y"), col("Cartn_z")
    n = len(xs)
    if n == 0:
        raise ValueError("mmCIF has no _atom_site coordinates")
    symbols = col("type_symbol")
    names = col("label_atom_id")
    comps = col("label_comp_id")
    chains = col("auth_asym_id") or col("label_asym_id")
    seqs = col("auth_seq_id") or col("label_seq_id")
    occs = col("occupancy")
    bfac = col("B_iso_or_equiv")
    groups = col("group_PDB")
    models = col("pdbx_PDB_model_num")
    first_model = models[0] if models else None

    def num(values: list[str], i: int, default: float) -> float:
        try:
            return float(values[i])
        except (ValueError, IndexError):
            return default

    elements: list[str] = []
    coords: list[tuple[float, float, float]] = []
    atom_names: list[str] = []
    res_names: list[str] = []
    res_ids: list[int] = []
    chain_ids: list[str] = []
    b_factors: list[float] = []
    occupancies: list[float] = []
    is_hetatm: list[bool] = []

    for i in range(n):
        if first_model is not None and models[i] != first_model:
            continue  # first model only
        elements.append((symbols[i] if i < len(symbols) else "C").upper())
        coords.append((float(xs[i]), float(ys[i]), float(zs[i])))
        atom_names.append(names[i] if i < len(names) else "")
        res_names.append(comps[i] if i < len(comps) else "UNL")
        res_ids.append(int(num(seqs, i, 0)))
        chain_ids.append(chains[i] if i < len(chains) else "A")
        b_factors.append(num(bfac, i, 0.0))
        occupancies.append(num(occs, i, 1.0))
        is_hetatm.append(i < len(groups) and groups[i] == "HETATM")

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


def parse_smiles_text(text: str, name: str = "ligand") -> Structure:
    """Parse a SMILES string and generate a 3D conformer (RDKit ETKDG + MMFF).

    SMILES carries no coordinates, so we add hydrogens, embed a 3D conformer, and
    energy-minimize it. The first whitespace-separated token is taken as the SMILES.
    """
    try:
        from rdkit import Chem  # noqa: PLC0415
        from rdkit.Chem import AllChem  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise ImportError(f"SMILES parsing needs RDKit; {_HINT}") from e

    smiles = text.strip().split()[0] if text.strip() else ""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit could not parse SMILES: {smiles!r}")
    mol = Chem.AddHs(mol)
    # AllChem's coordinate-embedding API is dynamically populated; treat as Any so
    # type-checking is consistent whether or not RDKit is installed.
    ac: Any = AllChem
    if ac.EmbedMolecule(mol, ac.ETKDGv3()) != 0:
        ac.EmbedMolecule(mol, useRandomCoords=True)  # fallback for tricky graphs
    try:
        ac.MMFFOptimizeMolecule(mol)
    except Exception:  # noqa: BLE001 - optimization is best-effort
        pass
    return _structure_from_rdkit(mol, name)
