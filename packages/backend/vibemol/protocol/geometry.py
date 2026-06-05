"""Builders for the binary draw groups streamed to the frontend.

A *draw group* is one batch of GPU primitives of a single kind. Bulk fields are
raw little-endian float32 blobs so the frontend wraps them directly as typed
arrays — never JSON arrays of vertices. Supported primitives:

  * ``spheres``   — positions (n*3), radii (n), colors (n*3)
  * ``cylinders`` — starts (n*3), ends (n*3), radii (n), colors (n*3)
  * ``lines``     — positions (2n*3), colors (2n*3)  [segment endpoint pairs]
  * ``points``    — positions (n*3), colors (n*3), size (scalar)
"""

from __future__ import annotations

from typing import Any

import numpy as np


def f32(arr: np.ndarray) -> bytes:
    """Contiguous little-endian float32 bytes for direct typed-array wrapping."""
    return np.ascontiguousarray(arr, dtype="<f4").tobytes()


def spheres_group(positions: np.ndarray, radii: np.ndarray, colors: np.ndarray) -> dict[str, Any]:
    return {
        "primitive": "spheres",
        "count": int(positions.shape[0]),
        "positions": f32(positions),
        "radii": f32(radii),
        "colors": f32(colors),
    }


def cylinders_group(
    starts: np.ndarray, ends: np.ndarray, radii: np.ndarray, colors: np.ndarray
) -> dict[str, Any]:
    return {
        "primitive": "cylinders",
        "count": int(starts.shape[0]),
        "starts": f32(starts),
        "ends": f32(ends),
        "radii": f32(radii),
        "colors": f32(colors),
    }


def lines_group(positions: np.ndarray, colors: np.ndarray) -> dict[str, Any]:
    return {
        "primitive": "lines",
        "count": int(positions.shape[0] // 2),
        "positions": f32(positions),
        "colors": f32(colors),
    }


def points_group(positions: np.ndarray, colors: np.ndarray, size: float) -> dict[str, Any]:
    return {
        "primitive": "points",
        "count": int(positions.shape[0]),
        "positions": f32(positions),
        "colors": f32(colors),
        "size": float(size),
    }
