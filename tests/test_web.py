"""Tests for the FastAPI web bridge, driven with an in-memory upstream client.

The bridge's ``IndiClient`` is wired to a fake indiserver (the ``read``/``write``
pattern from ``tests/test_client.py``), and the app is exercised through FastAPI's
``TestClient`` (HTTP + WebSocket). No real ``indiserver`` is involved.
"""

from __future__ import annotations

import asyncio
import json
import threading

from fastapi.testclient import TestClient

from indi_nexus.client import IndiClient
from indi_nexus.protocol import (
    DefVector,
    IPState,
    Number,
    NumberVector,
    SetVector,
    to_xml,
)
from indi_nexus.web import create_app


class _Server:
    """A fake indiserver: a thread-safe inbound queue and captured output."""

    def __init__(self) -> None:
        """Create the inbound queue and output buffer."""
        self._inbox: asyncio.Queue[bytes] = asyncio.Queue()
        self.written: list[bytes] = []

    def feed(self, msg: object) -> None:
        """Queue a message model as inbound bytes for the client."""
        self._inbox.put_nowait(to_xml(msg))  # type: ignore[arg-type]

    async def read(self) -> bytes:
        """Return the next queued inbound chunk."""
        return await self._inbox.get()

    async def write(self, data: bytes) -> None:
        """Capture outbound bytes from the client."""
        self.written.append(data)

    def connect(self):
        """Return a connect factory yielding this server's read/write pair."""

        async def _connect() -> tuple[object, object]:
            return self.read, self.write

        return _connect


def _numvec(value: float = 1.0, state: IPState = IPState.IDLE) -> NumberVector:
    """Build a one-element CCD EXPOSURE number vector."""
    return NumberVector(
        device="CCD",
        name="EXPOSURE",
        group="Main",
        state=state,
        elements=[Number(name="secs", format="%.2f", value=value)],
    )


def _app_and_server() -> tuple[object, _Server]:
    """Build a web app whose client is wired to a fresh fake server."""
    server = _Server()
    client = IndiClient(connect=server.connect(), reconnect_delay=0.0)
    return create_app(client=client), server


def test_health_reports_connection():
    """/health returns ok and reflects the upstream connection state."""
    app, _ = _app_and_server()
    with TestClient(app) as tc:
        body = tc.get("/health").json()
        assert body["status"] == "ok"
        assert body["connected"] is True


def test_rest_snapshot_reflects_cache():
    """The REST endpoints expose devices and properties after a def arrives."""
    app, server = _app_and_server()
    with TestClient(app) as tc:
        server.feed(DefVector(vector=_numvec(1.5, IPState.OK)))
        _wait_until(lambda: tc.get("/api/devices").json() == ["CCD"])

        assert tc.get("/api/devices").json() == ["CCD"]
        props = tc.get("/api/devices/CCD").json()
        assert "EXPOSURE" in props
        assert props["EXPOSURE"]["elements"][0]["value"] == 1.5

        one = tc.get("/api/devices/CCD/EXPOSURE").json()
        assert one["name"] == "EXPOSURE"
        assert tc.get("/api/devices/Nope").status_code == 404
        assert tc.get("/api/devices/CCD/Nope").status_code == 404


def test_index_serves_debug_page():
    """GET / serves the self-contained debug inspector page."""
    app, _ = _app_and_server()
    with TestClient(app) as tc:
        resp = tc.get("/")
        assert resp.status_code == 200
        assert "INDINexus" in resp.text
        assert "websocket" in resp.text.lower()


def test_ws_sends_snapshot_and_live_updates():
    """A WS client gets the current snapshot then subsequent live updates."""
    app, server = _app_and_server()
    with TestClient(app) as tc:
        server.feed(DefVector(vector=_numvec(1.0, IPState.OK)))
        _wait_until(lambda: tc.get("/api/devices").json() == ["CCD"])

        with tc.websocket_connect("/ws") as ws:
            snapshot = _drain_until_tag(ws, "def")
            assert snapshot["vector"]["name"] == "EXPOSURE"

            # A later upstream set is pushed live to the socket.
            server.feed(SetVector(vector=_numvec(2.5, IPState.OK)))
            update = _drain_until_tag(ws, "set")
            assert update["vector"]["elements"][0]["value"] == 2.5


def test_ws_forwards_browser_writes_upstream():
    """A new* frame sent by the browser reaches the upstream server."""
    app, server = _app_and_server()
    with TestClient(app) as tc:
        with tc.websocket_connect("/ws") as ws:
            ws.send_text(
                json.dumps(
                    {
                        "tag": "new",
                        "vector": {
                            "kind": "number",
                            "device": "CCD",
                            "name": "EXPOSURE",
                            "elements": [{"kind": "number", "name": "secs", "value": 3.0}],
                        },
                    }
                )
            )
            _wait_until(lambda: any(b"newNumberVector" in w for w in server.written))
        joined = b"".join(server.written)
        assert b"newNumberVector" in joined
        assert b"3" in joined


def _wait_until(pred, timeout: float = 2.0) -> None:
    """Block until ``pred()`` is true, pumping briefly (TestClient is threaded)."""
    deadline = threading.Event()
    waited = 0.0
    while waited < timeout:
        if pred():
            return
        deadline.wait(0.02)
        waited += 0.02
    raise AssertionError("condition not met within timeout")


def _drain_until_tag(ws, tag: str, limit: int = 20) -> dict:
    """Read frames from a WS until one with the given ``tag`` arrives."""
    for _ in range(limit):
        msg = json.loads(ws.receive_text())
        if msg.get("tag") == tag:
            return msg
    raise AssertionError(f"no {tag!r} frame received")
