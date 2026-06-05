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


def color_spectrum(structure: Structure, *, by: str = "b") -> np.ndarray:
    """Rainbow spectrum (blue=low -> red=high) over b-factor or occupancy."""
    values = structure.b_factors if by == "b" else structure.occupancies
    lo, hi = float(values.min()), float(values.max())
    span = hi - lo if hi > lo else 1.0
    norm = (values - lo) / span
    out = np.empty((structure.n_atoms, 3), dtype=np.float32)
    for i, v in enumerate(norm):
        hue = (1.0 - float(v)) * (2.0 / 3.0)  # 0.667 (blue) -> 0.0 (red)
        out[i] = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return out
