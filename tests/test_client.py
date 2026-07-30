"""Tests for :class:`IndiClient`, driven over in-memory transports.

Each test wires the client to a controllable ``(read, write)`` pair (the same
pattern as ``tests/test_driver.py``): a queue-backed reader feeds scripted server
bytes, and a list captures what the client writes, which is parsed back with the
M1 codec to assert on the exact wire output.
"""

from __future__ import annotations

import asyncio

from indi_nexus.client import IndiClient
from indi_nexus.protocol import (
    DefVector,
    EnableBLOB,
    GetProperties,
    IPState,
    Message,
    NewVector,
    Number,
    NumberVector,
    SetVector,
    SwitchVector,
    parse_indi,
    to_xml,
)


class _Server:
    """A fake indiserver end: scripted inbound bytes and captured output."""

    def __init__(self) -> None:
        """Create the inbound queue and the captured-output buffer."""
        self._inbox: asyncio.Queue[bytes] = asyncio.Queue()
        self.written: list[bytes] = []

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
