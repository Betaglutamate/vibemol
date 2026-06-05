"""The client/server wire protocol.

Control messages (commands, scene metadata, errors) are plain dicts serialized
with msgpack. Geometry travels in the same msgpack envelope but its bulk fields
(positions, radii, colors, …) are **raw little-endian float32 byte blobs**, so
the frontend wraps them directly as typed arrays / GPU buffers. This is the rule
for all geometry: never JSON arrays of vertices.

Scene/object message builders live in :mod:`vibemol.protocol.scene` (imported
directly, to avoid a cycle with :mod:`vibemol.geometry`).
"""

from .geometry import cylinders_group, lines_group, points_group, spheres_group
from .messages import ErrorMessage, LoadCommand

__all__ = [
    "spheres_group",
    "cylinders_group",
    "lines_group",
    "points_group",
    "ErrorMessage",
    "LoadCommand",
]
