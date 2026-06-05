"""The client/server wire protocol.

Control messages (commands, scene metadata, errors) are plain dicts serialized
with msgpack. Geometry travels in the same msgpack envelope but its bulk fields
(positions, radii, colors) are **raw little-endian float32 byte blobs**, so the
frontend can wrap them directly as typed arrays / GPU buffers without parsing
arrays of numbers. This is the rule for all geometry: never JSON arrays of
vertices.
"""

from .geometry import spheres_message
from .messages import ErrorMessage, LoadCommand

__all__ = ["spheres_message", "ErrorMessage", "LoadCommand"]
