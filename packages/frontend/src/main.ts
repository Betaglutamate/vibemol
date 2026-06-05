import { SceneClient, formatFromFilename } from "./scene/client";
import { appStore } from "./scene/store";
import { UI } from "./ui/ui";
import { Viewer } from "./renderer/viewer";

const appEl = document.getElementById("app")!;
const viewer = new Viewer(appEl);

const proto = location.protocol === "https:" ? "wss" : "ws";
const client = new SceneClient(`${proto}://${location.host}/ws`, viewer);

// Click-to-pick: identify the atom and add it to the `sele` selection.
viewer.onPick = (objectName, atomIndex) => {
  const scene = appStore.getState().scene;
  const obj = scene?.objects.find((o) => o.name === objectName);
  if (obj) {
    const a = obj.atoms;
    const id = `/${objectName}/${a.chains[atomIndex]}/${a.resns[atomIndex]}\`${a.resis[atomIndex]}/${a.names[atomIndex]}`;
    appStore.getState().appendLog({ level: "info", message: `picked ${id}` });
  }
  client.runCommand(`select sele, index ${atomIndex + 1}`);
};

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
