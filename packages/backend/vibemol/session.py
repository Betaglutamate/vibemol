"""Save and load VibeMol sessions (``.vibe``).

A ``.vibe`` file is a zip archive:

  * ``manifest.json`` — format/version, settings, object order, named selections
  * ``objects/<i>/meta.json``  — per-object string columns + visibility
  * ``objects/<i>/arrays.npz`` — per-object numeric arrays (coords, bonds, …),
    per-atom colors, and the stacked representation masks

This is VibeMol's own portable format; PyMOL ``.pse`` import/export is a later
phase. JSON for state, binary (``.npz``) for bulk arrays — never JSON vertices.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import IO

import numpy as np

from .model.scene import REP_KINDS, MolObject, Scene
from .model.structure import Structure

_FORMAT = "vibemol-session"
_VERSION = 1


def dump_session(scene: Scene) -> bytes:
    """Serialize the scene to ``.vibe`` archive bytes (for download)."""
    buf = io.BytesIO()
    save_session(scene, buf)
    return buf.getvalue()


def load_session_bytes(data: bytes) -> Scene:
    """Load a scene from ``.vibe`` archive bytes (from an upload)."""
    return load_session(io.BytesIO(data))


def save_session(scene: Scene, path: str | Path | IO[bytes]) -> None:
    """Write the scene to a ``.vibe`` archive (a path or a binary file object)."""
    names = list(scene.objects)
    index_of = {name: i for i, name in enumerate(names)}

    manifest = {
        "format": _FORMAT,
        "version": _VERSION,
        "settings": scene.settings,
        "objects": names,
        "selections": {
            sel: {name: np.flatnonzero(mask).tolist() for name, mask in masks.items()}
            for sel, masks in scene.selections.items()
        },
    }

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        for name in names:
            obj = scene.objects[name]
            s = obj.structure
            i = index_of[name]
            zf.writestr(
                f"objects/{i}/meta.json",
                json.dumps(
                    {
                        "name": name,
                        "visible": obj.visible,
                        "elements": s.elements,
                        "atom_names": s.atom_names,
                        "res_names": s.res_names,
                        "chain_ids": s.chain_ids,
                        "current_state": s.current_state,
                    }
                ),
            )
            rep_stack = np.stack([obj.rep_masks[k] for k in REP_KINDS])
            arrays = {
                "coords": s.coords,
                "res_ids": s.res_ids,
                "b_factors": s.b_factors,
                "occupancies": s.occupancies,
                "is_hetatm": s.is_hetatm,
                "bonds": s.bonds,
                "ids": s.ids,
                "colors": obj.colors,
                "rep_masks": rep_stack,
            }
            if s.states is not None:
                arrays["states"] = s.states
            buf = io.BytesIO()
            np.savez_compressed(buf, **arrays)  # type: ignore[arg-type]  # numpy stub quirk
            zf.writestr(f"objects/{i}/arrays.npz", buf.getvalue())


def load_session(path: str | Path | IO[bytes]) -> Scene:
    """Read a ``.vibe`` archive (a path or a binary file object) into a Scene."""
    scene = Scene()
    with zipfile.ZipFile(path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
        if manifest.get("format") != _FORMAT:
            raise ValueError(f"not a VibeMol session: {path}")

        for i, name in enumerate(manifest["objects"]):
            meta = json.loads(zf.read(f"objects/{i}/meta.json"))
            with zf.open(f"objects/{i}/arrays.npz") as fh:
                arr = np.load(io.BytesIO(fh.read()))
                structure = Structure(
                    name=name,
                    coords=arr["coords"],
                    elements=meta["elements"],
                    atom_names=meta["atom_names"],
                    res_names=meta["res_names"],
                    res_ids=arr["res_ids"],
                    chain_ids=meta["chain_ids"],
                    b_factors=arr["b_factors"],
                    occupancies=arr["occupancies"],
                    is_hetatm=arr["is_hetatm"],
                    bonds=arr["bonds"],
                    ids=arr["ids"],
                    states=arr["states"] if "states" in arr.files else None,
                    current_state=int(meta.get("current_state", 0)),
                )
                obj = MolObject(name=name, structure=structure, visible=meta["visible"])
                obj.colors = arr["colors"]
                for k, mask in zip(REP_KINDS, arr["rep_masks"], strict=True):
                    obj.rep_masks[k] = mask.copy()
            scene.objects[name] = obj

        scene.settings = manifest["settings"]
        for sel, per_obj in manifest["selections"].items():
            masks: dict[str, np.ndarray] = {}
            for obj_name, indices in per_obj.items():
                if obj_name in scene.objects:
                    m = np.zeros(scene.objects[obj_name].structure.n_atoms, dtype=bool)
                    m[indices] = True
                    masks[obj_name] = m
            scene.selections[sel] = masks
    return scene
