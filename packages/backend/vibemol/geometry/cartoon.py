"""Cartoon representation: a smooth ribbon/tube through the protein backbone.

Pipeline: group atoms into residues per chain, take the CA trace, assign a
secondary structure (a geometric heuristic over CA-CA distances — full DSSP is a
later refinement), interpolate a Catmull-Rom spline through the CA atoms, build a
parallel-transport frame along it, and sweep an elliptical cross-section whose
shape depends on SS (round tube for loops, flat ribbon for helices/strands).

Output is a single triangle ``mesh`` draw group (positions, normals, colors,
indices). Per-residue colors come from each residue's CA atom color.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..model.structure import Structure
from ..protocol.geometry import mesh_group

_SAMPLES_PER_SEGMENT = 8
_CROSS_SECTION_POINTS = 8

# Elliptical cross-section half-extents (width along normal, thickness along binormal).
_SS_SHAPE = {
    "L": (0.28, 0.28),   # coil/loop: round tube
    "H": (1.30, 0.32),   # helix: wide flat ribbon
    "S": (1.10, 0.32),   # strand: flat ribbon (arrowheads are a later refinement)
}


def _chain_residue_traces(structure: Structure, mask: np.ndarray) -> list[list[int]]:
    """Yield (ca_indices, colors_index_list) runs of in-mask residues per chain.

    Residues are ordered by first appearance; a residue is included when its CA
    atom is in ``mask``. Each contiguous run within a chain becomes one ribbon.
    """
    # Build ordered residues: (chain, resid) -> CA atom index.
    order: list[tuple[str, int]] = []
    ca_of: dict[tuple[str, int], int] = {}
    for i, name in enumerate(structure.atom_names):
        if name.upper() != "CA" or structure.elements[i] != "C":
            continue
        key = (structure.chain_ids[i], int(structure.res_ids[i]))
        if key not in ca_of:
            ca_of[key] = i
            order.append(key)

    # Split into per-chain contiguous runs of in-mask residues.
    runs: list[list[int]] = []
    current: list[int] = []
    prev_chain: str | None = None
    for key in order:
        ca = ca_of[key]
        same_chain = key[0] == prev_chain
        if mask[ca] and same_chain:
            current.append(ca)
        elif mask[ca]:
            if len(current) >= 2:
                runs.append(current)
            current = [ca]
        else:
            if len(current) >= 2:
                runs.append(current)
            current = []
        prev_chain = key[0]
    if len(current) >= 2:
        runs.append(current)
    return runs


def _assign_ss(ca: np.ndarray) -> list[str]:
    """Heuristic secondary structure ('H'/'S'/'L') from the CA trace geometry."""
    n = ca.shape[0]
    ss = ["L"] * n
    for i in range(n - 3):
        d3 = float(np.linalg.norm(ca[i] - ca[i + 3]))
        d2 = float(np.linalg.norm(ca[i] - ca[i + 2]))
        if 4.5 <= d3 <= 6.4 and d2 <= 6.5:
            for k in range(i, i + 4):
                ss[k] = "H"
        elif d3 >= 7.5 and d2 >= 6.0:
            for k in range(i, i + 3):
                if ss[k] == "L":
                    ss[k] = "S"
    # Demote runs shorter than a minimum length to coil (reduces noise).
    for label, min_len in (("H", 4), ("S", 3)):
        i = 0
        while i < n:
            if ss[i] != label:
                i += 1
                continue
            j = i
            while j < n and ss[j] == label:
                j += 1
            if j - i < min_len:
                for k in range(i, j):
                    ss[k] = "L"
            i = j
    return ss


def assign_chain_ss(structure: Structure) -> dict[tuple[str, int], str]:
    """Secondary structure per residue ('H'/'S'/'L') keyed by (chain, resid).

    Groups CA atoms into chains (in order of appearance), runs the per-chain
    :func:`_assign_ss` heuristic, and maps the result back to residue keys.
    Residues without a CA default to 'L'. Reused by the SS coloring scheme.
    """
    chains: dict[str, list[tuple[int, np.ndarray]]] = {}
    for i, name in enumerate(structure.atom_names):
        if name.upper() != "CA" or structure.elements[i] != "C":
            continue
        chain = structure.chain_ids[i]
        resid = int(structure.res_ids[i])
        residues = chains.setdefault(chain, [])
        if not residues or residues[-1][0] != resid:  # first CA per residue, ordered
            residues.append((resid, structure.coords[i]))

    out: dict[tuple[str, int], str] = {}
    for chain, residues in chains.items():
        if len(residues) < 2:
            for resid, _ in residues:
                out[(chain, resid)] = "L"
            continue
        ca = np.array([c for _, c in residues], dtype=np.float32)
        ss = _assign_ss(ca)
        for (resid, _), label in zip(residues, ss, strict=True):
            out[(chain, resid)] = label
    return out


def _residue_shapes(ss: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Per-residue ribbon (width, thickness); strand runs flare into an arrowhead."""
    n = len(ss)
    width = np.empty(n, dtype=np.float32)
    thick = np.empty(n, dtype=np.float32)
    for i, s in enumerate(ss):
        w, h = _SS_SHAPE[s]
        width[i], thick[i] = w, h
    # Arrowhead: widen the last residue of each strand run; the following coil's
    # narrow width then tapers it to a point over the next segment.
    i = 0
    while i < n:
        if ss[i] != "S":
            i += 1
            continue
        j = i
        while j < n and ss[j] == "S":
            j += 1
        width[j - 1] = 1.9  # arrow base
        i = j
    return width, thick


def _catmull_rom(points: np.ndarray, samples: int) -> tuple[np.ndarray, np.ndarray]:
    """Sample a Catmull-Rom spline; return sample points and their source segment t."""
    n = points.shape[0]
    out_pts: list[np.ndarray] = []
    out_idx: list[float] = []  # fractional residue index for color/SS lookup
    for i in range(n - 1):
        p0 = points[i - 1] if i > 0 else points[i] * 2 - points[i + 1]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < n else points[i + 1] * 2 - points[i]
        for s in range(samples):
            t = s / samples
            t2, t3 = t * t, t * t * t
            pt = 0.5 * (
                (2 * p1)
                + (-p0 + p2) * t
                + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                + (-p0 + 3 * p1 - 3 * p2 + p3) * t3
            )
            out_pts.append(pt)
            out_idx.append(i + t)
    out_pts.append(points[-1])
    out_idx.append(float(n - 1))
    return np.array(out_pts, dtype=np.float32), np.array(out_idx, dtype=np.float32)


def _frames(samples: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Parallel-transport normals/binormals along a sampled curve."""
    n = samples.shape[0]
    tangents = np.zeros((n, 3), dtype=np.float32)
    tangents[:-1] = samples[1:] - samples[:-1]
    tangents[-1] = tangents[-2]
    norms = np.linalg.norm(tangents, axis=1, keepdims=True)
    tangents /= np.where(norms < 1e-6, 1.0, norms)

    normals = np.zeros((n, 3), dtype=np.float32)
    # Seed a normal perpendicular to the first tangent.
    ref = np.array([0, 0, 1], np.float32)
    if abs(float(np.dot(tangents[0], ref))) > 0.9:
        ref = np.array([0, 1, 0], np.float32)
    normals[0] = np.cross(tangents[0], ref)
    normals[0] /= np.linalg.norm(normals[0]) + 1e-9
    for i in range(1, n):
        v = normals[i - 1] - tangents[i] * float(np.dot(normals[i - 1], tangents[i]))
        ln = np.linalg.norm(v)
        normals[i] = v / ln if ln > 1e-6 else normals[i - 1]
    binormals = np.cross(tangents, normals)
    return normals, binormals


def build_cartoon_mesh(
    structure: Structure, mask: np.ndarray, colors: np.ndarray
) -> dict[str, Any] | None:
    """Build the cartoon mesh draw group, or None when there is no protein trace."""
    runs = _chain_residue_traces(structure, mask)
    if not runs:
        return None

    all_pos: list[np.ndarray] = []
    all_norm: list[np.ndarray] = []
    all_col: list[np.ndarray] = []
    all_idx: list[np.ndarray] = []
    vert_offset = 0
    m = _CROSS_SECTION_POINTS
    angles = np.linspace(0, 2 * np.pi, m, endpoint=False)
    cos_a, sin_a = np.cos(angles), np.sin(angles)

    for ca_idx in runs:
        ca = structure.coords[np.array(ca_idx)]
        res_colors = colors[np.array(ca_idx)]
        ss = _assign_ss(ca)
        width_res, thick_res = _residue_shapes(ss)
        samples, frac = _catmull_rom(ca, _SAMPLES_PER_SEGMENT)
        normals, binormals = _frames(samples)
        n_samples = samples.shape[0]

        ring_pos = np.empty((n_samples, m, 3), dtype=np.float32)
        ring_norm = np.empty((n_samples, m, 3), dtype=np.float32)
        ring_col = np.empty((n_samples, m, 3), dtype=np.float32)
        for si in range(n_samples):
            lo = int(np.floor(frac[si]))
            hi = min(lo + 1, len(res_colors) - 1)
            f = frac[si] - lo
            # Interpolate cross-section + color between adjacent residues for
            # smooth ribbon width changes (and arrowhead taper).
            w = float(width_res[lo] * (1 - f) + width_res[hi] * f)
            h = float(thick_res[lo] * (1 - f) + thick_res[hi] * f)
            col = res_colors[lo] * (1 - f) + res_colors[hi] * f
            nrm, bnm = normals[si], binormals[si]
            offset = (cos_a[:, None] * w) * nrm + (sin_a[:, None] * h) * bnm
            vnormal = (cos_a[:, None] * h) * nrm + (sin_a[:, None] * w) * bnm
            ring_pos[si] = samples[si] + offset
            ring_norm[si] = vnormal / (np.linalg.norm(vnormal, axis=1, keepdims=True) + 1e-9)
            ring_col[si] = col

        # Triangulate consecutive rings into quads.
        idx: list[int] = []
        for si in range(n_samples - 1):
            for k in range(m):
                a = si * m + k
                b = si * m + (k + 1) % m
                c = (si + 1) * m + k
                d = (si + 1) * m + (k + 1) % m
                idx += [a, c, b, b, c, d]

        all_pos.append(ring_pos.reshape(-1, 3))
        all_norm.append(ring_norm.reshape(-1, 3))
        all_col.append(ring_col.reshape(-1, 3))
        all_idx.append(np.array(idx, dtype=np.uint32) + vert_offset)
        vert_offset += n_samples * m

    return mesh_group(
        np.concatenate(all_pos),
        np.concatenate(all_norm),
        np.concatenate(all_col),
        np.concatenate(all_idx),
    )


def has_protein_backbone(structure: Structure) -> bool:
    """True when the structure has CA atoms in at least two residues (a trace)."""
    seen: set[tuple[str, int]] = set()
    for i, name in enumerate(structure.atom_names):
        if name.upper() == "CA" and structure.elements[i] == "C":
            seen.add((structure.chain_ids[i], int(structure.res_ids[i])))
            if len(seen) >= 2:
                return True
    return False
