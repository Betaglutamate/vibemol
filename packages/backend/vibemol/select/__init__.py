"""PyMOL-style atom-selection language (parser + evaluator).

Phase 1 implements selection v1: ``resn/resi/chain/name/elem/index/id/b/q``,
ranges, wildcards, ``and/or/not`` (& | !), ``byres``, ``within X of``,
``around``, and named selections — evaluated over the NumPy atom arrays in
:mod:`vibemol.model`.
"""
