"""Per-element reference data: covalent radii, van der Waals radii, and CPK colors.

Values are pragmatic defaults sufficient for bonding heuristics and rendering.
Radii are in angstroms; colors are sRGB hex strings (PyMOL-like CPK scheme).
"""

from __future__ import annotations

# Covalent radii (A) — used for distance-based bond inference.
COVALENT_RADII: dict[str, float] = {
    "H": 0.31, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57,
    "P": 1.07, "S": 1.05, "CL": 1.02, "BR": 1.20, "I": 1.39,
    "NA": 1.66, "MG": 1.41, "K": 2.03, "CA": 1.76, "FE": 1.32,
    "ZN": 1.22, "MN": 1.39, "CU": 1.32, "SE": 1.20,
}
DEFAULT_COVALENT_RADIUS = 0.77

# Van der Waals radii (A) — used for sphere (CPK/VDW) representation.
VDW_RADII: dict[str, float] = {
    "H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52, "F": 1.47,
    "P": 1.80, "S": 1.80, "CL": 1.75, "BR": 1.85, "I": 1.98,
    "NA": 2.27, "MG": 1.73, "K": 2.75, "CA": 2.31, "FE": 2.00,
    "ZN": 1.39, "MN": 2.00, "CU": 1.40, "SE": 1.90,
}
DEFAULT_VDW_RADIUS = 1.70

# CPK colors as sRGB hex (no leading '#').
CPK_COLORS: dict[str, str] = {
    "H": "ffffff", "C": "33ff33", "N": "3333ff", "O": "ff4d4d", "F": "b3ffb3",
    "P": "ff8000", "S": "e6c819", "CL": "1ff01f", "BR": "992200", "I": "6600bb",
    "NA": "ab5cf2", "MG": "8aff00", "K": "8f40d4", "CA": "3dff00", "FE": "e06633",
    "ZN": "7d80b0", "MN": "9c7ac7", "CU": "c88033", "SE": "ffa100",
}
DEFAULT_COLOR = "ff1493"  # deep pink for unknown elements


def covalent_radius(element: str) -> float:
    return COVALENT_RADII.get(element.upper(), DEFAULT_COVALENT_RADIUS)


def vdw_radius(element: str) -> float:
    return VDW_RADII.get(element.upper(), DEFAULT_VDW_RADIUS)


def cpk_color(element: str) -> str:
    return CPK_COLORS.get(element.upper(), DEFAULT_COLOR)
