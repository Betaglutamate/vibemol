"""A PyMOL-style atom-selection language: tokenizer, parser, and evaluator.

A selection string is parsed into a small AST whose nodes evaluate against an
:class:`EvalContext` (a structure plus any named selections in scope) to a
boolean mask over the structure's atoms.

Supported in v1:
  * property selectors: ``resn``, ``resi``, ``chain``, ``name``, ``elem``,
    ``index``, ``id``, ``b``, ``q`` (the latter two with ``<``/``<=``/``=``/
    ``>``/``>=`` comparisons)
  * keyword selectors: ``all``, ``none``, ``hydro``/``hydrogens``, ``hetatm``,
    ``polymer``, ``solvent``, ``backbone``, ``sidechain``
  * **named selections** by name (e.g. ``color red, sele`` or ``mysel and chain A``)
  * ``+``-separated value lists, numeric ranges (``resi 10-20``), and ``*``/``?``
    wildcards (``name C*``)
  * boolean logic: ``and``/``&``, ``or``/``|``, ``not``/``!``, parentheses
  * modifiers: ``byres SEL`` (prefix), ``within X of SEL`` (prefix),
    ``SEL around X`` and ``SEL expand X`` (postfix)
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field

import numpy as np

from ..model.structure import Structure


class SelectionError(ValueError):
    """Raised when a selection string cannot be parsed or evaluated."""


@dataclass
class EvalContext:
    """What a selection evaluates against: a structure + named selections in scope."""

    structure: Structure
    named: dict[str, np.ndarray] = field(default_factory=dict)
    object_name: str = ""  # the object being evaluated (for object-name selectors)


# --- tokenizer --------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"\s+|(?P<lparen>\()|(?P<rparen>\))|(?P<op>[&|!])"
    r"|(?P<cmp><=|>=|==|=|<|>)|(?P<word>[^\s()&|!<>=]+)"
)

_KEYWORD_ZERO = {  # selectors taking no argument
    "all", "none", "hydro", "hydrogens", "hetatm",
    "polymer", "solvent", "backbone", "sidechain",
}
_KEYWORD_ARG = {  # selectors taking a +-separated value list
    "resn", "resi", "chain", "name", "elem", "element", "index", "id", "ss",
}
_COMPARE = {"b", "q"}


@dataclass
class _Tok:
    kind: str  # "word" | "op" | "cmp" | "lparen" | "rparen"
    value: str


def _tokenize(text: str) -> list[_Tok]:
    toks: list[_Tok] = []
    for m in _TOKEN_RE.finditer(text):
        if m.lastgroup is None:  # whitespace
            continue
        toks.append(_Tok(m.lastgroup, m.group()))
    return toks


# --- AST --------------------------------------------------------------------


class Node:
    def eval(self, ctx: EvalContext) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class All(Node):
    def eval(self, ctx: EvalContext) -> np.ndarray:
        return np.ones(ctx.structure.n_atoms, dtype=bool)


@dataclass
class NoneSel(Node):
    def eval(self, ctx: EvalContext) -> np.ndarray:
        return np.zeros(ctx.structure.n_atoms, dtype=bool)


@dataclass
class NamedSelection(Node):
    name: str

    def eval(self, ctx: EvalContext) -> np.ndarray:
        mask = ctx.named.get(self.name)
        if mask is None:
            lower = self.name.lower()
            for key, value in ctx.named.items():
                if key.lower() == lower:
                    mask = value
                    break
        if mask is None:
            return np.zeros(ctx.structure.n_atoms, dtype=bool)
        return mask.copy()


@dataclass
class ObjectSelector(Node):
    name: str

    def eval(self, ctx: EvalContext) -> np.ndarray:
        match = ctx.object_name.lower() == self.name.lower()
        return np.full(ctx.structure.n_atoms, match, dtype=bool)


@dataclass
class Keyword(Node):
    name: str

    def eval(self, ctx: EvalContext) -> np.ndarray:
        s = ctx.structure
        elems = np.array(s.elements)
        if self.name in ("hydro", "hydrogens"):
            return elems == "H"
        if self.name == "hetatm":
            return s.is_hetatm.copy()
        solvent = np.array([r in ("HOH", "WAT", "TIP", "SOL") for r in s.res_names])
        if self.name == "solvent":
            return solvent
        if self.name == "polymer":
            return ~solvent & ~s.is_hetatm
        names = np.array([n.upper() for n in s.atom_names])
        if self.name == "backbone":
            return np.isin(names, ["N", "CA", "C", "O", "P", "O1P", "O2P", "OP1", "OP2"])
        if self.name == "sidechain":
            bb = np.isin(names, ["N", "CA", "C", "O"])
            return ~bb & ~(elems == "H") & ~s.is_hetatm
        raise SelectionError(f"unknown keyword: {self.name}")


@dataclass
class ListSelector(Node):
    field: str
    values: list[str]

    def eval(self, ctx: EvalContext) -> np.ndarray:
        s = ctx.structure
        if self.field in ("resi", "index", "id"):
            return self._eval_numeric(s)
        return self._eval_string(s)

    def _eval_string(self, s: Structure) -> np.ndarray:
        if self.field == "resn":
            col = [v.upper() for v in s.res_names]
        elif self.field == "chain":
            col = [v.upper() for v in s.chain_ids]
        elif self.field == "name":
            col = [v.upper() for v in s.atom_names]
        else:  # elem / element
            col = [v.upper() for v in s.elements]
        patterns = [v.upper() for v in self.values]
        wild = [p for p in patterns if "*" in p or "?" in p]
        exact = {p for p in patterns if "*" not in p and "?" not in p}
        out = np.array([c in exact for c in col], dtype=bool)
        for p in wild:
            out |= np.array([fnmatch.fnmatchcase(c, p) for c in col], dtype=bool)
        return out

    def _eval_numeric(self, s: Structure) -> np.ndarray:
        wanted: set[int] = set()
        for v in self.values:
            if "-" in v[1:]:  # range like 10-20 (allow leading '-' for negatives)
                lo_s, hi_s = v[: v.index("-", 1)], v[v.index("-", 1) + 1 :]
                try:
                    lo, hi = int(lo_s), int(hi_s)
                except ValueError as e:
                    raise SelectionError(f"bad range: {v!r}") from e
                wanted.update(range(lo, hi + 1))
            else:
                try:
                    wanted.add(int(v))
                except ValueError as e:
                    raise SelectionError(f"bad {self.field} value: {v!r}") from e
        col = s.res_ids if self.field == "resi" else (
            s.ids if self.field == "id" else np.arange(1, s.n_atoms + 1)
        )
        return np.isin(col, list(wanted))


@dataclass
class Compare(Node):
    field: str  # "b" | "q"
    op: str
    value: float

    def eval(self, ctx: EvalContext) -> np.ndarray:
        col = ctx.structure.b_factors if self.field == "b" else ctx.structure.occupancies
        if self.op in ("=", "=="):
            return col == self.value
        if self.op == "<":
            return col < self.value
        if self.op == "<=":
            return col <= self.value
        if self.op == ">":
            return col > self.value
        return col >= self.value


@dataclass
class Not(Node):
    child: Node

    def eval(self, ctx: EvalContext) -> np.ndarray:
        return ~self.child.eval(ctx)


@dataclass
class And(Node):
    left: Node
    right: Node

    def eval(self, ctx: EvalContext) -> np.ndarray:
        return self.left.eval(ctx) & self.right.eval(ctx)


@dataclass
class Or(Node):
    left: Node
    right: Node

    def eval(self, ctx: EvalContext) -> np.ndarray:
        return self.left.eval(ctx) | self.right.eval(ctx)


@dataclass
class ByRes(Node):
    child: Node

    def eval(self, ctx: EvalContext) -> np.ndarray:
        mask = self.child.eval(ctx)
        labels = ctx.structure.residue_labels()
        hit = np.unique(labels[mask])
        return np.isin(labels, hit)


@dataclass
class Within(Node):
    distance: float
    child: Node
    exclude_self: bool = False  # True for `around`

    def eval(self, ctx: EvalContext) -> np.ndarray:
        coords = ctx.structure.coords
        ref_mask = self.child.eval(ctx)
        near = _within_mask(coords, coords[ref_mask], self.distance)
        if self.exclude_self:
            near &= ~ref_mask
        return near


def _within_mask(coords: np.ndarray, ref: np.ndarray, dist: float) -> np.ndarray:
    """Mask of ``coords`` atoms within ``dist`` (A) of any atom in ``ref``."""
    out = np.zeros(coords.shape[0], dtype=bool)
    if ref.shape[0] == 0:
        return out
    d2 = dist * dist
    block = 2048
    for start in range(0, coords.shape[0], block):
        chunk = coords[start : start + block]
        diff = chunk[:, None, :] - ref[None, :, :]
        min_d2 = (diff * diff).sum(axis=2).min(axis=1)
        out[start : start + block] = min_d2 <= d2
    return out


# --- parser -----------------------------------------------------------------


class _Parser:
    def __init__(
        self, toks: list[_Tok], names: frozenset[str], object_names: frozenset[str]
    ):
        self.toks = toks
        self.i = 0
        self.names = names
        self._names_lower = {n.lower() for n in names}
        self._object_names_lower = {n.lower() for n in object_names}

    def _peek(self) -> _Tok | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def _next(self) -> _Tok:
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def _is_word(self, *words: str) -> bool:
        tok = self._peek()
        return tok is not None and tok.kind == "word" and tok.value.lower() in words

    def _is_op(self, symbol: str) -> bool:
        tok = self._peek()
        return tok is not None and tok.kind == "op" and tok.value == symbol

    def parse(self) -> Node:
        node = self._or()
        if self.i != len(self.toks):
            raise SelectionError(f"unexpected token: {self.toks[self.i].value!r}")
        return node

    def _or(self) -> Node:
        node = self._and()
        while self._is_word("or") or self._is_op("|"):
            self._next()
            node = Or(node, self._and())
        return node

    def _and(self) -> Node:
        node = self._unary()
        while self._is_word("and") or self._is_op("&"):
            self._next()
            node = And(node, self._unary())
        return node

    def _unary(self) -> Node:
        tok = self._peek()
        if tok and (tok.value == "!" or self._is_word("not")):
            self._next()
            return Not(self._unary())
        if self._is_word("byres"):
            self._next()
            return ByRes(self._unary())
        if self._is_word("within"):
            self._next()
            dist = self._number()
            if not self._is_word("of"):
                raise SelectionError("expected 'of' after 'within <distance>'")
            self._next()
            return Within(dist, self._unary())
        return self._postfix()

    def _postfix(self) -> Node:
        node = self._primary()
        while self._is_word("around", "expand"):
            kw = self._next().value.lower()
            dist = self._number()
            node = Within(dist, node, exclude_self=(kw == "around"))
        return node

    def _primary(self) -> Node:
        tok = self._peek()
        if tok is None:
            raise SelectionError("unexpected end of selection")
        if tok.kind == "lparen":
            self._next()
            node = self._or()
            closing = self._peek()
            if closing is None or closing.kind != "rparen":
                raise SelectionError("missing closing parenthesis")
            self._next()
            return node
        if tok.kind != "word":
            raise SelectionError(f"unexpected token: {tok.value!r}")
        return self._selector()

    def _selector(self) -> Node:
        word = self._next().value
        lw = word.lower()
        if lw in ("all", "*"):
            return All()
        if lw == "none":
            return NoneSel()
        if lw in _KEYWORD_ZERO:
            return Keyword(lw)
        if lw in _COMPARE:
            cmp_tok = self._peek()
            if not cmp_tok or cmp_tok.kind != "cmp":
                raise SelectionError(f"expected comparison after {lw!r}")
            op = self._next().value
            return Compare(lw, op, self._number())
        if lw in _KEYWORD_ARG:
            arg = self._peek()
            if not arg or arg.kind != "word":
                raise SelectionError(f"expected value(s) after {lw!r}")
            sel_field = "elem" if lw == "element" else lw
            return ListSelector(sel_field, self._next().value.split("+"))
        if lw in self._names_lower:  # a named selection in scope
            return NamedSelection(word)
        if lw in self._object_names_lower:  # an object name (all atoms of that object)
            return ObjectSelector(word)
        raise SelectionError(f"unknown selector: {word!r}")

    def _number(self) -> float:
        tok = self._peek()
        if not tok or tok.kind != "word":
            raise SelectionError("expected a number")
        try:
            return float(self._next().value)
        except ValueError as e:
            raise SelectionError(f"expected a number, got {tok.value!r}") from e


def parse(
    text: str,
    names: frozenset[str] = frozenset(),
    object_names: frozenset[str] = frozenset(),
) -> Node:
    """Parse a selection string into an AST (raises :class:`SelectionError`).

    ``names`` are named selections in scope and ``object_names`` are loaded
    object names, so both can be referenced by name in a selection.
    """
    toks = _tokenize(text)
    if not toks:
        return All()
    return _Parser(toks, names, object_names).parse()


def select(
    structure: Structure,
    expression: str,
    named: dict[str, np.ndarray] | None = None,
    *,
    object_name: str = "",
    object_names: frozenset[str] = frozenset(),
) -> np.ndarray:
    """Evaluate a selection expression to a boolean mask over ``structure``.

    ``named`` maps selection names to masks; ``object_name`` is the object being
    evaluated and ``object_names`` the set of loaded names, so expressions like
    ``color red, sele``, ``mysel and chain A``, or ``mobile and resi 1-20`` resolve.
    """
    named = named or {}
    node = parse(expression, frozenset(named), object_names)
    return node.eval(EvalContext(structure, named, object_name))
