"""Builders for binary geometry envelopes streamed to the frontend."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..model.structure import Structure


def _f32_bytes(arr: np.ndarray) -> bytes:
    """Contiguous little-endian float32 bytes for direct typed-array wrapping."""
    return np.ascontiguousarray(arr, dtype="<f4").tobytes()


def spheres_message(structure: Structure, *, scale: float = 0.4) -> dict[str, Any]:
    """Build a ``geometry`` message rendering an object as VDW spheres.

    Bulk fields are raw float32 blobs:
      - ``positions``: n_atoms * 3  (x, y, z)
      - ``radii``:     n_atoms      (scaled VDW radius)
      - ``colors``:    n_atoms * 3  (r, g, b in [0, 1])
    """
    positions = structure.coords
    radii = structure.vdw_radii() * scale
    colors = structure.cpk_colors_rgb()

    return {
        "type": "geometry",
        "object": structure.name,
        "representation": "spheres",
        "n_atoms": structure.n_atoms,
        "center": structure.center().tolist(),
        "bounding_radius": structure.bounding_radius(),
        "positions": _f32_bytes(positions),
        "radii": _f32_bytes(radii),
        "colors": _f32_bytes(colors),
    }
