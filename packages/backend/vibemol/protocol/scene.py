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


def scene_message(scene: Scene) -> dict[str, Any]:
    center, radius = _scene_bounds(scene)
    return {
        "type": "scene",
        "settings": scene.settings,
        "selections": list(scene.selections.keys()),
        "center": center,
        "bounding_radius": radius,
        "objects": [object_message(o) for o in scene.objects.values()],
    }
