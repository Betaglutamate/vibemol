"""End-to-end test of the WebSocket walking skeleton."""

from __future__ import annotations

import msgpack
from fastapi.testclient import TestClient

from vibemol.server.app import create_app


def test_health() -> None:
    client = TestClient(create_app())
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["name"] == "vibemol"


def test_ws_load_demo_streams_sphere_geometry() -> None:
    client = TestClient(create_app())
    with client.websocket_connect("/ws") as ws:
        ws.send_bytes(msgpack.packb({"type": "load", "source": "demo"}))
        msg = msgpack.unpackb(ws.receive_bytes(), raw=False)

    assert msg["type"] == "geometry"
    assert msg["representation"] == "spheres"
    assert msg["n_atoms"] == 12
    # positions are raw float32: 12 atoms * 3 coords * 4 bytes.
    assert len(msg["positions"]) == 12 * 3 * 4
    assert len(msg["radii"]) == 12 * 4
    assert len(msg["colors"]) == 12 * 3 * 4


def test_ws_unknown_type_returns_error() -> None:
    client = TestClient(create_app())
    with client.websocket_connect("/ws") as ws:
        ws.send_bytes(msgpack.packb({"type": "bogus"}))
        msg = msgpack.unpackb(ws.receive_bytes(), raw=False)
    assert msg["type"] == "error"
