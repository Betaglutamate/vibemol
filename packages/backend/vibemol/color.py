"""Color parsing and per-atom coloring schemes.

Colors are RGB float triples in [0, 1]. ``color`` commands either assign a flat
color (a name or ``#rrggbb`` hex) to a selection, or apply a scheme
(``byelement``/``cpk``, ``bychain``, ``spectrum``/by b-factor).
"""

from __future__ import annotations

import colorsys

import numpy as np

from .model.structure import Structure

Rgb = tuple[float, float, float]

# A compact set of PyMOL-ish named colors.
NAMED_COLORS: dict[str, Rgb] = {
    "red": (1.0, 0.2, 0.2), "green": (0.2, 1.0, 0.2), "blue": (0.36, 0.36, 1.0),
    "yellow": (1.0, 1.0, 0.2), "cyan": (0.2, 1.0, 1.0), "magenta": (1.0, 0.2, 1.0),
    "orange": (1.0, 0.5, 0.0), "purple": (0.6, 0.1, 0.8), "pink": (1.0, 0.6, 0.8),
    "salmon": (1.0, 0.6, 0.6), "white": (1.0, 1.0, 1.0), "black": (0.0, 0.0, 0.0),
    "gray": (0.5, 0.5, 0.5), "grey": (0.5, 0.5, 0.5), "teal": (0.0, 0.6, 0.6),
    "lime": (0.5, 1.0, 0.5), "wheat": (0.99, 0.82, 0.65), "slate": (0.5, 0.5, 1.0),
}

# Palette cycled across chains for `color bychain`.
_CHAIN_PALETTE: list[Rgb] = [
    (0.4, 0.76, 1.0), (1.0, 0.6, 0.4), (0.6, 1.0, 0.6), (1.0, 0.9, 0.4),
    (0.85, 0.6, 1.0), (0.4, 1.0, 0.9), (1.0, 0.7, 0.85), (0.7, 0.85, 0.5),
]


class ColorError(ValueError):
    """Raised for an unrecognized color name or scheme."""


def parse_color(spec: str) -> Rgb:
    """Parse a color name or ``#rrggbb`` / ``rrggbb`` hex string to an RGB triple."""
    s = spec.strip().lower()
    if s in NAMED_COLORS:
        return NAMED_COLORS[s]
    h = s[1:] if s.startswith("#") else s
    if len(h) == 6 and all(c in "0123456789abcdef" for c in h):
        return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)
    raise ColorError(f"unknown color: {spec!r}")


def color_by_element(structure: Structure) -> np.ndarray:
    """CPK coloring (the default)."""
    return structure.cpk_colors_rgb()


def color_by_chain(structure: Structure) -> np.ndarray:
    """One palette color per chain, cycled in order of first appearance."""
    order: dict[str, int] = {}
    out = np.empty((structure.n_atoms, 3), dtype=np.float32)
    for i, chain in enumerate(structure.chain_ids):
        slot = order.setdefault(chain, len(order))
        out[i] = _CHAIN_PALETTE[slot % len(_CHAIN_PALETTE)]
    return out


def color_by_chain_ss(structure: Structure) -> np.ndarray:
    """Chain coloring with subtle secondary-structure tinting.

    Helices are warmed slightly (shifted toward pink), strands are cooled
    slightly (shifted toward gold), and loops keep the base chain colour.
    The shift is small enough that chain identity remains the dominant signal,
    but SS elements become visually distinguishable.
    """
    from .geometry.cartoon import assign_chain_ss  # noqa: PLC0415

    base = color_by_chain(structure)
    ss_by_res = assign_chain_ss(structure)

    # Very subtle tint vectors — just enough to see the difference.
    helix_tint = np.array([0.08, -0.04, -0.06], dtype=np.float32)   # warmer/pink
    strand_tint = np.array([-0.04, 0.02, 0.08], dtype=np.float32)   # cooler/blue-ish

    out = base.copy()
    for i in range(structure.n_atoms):
        key = (structure.chain_ids[i], int(structure.res_ids[i]))
        ss = ss_by_res.get(key, "L")
        if ss == "H":
            out[i] = np.clip(base[i] + helix_tint, 0.0, 1.0)
        elif ss == "S":
            out[i] = np.clip(base[i] + strand_tint, 0.0, 1.0)
    return out


def color_spectrum(structure: Structure, *, by: str = "b") -> np.ndarray:
    """Rainbow spectrum (blue=low -> red=high) over b-factor or occupancy."""
    return color_values(
        structure.b_factors if by == "b" else structure.occupancies, structure.n_atoms
    )


def color_values(values: np.ndarray, n_atoms: int) -> np.ndarray:
    """Map a per-atom scalar array to a blue->red rainbow (min->max)."""
    lo, hi = float(values.min()), float(values.max())
    span = hi - lo if hi > lo else 1.0
    norm = (values - lo) / span
    out = np.empty((n_atoms, 3), dtype=np.float32)
    for i, v in enumerate(norm):
        hue = (1.0 - float(v)) * (2.0 / 3.0)  # 0.667 (blue) -> 0.0 (red)
        out[i] = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return out


# Kyte-Doolittle hydropathy (higher = more hydrophobic).
KYTE_DOOLITTLE: dict[str, float] = {
    "ILE": 4.5, "VAL": 4.2, "LEU": 3.8, "PHE": 2.8, "CYS": 2.5, "MET": 1.9, "ALA": 1.8,
    "GLY": -0.4, "THR": -0.7, "SER": -0.8, "TRP": -0.9, "TYR": -1.3, "PRO": -1.6,
    "HIS": -3.2, "GLU": -3.5, "GLN": -3.5, "ASP": -3.5, "ASN": -3.5, "LYS": -3.9, "ARG": -4.5,
}
# Formal charge by residue at physiological pH.
RESIDUE_CHARGE: dict[str, float] = {
    "ASP": -1.0, "GLU": -1.0, "LYS": 1.0, "ARG": 1.0, "HIS": 0.5,
}


def color_by_hydrophobicity(structure: Structure) -> np.ndarray:
    """Kyte-Doolittle hydropathy: teal (hydrophilic) -> orange (hydrophobic)."""
    hydrophilic = np.array([0.30, 0.75, 0.78], dtype=np.float32)  # teal
    hydrophobic = np.array([1.00, 0.55, 0.15], dtype=np.float32)  # orange
    grey = np.array([0.62, 0.62, 0.62], dtype=np.float32)
    out = np.empty((structure.n_atoms, 3), dtype=np.float32)
    for i, resn in enumerate(structure.res_names):
        kd = KYTE_DOOLITTLE.get(resn.upper())
        if kd is None:
            out[i] = grey
        else:
            t = (kd + 4.5) / 9.0  # normalize [-4.5, 4.5] -> [0, 1]
            out[i] = hydrophilic * (1 - t) + hydrophobic * t
    return out


def color_by_charge(structure: Structure) -> np.ndarray:
    """Acidic (Asp/Glu) red, basic (Lys/Arg/His) blue, neutral light grey."""
    neg = np.array([1.0, 0.3, 0.3], dtype=np.float32)
    pos = np.array([0.3, 0.45, 1.0], dtype=np.float32)
    neutral = np.array([0.85, 0.85, 0.85], dtype=np.float32)
    out = np.empty((structure.n_atoms, 3), dtype=np.float32)
    for i, resn in enumerate(structure.res_names):
        q = RESIDUE_CHARGE.get(resn.upper(), 0.0)
        out[i] = neg if q < 0 else pos if q > 0 else neutral
    return out


def color_by_secondary_structure(structure: Structure) -> np.ndarray:
    """Color helices/strands/loops distinctly (reusing the cartoon SS heuristic)."""
    from .geometry.cartoon import assign_chain_ss  # noqa: PLC0415

    ss_color = {
        "H": np.array([1.0, 0.35, 0.55], dtype=np.float32),  # helix - pink/red
        "S": np.array([1.0, 0.85, 0.3], dtype=np.float32),   # strand - gold
        "L": np.array([0.6, 0.85, 0.95], dtype=np.float32),  # loop/coil - light blue
    }
    ss_by_res = assign_chain_ss(structure)  # (chain, resid) -> 'H'|'S'|'L'
    out = np.empty((structure.n_atoms, 3), dtype=np.float32)
    for i in range(structure.n_atoms):
        key = (structure.chain_ids[i], int(structure.res_ids[i]))
        out[i] = ss_color.get(ss_by_res.get(key, "L"), ss_color["L"])
    return out
