"""Cartoon representation: a smooth ribbon/tube through a polymer backbone.

Works for **proteins** (CA trace, with helix/strand/loop secondary structure) and
**nucleic acids** (DNA/RNA — phosphate/sugar trace, drawn as a rounded tube).
Pipeline: group atoms into residues per chain, pick each residue's trace atom,
assign secondary structure (a geometric CA-CA heuristic for proteins; nucleic
acids are all "loop"), interpolate a Catmull-Rom spline, build a
parallel-transport frame, and sweep an elliptical cross-section.

Output is a single triangle ``mesh`` draw group (positions, normals, colors,
indices). Per-residue colors come from each residue's trace-atom color.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..model.structure import Structure
from ..protocol.geometry import cylinders_group, mesh_group

_SAMPLES_PER_SEGMENT = 16
_CROSS_SECTION_POINTS = 16

# Elliptical cross-section half-extents (width along normal, thickness along binormal).
_SS_SHAPE = {
    "L": (0.28, 0.28),   # coil/loop: round tube
    "H": (1.30, 0.32),   # helix: wide flat ribbon
    "S": (1.10, 0.32),   # strand: flat ribbon
}
_NUCLEIC_SHAPE = (0.75, 0.75)  # DNA/RNA backbone: a fat rounded tube
# Trace-atom preference for nucleic-acid residues. Sugar atoms (C3'/C4') give a
# smoother backbone than the phosphates and exist on 5'-terminal residues too.
_NUCLEIC_TRACE = ("C3'", "C4'", "P", "C1'", "O5'")

# Sugar-phosphate backbone atom names; everything else in a nucleotide is the base.
_SUGAR_PHOSPHATE = {
    "P", "OP1", "OP2", "OP3", "O1P", "O2P", "O3P",
    "O5'", "C5'", "C4'", "O4'", "C3'", "O3'", "C2'", "C1'", "O2'",
}


def _residue_trace_atoms(structure: Structure) -> list[tuple[tuple[str, int], int, bool]]:
    """Per residue (in order): ((chain, resid), trace_atom_index, is_protein).

    Protein residues trace through CA; nucleic-acid residues through the
    phosphate/sugar backbone. Residues with no usable trace atom are skipped.
    """
    order: list[tuple[str, int]] = []
    by_res: dict[tuple[str, int], dict[str, int]] = {}
    for i, raw in enumerate(structure.atom_names):
        key = (structure.chain_ids[i], int(structure.res_ids[i]))
        names = by_res.get(key)
        if names is None:
            names = by_res[key] = {}
            order.append(key)
        nm = raw.upper()
        if nm not in names:
            names[nm] = i

    traces: list[tuple[tuple[str, int], int, bool]] = []
    for key in order:
        names = by_res[key]
        if "CA" in names and structure.elements[names["CA"]] == "C":
            traces.append((key, names["CA"], True))
            continue
        for nm in _NUCLEIC_TRACE:
            if nm in names:
                traces.append((key, names[nm], False))
                break
    return traces


def _chain_residue_traces(structure: Structure, mask: np.ndarray) -> list[tuple[list[int], bool]]:
    """Contiguous runs of in-mask residues per chain, as (trace_indices, is_protein).

    A run breaks at a chain change, a polymer-type change, or a gap in the mask.
    """
    runs: list[tuple[list[int], bool]] = []
    current: list[int] = []
    cur_chain: str | None = None
    cur_protein: bool | None = None
    for (chain, _resid), idx, is_protein in _residue_trace_atoms(structure):
        if mask[idx] and chain == cur_chain and is_protein == cur_protein:
            current.append(idx)
            continue
        if len(current) >= 2:
            runs.append((current, bool(cur_protein)))
        if mask[idx]:
            current, cur_chain, cur_protein = [idx], chain, is_protein
        else:
            current, cur_chain, cur_protein = [], chain, None
    if len(current) >= 2:
        runs.append((current, bool(cur_protein)))
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


def _residue_shapes(ss: list[str], is_protein: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Per-residue ribbon (width, thickness); strand runs flare into an arrowhead.

    Nucleic-acid runs use a uniform rounded tube (no secondary structure)."""
    n = len(ss)
    if not is_protein:
        w, h = _NUCLEIC_SHAPE
        return np.full(n, w, dtype=np.float32), np.full(n, h, dtype=np.float32)
    width = np.empty(n, dtype=np.float32)
    thick = np.empty(n, dtype=np.float32)
    for i, s in enumerate(ss):
        w, h = _SS_SHAPE[s]
        width[i], thick[i] = w, h
    # Arrowhead: gradually flare the last 2 residues of each strand run for a
    # smooth arrow shape, rather than an abrupt jump.
    i = 0
    while i < n:
        if ss[i] != "S":
            i += 1
            continue
        j = i
        while j < n and ss[j] == "S":
            j += 1
        run_len = j - i
        if run_len >= 2:
            width[j - 2] = 1.5   # pre-flare
        width[j - 1] = 2.0      # arrow tip (widest)
        i = j
    return width, thick


def _smooth_loop_trace(ca: np.ndarray, ss: list[str], window: int = 3) -> np.ndarray:
    """Smooth the CA positions of loop ('L') residues using a moving-average window.

    Helix and strand positions are kept exactly; loop positions are averaged
    over *window* neighbours (clamped at run boundaries). This reduces visual
    "frizz" in coil regions, matching PyMOL's ``cartoon_smooth_loops`` feature.
    """
    out = ca.copy()
    n = len(ss)
    hw = window // 2
    for i in range(n):
        if ss[i] != "L":
            continue
        lo = max(0, i - hw)
        hi = min(n, i + hw + 1)
        out[i] = ca[lo:hi].mean(axis=0)
    return out


def _flatten_sheet_normals(
    normals: np.ndarray, binormals: np.ndarray,
    frac: np.ndarray, ss: list[str],
) -> None:
    """Constrain ribbon normals in β-strand regions to a common sheet plane.

    For each strand run, the average normal is computed and all normals within
    that run are projected onto it. This produces flat, readable arrows that
    lie cleanly in a plane, matching PyMOL's ``cartoon_flat_sheets`` look.
    Operates in-place on *normals* and *binormals*.
    """
    n_res = len(ss)
    i = 0
    while i < n_res:
        if ss[i] != "S":
            i += 1
            continue
        j = i
        while j < n_res and ss[j] == "S":
            j += 1
        # Collect sample indices that fall within this strand run.
        mask = (frac >= i) & (frac <= j - 1 + 0.999)
        if not np.any(mask):
            i = j
            continue
        avg_normal = normals[mask].mean(axis=0)
        ln = np.linalg.norm(avg_normal)
        if ln < 1e-6:
            i = j
            continue
        avg_normal /= ln
        # Assign the average normal and recompute binormals.
        normals[mask] = avg_normal
        tangents = np.zeros_like(normals[mask])
        idxs = np.flatnonzero(mask)
        for si_idx, si in enumerate(idxs):
            tangents[si_idx] = np.cross(avg_normal, binormals[si])
            bl = np.linalg.norm(tangents[si_idx])
            if bl > 1e-6:
                tangents[si_idx] /= bl
        binormals[mask] = np.cross(tangents, avg_normal)
        i = j


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
    """Build the cartoon mesh draw group, or None when there is no backbone trace."""
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

    for ca_idx, is_protein in runs:
        ca = structure.coords[np.array(ca_idx)]
        res_colors = colors[np.array(ca_idx)]
        ss = _assign_ss(ca) if is_protein else ["L"] * len(ca_idx)
        # Smooth loop regions to reduce visual noise (like PyMOL smooth_loops).
        if is_protein:
            ca = _smooth_loop_trace(ca, ss)
        width_res, thick_res = _residue_shapes(ss, is_protein)
        samples, frac = _catmull_rom(ca, _SAMPLES_PER_SEGMENT)
        normals, binormals = _frames(samples)
        # Flatten β-sheet normals so strand arrows lie in a clean plane.
        if is_protein:
            _flatten_sheet_normals(normals, binormals, frac, ss)
        n_samples = samples.shape[0]

        # Highlight dimming factor for helix/strand interior face.
        # Bottom-half vertices (sin_a < 0) on flat ribbons are darkened for depth.
        _HIGHLIGHT_DIM = 0.70
        interior = sin_a < 0  # which cross-section vertices are on the interior

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
            # Apply interior highlight dimming for helices and strands.
            lo_ss = ss[min(lo, len(ss) - 1)]
            ring_col[si] = col
            if is_protein and lo_ss in ("H", "S"):
                ring_col[si, interior] *= _HIGHLIGHT_DIM

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


def build_nucleic_rungs(
    structure: Structure, mask: np.ndarray, colors: np.ndarray
) -> dict[str, Any] | None:
    """Short cylinders from each nucleotide's sugar (C1') to its base centroid.

    These "rungs" give the nucleic cartoon a recognizable ladder look, clearly
    distinct from a protein ribbon. Returns a cylinders draw group, or None."""
    by_res: dict[tuple[str, int], dict[str, int]] = {}
    for i in range(structure.n_atoms):
        if not mask[i]:
            continue
        key = (structure.chain_ids[i], int(structure.res_ids[i]))
        by_res.setdefault(key, {}).setdefault(structure.atom_names[i].upper(), i)

    starts: list[np.ndarray] = []
    ends: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    for names in by_res.values():
        if "C1'" not in names:
            continue  # not a nucleotide
        base = [
            idx for nm, idx in names.items()
            if nm not in _SUGAR_PHOSPHATE and structure.elements[idx] != "H"
        ]
        if not base:
            continue
        anchor = names["C1'"]
        starts.append(structure.coords[anchor])
        ends.append(structure.coords[base].mean(axis=0))
        cols.append(colors[anchor])
    if not starts:
        return None
    radii = np.full(len(starts), 0.30, dtype=np.float32)
    return cylinders_group(np.array(starts), np.array(ends), radii, np.array(cols))


# Atom names that form the purine (A/G) and pyrimidine (C/T/U) base rings.
_PURINE_RING = ["N9", "C8", "N7", "C5", "C6", "N1", "C2", "N3", "C4"]
_PYRIMIDINE_RING = ["N1", "C2", "N3", "C4", "C5", "C6"]


def build_nucleic_base_rings(
    structure: Structure, mask: np.ndarray, colors: np.ndarray
) -> dict[str, Any] | None:
    """Filled polygons for each nucleotide's base ring (PyMOL ring_mode 3 style).

    Renders purine 9-membered and pyrimidine 6-membered base rings as flat
    colored triangulated polygons, giving DNA/RNA a distinctive look with
    clearly visible base planes. Returns a mesh draw group, or None."""
    by_res: dict[tuple[str, int], dict[str, int]] = {}
    for i in range(structure.n_atoms):
        if not mask[i]:
            continue
        key = (structure.chain_ids[i], int(structure.res_ids[i]))
        by_res.setdefault(key, {}).setdefault(structure.atom_names[i].upper(), i)

    all_pos: list[np.ndarray] = []
    all_norm: list[np.ndarray] = []
    all_col: list[np.ndarray] = []
    all_idx: list[np.ndarray] = []
    vert_offset = 0

    for names in by_res.values():
        # Try purine ring first, then pyrimidine.
        ring_atoms = None
        for ring_def in (_PURINE_RING, _PYRIMIDINE_RING):
            idxs = [names[nm] for nm in ring_def if nm in names]
            if len(idxs) == len(ring_def):
                ring_atoms = idxs
                break
        if ring_atoms is None:
            continue

        ring_coords = structure.coords[ring_atoms]
        n_verts = len(ring_atoms)

        # Compute face normal from first 3 vertices.
        v1 = ring_coords[1] - ring_coords[0]
        v2 = ring_coords[2] - ring_coords[0]
        face_normal = np.cross(v1, v2)
        fn_len = np.linalg.norm(face_normal)
        if fn_len < 1e-6:
            continue
        face_normal = (face_normal / fn_len).astype(np.float32)

        # Color from the first ring atom.
        col = colors[ring_atoms[0]]

        # Create two-sided polygon: duplicate verts with flipped normals.
        pos = np.vstack([ring_coords, ring_coords]).astype(np.float32)
        nrm = np.vstack([
            np.tile(face_normal, (n_verts, 1)),
            np.tile(-face_normal, (n_verts, 1)),
        ]).astype(np.float32)
        col_arr = np.tile(col, (n_verts * 2, 1)).astype(np.float32)

        # Fan triangulation for front face.
        idx = []
        for k in range(1, n_verts - 1):
            idx += [0, k, k + 1]
        # Back face (reversed winding, offset by n_verts).
        for k in range(1, n_verts - 1):
            idx += [n_verts, n_verts + k + 1, n_verts + k]

        all_pos.append(pos)
        all_norm.append(nrm)
        all_col.append(col_arr)
        all_idx.append(np.array(idx, dtype=np.uint32) + vert_offset)
        vert_offset += n_verts * 2

    if not all_pos:
        return None
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


def has_cartoon_backbone(structure: Structure) -> bool:
    """True when a cartoon can be drawn — a protein *or* nucleic-acid trace of >= 2 residues."""
    protein = sum(1 for _k, _i, p in _residue_trace_atoms(structure) if p)
    total = len(_residue_trace_atoms(structure))
    return protein >= 2 or (total - protein) >= 2
