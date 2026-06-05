"""Structure I/O. Phase 0 ships a self-contained PDB reader; Phase 1 adds
Gemmi/RDKit-backed parsers (mmCIF, SDF, MOL2, XYZ) and RCSB fetch."""

from .pdb import parse_pdb_file, parse_pdb_text

__all__ = ["parse_pdb_file", "parse_pdb_text"]
