import { SceneClient, formatFromFilename } from "./scene/client";
import { appStore } from "./scene/store";
import { UI } from "./ui/ui";
import { Viewer } from "./renderer/viewer";

const appEl = document.getElementById("app")!;
const viewer = new Viewer(appEl);

const proto = location.protocol === "https:" ? "wss" : "ws";
const client = new SceneClient(`${proto}://${location.host}/ws`, viewer);

const ui = new UI({
  onCommand: (text) => client.runCommand(text),
  onFile: async (file) => {
    const format = formatFromFilename(file.name);
    if (!format) {
      appStore.getState().appendLog({ level: "error", message: `unsupported file type: ${file.name}` });
      return;
    }
    client.loadFile(file.name.replace(/\.[^.]+$/, ""), format, await file.text());
  },
  onDemo: () => client.loadDemo(),
  onResetView: () => viewer.resetView(),
  onQuality: (on) => viewer.setQuality(on),
  onSpin: (on) => viewer.setSpin(on),
  onProjection: (ortho) => viewer.setProjection(ortho),
  onState: (n) => client.runCommand(`set_state ${n}`),
  onSaveSession: () => client.saveSession(),
  onOpenSession: async (file) => client.openSession(new Uint8Array(await file.arrayBuffer())),
  onExportStructure: () => client.exportStructure(),
  onSmiles: (smiles, name) => client.loadFile(name, "smiles", smiles),
  onRunScript: (text) => client.runScript(text),
  onSnapshot: () => {
    const link = document.createElement("a");
    link.href = viewer.snapshot();
    link.download = "vibemol.png";
    link.click();
  },
});

// Click-to-pick: measure mode collects atoms; otherwise selects the whole residue
// (Shift = range in sequence, Cmd/Ctrl = add). Handled entirely in the UI.
viewer.onPick = (objectName, atomIndex, mods) => ui.handlePick(objectName, atomIndex, mods);

// Drive the UI from store changes; the viewer is updated directly by the client.
let lastScene = appStore.getState().scene;
let lastLog = appStore.getState().log;
let lastStatus = appStore.getState().status;
appStore.subscribe(() => {
  const s = appStore.getState();
  if (s.scene !== lastScene && s.scene) {
    ui.renderScene(s.scene);
    lastScene = s.scene;
  }
  if (s.log !== lastLog) {
    ui.renderLog(s.log);
    lastLog = s.log;
  }
  if (s.status !== lastStatus) {
    ui.setStatus(s.status);
    lastStatus = s.status;
  }
});

client.connect();
