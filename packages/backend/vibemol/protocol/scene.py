"""Scene/object message builders streamed to the frontend.

The server sends one ``scene`` message describing the whole session: settings,
overall bounds (for camera framing), the list of named selections, and one
``object`` sub-message per loaded object carrying its draw groups.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..geometry.representations import build_groups
from ..model.scene import MolObject, Scene
from ..model.structure import Structure
from .geometry import f32

# Three-letter -> one-letter codes for the sequence viewer.
_AA3to1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V", "MSE": "M", "SEC": "U", "PYL": "O",
}
# Nucleic acids: DNA (DA/DC/DG/DT) and RNA (A/C/G/U).
_NUC1 = {
    "DA": "A", "DC": "C", "DG": "G", "DT": "T", "DU": "U", "DI": "I",
    "A": "A", "C": "C", "G": "G", "U": "U", "I": "I", "N": "N",
}


def _residue_code(resn: str) -> str | None:
    """One-letter code for a residue, or None for water/ion only."""
    key = resn.upper()
    return _AA3to1.get(key) or _NUC1.get(key)


# Solvent residue names — these are hidden from the sequence display.
_SOLVENT_RESN = {"HOH", "WAT", "TIP", "SOL", "TIP3", "TIP4", "SPC"}


def _residues_payload(s: Structure) -> list[dict[str, Any]]:
    """Ordered residues with one-letter codes for the sequence viewer.

    Polymer residues get their standard one-letter code. Non-polymer HETATM
    residues (ligands, cofactors) are included with their three-letter name
    as the code and ``"kind": "ligand"`` so the frontend can style them
    distinctly. Waters are omitted."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for i in range(s.n_atoms):
        key = (s.chain_ids[i], int(s.res_ids[i]))
        if key in seen:
            continue
        seen.add(key)
        resn = s.res_names[i].upper()
        code = _residue_code(resn)
        if code is not None:
            out.append(
                {
                    "chain": s.chain_ids[i],
                    "resi": int(s.res_ids[i]),
                    "resn": s.res_names[i],
                    "code": code,
                    "kind": "polymer",
                }
            )
        elif resn not in _SOLVENT_RESN and s.is_hetatm[i]:
            # Ligand / cofactor / ion — include with 3-letter name.
            out.append(
                {
                    "chain": s.chain_ids[i],
                    "resi": int(s.res_ids[i]),
                    "resn": s.res_names[i],
                    "code": s.res_names[i],
                    "kind": "ligand",
                }
            )
    return out


def object_message(obj: MolObject, scene: Scene) -> dict[str, Any]:
    s = obj.structure

    # Build the set of selected (chain, resi) pairs from all named selections.
    selected_residues: list[list[str | int]] = []
    union = np.zeros(s.n_atoms, dtype=bool)
    for masks in scene.selections.values():
        m = masks.get(obj.name)
        if m is not None:
            union |= m
    if union.any():
        seen: set[tuple[str, int]] = set()
        idxs = np.where(union)[0]
        for i in idxs:
            key = (s.chain_ids[i], int(s.res_ids[i]))
            if key not in seen:
                seen.add(key)
                selected_residues.append([key[0], key[1]])

    return {
        "type": "object",
        "name": obj.name,
        "visible": obj.visible,
        "n_atoms": s.n_atoms,
        "center": s.center().tolist(),
        "bounding_radius": s.bounding_radius(),
        "active_reps": obj.active_kinds(),
        "n_states": s.n_states,
        "current_state": s.current_state,
        "groups": build_groups(obj),
        # Pick set: every atom position + compact per-atom info, used by the
        # client for click-to-identify regardless of the active representation.
        "pick_positions": f32(s.coords),
        "atoms": {
            "elements": s.elements,
            "names": s.atom_names,
            "resns": s.res_names,
            "resis": s.res_ids.tolist(),
            "chains": s.chain_ids,
        },
        "residues": _residues_payload(s),
        "selected_residues": selected_residues,
    }


def _scene_bounds(scene: Scene) -> tuple[list[float], float]:
    """Center and bounding radius over all visible objects' atoms."""
    all_coords = [
        o.structure.coords for o in scene.objects.values() if o.structure.n_atoms
    ]
    if not all_coords:
        return [0.0, 0.0, 0.0], 10.0
    coords = np.concatenate(all_coords, axis=0)
    center = coords.mean(axis=0)
    radius = float(np.linalg.norm(coords - center, axis=1).max())
    return center.tolist(), max(radius, 1.0)


def _measurements_payload(scene: Scene) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Dashed-line segments + text labels for all measurement annotations."""
    labels: list[dict[str, Any]] = []
    endpoints: list[list[float]] = []
    for m in scene.measurements:
        pts = m.points
        for k in range(len(pts) - 1):
            endpoints.append(pts[k])
            endpoints.append(pts[k + 1])
        centroid = np.array(pts, dtype=np.float32).mean(axis=0).tolist()
        labels.append({"text": m.label, "pos": centroid})
    lines = None
    if endpoints:
        lines = {
            "count": len(endpoints) // 2,
            "positions": f32(np.array(endpoints, dtype=np.float32)),
        }
    return lines, labels


def _selection_points(scene: Scene) -> bytes | None:
    """Positions of all atoms in any named selection (for 3D highlighting)."""
    pts: list[np.ndarray] = []
    for name, obj in scene.objects.items():
        union = np.zeros(obj.structure.n_atoms, dtype=bool)
        for masks in scene.selections.values():
            if name in masks:
                union |= masks[name]
        if union.any():
            pts.append(obj.structure.coords[union])
    if not pts:
        return None
    return f32(np.concatenate(pts))


def scene_message(scene: Scene) -> dict[str, Any]:
    center, radius = _scene_bounds(scene)
    measurement_lines, labels = _measurements_payload(scene)
    n_states = max((o.structure.n_states for o in scene.objects.values()), default=1)
    current_state = max((o.structure.current_state for o in scene.objects.values()), default=0)
    return {
        "type": "scene",
        "settings": scene.settings,
        "selections": list(scene.selections.keys()),
        "center": center,
        "bounding_radius": radius,
        "n_states": n_states,
        "current_state": current_state,
        "objects": [object_message(o, scene) for o in scene.objects.values()],
        "measurement_lines": measurement_lines,
        "labels": labels,
        "selection_points": _selection_points(scene),
    }
