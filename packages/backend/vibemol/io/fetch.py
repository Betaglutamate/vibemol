"""Fetch structures from the RCSB PDB by accession id.

Uses the standard library only (no extra runtime dependency). mmCIF is
preferred when the optional ``[science]`` extra (Gemmi) is available, since it
is the modern canonical format; otherwise the legacy PDB format is used.
"""

from __future__ import annotations

import urllib.request

from ..model.structure import Structure
from .pdb import parse_pdb_text

_PDB_URL = "https://files.rcsb.org/download/{id}.pdb"
_CIF_URL = "https://files.rcsb.org/download/{id}.cif"


def _download(url: str, timeout: float) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (trusted host)
        return resp.read().decode("utf-8", errors="replace")


def fetch_pdb(pdb_id: str, *, timeout: float = 30.0) -> Structure:
    """Fetch a structure from RCSB by 4-character PDB id (e.g. ``1ubq``)."""
    pid = pdb_id.strip().lower()
    if not pid:
        raise ValueError("empty PDB id")

    try:  # prefer mmCIF via Gemmi when available
        from .science import parse_mmcif_text  # noqa: PLC0415

        return parse_mmcif_text(_download(_CIF_URL.format(id=pid), timeout), name=pid)
    except ImportError:
        return parse_pdb_text(_download(_PDB_URL.format(id=pid), timeout), name=pid)
