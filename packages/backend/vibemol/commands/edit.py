"""Object-editing and quantitative commands: create, extract, count_atoms,
centerofmass, get_extent, translate, rotate."""

from __future__ import annotations

import numpy as np

from ..model.elements import atomic_mass
from ..model.structure import Structure
from .core import cmd_remove
from .registry import CommandError, CommandResult, Context, command


def _gather(ctx: Context, expr: str) -> list[Structure]:
    """Subset each object by ``expr`` into standalone structures (skipping empties)."""
    masks = ctx.resolve(expr)
    return [
        obj.structure.subset(masks[name])
        for name, obj in ctx.scene.objects.items()
        if masks[name].any()
    ]


@command("create")
def cmd_create(ctx: Context, args: list[str]) -> CommandResult:
    """Copy a selection into a new object (the sources are left untouched)."""
    if len(args) < 2 or not args[0] or not args[1]:
        raise CommandError("usage: create <name>, <selection>")
    parts = _gather(ctx, args[1])
    if not parts:
        raise CommandError(f"create: selection matched no atoms: {args[1]!r}")
    merged = parts[0] if len(parts) == 1 else Structure.concat(parts)
    obj = ctx.add_structure(merged, args[0].strip())
    return CommandResult(log=f"created {obj.name} ({obj.structure.n_atoms} atoms)")


@command("extract")
def cmd_extract(ctx: Context, args: list[str]) -> CommandResult:
    """Move a selection into a new object (removed from the sources)."""
    if len(args) < 2 or not args[0] or not args[1]:
        raise CommandError("usage: extract <name>, <selection>")
    parts = _gather(ctx, args[1])
    if not parts:
        raise CommandError(f"extract: selection matched no atoms: {args[1]!r}")
    # Remove from the sources first (the new object isn't added yet, so it's safe).
    cmd_remove(ctx, [args[1]])
    merged = parts[0] if len(parts) == 1 else Structure.concat(parts)
    obj = ctx.add_structure(merged, args[0].strip())
    return CommandResult(log=f"extracted {obj.name} ({obj.structure.n_atoms} atoms)")


@command("count_atoms")
def cmd_count_atoms(ctx: Context, args: list[str]) -> CommandResult:
    expr = args[0] if args and args[0] else "all"
    total = sum(int(m.sum()) for m in ctx.resolve(expr).values())
    return CommandResult(log=f"count_atoms: {total}", scene_changed=False)


@command("centerofmass", "com")
def cmd_centerofmass(ctx: Context, args: list[str]) -> CommandResult:
    expr = args[0] if args and args[0] else "all"
    masks = ctx.resolve(expr)
    coords: list[np.ndarray] = []
    masses: list[np.ndarray] = []
    for name, obj in ctx.scene.objects.items():
        mask = masks[name]
        if not mask.any():
            continue
        idx = np.flatnonzero(mask)
        coords.append(obj.structure.coords[idx])
        masses.append(np.array([atomic_mass(obj.structure.elements[i]) for i in idx]))
    if not coords:
        raise CommandError(f"centerofmass: selection matched no atoms: {expr!r}")
    xyz = np.concatenate(coords)
    w = np.concatenate(masses)
    com = (xyz * w[:, None]).sum(axis=0) / w.sum()
    return CommandResult(
        log=f"centerofmass: [{com[0]:.3f}, {com[1]:.3f}, {com[2]:.3f}]", scene_changed=False
    )


@command("get_extent")
def cmd_get_extent(ctx: Context, args: list[str]) -> CommandResult:
    expr = args[0] if args and args[0] else "all"
    xyz = ctx.selected_coords(expr)
    if xyz.shape[0] == 0:
        raise CommandError(f"get_extent: selection matched no atoms: {expr!r}")
    lo, hi = xyz.min(axis=0), xyz.max(axis=0)
    size = hi - lo
    return CommandResult(
        log=(
            f"get_extent: min [{lo[0]:.2f}, {lo[1]:.2f}, {lo[2]:.2f}]  "
            f"max [{hi[0]:.2f}, {hi[1]:.2f}, {hi[2]:.2f}]  "
            f"size [{size[0]:.2f}, {size[1]:.2f}, {size[2]:.2f}]"
        ),
        scene_changed=False,
    )


def _parse_vector(text: str) -> np.ndarray:
    nums = text.replace("[", " ").replace("]", " ").replace(",", " ").split()
    if len(nums) != 3:
        raise CommandError(f"expected a 3-vector like [x, y, z], got {text!r}")
    try:
        return np.array([float(n) for n in nums], dtype=np.float32)
    except ValueError as e:
        raise CommandError(f"bad vector: {text!r}") from e


def _object(ctx: Context, name: str, verb: str) -> object:
    obj = ctx.scene.objects.get(name.strip())
    if obj is None:
        raise CommandError(f"{verb}: no such object: {name.strip()!r}")
    return obj


@command("translate")
def cmd_translate(ctx: Context, args: list[str]) -> CommandResult:
    # The bracketed vector contains commas, so the parser splits it across args:
    # the object is the last arg and the vector is everything before it.
    if len(args) < 2:
        raise CommandError("usage: translate [x, y, z], <object>")
    vec = _parse_vector(",".join(args[:-1]))
    obj = _object(ctx, args[-1], "translate")
    obj.structure.coords = obj.structure.coords + vec  # type: ignore[attr-defined]
    return CommandResult(log=f"translate {args[-1].strip()} by [{vec[0]}, {vec[1]}, {vec[2]}]")


@command("rotate")
def cmd_rotate(ctx: Context, args: list[str]) -> CommandResult:
    if len(args) < 3:
        raise CommandError("usage: rotate <x|y|z>, <angle>, <object>")
    axis = args[0].strip().lower()
    try:
        angle = np.radians(float(args[1]))
    except ValueError as e:
        raise CommandError(f"rotate: bad angle: {args[1]!r}") from e
    c, s = np.cos(angle), np.sin(angle)
    if axis == "x":
        rot = np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float32)
    elif axis == "y":
        rot = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float32)
    elif axis == "z":
        rot = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float32)
    else:
        raise CommandError("rotate: axis must be x, y, or z")
    obj = _object(ctx, args[2], "rotate")
    coords = obj.structure.coords  # type: ignore[attr-defined]
    center = coords.mean(axis=0)
    obj.structure.coords = (coords - center) @ rot.T + center  # type: ignore[attr-defined]
    return CommandResult(log=f"rotate {args[2].strip()} {axis} by {args[1].strip()} deg")
