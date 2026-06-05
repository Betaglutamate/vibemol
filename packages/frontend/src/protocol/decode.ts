import type { RawGeometryMessage, SphereGeometry } from "./types";

/** Wrap a raw byte blob as Float32Array, copying to guarantee 4-byte alignment. */
export function asFloat32(bytes: Uint8Array): Float32Array {
  // msgpack may hand back a view into a larger buffer at an arbitrary offset;
  // Float32Array requires a 4-byte-aligned offset, so copy into a fresh buffer.
  const copy = bytes.slice();
  return new Float32Array(copy.buffer, copy.byteOffset, copy.byteLength / 4);
}

/** Decode a `geometry` message's bulk fields into GPU-ready typed arrays. */
export function decodeSpheres(msg: RawGeometryMessage): SphereGeometry {
  return {
    object: msg.object,
    nAtoms: msg.n_atoms,
    center: msg.center,
    boundingRadius: msg.bounding_radius,
    positions: asFloat32(msg.positions),
    radii: asFloat32(msg.radii),
    colors: asFloat32(msg.colors),
  };
}
