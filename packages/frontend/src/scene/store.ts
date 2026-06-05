import { createStore } from "zustand/vanilla";

import type { DecodedScene } from "../protocol/types";

export type ConnectionStatus = "connecting" | "open" | "closed" | "error";

export interface LogLine {
  level: "info" | "error";
  message: string;
}

// The frontend owns the *camera*; the backend owns the *scene*. This store holds
// client-side connection state, the latest decoded scene, and the console log.
export interface AppState {
  status: ConnectionStatus;
  scene: DecodedScene | null;
  log: LogLine[];
  setStatus: (status: ConnectionStatus) => void;
  setScene: (scene: DecodedScene) => void;
  appendLog: (line: LogLine) => void;
}

export const appStore = createStore<AppState>((set) => ({
  status: "connecting",
  scene: null,
  log: [],
  setStatus: (status) => set({ status }),
  setScene: (scene) => set({ scene }),
  appendLog: (line) => set((s) => ({ log: [...s.log.slice(-199), line] })),
}));
