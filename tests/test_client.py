"""Tests for :class:`IndiClient`, driven over in-memory transports.

Each test wires the client to a controllable ``(read, write)`` pair (the same
pattern as ``tests/test_driver.py``): a queue-backed reader feeds scripted server
bytes, and a list captures what the client writes, which is parsed back with the
M1 codec to assert on the exact wire output.
"""

from __future__ import annotations

import asyncio
import logging

import indi_nexus.client.client as client_module
from indi_nexus.client import IndiClient
from indi_nexus.exceptions import NotConnectedError, SendQueueFull
from indi_nexus.logging_config import WIRE_LOGGER
from indi_nexus.protocol import (
    BLOBVector,
    DefVector,
    DelProperty,
    EnableBLOB,
    GetProperties,
    IPState,
    ISState,
    Message,
    NewVector,
    Number,
    NumberVector,
    SetVector,
    SwitchVector,
    TextVector,
    parse_indi,
    to_xml,
)
from indi_nexus.protocol import xml as xml_module


class _Server:
    """A fake indiserver end: scripted inbound bytes and captured output."""

    def __init__(self) -> None:
        """Create the inbound queue and the captured-output buffer."""
        self._inbox: asyncio.Queue[bytes] = asyncio.Queue()
        self.written: list[bytes] = []
        self.closed = 0

    def feed(self, msg: object) -> None:
        """Queue a message model (or raw bytes) as bytes the client will read."""
        data = msg if isinstance(msg, bytes) else to_xml(msg)  # type: ignore[arg-type]
        self._inbox.put_nowait(data)

    def eof(self) -> None:
        """Signal the connection has closed."""
        self._inbox.put_nowait(b"")

    async def read(self) -> bytes:
        """Return the next queued inbound chunk."""
        return await self._inbox.get()

    async def write(self, data: bytes) -> None:
        """Capture one outbound chunk from the client."""
        self.written.append(data)

    def sent(self) -> list[object]:
        """Parse everything the client has written into message models."""
        return parse_indi(b"".join(self.written))

    async def close(self) -> None:
        """Record that the client released the transport."""
        self.closed += 1

    def connect(self):
        """Return a connect factory yielding this server's read/write/close trio."""

        async def _connect() -> tuple[object, object, object]:
            return self.read, self.write, self.close

        return _connect


def _numvec(value: float = 1.0, state: IPState = IPState.IDLE) -> NumberVector:
    """Build a one-element CCD EXPOSURE number vector."""
    return NumberVector(
        device="CCD",
        name="EXPOSURE",
        state=state,
        elements=[Number(name="secs", format="%.2f", value=value)],
    )


async def _settle() -> None:
    """Yield control briefly so the client's background tasks can run."""
    for _ in range(5):
        await asyncio.sleep(0)


def test_sends_get_properties_on_connect():
    """The client enumerates the server on its first connect."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()):
            await _settle()
        assert any(isinstance(m, GetProperties) for m in server.sent())

    asyncio.run(scenario())


def test_inbound_def_and_set_populate_store():
    """Inbound def then set are cached with the merged value and state."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()) as client:
            server.feed(DefVector(vector=_numvec(1.0)))
            server.feed(SetVector(vector=_numvec(2.5, IPState.OK)))
            await _settle()
            vec = client.get("CCD", "EXPOSURE")
            assert vec is not None
            assert vec.element("secs").value == 2.5
            assert vec.state == IPState.OK

    asyncio.run(scenario())


def test_subscription_fires_for_updates():
    """A subscribed callback receives events for matching properties."""

    async def scenario() -> None:
        server = _Server()
        seen: list[str] = []
        async with IndiClient(connect=server.connect()) as client:
            client.subscribe(lambda e: seen.append(e.type), device="CCD", name="EXPOSURE")
            server.feed(DefVector(vector=_numvec(1.0)))
            server.feed(SetVector(vector=_numvec(2.0, IPState.OK)))
            await _settle()
        assert seen == ["def", "set"]

    asyncio.run(scenario())


def test_async_subscription_can_send():
    """An async subscriber may await client sends from inside the callback."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()) as client:

            async def on_def(event: object) -> None:
                await client.set_number("CCD", "EXPOSURE", {"secs": 3.0})

            client.subscribe(on_def, name="EXPOSURE")
            server.feed(DefVector(vector=_numvec(1.0)))
            await _settle()
        news = [m for m in server.sent() if isinstance(m, NewVector)]
        assert news and news[0].vector.element("secs").value == 3.0

    asyncio.run(scenario())


def test_on_message_receives_messages():
    """Inbound message notifications reach on_message subscribers."""

    async def scenario() -> None:
        server = _Server()
        got: list[str] = []
        async with IndiClient(connect=server.connect()) as client:
            client.on_message(lambda m: got.append(m.message))
            server.feed(Message(device="CCD", message="hello"))
            await _settle()
        assert got == ["hello"]

    asyncio.run(scenario())


def test_set_switch_emits_new_switch_vector():
    """set_switch enqueues a newSwitchVector that parses back correctly."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()) as client:
            await client.set_switch("CCD", "CONNECTION", {"CONNECT": True})
            await _settle()
        news = [m for m in server.sent() if isinstance(m, NewVector)]
        assert news
        vec = news[0].vector
        assert isinstance(vec, SwitchVector)
        assert vec.name == "CONNECTION"
        assert vec.element("CONNECT").value.value == "On"

    asyncio.run(scenario())


def test_enable_blob_sends_and_is_replayed_on_reconnect():
    """enable_blob is sent immediately and replayed after a reconnect."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect(), reconnect_delay=0.0) as client:
            await client.enable_blob("CCD")
            await _settle()
            server.eof()  # drop the connection; the loop reconnects to same server
            await _settle()
        blobs = [m for m in server.sent() if isinstance(m, EnableBLOB)]
        # Once for the initial send, at least once more replayed on reconnect.
        assert len(blobs) >= 2

    asyncio.run(scenario())


def test_wait_for_resolves_on_matching_update():
    """wait_for returns when the predicate is satisfied by an update."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()) as client:

            async def feed_later() -> None:
                await asyncio.sleep(0.01)
                server.feed(DefVector(vector=_numvec(1.0)))
                server.feed(SetVector(vector=_numvec(2.0, IPState.OK)))

            asyncio.create_task(feed_later())
            vec = await client.wait_for(
                "CCD", "EXPOSURE", lambda v: v.state == IPState.OK, timeout=2
            )
            assert vec.state == IPState.OK

    asyncio.run(scenario())


def test_wait_for_times_out():
    """wait_for raises TimeoutError when nothing matches in time."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()) as client:
            try:
                await client.wait_for("CCD", "EXPOSURE", timeout=0.05)
                raise AssertionError("expected TimeoutError")
            except TimeoutError:
                pass

    asyncio.run(scenario())


def test_getitem_exposes_a_device_snapshot():
    """client[device] returns the device's cached property mapping."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()) as client:
            server.feed(DefVector(vector=_numvec(1.0)))
            await _settle()
            assert "EXPOSURE" in client["CCD"]

    asyncio.run(scenario())


def test_on_message_unsubscribe_stops_delivery():
    """The handle returned by on_message removes the subscription."""

    async def scenario() -> None:
        server = _Server()
        got: list[str] = []
        async with IndiClient(connect=server.connect()) as client:
            unsubscribe = client.on_message(lambda m: got.append(m.message))
            server.feed(Message(device="CCD", message="first"))
            await _settle()
            unsubscribe()
            server.feed(Message(device="CCD", message="second"))
            await _settle()
        assert got == ["first"]

    asyncio.run(scenario())


def test_wait_for_returns_cached_vector_immediately():
    """wait_for resolves at once when the cache already satisfies it."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()) as client:
            server.feed(DefVector(vector=_numvec(1.0)))
            await _settle()
            vec = await client.wait_for("CCD", "EXPOSURE")
            assert vec.element("secs").value == 1.0

    asyncio.run(scenario())


def test_wait_for_without_timeout_resolves_on_update():
    """wait_for with no timeout still resolves when the property arrives."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()) as client:

            async def feed_later() -> None:
                await asyncio.sleep(0.01)
                server.feed(DefVector(vector=_numvec(4.0)))

            task = asyncio.create_task(feed_later())
            async with asyncio.timeout(2):
                vec = await client.wait_for("CCD", "EXPOSURE")
            await task
            assert vec.element("secs").value == 4.0

    asyncio.run(scenario())


def test_set_text_emits_new_text_vector():
    """set_text enqueues a newTextVector carrying the given strings."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()) as client:
            await client.set_text("Focuser", "INFO", {"MODEL": "ZWO"})
            await _settle()
        news = [m for m in server.sent() if isinstance(m, NewVector)]
        assert news
        vec = news[0].vector
        assert isinstance(vec, TextVector)
        assert vec.element("MODEL").value == "ZWO"

    asyncio.run(scenario())


def test_set_blob_emits_new_blob_vector():
    """set_blob enqueues a newBLOBVector with the payload and its size."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()) as client:
            await client.set_blob("CCD", "UPLOAD", {"frame": b"\x00FITS\xff"})
            await _settle()
        news = [m for m in server.sent() if isinstance(m, NewVector)]
        assert news
        vec = news[0].vector
        assert isinstance(vec, BLOBVector)
        assert vec.element("frame").data == b"\x00FITS\xff"
        assert vec.element("frame").size == 6

    asyncio.run(scenario())


def test_set_switch_accepts_isstate_and_wire_strings():
    """set_switch coerces ISState members and "On"/"Off" strings alike."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()) as client:
            await client.set_switch("CCD", "MODE", {"a": ISState.ON, "b": "Off"})
            await _settle()
        news = [m for m in server.sent() if isinstance(m, NewVector)]
        assert news
        vec = news[0].vector
        assert vec.element("a").value == ISState.ON
        assert vec.element("b").value == ISState.OFF

    asyncio.run(scenario())


def test_failed_connect_is_retried():
    """A connect attempt that raises OSError is retried until it succeeds."""

    async def scenario() -> None:
        server = _Server()
        attempts = 0
        real_connect = server.connect()

        async def flaky_connect() -> tuple[object, object]:
            """Fail the first attempt, then behave like the real server."""
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("connection refused")
            return await real_connect()

        async with IndiClient(connect=flaky_connect, reconnect_delay=0.0) as client:
            assert client.connected
        assert attempts >= 2
        assert any(isinstance(m, GetProperties) for m in server.sent())

    asyncio.run(scenario())


def test_read_error_triggers_reconnect():
    """An OSError from the transport read is treated as a lost connection."""

    async def scenario() -> None:
        server = _Server()
        attempts = 0
        real_connect = server.connect()

        async def failing_read() -> bytes:
            """Simulate the socket erroring out mid-read."""
            raise OSError("reset by peer")

        async def noop_close() -> None:
            """Nothing to release for the broken transport."""

        async def connect() -> tuple[object, object, object]:
            """Yield a broken transport first, then the healthy server."""
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return failing_read, server.write, noop_close
            return await real_connect()

        async with IndiClient(connect=connect, reconnect_delay=0.0) as client:
            await _settle()
            assert client.connected
        assert attempts >= 2

    asyncio.run(scenario())


def test_eof_while_closing_stops_the_loop():
    """When closing, a connection ending does not trigger a reconnect."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect(), reconnect_delay=0.0) as client:
            await _settle()
            client._closing = True
            server.eof()
            await _settle()
            assert not client.connected
        # A reconnect would have re-sent getProperties; closing prevents it.
        get_props = [m for m in server.sent() if isinstance(m, GetProperties)]
        assert len(get_props) == 1

    asyncio.run(scenario())


def test_default_connect_reaches_a_real_tcp_server_and_closes_cleanly():
    """The client dials host/port over TCP and sends FIN when closed.

    The server handler deliberately reads until the *client* closes its end -
    before the transport-close fix this hung forever, because ``aclose()`` only
    cancelled tasks and left the socket to the garbage collector.
    """

    async def scenario() -> None:
        received: list[bytes] = []
        done = asyncio.Event()

        async def handler(reader, writer) -> None:
            """Capture everything the client sends until it closes (EOF)."""
            buf = b""
            while data := await reader.read(65536):
                buf += data
            received.append(buf)
            writer.close()
            done.set()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            async with IndiClient("127.0.0.1", port) as client:
                assert client.connected
                await _settle()
            # aclose() must close the socket: the handler sees EOF and finishes.
            async with asyncio.timeout(2):
                await done.wait()
            assert b"getProperties" in b"".join(received)
        finally:
            server.close()
            async with asyncio.timeout(2):
                await server.wait_closed()

    asyncio.run(scenario())


def test_transport_is_closed_on_disconnect_and_on_aclose():
    """Every ended connection - dropped or aclosed - releases its transport."""

    async def scenario() -> _Server:
        server = _Server()
        async with IndiClient(connect=server.connect(), reconnect_delay=0.0) as client:
            await _settle()
            server.eof()  # drop the connection; the client closes, then redials
            await _settle()
            assert server.closed >= 1
            assert client.connected
        return server

    server = asyncio.run(scenario())
    # Leaving the context (aclose) must have closed the reconnected transport too.
    assert server.closed >= 2


class _InterruptingEvent:
    """An asyncio.Event stand-in whose wait raises KeyboardInterrupt."""

    async def wait(self):
        """Raise KeyboardInterrupt instead of blocking forever."""
        raise KeyboardInterrupt


class _AsyncioProxy:
    """A pass-through for the asyncio module that swaps in a fake Event."""

    def __getattr__(self, name):
        """Delegate to the real asyncio, except for Event."""
        if name == "Event":
            return _InterruptingEvent
        return getattr(asyncio, name)


def test_run_blocks_until_interrupted(monkeypatch):
    """run() starts the client, blocks, and closes cleanly on interrupt."""
    server = _Server()
    client = IndiClient(connect=server.connect())
    # The client was built with a real asyncio; only run()'s park-forever
    # Event is swapped so the blocking entrypoint returns.
    monkeypatch.setattr(client_module, "asyncio", _AsyncioProxy())

    client.run()

    assert not client.connected
    assert any(isinstance(m, GetProperties) for m in server.sent())


def test_a_malformed_frame_does_not_kill_the_client():
    """Junk from the server costs one message, not the session.

    The parse error used to surface while the reader iterated the parser's
    generator, so it escaped the ``except OSError`` around the connection and
    ended the reconnect loop for good: the client stayed "up" and never read
    another byte.
    """

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect(), reconnect_delay=0.0) as client:
            server.feed(
                b"<setNumberVector device='CCD' name='EXPOSURE'>"
                b"<oneNumber name='secs'>not-a-number</oneNumber></setNumberVector>"
            )
            await _settle()

            assert client.connected
            assert client._loop_task is not None and not client._loop_task.done()

            # and the connection is still carrying traffic
            server.feed(DefVector(vector=_numvec(1.0)))
            await _settle()
            assert client.get("CCD", "EXPOSURE") is not None

    asyncio.run(scenario())


def test_a_raising_subscriber_does_not_kill_the_client():
    """Application code is isolated: one bad callback is not a dropped server."""

    def explode(_arg: object) -> None:
        """Stand in for a subscriber with a bug in it."""
        raise RuntimeError("boom")

    async def scenario() -> None:
        server = _Server()
        seen: list[str] = []
        async with IndiClient(connect=server.connect(), reconnect_delay=0.0) as client:
            client.subscribe(explode)
            client.subscribe(lambda event: seen.append(event.type))
            client.on_message(explode)

            server.feed(DefVector(vector=_numvec(1.0)))
            server.feed(Message(device="CCD", message="hello"))
            await _settle()

            assert seen == ["def"]  # the healthy subscriber still ran
            assert client.connected
            assert client._loop_task is not None and not client._loop_task.done()

    asyncio.run(scenario())


def test_a_muted_parser_is_treated_as_a_lost_connection(monkeypatch):
    """Bytes arriving with no message coming out means reconnect and resync.

    lxml can be left in a state that emits nothing at all - a root close landing
    mid-start-tag does it - and the client's only way out is a new connection: a
    fresh parser, and a server that re-sends every definition.
    """
    monkeypatch.setattr(xml_module, "STALL_THRESHOLD_BYTES", 32)

    async def scenario() -> _Server:
        server = _Server()
        async with IndiClient(connect=server.connect(), reconnect_delay=0.0) as client:
            await _settle()
            server.feed(b"<setNumberVector device='CCD' name='EXPOSURE'")
            server.feed(b"</indinexus>")
            for _ in range(4):
                server.feed(Message(device="CCD", message="lost"))
            await _settle()

            assert client.connected  # reconnected rather than sitting mute
            assert server.closed >= 1
        return server

    server = asyncio.run(scenario())
    # The resync is the point: a second getProperties re-enumerates the server.
    assert len([m for m in server.sent() if isinstance(m, GetProperties)]) >= 2


def test_the_stall_warning_carries_what_this_connection_saw(monkeypatch, caplog):
    """The parser dies with the connection, so its history goes out in the warning.

    Carrying the counters into the *next* connection would be a lie - that is a
    new parser and a fresh peer state - but dropping them silently at the moment
    the stream went quiet threw away the evidence of what the peer had been
    sending. The driver's reader logs the same two numbers before it resyncs.
    """
    monkeypatch.setattr(xml_module, "STALL_THRESHOLD_BYTES", 32)

    async def scenario() -> None:
        """Drop one element, then mute the parser with a root close mid-start-tag."""
        server = _Server()
        async with IndiClient(connect=server.connect(), reconnect_delay=0.0) as client:
            await _settle()
            server.feed(
                b"<setNumberVector device='CCD' name='EXPOSURE'>"
                b"<oneNumber name='secs'>not-a-number</oneNumber></setNumberVector>"
            )
            server.feed(b"<setNumberVector device='CCD' name='EXPOSURE'")
            server.feed(b"</indinexus>")
            for _ in range(4):
                server.feed(Message(device="CCD", message="lost"))
            await _settle()

            assert client.connected

    with caplog.at_level(logging.WARNING, logger="indi_nexus.client.client"):
        asyncio.run(scenario())

    # Only this logger's own records: the codec logs each drop as it happens too.
    (warning,) = [r.getMessage() for r in caplog.records if r.name == "indi_nexus.client.client"]
    assert "reconnecting to resync" in warning
    assert "1 dropped" in warning


def test_reconnects_after_connection_drop():
    """The client reconnects and re-enumerates after the stream closes."""

    async def scenario() -> None:
        server = _Server()
        transitions: list[bool] = []
        async with IndiClient(connect=server.connect(), reconnect_delay=0.0) as client:
            client.on_connection(lambda up: transitions.append(up))
            await _settle()
            server.eof()
            await _settle()
            assert client.connected
        # on_connection was registered after the first connect, so it observes
        # the drop (False) and the reconnect (True).
        assert False in transitions  # a drop was observed
        assert True in transitions  # followed by a reconnect
        get_props = [m for m in server.sent() if isinstance(m, GetProperties)]
        assert len(get_props) >= 2  # initial + after reconnect

    asyncio.run(scenario())


def test_send_while_disconnected_raises_and_is_not_replayed_later():
    """A command issued with the hub down fails; it does not sit in a queue.

    The failure this guards: ``indiserver`` is away, ``set_number`` returns
    happily, and the exposure is delivered whenever the hub comes back - to an
    instrument whose state has nothing to do with the one the caller meant.
    """

    async def scenario() -> None:
        server = _Server()
        gate = asyncio.Event()
        real_connect = server.connect()

        async def gated_connect() -> tuple[object, object, object]:
            """Refuse to connect until the gate opens, then behave normally."""
            if not gate.is_set():
                raise OSError("indiserver is down")
            return await real_connect()

        client = IndiClient(connect=gated_connect, reconnect_delay=0.01)
        await client.start(wait=False)
        await _settle()
        assert not client.connected

        try:
            await client.set_number("CCD", "EXPOSURE", {"secs": 1.0})
            raise AssertionError("expected NotConnectedError")
        except NotConnectedError:
            pass

        gate.set()
        async with asyncio.timeout(2):
            await client.start()  # returns once the connection is up
        await _settle()
        await client.aclose()

        assert any(isinstance(m, GetProperties) for m in server.sent())
        assert not [m for m in server.sent() if isinstance(m, NewVector)]

    asyncio.run(scenario())


def test_enable_blob_while_disconnected_is_still_replayed_on_connect():
    """A BLOB policy is a standing preference: recorded even when the send fails."""

    async def scenario() -> None:
        server = _Server()
        gate = asyncio.Event()
        real_connect = server.connect()

        async def gated_connect() -> tuple[object, object, object]:
            """Refuse to connect until the gate opens, then behave normally."""
            if not gate.is_set():
                raise OSError("indiserver is down")
            return await real_connect()

        client = IndiClient(connect=gated_connect, reconnect_delay=0.01)
        await client.start(wait=False)
        await _settle()

        try:
            await client.enable_blob("CCD")
            raise AssertionError("expected NotConnectedError")
        except NotConnectedError:
            pass

        gate.set()
        async with asyncio.timeout(2):
            await client.start()
        await _settle()
        await client.aclose()

        assert [m for m in server.sent() if isinstance(m, EnableBLOB)]

    asyncio.run(scenario())


def test_aclose_fails_a_parked_wait_for():
    """Closing the client resolves waiters instead of leaving them hanging."""

    async def scenario() -> None:
        server = _Server()
        client = IndiClient(connect=server.connect())
        await client.start()
        waiting = asyncio.create_task(client.wait_for("CCD", "EXPOSURE"))
        await _settle()
        assert not waiting.done()

        await client.aclose()
        try:
            async with asyncio.timeout(1):
                await waiting
            raise AssertionError("expected NotConnectedError")
        except NotConnectedError:
            pass

    asyncio.run(scenario())


def test_wait_for_returns_a_snapshot_taken_when_the_predicate_held():
    """Two sets in one chunk cannot rewrite the vector a wait_for handed back.

    Every message in a read() chunk is folded in before the reader yields, so
    the Ok that satisfies the wait and the Busy that follows it both land
    before the waiting coroutine runs. The vector it receives has to be the one
    the predicate saw.
    """

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()) as client:
            server.feed(DefVector(vector=_numvec(1.0, IPState.BUSY)))
            await _settle()

            waiting = asyncio.create_task(
                client.wait_for("CCD", "EXPOSURE", lambda v: v.state == IPState.OK)
            )
            await _settle()

            server.feed(
                to_xml(SetVector(vector=_numvec(2.0, IPState.OK)))
                + to_xml(SetVector(vector=_numvec(3.0, IPState.BUSY)))
            )
            async with asyncio.timeout(1):
                vec = await waiting

        assert vec.state == IPState.OK
        assert vec.element("secs").value == 2.0
        live = client.get("CCD", "EXPOSURE")
        assert live is not None
        assert live.state == IPState.BUSY  # the cache moved on; the snapshot did not

    asyncio.run(scenario())


def test_whole_device_delete_reaches_a_name_filtered_subscriber():
    """A driver crash withdrawing the whole device notifies property watchers."""

    async def scenario() -> None:
        server = _Server()
        seen: list[str | None] = []
        async with IndiClient(connect=server.connect()) as client:
            client.subscribe(lambda e: seen.append(e.name), device="CCD", name="EXPOSURE")
            server.feed(DefVector(vector=_numvec(1.0)))
            server.feed(DelProperty(device="CCD"))
            await _settle()
        assert seen == ["EXPOSURE", None]

    asyncio.run(scenario())


def test_outbox_overflow_raises_rather_than_blocking():
    """A writer that has stopped draining fails sends instead of absorbing them."""

    async def scenario() -> None:
        server = _Server()
        stuck = asyncio.Event()

        async def stuck_write(data: bytes) -> None:
            """Accept one message and then never return."""
            await stuck.wait()

        async def connect() -> tuple[object, object, object]:
            """Connect with a writer that has wedged."""
            return server.read, stuck_write, server.close

        client = IndiClient(connect=connect)
        await client.start()
        try:
            for _ in range(client_module._OUTBOX_MAXSIZE + 5):
                await client.get_properties()
            raise AssertionError("expected SendQueueFull")
        except SendQueueFull:
            pass
        finally:
            stuck.set()
            await client.aclose()

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Statistics and the per-connection parser                                     #
# --------------------------------------------------------------------------- #
#: A top-level element the parser will refuse, so it counts one `dropped`. The
#: value is not a number and `Number.value` is not nullable, so the whole element
#: goes rather than a value being invented.
_BAD_ELEMENT = (
    b"<setNumberVector device='CCD' name='EXPOSURE'>"
    b"<oneNumber name='secs'>not-a-number</oneNumber></setNumberVector>"
)


def test_stats_before_the_first_connection():
    """/health is reachable before a connection exists, so this must answer.

    ``Bridge.start`` calls ``start(wait=False)``, so the bridge serves ``/health``
    while the client is still trying. There is no parser yet, and every
    parser-derived number is genuinely zero rather than unknown.
    """

    async def scenario() -> None:
        async def refuse() -> tuple[object, object, object]:
            """Fail every attempt, as a down indiserver would."""
            raise OSError("connection refused")

        client = IndiClient(connect=refuse, reconnect_delay=0.0)
        await client.start(wait=False)
        await _settle()
        stats = client.stats
        await client.aclose()

        assert client._parser is None
        assert stats.connected is False
        # A bridge that has never reached indiserver reports no reconnects, which
        # with connected=False already tells that story; counting failed attempts
        # here would make a dead link look like a flapping one.
        assert stats.reconnects == 0
        assert stats.uptime_seconds is None
        assert stats.last_message_age_seconds is None
        assert (stats.dropped, stats.resets, stats.bytes_since_last_message) == (0, 0, 0)
        assert (stats.dropped_total, stats.resets_total) == (0, 0)

    asyncio.run(scenario())


def test_the_parser_is_replaced_on_every_connection():
    """A connection gets its own parser, and that is what makes the stall recover.

    The reader returns on ``parser.stalled`` precisely so the reconnect hands it
    a parser with no half-open lxml document in it. Holding the parser on ``self``
    for ``stats`` to read must not quietly become one parser for the client's
    life: everything else would still pass, and only a peer that had actually
    gone mute would ever show it.
    """

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect(), reconnect_delay=0.0) as client:
            await _settle()
            first = client._parser
            assert first is not None
            server.eof()
            await _settle()
            assert client.connected
            assert client._parser is not None
            assert client._parser is not first

    asyncio.run(scenario())


def test_the_parser_counters_reset_per_connection_but_the_totals_do_not():
    """Per-connection counters describe this peer's stream; the totals are history."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect(), reconnect_delay=0.0) as client:
            await _settle()
            server.feed(_BAD_ELEMENT)
            await _settle()
            assert client.stats.dropped == 1
            assert client.stats.dropped_total == 1

            server.eof()
            await _settle()
            assert client.connected
            after = client.stats
            # A new parser, so a new history...
            assert after.dropped == 0
            # ...but the question "has this ever happened" still answers yes.
            assert after.dropped_total == 1

    asyncio.run(scenario())


def test_the_totals_never_fall_behind_the_connection_in_progress():
    """``dropped_total`` includes the connection that is happening right now.

    Folding a parser's counters only when the *next* connection starts left the
    totals holding connections 1..N-1 while the per-connection fields held N, so
    ``dropped_total < dropped`` was the ordinary case, and after ``aclose()`` the
    last connection - the one an operator is asking about - was never counted at
    all.
    """

    async def scenario() -> IndiClient:
        server = _Server()
        client = IndiClient(connect=server.connect(), reconnect_delay=0.0)
        await client.start()
        await _settle()

        server.feed(_BAD_ELEMENT)
        await _settle()
        assert client.stats.dropped_total >= client.stats.dropped

        # Across a reconnect, on the connection that carries the second drop.
        server.eof()
        await _settle()
        server.feed(_BAD_ELEMENT)
        await _settle()
        assert client.stats.dropped == 1
        assert client.stats.dropped_total == 2
        assert client.stats.dropped_total >= client.stats.dropped

        await client.aclose()
        return client

    client = asyncio.run(scenario())
    # And after aclose, when there is no next connection to fold on.
    assert client.stats.dropped == 1
    assert client.stats.dropped_total == 2
    assert client.stats.dropped_total >= client.stats.dropped


def test_reconnects_counts_only_re_establishments():
    """The first connection is not a reconnect; each later one is."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect(), reconnect_delay=0.0) as client:
            await _settle()
            assert client.stats.reconnects == 0
            server.eof()
            await _settle()
            assert client.stats.reconnects == 1
            server.eof()
            await _settle()
            assert client.stats.reconnects == 2

    asyncio.run(scenario())


def test_uptime_measures_this_connection_and_is_null_while_down():
    """It is the link's uptime, not the process's, so a reconnect restarts it."""

    async def scenario() -> None:
        server = _Server()
        client = IndiClient(connect=server.connect(), reconnect_delay=10.0)
        await client.start()
        await _settle()
        assert client.stats.uptime_seconds is not None

        # A ten-second reconnect delay keeps the client observably disconnected.
        server.eof()
        await _settle()
        assert client.stats.connected is False
        assert client.stats.uptime_seconds is None
        await client.aclose()

    asyncio.run(scenario())


def test_last_message_age_follows_parsed_messages_not_bytes():
    """A peer dribbling malformed bytes must not read as healthy.

    ``bytes_since_last_message`` already answers the byte question, and the two
    have to stay distinct rather than measuring the same thing twice.
    """

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect(), reconnect_delay=0.0) as client:
            await _settle()
            assert client.stats.last_message_age_seconds is None

            server.feed(DefVector(vector=_numvec(1.0)))
            await _settle()
            first = client.stats.last_message_age_seconds
            assert first is not None

            # Junk that never completes an element: bytes move, the age does not.
            server.feed(b"<setNumberVector device='CCD' ")
            await _settle()
            stats = client.stats
            assert stats.bytes_since_last_message > 0
            assert stats.last_message_age_seconds is not None
            assert stats.last_message_age_seconds >= first

    asyncio.run(scenario())


def test_wire_logging_reports_one_line_per_message_per_direction(caplog):
    """``--wire`` answers "what is on the wire" without a packet capture."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()) as client:
            server.feed(DefVector(vector=_numvec(1.0)))
            await _settle()
            await client.set_number("CCD", "EXPOSURE", {"secs": 2.0})
            await _settle()

    with caplog.at_level(logging.DEBUG, logger=WIRE_LOGGER):
        asyncio.run(scenario())

    lines = [r.getMessage() for r in caplog.records if r.name == WIRE_LOGGER]
    assert "<- def CCD.EXPOSURE" in lines
    assert any(line.startswith("-> getProperties (") for line in lines)
    assert any(line.startswith("-> new CCD.EXPOSURE (") for line in lines)


def test_wire_logging_is_silent_below_debug(caplog):
    """The ``isEnabledFor`` guard is what keeps the reader's hot path free."""

    async def scenario() -> None:
        server = _Server()
        async with IndiClient(connect=server.connect()) as client:
            server.feed(DefVector(vector=_numvec(1.0)))
            await _settle()
            await client.get_properties()
            await _settle()

    with caplog.at_level(logging.INFO, logger=WIRE_LOGGER):
        asyncio.run(scenario())

    assert [r for r in caplog.records if r.name == WIRE_LOGGER] == []
