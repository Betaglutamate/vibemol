"""Measurement and alignment commands: distance, angle, dihedral, polar_contacts,
align/super."""

from __future__ import annotations

import numpy as np

from ..analysis import angle, apply_transform, dihedral, distance, kabsch, polar_contacts
from ..model.scene import Measurement
from ..select import select
from .registry import CommandError, CommandResult, Context, command


def _centroid(ctx: Context, expr: str) -> np.ndarray:
    coords = ctx.selected_coords(expr)
    if coords.shape[0] == 0:
        raise CommandError(f"selection matched no atoms: {expr!r}")
    return coords.mean(axis=0)


def _named(args: list[str], n_sel: int) -> tuple[str, list[str]]:
    """Split args into (name, selections). An extra leading arg is the name."""
    if len(args) == n_sel:
        return f"m{n_sel}", args
    if len(args) == n_sel + 1:
        return args[0], args[1:]
    raise CommandError(f"expected {n_sel} selection(s)")


@command("distance", "dist")
def cmd_distance(ctx: Context, args: list[str]) -> CommandResult:
    name, sels = _named(args, 2)
    a, b = _centroid(ctx, sels[0]), _centroid(ctx, sels[1])
    value = distance(a, b)
    ctx.scene.measurements.append(
        Measurement(kind="distance", label=f"{value:.2f} A", points=[a.tolist(), b.tolist()])
    )
    return CommandResult(log=f"{name}: distance = {value:.2f} A")


@command("angle", "angle_measure")
def cmd_angle(ctx: Context, args: list[str]) -> CommandResult:
    name, sels = _named(args, 3)
    a, b, c = (_centroid(ctx, s) for s in sels)
    value = angle(a, b, c)
    ctx.scene.measurements.append(
        Measurement(
            kind="angle", label=f"{value:.1f} deg",
            points=[a.tolist(), b.tolist(), c.tolist()],
        )
    )
    return CommandResult(log=f"{name}: angle = {value:.1f} deg")


@command("dihedral", "torsion")
def cmd_dihedral(ctx: Context, args: list[str]) -> CommandResult:
    name, sels = _named(args, 4)
    a, b, c, d = (_centroid(ctx, s) for s in sels)
    value = dihedral(a, b, c, d)
    ctx.scene.measurements.append(
        Measurement(
            kind="dihedral", label=f"{value:.1f} deg",
            points=[a.tolist(), b.tolist(), c.tolist(), d.tolist()],
        )
    )
    return CommandResult(log=f"{name}: dihedral = {value:.1f} deg")


@command("polar_contacts", "contacts")
def cmd_polar_contacts(ctx: Context, args: list[str]) -> CommandResult:
    expr = args[0] if args and args[0] else "all"
    total = 0
    for obj in ctx.scene.objects.values():
        mask = select(obj.structure, expr)
        for i, j, dist in polar_contacts(obj.structure, mask):
            pi = obj.structure.coords[i].tolist()
            pj = obj.structure.coords[j].tolist()
            ctx.scene.measurements.append(
                Measurement(kind="contact", label=f"{dist:.2f} A", points=[pi, pj])
            )
            total += 1
    return CommandResult(log=f"polar_contacts: {total} contacts")


@command("undistance", "delete_measurements")
def cmd_clear_measurements(ctx: Context, _args: list[str]) -> CommandResult:
    ctx.scene.measurements.clear()
    return CommandResult(log="cleared measurements")


@command("align", "super")
def cmd_align(ctx: Context, args: list[str]) -> CommandResult:
    if len(args) < 2:
        raise CommandError("usage: align <mobile_object>, <target_object>")
    mobile_name, target_name = args[0].strip(), args[1].strip()
    if mobile_name not in ctx.scene.objects or target_name not in ctx.scene.objects:
        raise CommandError("align: both arguments must be loaded object names")
    mobile = ctx.scene.objects[mobile_name]
    target = ctx.scene.objects[target_name]

    m_ca = mobile.structure.coords[select(mobile.structure, "name CA")]
    t_ca = target.structure.coords[select(target.structure, "name CA")]
    if m_ca.shape[0] < 3 or t_ca.shape[0] < 3:
        raise CommandError("align: need >= 3 CA atoms in each object")
    n = min(m_ca.shape[0], t_ca.shape[0])  # v1: positional CA pairing
    rot, trans, err = kabsch(m_ca[:n], t_ca[:n])
    mobile.structure.coords = apply_transform(mobile.structure.coords, rot, trans)
    return CommandResult(log=f"align {mobile_name} -> {target_name}: RMSD {err:.3f} A ({n} CA)")
