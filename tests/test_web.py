"""Tests for the FastAPI web bridge, driven with an in-memory upstream client.

The bridge's ``IndiClient`` is wired to a fake indiserver (the ``read``/``write``
pattern from ``tests/test_client.py``), and the app is exercised through FastAPI's
``TestClient`` (HTTP + WebSocket). No real ``indiserver`` is involved.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import threading
from pathlib import Path

from fastapi.testclient import TestClient

import indi_nexus.web.app as app_module
from indi_nexus.client import IndiClient
from indi_nexus.protocol import (
    DefVector,
    DelProperty,
    IPState,
    Message,
    Number,
    NumberVector,
    SetVector,
    to_xml,
)
from indi_nexus.web import create_app
from indi_nexus.web.bridge import Bridge


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
        """Return a connect factory yielding this server's read/write/close trio."""

        async def _close() -> None:
            """Nothing to release for the in-memory transport."""

        async def _connect() -> tuple[object, object, object]:
            return self.read, self.write, _close

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
        assert tc.get("/health").json()["status"] == "ok"
        # Startup no longer blocks on the upstream, so connect lands just after.
        _wait_until(lambda: tc.get("/health").json()["connected"] is True)


async def test_bridge_start_does_not_wait_for_upstream():
    """``Bridge.start`` returns while indiserver is unreachable, and keeps trying."""
    attempts = 0

    async def _refuse() -> tuple[object, object, object]:
        """Fail every connection attempt, as a down indiserver would."""
        nonlocal attempts
        attempts += 1
        raise OSError("connection refused")

    client = IndiClient(connect=_refuse, reconnect_delay=0.01)
    bridge = Bridge(client)
    try:
        # Without this the whole web app hangs in startup whenever indiserver is
        # down, which is the state a first-time `indi-nexus serve` starts in.
        async with asyncio.timeout(2):
            await bridge.start()
        assert client.connected is False
        await asyncio.sleep(0.05)
        assert attempts > 1, "the client should keep retrying in the background"
    finally:
        await bridge.aclose()


def test_app_serves_while_upstream_is_down():
    """The app starts and answers requests with no indiserver to talk to."""

    async def _refuse() -> tuple[object, object, object]:
        """Fail every connection attempt, as a down indiserver would."""
        raise OSError("connection refused")

    app = create_app(client=IndiClient(connect=_refuse, reconnect_delay=0.05))
    with TestClient(app) as tc:
        body = tc.get("/health").json()
        assert body["status"] == "ok"
        assert body["connected"] is False
        assert tc.get("/api/devices").json() == []
        assert tc.get("/").status_code == 200


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


def test_debug_page_served():
    """GET /debug serves the self-contained debug inspector page."""
    app, _ = _app_and_server()
    with TestClient(app) as tc:
        resp = tc.get("/debug")
        assert resp.status_code == 200
        assert "INDINexus" in resp.text
        assert "websocket" in resp.text.lower()


def test_index_serves_a_page():
    """GET / serves an HTML page (the built panel if present, else the debug page)."""
    app, _ = _app_and_server()
    with TestClient(app) as tc:
        resp = tc.get("/")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")


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


def test_index_falls_back_to_debug_page_without_panel(monkeypatch):
    """GET / serves the debug page when the built panel is absent."""
    monkeypatch.setattr(app_module, "_PANEL", Path("/nonexistent/panel"))
    app, _ = _app_and_server()
    with TestClient(app) as tc:
        resp = tc.get("/")
        assert resp.status_code == 200
        assert "INDINexus" in resp.text


def test_bridge_exposes_its_client():
    """The bridge's client property returns the wrapped upstream client."""
    server = _Server()
    client = IndiClient(connect=server.connect())
    assert Bridge(client).client is client


def test_malformed_ws_frame_is_dropped():
    """A malformed browser frame is dropped without closing the socket."""
    app, server = _app_and_server()
    with TestClient(app) as tc:
        with tc.websocket_connect("/ws") as ws:
            ws.send_text("{not json")
            # The socket stays open: a valid frame sent next still goes upstream.
            ws.send_text(json.dumps({"tag": "getProperties", "device": "CCD"}))
            _wait_until(lambda: any(b"getProperties" in w for w in server.written))
        assert not any(b"not json" in w for w in server.written)


def test_del_property_is_broadcast_to_sockets():
    """An upstream delProperty reaches connected sockets as a del frame."""
    app, server = _app_and_server()
    with TestClient(app) as tc:
        server.feed(DefVector(vector=_numvec(1.0)))
        _wait_until(lambda: tc.get("/api/devices").json() == ["CCD"])

        with tc.websocket_connect("/ws") as ws:
            _drain_until_tag(ws, "def")
            server.feed(DelProperty(device="CCD", name="EXPOSURE"))
            frame = _drain_until_tag(ws, "delProperty")
            assert frame["device"] == "CCD"
            assert frame["name"] == "EXPOSURE"


def test_a_device_that_retracted_everything_is_still_listed_and_empty():
    """A device with no properties left answers with ``{}``, not a 404.

    ``/api/devices`` and ``/api/devices/{device}`` have to agree: the device is
    still there, it just publishes nothing right now, which is where a driver
    that defines on connect sits while disconnected. A genuinely unknown device
    is still a 404.
    """
    app, server = _app_and_server()
    with TestClient(app) as tc:
        server.feed(DefVector(vector=_numvec(1.0)))
        _wait_until(lambda: tc.get("/api/devices").json() == ["CCD"])

        server.feed(DelProperty(device="CCD", name="EXPOSURE"))
        _wait_until(lambda: tc.get("/api/devices/CCD").json() == {})

        assert tc.get("/api/devices").json() == ["CCD"]
        assert tc.get("/api/devices/CCD").status_code == 200
        assert tc.get("/api/devices/Nope").status_code == 404


def test_a_deletions_message_reaches_the_browser():
    """The explanation on a delProperty survives the trip to a browser frame.

    The bridge rebuilds the del frame from its cache event rather than
    forwarding the message, so the text a driver wrote ("only while connected")
    was being dropped one hop short of the UI that would show it. It is the only
    account the browser gets of why a property went away.
    """
    app, server = _app_and_server()
    with TestClient(app) as tc:
        server.feed(DefVector(vector=_numvec(1.0)))
        _wait_until(lambda: tc.get("/api/devices").json() == ["CCD"])

        with tc.websocket_connect("/ws") as ws:
            _drain_until_tag(ws, "def")
            stamped = dt.datetime(2026, 8, 14, 12, 30, tzinfo=dt.UTC)
            server.feed(
                DelProperty(
                    device="CCD",
                    name="EXPOSURE",
                    timestamp=stamped,
                    message="only while connected",
                )
            )

            frame = _drain_until_tag(ws, "delProperty")
            assert frame["message"] == "only while connected"
            assert frame["timestamp"] is not None


def test_broadcast_drops_a_failing_sink():
    """A sink that raises is dropped; healthy sinks keep receiving frames."""

    async def scenario() -> None:
        server = _Server()
        bridge = Bridge(IndiClient(connect=server.connect()))
        good: list[str] = []
        bad_calls = 0

        async def good_sink(frame: str) -> None:
            """Record every delivered frame."""
            good.append(frame)

        async def bad_sink(frame: str) -> None:
            """Fail on every delivery."""
            nonlocal bad_calls
            bad_calls += 1
            raise RuntimeError("socket gone")

        bridge.add_sink(good_sink)
        bridge.add_sink(bad_sink)
        await bridge._broadcast("one")
        await bridge._broadcast("two")

        assert good == ["one", "two"]
        assert bad_calls == 1  # dropped after the first failure

    asyncio.run(scenario())


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


def test_snapshot_replays_recent_messages_to_new_browsers():
    """A browser connecting after an INDI message was sent still receives it.

    Messages are transient (not part of the property cache), so the bridge keeps
    a bounded history and replays it in the snapshot - otherwise a fresh page's
    log is always empty.
    """
    app, server = _app_and_server()
    with TestClient(app) as tc:
        # The message and a def arrive while no browser is connected. The def
        # doubles as a barrier: once REST shows the device, the (ordered)
        # message before it has been processed too.
        server.feed(Message(device="CCD", message="Demo device ready."))
        server.feed(DefVector(vector=_numvec()))
        _wait_until(lambda: "CCD" in tc.get("/api/devices").json())

        with tc.websocket_connect("/ws") as ws:
            frame = _drain_until_tag(ws, "message")
            assert frame["message"] == "Demo device ready."
            assert frame["device"] == "CCD"
