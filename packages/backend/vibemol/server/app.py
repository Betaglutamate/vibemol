"""The FastAPI application: REST health, a WebSocket hub, and static SPA serving.

Phase 0 wires the walking skeleton: a client connects over WebSocket, asks to
load the bundled demo, and the server streams sphere geometry. The scene lives
server-side (here, a single in-process structure); later phases promote this to
a full per-session scene graph and a command interpreter.
"""

from __future__ import annotations

import importlib.resources as resources
from pathlib import Path

import msgpack
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..io.pdb import parse_pdb_text
from ..model.structure import Structure
from ..protocol.geometry import spheres_message
from ..protocol.messages import ErrorMessage

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def load_demo() -> Structure:
    """Load the bundled demo structure (benzene)."""
    text = resources.files("vibemol.data").joinpath("benzene.pdb").read_text()
    return parse_pdb_text(text, name="demo")


def create_app() -> FastAPI:
    app = FastAPI(title="VibeMol", version=__version__)

    @app.get("/api/health")
    def health() -> JSONResponse:
        return JSONResponse({"name": "vibemol", "version": __version__, "status": "ok"})

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        try:
            while True:
                raw = await socket.receive_bytes()
                msg = msgpack.unpackb(raw, raw=False)
                await _handle(socket, msg)
        except WebSocketDisconnect:
            return

    # Serve the built frontend at the root when present (production / `vibemol serve`).
    # During frontend dev you instead run Vite, which proxies /api and /ws here.
    if _STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="spa")

    return app


async def _handle(socket: WebSocket, msg: dict) -> None:
    """Dispatch a single client message."""
    msg_type = msg.get("type")
    if msg_type == "load":
        if msg.get("source", "demo") == "demo":
            structure = load_demo()
            await socket.send_bytes(msgpack.packb(spheres_message(structure)))
        else:
            err = ErrorMessage(message=f"source '{msg.get('source')}' arrives in Phase 1")
            await socket.send_bytes(msgpack.packb(err.model_dump()))
    else:
        err = ErrorMessage(message=f"unknown message type: {msg_type!r}")
        await socket.send_bytes(msgpack.packb(err.model_dump()))
