"""Measurement and alignment commands: distance, angle, dihedral, polar_contacts,
align/super."""

from __future__ import annotations

import numpy as np

from ..analysis import (
    align_structures,
    angle,
    apply_transform,
    dihedral,
    distance,
    kabsch,
    polar_contacts,
    rmsd,
    sasa,
    super_structures,
    tm_align,
)
from ..color import color_values
from ..model.scene import Measurement, MolObject
from ..model.structure import Structure
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


@command("sasa", "surface_area")
def cmd_sasa(ctx: Context, args: list[str]) -> CommandResult:
    expr = args[0] if args and args[0] else "all"
    total = 0.0
    n_atoms = 0
    for obj in ctx.scene.objects.values():
        mask = select(obj.structure, expr)
        if not mask.any():
            continue
        areas = sasa(obj.structure, mask)
        total += float(areas[mask].sum())
        n_atoms += int(mask.sum())
        # Color atoms by exposure (buried -> blue, exposed -> red) for a visual read.
        obj.colors[mask] = color_values(areas, obj.structure.n_atoms)[mask]
    if n_atoms == 0:
        raise CommandError(f"sasa: selection matched no atoms: {expr!r}")
    return CommandResult(log=f"SASA = {total:.1f} A^2 over {n_atoms} atoms")


@command("interface")
def cmd_interface(ctx: Context, args: list[str]) -> CommandResult:
    if len(args) < 2:
        raise CommandError("usage: interface <sel1>, <sel2> [, cutoff=5]")
    sel1, sel2 = args[0], args[1]
    cutoff = args[2].strip() if len(args) > 2 and args[2].strip() else "5"
    # Residues of sel1 near sel2 (and vice versa) — reuses within/byres + named refs.
    near12 = f"(({sel1}) and (within {cutoff} of ({sel2})))"
    near21 = f"(({sel2}) and (within {cutoff} of ({sel1})))"
    expr = f"byres ({near12} or {near21})"
    masks = ctx.resolve(expr)
    ctx.scene.selections["interface"] = masks
    total = sum(int(m.sum()) for m in masks.values())
    return CommandResult(
        log=f"interface: {total} atoms (within {cutoff} A)",
        scene_changed=False,
        selections_changed=True,
    )


def _two_objects(ctx: Context, args: list[str], verb: str) -> tuple[MolObject, MolObject]:
    if len(args) < 2:
        raise CommandError(f"usage: {verb} <mobile_object>, <target_object>")
    mob_name, tgt_name = args[0].strip(), args[1].strip()
    if mob_name not in ctx.scene.objects or tgt_name not in ctx.scene.objects:
        raise CommandError(f"{verb}: both arguments must be loaded object names")
    return ctx.scene.objects[mob_name], ctx.scene.objects[tgt_name]


@command("align")
def cmd_align(ctx: Context, args: list[str]) -> CommandResult:
    """Sequence-based superposition (Needleman-Wunsch pairing + iterative fit)."""
    mobile, target = _two_objects(ctx, args, "align")
    try:
        rot, trans, err, n, cycles = align_structures(mobile.structure, target.structure)
    except ValueError as e:
        raise CommandError(str(e)) from e
    mobile.structure.coords = apply_transform(mobile.structure.coords, rot, trans)
    return CommandResult(
        log=f"align {mobile.name} -> {target.name}: RMSD {err:.3f} A, {n} atoms, {cycles} cycles"
    )


@command("super")
def cmd_super(ctx: Context, args: list[str]) -> CommandResult:
    """Sequence-independent structural superposition (PCA-seeded ICP)."""
    mobile, target = _two_objects(ctx, args, "super")
    try:
        rot, trans, err, n, _ = super_structures(mobile.structure, target.structure)
    except ValueError as e:
        raise CommandError(str(e)) from e
    mobile.structure.coords = apply_transform(mobile.structure.coords, rot, trans)
    return CommandResult(log=f"super {mobile.name} -> {target.name}: RMSD {err:.3f} A, {n} atoms")


@command("usalign", "tmalign", "tm_align")
def cmd_usalign(ctx: Context, args: list[str]) -> CommandResult:
    """TM-align superposition — aligns even partially overlapping proteins."""
    mobile, target = _two_objects(ctx, args, "usalign")
    try:
        rot, trans, tm_mob, tm_tgt, err, n = tm_align(mobile.structure, target.structure)
    except ValueError as e:
        raise CommandError(str(e)) from e
    mobile.structure.coords = apply_transform(mobile.structure.coords, rot, trans)
    return CommandResult(
        log=(
            f"usalign {mobile.name} -> {target.name}: "
            f"TM-score {tm_tgt:.4f} (norm. {target.name}), {tm_mob:.4f} (norm. {mobile.name}); "
            f"RMSD {err:.3f} A over {n} residues"
        )
    )


def _matched_atoms(mob: Structure, tgt: Structure) -> tuple[np.ndarray, np.ndarray]:
    """Coords of atoms sharing (chain, resid, atom name) between two structures."""
    tgt_index: dict[tuple[str, int, str], int] = {}
    for i in range(tgt.n_atoms):
        tgt_index[(tgt.chain_ids[i], int(tgt.res_ids[i]), tgt.atom_names[i].upper())] = i
    mob_pts: list[np.ndarray] = []
    tgt_pts: list[np.ndarray] = []
    for i in range(mob.n_atoms):
        key = (mob.chain_ids[i], int(mob.res_ids[i]), mob.atom_names[i].upper())
        j = tgt_index.get(key)
        if j is not None:
            mob_pts.append(mob.coords[i])
            tgt_pts.append(tgt.coords[j])
    if len(mob_pts) < 3:
        raise CommandError("need >= 3 atoms with matching chain/residue/name")
    return np.array(mob_pts), np.array(tgt_pts)


@command("fit")
def cmd_fit(ctx: Context, args: list[str]) -> CommandResult:
    """Fit mobile onto target over identically-named matched atoms (then move it)."""
    mobile, target = _two_objects(ctx, args, "fit")
    mob, tgt = _matched_atoms(mobile.structure, target.structure)
    rot, trans, err = kabsch(mob, tgt)
    mobile.structure.coords = apply_transform(mobile.structure.coords, rot, trans)
    return CommandResult(
        log=f"fit {mobile.name} -> {target.name}: RMSD {err:.3f} A, {mob.shape[0]} atoms"
    )


@command("rms_cur", "rms")
def cmd_rms_cur(ctx: Context, args: list[str]) -> CommandResult:
    """RMSD over matched atoms at current positions (no superposition)."""
    mobile, target = _two_objects(ctx, args, "rms_cur")
    mob, tgt = _matched_atoms(mobile.structure, target.structure)
    return CommandResult(
        log=f"rms_cur {mobile.name} vs {target.name}: {rmsd(mob, tgt):.3f} A, {mob.shape[0]} atoms",
        scene_changed=False,
    )
