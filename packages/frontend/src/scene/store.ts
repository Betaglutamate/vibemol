import { createStore } from "zustand/vanilla";

import type { SphereGeometry } from "../protocol/types";

export type ConnectionStatus = "connecting" | "open" | "closed" | "error";

// The frontend owns the *camera*; the backend owns the *scene*. This store holds
// only client-side view/connection state plus the latest geometry pushed by the
// server. In Phase 1 it grows into the object/selection list and settings.
export interface SceneState {
  status: ConnectionStatus;
  geometry: SphereGeometry | null;
  error: string | null;
  setStatus: (status: ConnectionStatus) => void;
  setGeometry: (geometry: SphereGeometry) => void;
  setError: (error: string) => void;
}

export const sceneStore = createStore<SceneState>((set) => ({
  status: "connecting",
  geometry: null,
  error: null,
  setStatus: (status) => set({ status }),
  setGeometry: (geometry) => set({ geometry, error: null }),
  setError: (error) => set({ error, status: "error" }),
}));
