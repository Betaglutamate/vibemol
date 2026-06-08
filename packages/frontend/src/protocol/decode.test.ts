import { describe, expect, it } from "vitest";

import { asFloat32, decodeScene } from "./decode";
import type { SceneMessage } from "./types";

describe("asFloat32", () => {
  it("round-trips float32 bytes", () => {
    const source = new Float32Array([1.5, -2.25, 3.0]);
    expect(Array.from(asFloat32(new Uint8Array(source.buffer)))).toEqual([1.5, -2.25, 3.0]);
  });

  it("handles a misaligned view by copying", () => {
    const backing = new Uint8Array(5);
    backing.set(new Uint8Array(new Float32Array([7.0]).buffer), 1);
    expect(Array.from(asFloat32(backing.subarray(1)))).toEqual([7.0]);
  });
});

describe("decodeScene", () => {
  it("decodes objects and their draw groups into typed arrays", () => {
    const positions = new Float32Array([0, 0, 0, 1, 1, 1]);
    const radii = new Float32Array([1.7, 1.2]);
    const colors = new Float32Array([1, 0, 0, 0, 1, 0]);
    const msg: SceneMessage = {
      type: "scene",
      settings: { bg_color: "#000000" },
      selections: ["sele"],
      center: [0.5, 0.5, 0.5],
      bounding_radius: 1,
      n_states: 1,
      current_state: 0,
      objects: [
        {
          name: "demo",
          visible: true,
          n_atoms: 2,
          center: [0.5, 0.5, 0.5],
          bounding_radius: 1,
          active_reps: ["spheres"],
          n_states: 1,
          current_state: 0,
          groups: [
            {
              primitive: "spheres",
              count: 2,
              positions: new Uint8Array(positions.buffer),
              radii: new Uint8Array(radii.buffer),
              colors: new Uint8Array(colors.buffer),
            },
          ],
          pick_positions: new Uint8Array(positions.buffer),
          atoms: { elements: ["C", "O"], names: ["C", "O"], resns: ["A", "A"], resis: [1, 1], chains: ["A", "A"] },
          residues: [{ chain: "A", resi: 1, resn: "ALA", code: "A" }],
          selected_residues: [],
        },
      ],
      measurement_lines: null,
      labels: [],
      selection_points: null,
    };

    const scene = decodeScene(msg);
    expect(scene.objects).toHaveLength(1);
    const group = scene.objects[0].groups[0];
    expect(group.primitive).toBe("spheres");
    if (group.primitive === "spheres") {
      expect(group.count).toBe(2);
      expect(group.positions.length).toBe(6);
      expect(group.radii[0]).toBeCloseTo(1.7);
    }
    expect(scene.selections).toEqual(["sele"]);
  });
});
