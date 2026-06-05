import { decode, encode } from "@msgpack/msgpack";

import type { Viewer } from "../renderer/viewer";
import { decodeScene } from "../protocol/decode";
import type { ClientMessage, ServerMessage } from "../protocol/types";
import { appStore } from "./store";

// Detect a structure file format from its filename extension (for drag & drop).
const EXT_FORMAT: Record<string, string> = {
  pdb: "pdb", ent: "pdb", cif: "mmcif", mmcif: "mmcif",
  xyz: "xyz", sdf: "sdf", mol: "sdf", mol2: "mol2",
};

export function formatFromFilename(name: string): string | null {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return EXT_FORMAT[ext] ?? null;
}

/** WebSocket sync client: sends commands, applies scene/camera/log pushes. */
export class SceneClient {
  private socket: WebSocket | null = null;

  constructor(
    private readonly url: string,
    private readonly viewer: Viewer,
  ) {}

  connect(): void {
    const { setStatus, setScene, appendLog } = appStore.getState();
    setStatus("connecting");

    const socket = new WebSocket(this.url);
    socket.binaryType = "arraybuffer";
    this.socket = socket;

    socket.onopen = () => setStatus("open"); // start empty; the user loads/fetches a structure

    socket.onmessage = (ev: MessageEvent<ArrayBuffer>) => {
      const msg = decode(new Uint8Array(ev.data)) as ServerMessage;
      if (msg.type === "scene") {
        const scene = decodeScene(msg);
        setScene(scene);
        this.viewer.setScene(scene);
      } else if (msg.type === "camera") {
        this.viewer.frameTo(msg.center, msg.radius);
      } else if (msg.type === "log") {
        appendLog({ level: msg.level, message: msg.message });
      } else if (msg.type === "download") {
        triggerDownload(msg.filename, msg.mime, msg.data);
      }
    };

    socket.onerror = () => setStatus("error");
    socket.onclose = () => setStatus("closed");
  }

  private send(msg: ClientMessage): void {
    this.socket?.send(encode(msg));
  }

  runCommand(text: string): void {
    if (text.trim()) {
      appStore.getState().appendLog({ level: "info", message: `> ${text}` });
      this.send({ type: "command", text });
    }
  }

  loadDemo(): void {
    this.send({ type: "load", source: "demo" });
  }

  loadFile(name: string, format: string, text: string): void {
    this.send({ type: "load_data", name, format, text });
  }

  saveSession(): void {
    this.send({ type: "save_session" });
  }

  openSession(data: Uint8Array): void {
    this.send({ type: "load_session", data });
  }

  exportStructure(object?: string): void {
    this.send({ type: "export_structure", object });
  }
}

/** Turn a server `download` message into a browser file download. */
function triggerDownload(filename: string, mime: string, data: Uint8Array | string): void {
  // Copy bytes into a fresh ArrayBuffer so the Blob part is well-typed.
  const part: BlobPart = typeof data === "string" ? data : new Uint8Array(data).slice().buffer;
  const blob = new Blob([part], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
