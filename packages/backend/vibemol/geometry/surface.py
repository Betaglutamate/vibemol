"""Molecular surface generation via a Gaussian density field + marching cubes.

A smooth ("blobby") surface is built by summing per-atom Gaussians onto a 3D
grid and extracting an isosurface. Each Gaussian is tuned so a lone atom's
surface sits at its van der Waals radius; overlapping atoms blend smoothly.

Requires the optional ``[science]`` extra (SciPy + scikit-image). Vertices are
colored by their nearest atom.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..model.structure import Structure
from ..protocol.geometry import mesh_group

_LEVEL = 0.5            # isosurface threshold (atom surface at its VDW radius)
_SIGMA_FACTOR = 1.1774  # sqrt(2 ln 2): exp(-r^2 / 2 sigma^2) = 0.5 at r = radius
_MAX_DIM = 110          # cap grid dimension for performance


def build_surface_mesh(
    structure: Structure, mask: np.ndarray, colors: np.ndarray
) -> dict[str, Any] | None:
    """Build the surface mesh draw group, or None if unavailable/empty."""
    try:
        from scipy.spatial import cKDTree  # noqa: PLC0415
        from skimage.measure import marching_cubes  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise ImportError(
            "surface needs SciPy + scikit-image: pip install 'vibemol[science]'"
        ) from e

    idx = np.flatnonzero(mask)
    if idx.shape[0] == 0:
        return None
    coords = structure.coords[idx].astype(np.float64)
    radii = structure.vdw_radii()[idx].astype(np.float64)

    pad = float(radii.max()) * 1.5 + 1.0
    lo = coords.min(axis=0) - pad
    hi = coords.max(axis=0) + pad
    extent = hi - lo
    spacing = max(float(extent.max()) / _MAX_DIM, 0.5)
    dims = np.maximum(np.ceil(extent / spacing).astype(int) + 1, 2)

    field = np.zeros(tuple(dims), dtype=np.float32)
    sigmas = radii / _SIGMA_FACTOR
    inv_two_sigma2 = 1.0 / (2.0 * sigmas * sigmas)
    reach = (radii * 2.0 + spacing)  # voxel window half-width per atom

    for a in range(coords.shape[0]):
        center = coords[a]
        r = reach[a]
        i0 = np.maximum(((center - r - lo) / spacing).astype(int), 0)
        i1 = np.minimum(((center + r - lo) / spacing).astype(int) + 1, dims)
        if np.any(i1 <= i0):
            continue
        xs = (lo[0] + np.arange(i0[0], i1[0]) * spacing) - center[0]
        ys = (lo[1] + np.arange(i0[1], i1[1]) * spacing) - center[1]
        zs = (lo[2] + np.arange(i0[2], i1[2]) * spacing) - center[2]
        d2 = (xs[:, None, None] ** 2 + ys[None, :, None] ** 2 + zs[None, None, :] ** 2)
        field[i0[0]:i1[0], i0[1]:i1[1], i0[2]:i1[2]] += np.exp(-d2 * inv_two_sigma2[a]).astype(
            np.float32
        )

    if float(field.max()) < _LEVEL:
        return None
    try:
        verts, faces, normals, _ = marching_cubes(field, level=_LEVEL, spacing=(spacing,) * 3)
    except (ValueError, RuntimeError):  # pragma: no cover - degenerate fields
        return None

    verts = verts + lo  # grid-index coords -> world coords
    tree = cKDTree(coords)
    _, nearest = tree.query(verts)
    vert_colors = colors[idx][nearest]

    return mesh_group(
        verts.astype(np.float32),
        normals.astype(np.float32),
        vert_colors.astype(np.float32),
        faces.astype(np.uint32),
    )
