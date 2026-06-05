"""The structure model: SoA atom arrays, element data, and bond inference."""

from .bonds import infer_bonds
from .structure import Structure

__all__ = ["Structure", "infer_bonds"]
