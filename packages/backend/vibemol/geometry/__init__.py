"""Representation geometry generators.

Phase 1 ships lines, sticks, ball-and-stick, spheres, nonbonded, and dots via
:func:`build_groups`. Phase 2 adds cartoon and molecular surfaces (marching
cubes). All generators emit binary draw groups (see :mod:`vibemol.protocol`).
"""

from .representations import build_groups

__all__ = ["build_groups"]
