"""End-to-end tests of the command-driven WebSocket session."""

from __future__ import annotations

from typing import Any

import msgpack
from fastapi.testclient import TestClient

from vibemol.server.app import create_app


def _recv(ws: Any) -> dict:
    return msgpack.unpackb(ws.receive_bytes(), raw=False)


def _recv_until(ws: Any, msg_type: str) -> dict:
    """Read messages until one of the given type arrives."""
    for _ in range(10):
        msg = _recv(ws)
        if msg["type"] == msg_type:
            return msg
    raise AssertionError(f"no {msg_type!r} message received")


def _send(ws: Any, payload: dict) -> None:
    ws.send_bytes(msgpack.packb(payload))


def test_health_and_commands() -> None:
    client = TestClient(create_app())
    assert client.get("/api/health").json()["name"] == "vibemol"
    cmds = client.get("/api/commands").json()["commands"]
    assert "fetch" in cmds and "show" in cmds and "color" in cmds


def test_load_demo_streams_scene() -> None:
    client = TestClient(create_app())
    with client.websocket_connect("/ws") as ws:
        _send(ws, {"type": "load", "source": "demo"})
        scene = _recv_until(ws, "scene")

    assert len(scene["objects"]) == 1
    obj = scene["objects"][0]
    assert obj["name"] == "demo"
    assert obj["n_atoms"] == 12
    groups = {g["primitive"]: g for g in obj["groups"]}
    # Default representation is lines (one segment per bond: 12 bonds).
    assert groups["lines"]["count"] == 12


def test_command_changes_representation() -> None:
    client = TestClient(create_app())
    with client.websocket_connect("/ws") as ws:
        _send(ws, {"type": "load", "source": "demo"})
        _recv_until(ws, "scene")
        _send(ws, {"type": "command", "text": "as spheres"})
        scene = _recv_until(ws, "scene")

    groups = {g["primitive"]: g for g in scene["objects"][0]["groups"]}
    assert "spheres" in groups
    assert groups["spheres"]["count"] == 12
    assert "lines" not in groups  # `as` cleared the default lines


def test_zoom_emits_camera() -> None:
    client = TestClient(create_app())
    with client.websocket_connect("/ws") as ws:
        _send(ws, {"type": "load", "source": "demo"})
        _recv_until(ws, "scene")
        _send(ws, {"type": "command", "text": "zoom all"})
        cam = _recv_until(ws, "camera")
    assert cam["radius"] >= 1.0
    assert len(cam["center"]) == 3


def test_bad_command_returns_error_log() -> None:
    client = TestClient(create_app())
    with client.websocket_connect("/ws") as ws:
        _send(ws, {"type": "command", "text": "frobnicate"})
        log = _recv_until(ws, "log")
    assert log["level"] == "error"


def test_run_script_executes_chunk_and_streams_one_scene() -> None:
    client = TestClient(create_app())
    with client.websocket_connect("/ws") as ws:
        _send(ws, {"type": "load", "source": "demo"})
        _recv_until(ws, "scene")
        script = "# a script\nas spheres\ncolor red, elem C\nselect ring, elem C\n"
        _send(ws, {"type": "run_script", "text": script})
        # Collect everything until the trailing scene update.
        logs: list[str] = []
        scene = None
        for _ in range(20):
            m = _recv(ws)
            if m["type"] == "log":
                logs.append(m["message"])
            elif m["type"] == "scene":
                scene = m
                break

    assert scene is not None
    groups = {g["primitive"]: g for g in scene["objects"][0]["groups"]}
    assert "spheres" in groups  # `as spheres` applied
    assert "ring" in scene["selections"]  # `select` ran
    assert "> as spheres" in logs  # each command line is echoed
    assert any(line.startswith("# ") is False and ">" in line for line in logs)


def test_run_script_continues_past_errors() -> None:
    client = TestClient(create_app())
    with client.websocket_connect("/ws") as ws:
        _send(ws, {"type": "load", "source": "demo"})
        _recv_until(ws, "scene")
        _send(ws, {"type": "run_script", "text": "boguscmd\nas spheres\n"})
        errored = False
        scene = None
        for _ in range(20):
            m = _recv(ws)
            if m["type"] == "log" and m["level"] == "error":
                errored = True
            elif m["type"] == "scene":
                scene = m
                break
    assert errored and scene is not None  # bad line logged, good line still applied
    assert "spheres" in {g["primitive"] for g in scene["objects"][0]["groups"]}
