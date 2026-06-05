"""The command registry and PyMOL-compatible command implementations.

Importing this package registers the core commands (see :mod:`.core`). Use
:func:`dispatch` to run a command line against a :class:`Context`.
"""

from . import core  # noqa: F401 - registers commands as a side effect
from .registry import (
    CommandError,
    CommandResult,
    Context,
    dispatch,
    parse_command_line,
    registered_commands,
)

__all__ = [
    "Context",
    "CommandError",
    "CommandResult",
    "dispatch",
    "parse_command_line",
    "registered_commands",
]
