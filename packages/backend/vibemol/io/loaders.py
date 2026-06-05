"""Format-dispatching loaders: pick the right parser by format or file suffix."""

from __future__ import annotations

from pathlib import Path

from ..model.structure import Structure
from .pdb import parse_pdb_text
from .xyz import parse_xyz_text

_SUFFIX_FORMAT = {
    ".pdb": "pdb", ".ent": "pdb",
    ".cif": "mmcif", ".mmcif": "mmcif",
    ".xyz": "xyz",
    ".sdf": "sdf", ".mol": "sdf",
    ".mol2": "mol2",
    ".smi": "smiles", ".smiles": "smiles",
}

SUPPORTED_FORMATS = ("pdb", "mmcif", "xyz", "sdf", "mol2", "smiles")


def load_text(text: str, fmt: str, name: str = "structure") -> Structure:
    """Parse ``text`` in the given format into a Structure."""
    fmt = fmt.lower()
    if fmt == "pdb":
        return parse_pdb_text(text, name=name)
    if fmt == "xyz":
        return parse_xyz_text(text, name=name)
    if fmt in ("mmcif", "cif"):
        from .science import parse_mmcif_text  # noqa: PLC0415

        return parse_mmcif_text(text, name=name)
    if fmt in ("sdf", "mol"):
        from .science import parse_sdf_text  # noqa: PLC0415

        return parse_sdf_text(text, name=name)
    if fmt == "mol2":
        from .science import parse_mol2_text  # noqa: PLC0415

        return parse_mol2_text(text, name=name)
    if fmt in ("smiles", "smi"):
        from .science import parse_smiles_text  # noqa: PLC0415

        return parse_smiles_text(text, name=name)
    raise ValueError(f"unsupported format: {fmt!r} (supported: {', '.join(SUPPORTED_FORMATS)})")


def load_path(path: str | Path) -> Structure:
    """Load a structure file, choosing the parser from its extension."""
    path = Path(path)
    fmt = _SUFFIX_FORMAT.get(path.suffix.lower())
    if fmt is None:
        raise ValueError(f"unrecognized file extension: {path.suffix!r}")
    return load_text(path.read_text(), fmt, name=path.stem)
