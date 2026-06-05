"""The command registry, execution context, and text command parser.

A command is ``fn(ctx, args) -> CommandResult``. Commands mutate the
backend-owned :class:`~vibemol.model.scene.Scene` via the :class:`Context`; the
server re-streams the scene (and applies any camera directive) afterward.

Text syntax mirrors PyMOL: ``<name> <arg1>, <arg2>, …`` — the command name runs
to the first space, and the remainder is split on commas into positional args.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from ..model.scene import MolObject, Scene
from ..model.structure import Structure
from ..select import select


class CommandError(ValueError):
    """Raised for unknown commands or invalid arguments."""


@dataclass
class CommandResult:
    """Outcome of a command: a log line, optional camera move, and dirty flags."""

    log: str = ""
    camera: dict[str, object] | None = None
    scene_changed: bool = True
    selections_changed: bool = False


class Context:
    """Execution context wrapping the scene plus selection/loading helpers."""

    def __init__(self, scene: Scene):
        self.scene = scene

    def add_structure(self, structure: Structure, name: str | None = None) -> MolObject:
        base = name or structure.name or "obj"
        unique = self.scene.unique_name(base)
        structure.name = unique
        return self.scene.add_object(MolObject(name=unique, structure=structure))

    def resolve(self, expression: str) -> dict[str, np.ndarray]:
        """Evaluate a selection expression against every object's atoms."""
        return {
            name: select(obj.structure, expression)
            for name, obj in self.scene.objects.items()
        }

    def selected_coords(self, expression: str) -> np.ndarray:
        """Concatenated coordinates of all atoms matching ``expression``."""
        masks = self.resolve(expression)
        parts = [
            obj.structure.coords[masks[name]]
            for name, obj in self.scene.objects.items()
            if masks[name].any()
        ]
        return np.concatenate(parts) if parts else np.empty((0, 3), dtype=np.float32)


Command = Callable[[Context, list[str]], CommandResult]
_REGISTRY: dict[str, Command] = {}
_ALIASES: dict[str, str] = {}


def command(name: str, *aliases: str) -> Callable[[Command], Command]:
    """Decorator registering a command (and optional aliases)."""

    def wrap(fn: Command) -> Command:
        _REGISTRY[name] = fn
        for alias in aliases:
            _ALIASES[alias] = name
        return fn

    return wrap


def registered_commands() -> list[str]:
    return sorted(_REGISTRY)


@dataclass
class _Parsed:
    name: str
    args: list[str] = field(default_factory=list)


def parse_command_line(line: str) -> _Parsed | None:
    """Parse one command line into a name + positional args (None if blank)."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    head, _, rest = line.partition(" ")
    args = [a.strip() for a in rest.split(",")] if rest.strip() else []
    return _Parsed(head.lower(), args)


def dispatch(ctx: Context, line: str) -> CommandResult:
    """Parse and execute a single command line."""
    parsed = parse_command_line(line)
    if parsed is None:
        return CommandResult(scene_changed=False)
    name = _ALIASES.get(parsed.name, parsed.name)
    fn = _REGISTRY.get(name)
    if fn is None:
        raise CommandError(f"unknown command: {parsed.name!r}")
    return fn(ctx, parsed.args)
