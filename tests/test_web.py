"""Tests for the FastAPI web bridge, driven with an in-memory upstream client.

The bridge's ``IndiClient`` is wired to a fake indiserver (the ``read``/``write``
pattern from ``tests/test_client.py``), and the app is exercised through FastAPI's
``TestClient`` (HTTP + WebSocket). No real ``indiserver`` is involved.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import json
import logging
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import indi_nexus.web.app as app_module
from indi_nexus.client import IndiClient
from indi_nexus.exceptions import SendQueueFull
from indi_nexus.protocol import (
    DefVector,
    DelProperty,
    IPState,
    Message,
    Number,
    NumberVector,
    SetVector,
    to_json,
    to_xml,
)
from indi_nexus.web import create_app
from indi_nexus.web.bridge import _MAX_BACKLOG, Bridge


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

    def disconnect(self) -> None:
        """End the current connection, as an indiserver going away would."""
        self._inbox.put_nowait(b"")

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


def _app_and_server(**kwargs) -> tuple[object, _Server]:
    """Build a web app whose client is wired to a fresh fake server."""
    server = _Server()
    client = IndiClient(connect=server.connect(), reconnect_delay=0.0)
    return create_app(client=client, **kwargs), server


def _wait_connected(tc: TestClient) -> None:
    """Block until the app reports a live upstream connection.

    A send with no connection raises rather than being queued for later, so any
    test that writes through the bridge has to wait for the link first. Without
    this barrier the write races the first connection attempt.
    """
    _wait_until(lambda: tc.get("/health").json()["connected"] is True)


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
        _wait_connected(tc)
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
        # The second frame is a real getProperties, so the link has to be up.
        _wait_connected(tc)
        with tc.websocket_connect("/ws") as ws:
            ws.send_text("{not json")
            # The socket stays open: a valid frame sent next still goes upstream.
            ws.send_text(json.dumps({"tag": "getProperties", "device": "CCD"}))
            _wait_until(lambda: any(b"getProperties" in w for w in server.written))
        assert not any(b"not json" in w for w in server.written)


def test_a_control_frame_echoed_back_does_not_go_upstream():
    """A browser cannot get a bridge control frame forwarded to indiserver.

    ``{"event": ...}`` frames are the bridge's own, not INDI, and they used to
    parse as a ``getProperties``: the message union was undiscriminated,
    ``GetProperties`` defaults every field and the models ignore extras, so any
    object with nothing recognisable in it validated as one. A browser echoing
    what it received sent an upstream enumerate.
    """
    app, server = _app_and_server()
    with TestClient(app) as tc:
        _wait_connected(tc)
        # The client's own handshake getProperties is already on the wire, so
        # count rather than look: nothing new may join it.
        before = sum(b"getProperties" in written for written in server.written)
        with tc.websocket_connect("/ws") as ws:
            ws.send_text(Bridge.connection_frame(True))
            assert _drain_until_event(ws, "error")["code"] == "malformed"
        assert sum(b"getProperties" in written for written in server.written) == before


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


class _WedgedSink:
    """A browser whose socket accepts nothing until the test releases it.

    Stands in for the failure that matters: a browser under TCP back-pressure,
    where ``websocket.send_text`` simply does not return.
    """

    def __init__(self) -> None:
        """Create the gate and the delivery log."""
        self.gate = asyncio.Event()
        self.delivered: list[str] = []

    async def __call__(self, frame: str) -> None:
        """Block until released, then record the frame."""
        await self.gate.wait()
        self.delivered.append(frame)


def _bridge() -> tuple[Bridge, _Server]:
    """Build a bridge over a fresh fake indiserver, not started."""
    server = _Server()
    return Bridge(IndiClient(connect=server.connect(), reconnect_delay=0.0)), server


async def _until(predicate, seconds: float = 2.0) -> None:
    """Yield to the loop until ``predicate()`` holds, or fail the test."""
    async with asyncio.timeout(seconds):
        # noqa is not a lapse: the condition is another task's progress, which
        # has no event to wait on, so yielding the loop is exactly the wait.
        while not predicate():  # noqa: ASYNC110
            await asyncio.sleep(0)


async def test_broadcast_drops_a_failing_sink():
    """A sink that raises is dropped; healthy sinks keep receiving frames."""
    bridge, _ = _bridge()
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

    healthy = bridge.attach(good_sink)
    broken = bridge.attach(bad_sink)
    try:
        bridge._broadcast("one")
        bridge._broadcast("two")
        await _until(lambda: good[-2:] == ["one", "two"])

        # The failure is noticed by the broken browser's own pump, so it costs
        # exactly one delivery and nothing else stops.
        assert bad_calls == 1
        await _until(lambda: broken.closed.is_set())
        assert bridge.sink_count() == 1

        # `closed` is set by every way out of the pump, including this one, so it
        # cannot be the route's reason for a close code. Only the backlog drop
        # earns 1013; a write failure racing an ordinary disconnect must not tell
        # the browser to try again later.
        assert not broken.dropped_for_backlog
        assert not healthy.dropped_for_backlog
    finally:
        await healthy.aclose()
        await broken.aclose()


async def test_a_wedged_browser_does_not_stall_the_upstream_reader():
    """A browser that accepts nothing must not hold up the upstream stream.

    This is the defect: broadcasting used to ``await`` each sink inline on the
    client's task, so one browser under back-pressure stopped the reader for
    every browser and eventually stalled the parser on a healthy connection.
    """
    bridge, server = _bridge()
    client = bridge.client
    wedged = _WedgedSink()
    await bridge.start()
    sub = bridge.attach(wedged)
    try:
        server.feed(DefVector(vector=_numvec(0.0)))
        for value in range(1, 51):
            server.feed(SetVector(vector=_numvec(float(value))))

        # The store keeps advancing while the browser has taken nothing at all.
        await _until(
            lambda: (
                (vec := client.get("CCD", "EXPOSURE")) is not None and vec.elements[0].value == 50.0
            )
        )
        assert wedged.delivered == []
    finally:
        wedged.gate.set()
        await sub.aclose()
        await bridge.aclose()


async def test_queued_sets_for_one_property_coalesce():
    """A queued ``set`` is replaced by the next one for the same property.

    INDI ``set`` is last-writer-wins state, so a fast instrument spamming one
    property costs one queue slot however fast it goes. Without this, a browser
    dropped for being slow is re-seeded in full and immediately overruns again.
    """
    bridge, _ = _bridge()
    wedged = _WedgedSink()
    sub = bridge.attach(wedged)
    try:
        for value in range(1000):
            bridge._broadcast(f"set-{value}", coalesce=("CCD", "EXPOSURE"))

        assert len(sub.queue) == 1
        assert sub.queue[0].frame == "set-999"
        assert bridge.sink_count() == 1
        assert bridge.dropped_slow_sinks == 0
    finally:
        wedged.gate.set()
        await sub.aclose()


async def test_a_def_after_a_queued_set_is_not_overtaken():
    """A ``set`` never folds into a slot sitting ahead of a ``def`` or ``del``.

    The correctness condition the coalescing turns on. Get it wrong and a
    property retracted and redefined arrives in the wrong order, leaving the
    browser's store quietly wrong with nothing logged anywhere.
    """
    bridge, _ = _bridge()
    key = ("CCD", "EXPOSURE")
    wedged = _WedgedSink()
    sub = bridge.attach(wedged)
    try:
        bridge._broadcast("set-1", coalesce=key)
        bridge._broadcast("del", invalidate=key)
        bridge._broadcast("def", invalidate=key)
        bridge._broadcast("set-2", coalesce=key)

        assert [slot.frame for slot in sub.queue] == ["set-1", "del", "def", "set-2"]

        wedged.gate.set()
        await _until(lambda: wedged.delivered[-4:] == ["set-1", "del", "def", "set-2"])
    finally:
        wedged.gate.set()
        await sub.aclose()


async def test_a_whole_device_del_invalidates_every_slot_for_that_device():
    """An unnamed ``delProperty`` invalidates the whole device, and only it.

    A whole-device deletion names no property - it takes all of them - so every
    queued ``set`` for that device has to stop being coalescible at once, or a
    later ``set`` folds into a slot sitting ahead of the retraction and overtakes
    it. Every other coalescing test uses a concrete ``(device, name)``, so the
    ``name is None`` branch would break silently without this.
    """
    bridge, _ = _bridge()
    wedged = _WedgedSink()
    sub = bridge.attach(wedged)
    try:
        for name in ("EXPOSURE", "TEMP", "GAIN"):
            bridge._broadcast(f"set-{name}-1", coalesce=("CCD", name))
        bridge._broadcast("set-Mount-1", coalesce=("Mount", "TRACK"))

        bridge._broadcast("del-CCD", invalidate=("CCD", None))

        # Every CCD slot is now un-foldable: a later set appends after the
        # deletion instead of rewriting a frame that precedes it.
        for name in ("EXPOSURE", "TEMP", "GAIN"):
            bridge._broadcast(f"set-{name}-2", coalesce=("CCD", name))
        # The other device was not in the deletion, so its slot still folds.
        bridge._broadcast("set-Mount-2", coalesce=("Mount", "TRACK"))

        assert [slot.frame for slot in sub.queue] == [
            "set-EXPOSURE-1",
            "set-TEMP-1",
            "set-GAIN-1",
            "set-Mount-2",
            "del-CCD",
            "set-EXPOSURE-2",
            "set-TEMP-2",
            "set-GAIN-2",
        ]
    finally:
        wedged.gate.set()
        await sub.aclose()


async def test_a_browser_that_falls_far_behind_is_dropped(caplog):
    """Past the backlog a browser is dropped, counted, logged - and alone."""
    bridge, _ = _bridge()
    wedged = _WedgedSink()
    healthy: list[str] = []

    async def healthy_sink(frame: str) -> None:
        """Take every frame immediately."""
        healthy.append(frame)

    sub = bridge.attach(wedged)
    other = bridge.attach(healthy_sink)
    try:
        with caplog.at_level(logging.WARNING, logger="indi_nexus.web.bridge"):
            for index in range(_MAX_BACKLOG + 1):
                bridge._broadcast(f"f{index}", coalesce=("CCD", f"P{index}"))
                # Give the pumps a turn, so the browser keeping up is measured
                # against a browser that is genuinely wedged rather than against
                # a loop that never let either of them run.
                await asyncio.sleep(0)

            await _until(lambda: sub.closed.is_set())

        assert bridge.dropped_slow_sinks == 1
        assert any("dropping browser sink" in record.message for record in caplog.records)
        assert bridge.sink_count() == 1
        # This, not `closed`, is what the route turns into a 1013 close code.
        assert sub.dropped_for_backlog
        await _until(lambda: healthy[-1] == f"f{_MAX_BACKLOG}")
        assert not other.closed.is_set()
    finally:
        wedged.gate.set()
        await sub.aclose()
        await other.aclose()


async def test_the_seed_is_not_counted_against_the_backlog():
    """A large cache does not cost a new browser its backlog allowance.

    The bound measures how far behind a browser has fallen, not how much state
    the observatory has. Counting the seed made it a function of cache size and
    froze it at attach time.
    """
    bridge, _ = _bridge()
    store = bridge.client.store
    for index in range(_MAX_BACKLOG * 2):
        store.apply(
            DefVector(
                vector=NumberVector(
                    device="CCD",
                    name=f"P{index}",
                    elements=[Number(name="v", value=float(index))],
                )
            )
        )
    wedged = _WedgedSink()
    sub = bridge.attach(wedged)
    try:
        assert len(sub.seed_vectors) == _MAX_BACKLOG * 2
        for index in range(10):
            bridge._broadcast(f"f{index}")

        assert bridge.dropped_slow_sinks == 0
        assert not sub.closed.is_set()
        assert len(sub.queue) == 10
    finally:
        wedged.gate.set()
        await sub.aclose()


async def test_no_event_is_lost_between_the_snapshot_and_registration():
    """Seeding and registering are one uninterruptible step.

    The route used to send the snapshot and only then register the socket, so
    anything the upstream published in between was lost for that browser for
    good. ``attach`` being synchronous is what closes it, which is why the
    assertion on that is here and not left implicit.
    """
    assert not inspect.iscoroutinefunction(Bridge.attach)

    bridge, _ = _bridge()
    store = bridge.client.store
    received: list[str] = []

    async def sink(frame: str) -> None:
        """Record every delivered frame."""
        received.append(frame)

    async def produce() -> None:
        """Define one property per loop turn, exactly as the reader would."""
        for index in range(1, 201):
            vector = NumberVector(
                device="CCD", name=f"P{index}", elements=[Number(name="v", value=float(index))]
            )
            store.apply(DefVector(vector=vector))
            bridge._broadcast(to_json(DefVector(vector=vector)), invalidate=("CCD", f"P{index}"))
            await asyncio.sleep(0)

    producing = asyncio.create_task(produce())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    sub = bridge.attach(sink)
    try:
        await producing
        await _until(lambda: len(received) >= 201)

        defs = [json.loads(frame) for frame in received if '"tag":"def"' in frame]
        names = [frame["vector"]["name"] for frame in defs]
        assert names == [f"P{index}" for index in range(1, 201)]
    finally:
        await sub.aclose()


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


def _drain_until_event(ws, event: str, limit: int = 20) -> dict:
    """Read frames from a WS until a control frame with ``event`` arrives."""
    for _ in range(limit):
        frame = json.loads(ws.receive_text())
        if frame.get("event") == event:
            return frame
    raise AssertionError(f"no {event!r} control frame received")


def test_a_write_while_the_upstream_is_down_is_reported_not_dropped_silently():
    """A write with no upstream is refused out loud, and the socket survives.

    Sends are no longer queued for a connection that may be an hour away, so a
    browser that hears nothing back would have every reason to believe its slew
    was accepted. It is told instead, and it stays connected.
    """

    async def _refuse() -> tuple[object, object, object]:
        """Fail every connection attempt, as a down indiserver would."""
        raise OSError("connection refused")

    app = create_app(client=IndiClient(connect=_refuse, reconnect_delay=0.05))
    with TestClient(app) as tc, tc.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"tag": "getProperties", "device": "CCD"}))
        frame = _drain_until_event(ws, "error")
        assert frame["code"] == "not_connected"
        assert frame["tag"] == "getProperties"

        # Still open: a second frame is answered the same way.
        ws.send_text(json.dumps({"tag": "getProperties", "device": "CCD"}))
        assert _drain_until_event(ws, "error")["code"] == "not_connected"


def test_a_full_upstream_outbox_is_reported(monkeypatch):
    """An upstream outbox that has stopped draining is reported to the browser."""
    app, _ = _app_and_server()
    with TestClient(app) as tc:
        _wait_connected(tc)

        async def _full(msg: object) -> None:
            """Refuse every send, as a wedged writer would."""
            raise SendQueueFull("outbox is full")

        monkeypatch.setattr(app.state.client, "send", _full)
        with tc.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"tag": "getProperties", "device": "CCD"}))
            assert _drain_until_event(ws, "error")["code"] == "upstream_busy"


def test_a_browser_may_not_send_a_def_frame():
    """A browser cannot claim to be a device; a legitimate frame still gets through."""
    app, server = _app_and_server()
    with TestClient(app) as tc:
        _wait_connected(tc)
        with tc.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"tag": "def", "vector": _numvec().model_dump(mode="json")}))
            frame = _drain_until_event(ws, "error")
            assert frame["code"] == "not_permitted"
            assert frame["tag"] == "def"

            ws.send_text(json.dumps({"tag": "getProperties", "device": "CCD"}))
            _wait_until(lambda: any(b"getProperties" in w and b"CCD" in w for w in server.written))
        assert not any(b"defNumberVector" in w for w in server.written)


def test_enable_blob_from_a_browser_is_replayed_on_reconnect():
    """A browser's BLOB policy is recorded upstream, so it survives a reconnect.

    Relaying it with a plain ``send`` bypassed the client's policy registry, so
    the browser's BLOBs stopped arriving the first time indiserver restarted and
    nothing said why.
    """
    app, server = _app_and_server()

    def _sent(count: int) -> bool:
        """Poll /health - which pumps the app's loop - and count BLOB policies."""
        tc.get("/health")
        return sum(b"enableBLOB" in written for written in server.written) >= count

    with TestClient(app) as tc:
        _wait_connected(tc)
        with tc.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"tag": "enableBLOB", "device": "CCD", "policy": "Also"}))
            _wait_until(lambda: _sent(1))

            # The upstream goes away and comes back; the policy is part of the
            # handshake now, so it is replayed without the browser asking again.
            server.disconnect()
            _wait_until(lambda: _sent(2))


def test_ws_rejects_a_foreign_origin():
    """A page on another origin cannot open the write surface.

    Browsers apply neither the same-origin policy nor CORS to WebSockets, so
    without this check any page an operator visits can drive the instrument.
    """
    app, _ = _app_and_server()
    with (
        TestClient(app) as tc,
        pytest.raises(WebSocketDisconnect),
        tc.websocket_connect("/ws", headers={"origin": "http://evil.example"}) as ws,
    ):
        ws.receive_text()


def test_ws_accepts_the_same_origin():
    """The panel the bridge itself serves connects with no configuration."""
    app, _ = _app_and_server()
    with (
        TestClient(app) as tc,
        tc.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws,
    ):
        assert json.loads(ws.receive_text())["event"] == "connection"


def test_ws_accepts_a_missing_origin():
    """A peer that is not a browser sends no Origin, and is not a browser threat.

    Node consumers of ``@indi-nexus/client``, curl, the interop suite and
    Starlette's own TestClient all send none; a browser always sends one and an
    attacker outside a browser forges whatever it likes.
    """
    app, _ = _app_and_server()
    with TestClient(app) as tc, tc.websocket_connect("/ws") as ws:
        assert json.loads(ws.receive_text())["event"] == "connection"


def test_ws_accepts_a_configured_origin():
    """A front end on another port connects once its origin is named."""
    app, _ = _app_and_server(allowed_origins=["http://localhost:5173"])
    with (
        TestClient(app) as tc,
        tc.websocket_connect("/ws", headers={"origin": "http://localhost:5173"}) as ws,
    ):
        assert json.loads(ws.receive_text())["event"] == "connection"


def test_ws_and_api_require_a_configured_token():
    """With a token configured, /ws and /api both demand it."""
    app, _ = _app_and_server(token="s3cret")
    with TestClient(app) as tc:
        assert tc.get("/api/devices").status_code == 403
        assert tc.get("/api/devices", headers={"Authorization": "Bearer s3cret"}).status_code == 200
        assert tc.get("/api/devices", headers={"Authorization": "Bearer wrong"}).status_code == 403

        with pytest.raises(WebSocketDisconnect), tc.websocket_connect("/ws") as ws:
            ws.receive_text()
        with tc.websocket_connect("/ws?token=s3cret") as ws:
            assert json.loads(ws.receive_text())["event"] == "connection"


def test_api_does_not_accept_a_query_token():
    """``?token=`` is a WebSocket affordance and stops there.

    A browser cannot set a header on a WebSocket handshake, which is the whole
    reason the query parameter exists; an HTTP caller on ``/api`` always can, and
    a token in a URL is written into reverse-proxy and CDN access logs, `Referer`
    headers and browser history.
    """
    app, _ = _app_and_server(token="s3cret")
    with TestClient(app) as tc:
        assert tc.get("/api/devices", params={"token": "s3cret"}).status_code == 403
        assert tc.get("/api/devices/CCD", params={"token": "s3cret"}).status_code == 403
        assert tc.get("/api/devices/CCD/EXPOSURE", params={"token": "s3cret"}).status_code == 403


def test_health_is_reachable_without_a_token():
    """The container's HEALTHCHECK calls /health with no credentials."""
    app, _ = _app_and_server(token="s3cret")
    with TestClient(app) as tc:
        body = tc.get("/health").json()
        assert body["status"] == "ok"
        assert body["dropped_slow_sinks"] == 0
