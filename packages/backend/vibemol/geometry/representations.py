"""Turn a :class:`~vibemol.model.scene.MolObject`'s active representation masks
into binary draw groups for the frontend.

Each representation kind maps to one or more GPU primitive groups:

  * ``spheres``        -> full-VDW spheres
  * ``ball_and_stick`` -> small spheres + thin half-bond cylinders
  * ``sticks``         -> half-bond cylinders + capping spheres at joints
  * ``lines``          -> bond line segments (per-endpoint colors)
  * ``nonbonded``      -> points at atom centres
  * ``dots``           -> a coarse VDW dot cloud per atom
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..model.scene import MolObject
from ..model.structure import Structure
from ..protocol.geometry import cylinders_group, lines_group, points_group, spheres_group
from .cartoon import build_cartoon_mesh, build_nucleic_rungs

_STICK_RADIUS = 0.20
_BALL_STICK_BOND_RADIUS = 0.13
_BALL_SCALE = 0.25  # ball radius as a fraction of VDW
_DOTS_PER_ATOM = 36


def _bonds_within(structure: Structure, mask: np.ndarray) -> np.ndarray:
    """Bonds whose *both* endpoints are in ``mask``."""
    if structure.n_bonds == 0:
        return np.empty((0, 2), dtype=np.int32)
    b = structure.bonds
    keep = mask[b[:, 0]] & mask[b[:, 1]]
    return b[keep]


def _half_bond_cylinders(
    coords: np.ndarray, colors: np.ndarray, bonds: np.ndarray, radius: float
) -> dict[str, Any]:
    """Split each bond at its midpoint into two colored half-cylinders."""
    i, j = bonds[:, 0], bonds[:, 1]
    pi, pj = coords[i], coords[j]
    mid = (pi + pj) * 0.5
    starts = np.vstack([pi, mid])
    ends = np.vstack([mid, pj])
    cols = np.vstack([colors[i], colors[j]])
    radii = np.full(starts.shape[0], radius, dtype=np.float32)
    return cylinders_group(starts, ends, radii, cols)


def _fibonacci_sphere(n: int) -> np.ndarray:
    """``n`` roughly-uniform unit vectors on a sphere (for the dots cloud)."""
    k = np.arange(n)
    phi = np.pi * (3.0 - np.sqrt(5.0))  # golden angle
    y = 1.0 - 2.0 * (k + 0.5) / n
    r = np.sqrt(np.maximum(0.0, 1.0 - y * y))
    theta = phi * k
    return np.stack([np.cos(theta) * r, y, np.sin(theta) * r], axis=1).astype(np.float32)


def build_groups(obj: MolObject) -> list[dict[str, Any]]:
    """Build all draw groups for an object from its active representation masks."""
    s = obj.structure
    coords = s.coords
    colors = obj.colors
    vdw = s.vdw_radii()
    groups: list[dict[str, Any]] = []

    for kind in obj.active_kinds():
        mask = obj.rep_masks[kind]
        idx = np.flatnonzero(mask)

        if kind == "spheres":
            groups.append(spheres_group(coords[idx], vdw[idx], colors[idx]))

        elif kind == "ball_and_stick":
            groups.append(spheres_group(coords[idx], vdw[idx] * _BALL_SCALE, colors[idx]))
            bonds = _bonds_within(s, mask)
            if bonds.shape[0]:
                groups.append(
                    _half_bond_cylinders(coords, colors, bonds, _BALL_STICK_BOND_RADIUS)
                )

        elif kind == "sticks":
            bonds = _bonds_within(s, mask)
            if bonds.shape[0]:
                groups.append(_half_bond_cylinders(coords, colors, bonds, _STICK_RADIUS))
                joints = np.unique(bonds.reshape(-1))
                radii = np.full(joints.shape[0], _STICK_RADIUS, dtype=np.float32)
                groups.append(spheres_group(coords[joints], radii, colors[joints]))

        elif kind == "lines":
            bonds = _bonds_within(s, mask)
            if bonds.shape[0]:
                pos = np.empty((bonds.shape[0] * 2, 3), dtype=np.float32)
                col = np.empty((bonds.shape[0] * 2, 3), dtype=np.float32)
                pos[0::2], pos[1::2] = coords[bonds[:, 0]], coords[bonds[:, 1]]
                col[0::2], col[1::2] = colors[bonds[:, 0]], colors[bonds[:, 1]]
                groups.append(lines_group(pos, col))

        elif kind == "nonbonded":
            groups.append(points_group(coords[idx], colors[idx], size=5.0))

        elif kind == "dots":
            dirs = _fibonacci_sphere(_DOTS_PER_ATOM)
            # (n_atoms, dots, 3): atom centre + unit dir * VDW radius.
            pts = coords[idx][:, None, :] + dirs[None, :, :] * vdw[idx][:, None, None]
            pos = pts.reshape(-1, 3)
            col = np.repeat(colors[idx], _DOTS_PER_ATOM, axis=0)
            groups.append(points_group(pos, col, size=2.0))

        elif kind == "cartoon":
            cartoon = build_cartoon_mesh(s, mask, colors)
            if cartoon is not None:
                groups.append(cartoon)
            rungs = build_nucleic_rungs(s, mask, colors)  # base ladder for nucleic acids
            if rungs is not None:
                groups.append(rungs)

        elif kind == "surface":
            from .surface import build_surface_mesh  # noqa: PLC0415

            surface = build_surface_mesh(s, mask, colors)
            if surface is not None:
                groups.append(surface)

    return groups
