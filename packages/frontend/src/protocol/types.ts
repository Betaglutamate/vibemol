// TypeScript mirror of the backend wire protocol (vibemol/protocol).
// Geometry bulk fields arrive as raw little-endian float32 byte blobs.

export interface LoadCommand {
  type: "load";
  source: "demo" | "rcsb" | "upload";
  id?: string;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

/** Raw `geometry` message as decoded from msgpack (bulk fields are Uint8Array). */
export interface RawGeometryMessage {
  type: "geometry";
  object: string;
  representation: string;
  n_atoms: number;
  center: [number, number, number];
  bounding_radius: number;
  positions: Uint8Array;
  radii: Uint8Array;
  colors: Uint8Array;
}

export type ServerMessage = RawGeometryMessage | ErrorMessage;

/** Geometry with bulk fields decoded into typed arrays, ready for the GPU. */
export interface SphereGeometry {
  object: string;
  nAtoms: number;
  center: [number, number, number];
  boundingRadius: number;
  positions: Float32Array; // nAtoms * 3
  radii: Float32Array; // nAtoms
  colors: Float32Array; // nAtoms * 3, [0,1]
}
