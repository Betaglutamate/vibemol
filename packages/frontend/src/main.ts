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
});

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
