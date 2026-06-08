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
    # Additional elements for ligands and metals.
    "B": 0.84, "SI": 1.11, "AL": 1.21, "LI": 1.28,
    "CO": 1.26, "NI": 1.24, "CR": 1.39, "V": 1.53, "MO": 1.54,
    "W": 1.62, "RU": 1.46, "RH": 1.42, "PD": 1.39, "AG": 1.45,
    "CD": 1.44, "PT": 1.36, "AU": 1.36, "HG": 1.32, "PB": 1.46,
    "AS": 1.19, "SN": 1.39, "BI": 1.48, "SR": 1.95, "BA": 2.15,
    "TI": 1.60, "SC": 1.70, "GA": 1.22, "GE": 1.20, "IN": 1.42,
}
DEFAULT_COVALENT_RADIUS = 0.77

# Van der Waals radii (A) — used for sphere (CPK/VDW) representation.
VDW_RADII: dict[str, float] = {
    "H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52, "F": 1.47,
    "P": 1.80, "S": 1.80, "CL": 1.75, "BR": 1.85, "I": 1.98,
    "NA": 2.27, "MG": 1.73, "K": 2.75, "CA": 2.31, "FE": 2.00,
    "ZN": 1.39, "MN": 2.00, "CU": 1.40, "SE": 1.90,
    "B": 1.92, "SI": 2.10, "AL": 1.84, "LI": 1.82,
    "CO": 2.00, "NI": 1.63, "CR": 2.00, "V": 2.00, "MO": 2.00,
    "W": 2.00, "RU": 2.00, "RH": 2.00, "PD": 1.63, "AG": 1.72,
    "CD": 1.58, "PT": 1.75, "AU": 1.66, "HG": 1.55, "PB": 2.02,
    "AS": 1.85, "SN": 2.17, "BI": 2.07, "SR": 2.49, "BA": 2.68,
    "TI": 2.00, "SC": 2.00, "GA": 1.87, "GE": 2.11, "IN": 1.93,
}
DEFAULT_VDW_RADIUS = 1.70

# CPK colors as sRGB hex (no leading '#').
CPK_COLORS: dict[str, str] = {
    "H": "ffffff", "C": "33ff33", "N": "3333ff", "O": "ff4d4d", "F": "b3ffb3",
    "P": "ff8000", "S": "e6c819", "CL": "1ff01f", "BR": "992200", "I": "6600bb",
    "NA": "ab5cf2", "MG": "8aff00", "K": "8f40d4", "CA": "3dff00", "FE": "e06633",
    "ZN": "7d80b0", "MN": "9c7ac7", "CU": "c88033", "SE": "ffa100",
    "B": "ffb5b5", "SI": "f0c8a0", "AL": "bfa6a6", "LI": "cc80ff",
    "CO": "f090a0", "NI": "50d050", "CR": "8a99c7", "V": "a6a6ab", "MO": "54b5b5",
    "W": "2194d6", "RU": "248f8f", "RH": "0a7d8c", "PD": "006985", "AG": "c0c0c0",
    "CD": "ffd98f", "PT": "d0d0e0", "AU": "ffd123", "HG": "b8b8d0", "PB": "575961",
    "AS": "bd80e3", "SN": "668080", "BI": "9e4fb5", "SR": "00ff00", "BA": "00c900",
    "TI": "bfc2c7", "SC": "e6e6e6", "GA": "c28f8f", "GE": "668f8f", "IN": "a67573",
}
DEFAULT_COLOR = "ff1493"  # deep pink for unknown elements


def covalent_radius(element: str) -> float:
    return COVALENT_RADII.get(element.upper(), DEFAULT_COVALENT_RADIUS)


def vdw_radius(element: str) -> float:
    return VDW_RADII.get(element.upper(), DEFAULT_VDW_RADIUS)


def cpk_color(element: str) -> str:
    return CPK_COLORS.get(element.upper(), DEFAULT_COLOR)


# Standard atomic weights (g/mol) for common biomolecular elements.
ATOMIC_MASS: dict[str, float] = {
    "H": 1.008, "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998,
    "P": 30.974, "S": 32.06, "CL": 35.45, "BR": 79.904, "I": 126.90,
    "NA": 22.990, "MG": 24.305, "K": 39.098, "CA": 40.078, "FE": 55.845,
    "ZN": 65.38, "MN": 54.938, "CU": 63.546, "SE": 78.971,
    "B": 10.81, "SI": 28.086, "AL": 26.982, "LI": 6.941,
    "CO": 58.933, "NI": 58.693, "CR": 51.996, "V": 50.942, "MO": 95.95,
    "W": 183.84, "RU": 101.07, "RH": 102.91, "PD": 106.42, "AG": 107.87,
    "CD": 112.41, "PT": 195.08, "AU": 196.97, "HG": 200.59, "PB": 207.2,
    "AS": 74.922, "SN": 118.71, "BI": 208.98, "SR": 87.62, "BA": 137.33,
    "TI": 47.867, "SC": 44.956, "GA": 69.723, "GE": 72.630, "IN": 114.82,
}
DEFAULT_MASS = 12.011


def atomic_mass(element: str) -> float:
    return ATOMIC_MASS.get(element.upper(), DEFAULT_MASS)
