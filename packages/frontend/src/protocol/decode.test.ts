import { describe, expect, it } from "vitest";

import { asFloat32, decodeSpheres } from "./decode";
import type { RawGeometryMessage } from "./types";

describe("asFloat32", () => {
  it("round-trips float32 bytes", () => {
    const source = new Float32Array([1.5, -2.25, 3.0]);
    const bytes = new Uint8Array(source.buffer);
    expect(Array.from(asFloat32(bytes))).toEqual([1.5, -2.25, 3.0]);
  });

  it("handles a misaligned view by copying", () => {
    // Place float data at a non-4-byte-aligned offset inside a larger buffer.
    const backing = new Uint8Array(5);
    const floats = new Float32Array([7.0]);
    backing.set(new Uint8Array(floats.buffer), 1);
    const view = backing.subarray(1); // byteOffset = 1 (misaligned)
    expect(Array.from(asFloat32(view))).toEqual([7.0]);
  });
});

describe("decodeSpheres", () => {
  it("decodes bulk fields into typed arrays", () => {
    const positions = new Float32Array([0, 0, 0, 1, 1, 1]);
    const radii = new Float32Array([1.7, 1.2]);
    const colors = new Float32Array([1, 0, 0, 0, 1, 0]);
    const msg: RawGeometryMessage = {
      type: "geometry",
      object: "demo",
      representation: "spheres",
      n_atoms: 2,
      center: [0.5, 0.5, 0.5],
      bounding_radius: 1,
      positions: new Uint8Array(positions.buffer),
      radii: new Uint8Array(radii.buffer),
      colors: new Uint8Array(colors.buffer),
    };
    const g = decodeSpheres(msg);
    expect(g.nAtoms).toBe(2);
    expect(g.positions.length).toBe(6);
    expect(g.radii[0]).toBeCloseTo(1.7);
    expect(g.colors.length).toBe(6);
  });
});
