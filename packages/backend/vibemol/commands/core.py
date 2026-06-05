"""The core PyMOL-compatible commands.

Implemented: load, fetch, show, hide, as, color, select, deselect, set,
bg_color, zoom/orient, delete, remove.
"""

from __future__ import annotations

import numpy as np

from ..color import (
    color_by_chain,
    color_by_charge,
    color_by_element,
    color_by_hydrophobicity,
    color_by_secondary_structure,
    color_spectrum,
    parse_color,
)
from ..io import fetch_pdb, load_path
from ..model.scene import REP_KINDS
from .registry import CommandError, CommandResult, Context, command

# Friendly aliases for representation names.
_REP_ALIASES = {
    "line": "lines", "stick": "sticks", "sphere": "spheres", "dot": "dots",
    "nb": "nonbonded", "nonbond": "nonbonded", "bs": "ball_and_stick",
    "ball+stick": "ball_and_stick", "licorice": "sticks",
}
# Coloring schemes (vs. a flat color) -> the function that computes per-atom RGB.
_COLOR_SCHEMES = {
    "byelement": color_by_element,
    "cpk": color_by_element,
    "element": color_by_element,
    "bychain": color_by_chain,
    "spectrum": lambda s: color_spectrum(s, by="b"),
    "hydrophobicity": color_by_hydrophobicity,
    "hydro": color_by_hydrophobicity,
    "charge": color_by_charge,
    "ss": color_by_secondary_structure,
}


def _rep(name: str) -> str:
    kind = _REP_ALIASES.get(name.lower(), name.lower())
    if kind not in REP_KINDS:
        raise CommandError(f"unknown representation: {name!r} (one of {', '.join(REP_KINDS)})")
    return kind


def _sel(args: list[str], idx: int, default: str = "all") -> str:
    return args[idx] if len(args) > idx and args[idx] else default


# --- loading ---------------------------------------------------------------


@command("load")
def cmd_load(ctx: Context, args: list[str]) -> CommandResult:
    if not args or not args[0]:
        raise CommandError("usage: load <path> [, <name>]")
    structure = load_path(args[0])
    name = args[1] if len(args) > 1 and args[1] else None
    obj = ctx.add_structure(structure, name)
    return CommandResult(log=f"loaded {obj.name} ({obj.structure.n_atoms} atoms)")


@command("fetch")
def cmd_fetch(ctx: Context, args: list[str]) -> CommandResult:
    if not args or not args[0]:
        raise CommandError("usage: fetch <pdb_id>")
    structure = fetch_pdb(args[0])
    obj = ctx.add_structure(structure, args[0].strip().lower())
    return CommandResult(log=f"fetched {obj.name} ({obj.structure.n_atoms} atoms)")


# --- representations -------------------------------------------------------


def _apply_rep(ctx: Context, kind: str, expr: str, mode: str) -> int:
    masks = ctx.resolve(expr)
    method = {"show": "show", "hide": "hide", "as": "show_as"}[mode]
    touched = 0
    for name, obj in ctx.scene.objects.items():
        mask = masks[name]
        if not mask.any():
            continue
        getattr(obj, method)(kind, mask)
        touched += int(mask.sum())
    return touched


@command("show")
def cmd_show(ctx: Context, args: list[str]) -> CommandResult:
    if not args:
        raise CommandError("usage: show <representation> [, <selection>]")
    kind = _rep(args[0])
    n = _apply_rep(ctx, kind, _sel(args, 1), "show")
    return CommandResult(log=f"show {kind} ({n} atoms)")


@command("hide")
def cmd_hide(ctx: Context, args: list[str]) -> CommandResult:
    if not args:
        raise CommandError("usage: hide <representation> [, <selection>]")
    kind = _rep(args[0])
    n = _apply_rep(ctx, kind, _sel(args, 1), "hide")
    return CommandResult(log=f"hide {kind} ({n} atoms)")


@command("as")
def cmd_as(ctx: Context, args: list[str]) -> CommandResult:
    if not args:
        raise CommandError("usage: as <representation> [, <selection>]")
    kind = _rep(args[0])
    n = _apply_rep(ctx, kind, _sel(args, 1), "as")
    return CommandResult(log=f"as {kind} ({n} atoms)")


# --- coloring --------------------------------------------------------------


@command("color")
def cmd_color(ctx: Context, args: list[str]) -> CommandResult:
    if not args or not args[0]:
        raise CommandError("usage: color <color|scheme> [, <selection>]")
    spec = args[0].lower()
    expr = _sel(args, 1)
    scheme_fn = _COLOR_SCHEMES.get(spec)
    rgb = None if scheme_fn else parse_color(args[0])

    masks = ctx.resolve(expr)
    for name, obj in ctx.scene.objects.items():
        mask = masks[name]
        if not mask.any():
            continue
        if scheme_fn is None:
            obj.colors[mask] = rgb
        else:
            obj.colors[mask] = scheme_fn(obj.structure)[mask]
    return CommandResult(log=f"color {spec}")


# --- selections ------------------------------------------------------------


@command("select", "sele")
def cmd_select(ctx: Context, args: list[str]) -> CommandResult:
    if not args:
        raise CommandError("usage: select [<name>,] <selection>")
    if len(args) == 1:
        name, expr = "sele", args[0]
    else:
        name, expr = args[0], args[1]
    masks = ctx.resolve(expr)
    ctx.scene.selections[name] = masks
    total = sum(int(m.sum()) for m in masks.values())
    return CommandResult(
        log=f"selection '{name}' ({total} atoms)",
        scene_changed=False,
        selections_changed=True,
    )


@command("set_name", "rename")
def cmd_set_name(ctx: Context, args: list[str]) -> CommandResult:
    if len(args) < 2 or not args[0] or not args[1]:
        raise CommandError("usage: set_name <old>, <new>")
    old, new = args[0].strip(), args[1].strip()
    if new in ctx.scene.objects or new in ctx.scene.selections:
        raise CommandError(f"name already in use: {new!r}")

    if old in ctx.scene.selections:
        ctx.scene.selections[new] = ctx.scene.selections.pop(old)
        return CommandResult(
            log=f"renamed selection '{old}' -> '{new}'",
            scene_changed=False,
            selections_changed=True,
        )
    if old in ctx.scene.objects:
        obj = ctx.scene.objects[old]
        obj.name = new
        obj.structure.name = new
        # Rebuild the ordered dict, preserving position; remap selection masks.
        ctx.scene.objects = {(new if k == old else k): v for k, v in ctx.scene.objects.items()}
        for masks in ctx.scene.selections.values():
            if old in masks:
                masks[new] = masks.pop(old)
        return CommandResult(log=f"renamed object '{old}' -> '{new}'")
    raise CommandError(f"no such object or selection: {old!r}")


@command("deselect")
def cmd_deselect(ctx: Context, args: list[str]) -> CommandResult:
    name = args[0] if args and args[0] else "sele"
    ctx.scene.selections.pop(name, None)
    return CommandResult(log=f"deselected '{name}'", scene_changed=False, selections_changed=True)


# --- settings & camera -----------------------------------------------------


@command("set")
def cmd_set(ctx: Context, args: list[str]) -> CommandResult:
    if len(args) < 2:
        raise CommandError("usage: set <name>, <value>")
    ctx.scene.settings[args[0]] = args[1]
    return CommandResult(log=f"set {args[0]} = {args[1]}")


@command("bg_color", "bg")
def cmd_bg_color(ctx: Context, args: list[str]) -> CommandResult:
    if not args or not args[0]:
        raise CommandError("usage: bg_color <color>")
    r, g, b = parse_color(args[0])
    hex_color = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
    ctx.scene.settings["bg_color"] = hex_color
    return CommandResult(log=f"bg_color {args[0]}")


@command("set_state", "frame", "state")
def cmd_set_state(ctx: Context, args: list[str]) -> CommandResult:
    if not args or not args[0]:
        raise CommandError("usage: set_state <n>  (1-based)")
    try:
        n = int(args[0]) - 1  # PyMOL states are 1-based
    except ValueError as e:
        raise CommandError(f"set_state: not an integer: {args[0]!r}") from e
    for obj in ctx.scene.objects.values():
        obj.structure.set_state(n)
    return CommandResult(log=f"state {n + 1}")


@command("zoom", "orient", "center")
def cmd_zoom(ctx: Context, args: list[str]) -> CommandResult:
    expr = _sel(args, 0)
    masks = ctx.resolve(expr)
    pts = []
    for name, obj in ctx.scene.objects.items():
        mask = masks[name]
        if mask.any():
            pts.append(obj.structure.coords[mask])
    if not pts:
        return CommandResult(log="zoom: nothing selected", scene_changed=False)
    coords = np.concatenate(pts, axis=0)
    center = coords.mean(axis=0)
    radius = float(np.linalg.norm(coords - center, axis=1).max())
    return CommandResult(
        log=f"zoom ({coords.shape[0]} atoms)",
        camera={"center": center.tolist(), "radius": max(radius, 1.0)},
        scene_changed=False,
    )


# --- deletion --------------------------------------------------------------


@command("delete")
def cmd_delete(ctx: Context, args: list[str]) -> CommandResult:
    target = args[0] if args and args[0] else ""
    if not target:
        raise CommandError("usage: delete <name|all>")
    if target.lower() == "all":
        ctx.scene.objects.clear()
        ctx.scene.selections.clear()
        return CommandResult(log="deleted all objects")
    if target in ctx.scene.selections:
        ctx.scene.selections.pop(target)
        return CommandResult(log=f"deleted selection '{target}'", scene_changed=False,
                             selections_changed=True)
    if ctx.scene.delete_object(target):
        return CommandResult(log=f"deleted object '{target}'")
    raise CommandError(f"no such object or selection: {target!r}")


@command("remove")
def cmd_remove(ctx: Context, args: list[str]) -> CommandResult:
    if not args or not args[0]:
        raise CommandError("usage: remove <selection>")
    expr = args[0]
    masks = ctx.resolve(expr)
    removed = 0
    for name in list(ctx.scene.objects):
        obj = ctx.scene.objects[name]
        mask = masks[name]
        if not mask.any():
            continue
        removed += int(mask.sum())
        keep = ~mask
        if not keep.any():
            ctx.scene.delete_object(name)
            continue
        # Rebuild the object on the surviving atoms, preserving rep/colors.
        from ..model.scene import MolObject  # noqa: PLC0415

        new = MolObject(name=name, structure=obj.structure.subset(keep))
        for kind in REP_KINDS:
            new.rep_masks[kind] = obj.rep_masks[kind][keep]
        new.colors = obj.colors[keep]
        ctx.scene.objects[name] = new
    return CommandResult(log=f"removed {removed} atoms")
