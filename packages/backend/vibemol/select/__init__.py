"""PyMOL-style atom-selection language (parser + evaluator).

Selection v1: ``resn/resi/chain/name/elem/index/id/b/q``, ranges, wildcards,
``and/or/not`` (& | !), ``byres``, ``within X of``, ``around`` — evaluated over
the NumPy atom arrays in :mod:`vibemol.model`.
"""

from .engine import EvalContext, SelectionError, parse, select

__all__ = ["select", "parse", "SelectionError", "EvalContext"]
