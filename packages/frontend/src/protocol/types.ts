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
  primitive: "spheres" | "cylinders" | "lines" | "points" | "mesh";
  count: number;
  size?: number;
  n_vertices?: number;
  positions?: Uint8Array;
  radii?: Uint8Array;
  colors?: Uint8Array;
  starts?: Uint8Array;
  ends?: Uint8Array;
  normals?: Uint8Array;
  indices?: Uint8Array;
}

export interface AtomInfo {
  elements: string[];
  names: string[];
  resns: string[];
  resis: number[];
  chains: string[];
}

export interface Residue {
  chain: string;
  resi: number;
  resn: string;
  code: string;
}

export interface RawObject {
  name: string;
  visible: boolean;
  n_atoms: number;
  center: [number, number, number];
  bounding_radius: number;
  active_reps: string[];
  n_states: number;
  current_state: number;
  groups: RawGroup[];
  pick_positions: Uint8Array;
  atoms: AtomInfo;
  residues: Residue[];
}

export interface Label {
  text: string;
  pos: [number, number, number];
}

export interface SceneMessage {
  type: "scene";
  settings: { bg_color?: string };
  selections: string[];
  center: [number, number, number];
  bounding_radius: number;
  n_states: number;
  current_state: number;
  objects: RawObject[];
  measurement_lines: { count: number; positions: Uint8Array } | null;
  labels: Label[];
  selection_points: Uint8Array | null;
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
  | { primitive: "points"; count: number; positions: Float32Array; colors: Float32Array; size: number }
  | { primitive: "mesh"; count: number; positions: Float32Array; normals: Float32Array; colors: Float32Array; indices: Uint32Array };

export interface DecodedObject {
  name: string;
  visible: boolean;
  nAtoms: number;
  center: [number, number, number];
  boundingRadius: number;
  activeReps: string[];
  groups: DecodedGroup[];
  pickPositions: Float32Array;
  atoms: AtomInfo;
  residues: Residue[];
}

export interface DecodedScene {
  settings: { bg_color?: string };
  selections: string[];
  center: [number, number, number];
  boundingRadius: number;
  nStates: number;
  currentState: number;
  objects: DecodedObject[];
  measurementLines: Float32Array | null;
  labels: Label[];
  selectionPoints: Float32Array | null;
}
