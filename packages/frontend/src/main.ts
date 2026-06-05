import { SceneClient } from "./scene/client";
import { sceneStore } from "./scene/store";
import { Viewer } from "./renderer/viewer";

const appEl = document.getElementById("app")!;
const statusEl = document.getElementById("status")!;

const viewer = new Viewer(appEl);

// Render whatever geometry the server pushes; reflect connection state in the HUD.
sceneStore.subscribe((state) => {
  if (state.error) {
    statusEl.textContent = `error: ${state.error}`;
    return;
  }
  if (state.geometry) {
    const g = state.geometry;
    viewer.setSpheres(g);
    statusEl.textContent = `${g.object}: ${g.nAtoms} atoms — drag to orbit, scroll to zoom`;
  } else {
    statusEl.textContent = state.status;
  }
});

// Connect through same-origin /ws (Vite proxies it to the backend in dev).
const proto = location.protocol === "https:" ? "wss" : "ws";
const client = new SceneClient(`${proto}://${location.host}/ws`);
client.connect();
