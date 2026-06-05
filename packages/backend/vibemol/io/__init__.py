"""Structure I/O.

Core (no extra deps): PDB and XYZ readers, RCSB fetch, and a format dispatcher.
The optional ``[science]`` extra adds Gemmi (mmCIF) and RDKit (SDF/MOL2) parsers
via :mod:`vibemol.io.science`.
"""

from .fetch import fetch_pdb
from .loaders import SUPPORTED_FORMATS, load_path, load_text
from .pdb import parse_pdb_file, parse_pdb_text
from .xyz import parse_xyz_file, parse_xyz_text

__all__ = [
    "parse_pdb_file",
    "parse_pdb_text",
    "parse_xyz_file",
    "parse_xyz_text",
    "fetch_pdb",
    "load_text",
    "load_path",
    "SUPPORTED_FORMATS",
]
