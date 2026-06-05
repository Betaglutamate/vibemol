// TypeScript mirror of the backend wire protocol (vibemol/protocol).
// Geometry bulk fields arrive as raw little-endian float32 byte blobs.

// --- client -> server ---

export interface LoadCommand {
  type: "load";
  source: "demo";
}

export interface LoadDataCommand {
  type: "load_data";
  name: string;
  format: string;
  text: string;
}

export interface CommandMessage {
  type: "command";
  text: string;
}

export type ClientMessage = LoadCommand | LoadDataCommand | CommandMessage;

// --- server -> client (raw, bulk fields are Uint8Array) ---

export interface RawGroup {
  primitive: "spheres" | "cylinders" | "lines" | "points";
  count: number;
  size?: number;
  positions?: Uint8Array;
  radii?: Uint8Array;
  colors?: Uint8Array;
  starts?: Uint8Array;
  ends?: Uint8Array;
}

export interface RawObject {
  name: string;
  visible: boolean;
  n_atoms: number;
  center: [number, number, number];
  bounding_radius: number;
  active_reps: string[];
  groups: RawGroup[];
}

export interface SceneMessage {
  type: "scene";
  settings: { bg_color?: string };
  selections: string[];
  center: [number, number, number];
  bounding_radius: number;
  objects: RawObject[];
}

export interface CameraMessage {
  type: "camera";
  center: [number, number, number];
  radius: number;
}

export interface LogMessage {
  type: "log";
  level: "info" | "error";
  message: string;
}

export type ServerMessage = SceneMessage | CameraMessage | LogMessage;

// --- decoded (GPU-ready typed arrays) ---

export type DecodedGroup =
  | { primitive: "spheres"; count: number; positions: Float32Array; radii: Float32Array; colors: Float32Array }
  | { primitive: "cylinders"; count: number; starts: Float32Array; ends: Float32Array; radii: Float32Array; colors: Float32Array }
  | { primitive: "lines"; count: number; positions: Float32Array; colors: Float32Array }
  | { primitive: "points"; count: number; positions: Float32Array; colors: Float32Array; size: number };

export interface DecodedObject {
  name: string;
  visible: boolean;
  nAtoms: number;
  center: [number, number, number];
  boundingRadius: number;
  activeReps: string[];
  groups: DecodedGroup[];
}

export interface DecodedScene {
  settings: { bg_color?: string };
  selections: string[];
  center: [number, number, number];
  boundingRadius: number;
  objects: DecodedObject[];
}
