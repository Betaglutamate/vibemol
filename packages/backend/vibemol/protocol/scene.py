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

# Three-letter -> one-letter amino acid codes (for the sequence viewer).
_AA3to1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V",
}


def _residues_payload(s: Structure) -> list[dict[str, Any]]:
    """Ordered residues (by first appearance) with one-letter codes."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for i in range(s.n_atoms):
        key = (s.chain_ids[i], int(s.res_ids[i]))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "chain": s.chain_ids[i],
                "resi": int(s.res_ids[i]),
                "resn": s.res_names[i],
                "code": _AA3to1.get(s.res_names[i].upper(), "X"),
            }
        )
    return out


def object_message(obj: MolObject) -> dict[str, Any]:
    s = obj.structure
    return {
        "type": "object",
        "name": obj.name,
        "visible": obj.visible,
        "n_atoms": s.n_atoms,
        "center": s.center().tolist(),
        "bounding_radius": s.bounding_radius(),
        "active_reps": obj.active_kinds(),
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
    return {
        "type": "scene",
        "settings": scene.settings,
        "selections": list(scene.selections.keys()),
        "center": center,
        "bounding_radius": radius,
        "objects": [object_message(o) for o in scene.objects.values()],
        "measurement_lines": measurement_lines,
        "labels": labels,
        "selection_points": _selection_points(scene),
    }
