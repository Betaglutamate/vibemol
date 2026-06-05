"""Builders for the binary draw groups streamed to the frontend.

A *draw group* is one batch of GPU primitives of a single kind. Bulk fields are
raw little-endian float32 blobs so the frontend wraps them directly as typed
arrays — never JSON arrays of vertices. Supported primitives:

  * ``spheres``   — positions (n*3), radii (n), colors (n*3)
  * ``cylinders`` — starts (n*3), ends (n*3), radii (n), colors (n*3)
  * ``lines``     — positions (2n*3), colors (2n*3)  [segment endpoint pairs]
  * ``points``    — positions (n*3), colors (n*3), size (scalar)
  * ``mesh``      — positions (v*3), normals (v*3), colors (v*3), indices (t*3 uint32)
"""

from __future__ import annotations

from typing import Any

import numpy as np


def f32(arr: np.ndarray) -> bytes:
    """Contiguous little-endian float32 bytes for direct typed-array wrapping."""
    return np.ascontiguousarray(arr, dtype="<f4").tobytes()


def u32(arr: np.ndarray) -> bytes:
    """Contiguous little-endian uint32 bytes (mesh triangle indices)."""
    return np.ascontiguousarray(arr, dtype="<u4").tobytes()


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


def mesh_group(
    positions: np.ndarray, normals: np.ndarray, colors: np.ndarray, indices: np.ndarray
) -> dict[str, Any]:
    flat = np.ascontiguousarray(indices).reshape(-1)  # accept (t,3) or flat indices
    return {
        "primitive": "mesh",
        "count": int(flat.shape[0] // 3),
        "n_vertices": int(positions.shape[0]),
        "positions": f32(positions),
        "normals": f32(normals),
        "colors": f32(colors),
        "indices": u32(flat),
    }
