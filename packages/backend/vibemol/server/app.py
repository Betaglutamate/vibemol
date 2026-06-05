"""The FastAPI application: REST health, a command-driven WebSocket session, and
static SPA serving.

Each WebSocket connection owns its own :class:`~vibemol.model.scene.Scene` (and
:class:`~vibemol.commands.Context`), so browser tabs are independent sessions.
The client sends commands and load requests; the server mutates the scene and
streams back the full scene, camera directives, and log lines.
"""

from __future__ import annotations

import importlib.resources as resources
from pathlib import Path
from typing import Any

import msgpack
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..commands import Context, dispatch, registered_commands
from ..io import load_text
from ..io.pdb import parse_pdb_text
from ..model.scene import Scene
from ..protocol.scene import scene_message

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def load_demo_into(ctx: Context) -> None:
    text = resources.files("vibemol.data").joinpath("benzene.pdb").read_text()
    ctx.add_structure(parse_pdb_text(text, name="demo"))


def create_app() -> FastAPI:
    app = FastAPI(title="VibeMol", version=__version__)

    @app.get("/api/health")
    def health() -> JSONResponse:
        return JSONResponse({"name": "vibemol", "version": __version__, "status": "ok"})

    @app.get("/api/commands")
    def commands() -> JSONResponse:
        return JSONResponse({"commands": registered_commands()})

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        ctx = Context(Scene())
        try:
            while True:
                msg = msgpack.unpackb(await socket.receive_bytes(), raw=False)
                await _handle(socket, ctx, msg)
        except WebSocketDisconnect:
            return

    if _STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="spa")

    return app


async def _send(socket: WebSocket, payload: dict[str, Any]) -> None:
    await socket.send_bytes(msgpack.packb(payload))


async def _log(socket: WebSocket, message: str, level: str = "info") -> None:
    await _send(socket, {"type": "log", "level": level, "message": message})


async def _handle(socket: WebSocket, ctx: Context, msg: dict) -> None:
    msg_type = msg.get("type")

    if msg_type == "load" and msg.get("source", "demo") == "demo":
        load_demo_into(ctx)
        await _send(socket, scene_message(ctx.scene))
        await _log(socket, "loaded demo (benzene)")

    elif msg_type == "load_data":
        # Drag-and-drop / upload: raw file text plus its format.
        try:
            structure = load_text(msg["text"], msg["format"], name=msg.get("name", "structure"))
            obj = ctx.add_structure(structure, msg.get("name"))
        except Exception as exc:  # parser/format errors are user-facing
            await _log(socket, f"load failed: {exc}", level="error")
            return
        await _send(socket, scene_message(ctx.scene))
        await _log(socket, f"loaded {obj.name} ({obj.structure.n_atoms} atoms)")

    elif msg_type == "command":
        try:
            result = dispatch(ctx, msg.get("text", ""))
        except Exception as exc:  # CommandError / SelectionError / ColorError / ValueError
            await _log(socket, str(exc), level="error")
            return
        if result.log:
            await _log(socket, result.log)
        if result.camera is not None:
            await _send(socket, {"type": "camera", **result.camera})
        if result.scene_changed or result.selections_changed:
            await _send(socket, scene_message(ctx.scene))

    else:
        await _log(socket, f"unknown message type: {msg_type!r}", level="error")
