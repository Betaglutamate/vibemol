import type {
  DecodedGroup,
  DecodedObject,
  DecodedScene,
  RawGroup,
  RawObject,
  SceneMessage,
} from "./types";

/** Wrap a raw byte blob as Float32Array, copying to guarantee 4-byte alignment. */
export function asFloat32(bytes: Uint8Array): Float32Array {
  // msgpack may hand back a view into a larger buffer at an arbitrary offset;
  // Float32Array requires a 4-byte-aligned offset, so copy into a fresh buffer.
  const copy = bytes.slice();
  return new Float32Array(copy.buffer, copy.byteOffset, copy.byteLength / 4);
}

function decodeGroup(g: RawGroup): DecodedGroup {
  switch (g.primitive) {
    case "spheres":
      return {
        primitive: "spheres",
        count: g.count,
        positions: asFloat32(g.positions!),
        radii: asFloat32(g.radii!),
        colors: asFloat32(g.colors!),
      };
    case "cylinders":
      return {
        primitive: "cylinders",
        count: g.count,
        starts: asFloat32(g.starts!),
        ends: asFloat32(g.ends!),
        radii: asFloat32(g.radii!),
        colors: asFloat32(g.colors!),
      };
    case "lines":
      return {
        primitive: "lines",
        count: g.count,
        positions: asFloat32(g.positions!),
        colors: asFloat32(g.colors!),
      };
    case "points":
      return {
        primitive: "points",
        count: g.count,
        positions: asFloat32(g.positions!),
        colors: asFloat32(g.colors!),
        size: g.size ?? 3,
      };
  }
}

function decodeObject(o: RawObject): DecodedObject {
  return {
    name: o.name,
    visible: o.visible,
    nAtoms: o.n_atoms,
    center: o.center,
    boundingRadius: o.bounding_radius,
    activeReps: o.active_reps,
    groups: o.groups.map(decodeGroup),
  };
}

export function decodeScene(msg: SceneMessage): DecodedScene {
  return {
    settings: msg.settings,
    selections: msg.selections,
    center: msg.center,
    boundingRadius: msg.bounding_radius,
    objects: msg.objects.map(decodeObject),
  };
}
