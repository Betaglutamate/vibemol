"""Typed control messages (the non-geometry parts of the protocol)."""

from __future__ import annotations

from pydantic import BaseModel


class LoadCommand(BaseModel):
    """Client -> server: load a structure.

    Phase 0 supports the bundled demo (``source="demo"``). Phase 1 extends this
    with ``source="rcsb"`` (fetch by PDB id) and ``source="upload"``.
    """

    type: str = "load"
    source: str = "demo"
    id: str | None = None


class ErrorMessage(BaseModel):
    """Server -> client: a human-readable error."""

    type: str = "error"
    message: str
