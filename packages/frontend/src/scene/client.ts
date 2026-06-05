import { decode, encode } from "@msgpack/msgpack";

import { decodeSpheres } from "../protocol/decode";
import type { LoadCommand, ServerMessage } from "../protocol/types";
import { sceneStore } from "./store";

/** WebSocket sync client: sends commands, applies server scene/geometry pushes. */
export class SceneClient {
  private socket: WebSocket | null = null;

  constructor(private readonly url: string) {}

  connect(): void {
    const { setStatus, setGeometry, setError } = sceneStore.getState();
    setStatus("connecting");

    const socket = new WebSocket(this.url);
    socket.binaryType = "arraybuffer";
    this.socket = socket;

    socket.onopen = () => {
      setStatus("open");
      // Phase 0: immediately request the bundled demo structure.
      this.send({ type: "load", source: "demo" });
    };

    socket.onmessage = (ev: MessageEvent<ArrayBuffer>) => {
      const msg = decode(new Uint8Array(ev.data)) as ServerMessage;
      if (msg.type === "geometry") {
        setGeometry(decodeSpheres(msg));
      } else if (msg.type === "error") {
        setError(msg.message);
      }
    };

    socket.onerror = () => setError("WebSocket error");
    socket.onclose = () => setStatus("closed");
  }

  send(command: LoadCommand): void {
    this.socket?.send(encode(command));
  }
}
