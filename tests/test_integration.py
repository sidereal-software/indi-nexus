"""End-to-end tests wiring the driver SDK, client, and web bridge together.

No ``indiserver`` is involved: a :class:`DriverRuntime` (M2) and an
:class:`IndiClient` (M3) are cross-connected through two in-memory byte pipes
(driver output -> client input, client output -> driver input), proving the
layers interoperate purely through the M1 protocol models. The second test adds
the M4 :class:`Bridge` on top with a fake browser sink.
"""

from __future__ import annotations

import asyncio
import json

from examples.demo_device import Demo
from indi_nexus.client import IndiClient
from indi_nexus.driver import DriverRuntime
from indi_nexus.protocol import IPState, ISState
from indi_nexus.web import Bridge


class _Pipe:
    """A one-way in-memory byte channel with an EOF sentinel."""

    def __init__(self) -> None:
        """Create the channel's backing queue."""
        self._q: asyncio.Queue[bytes] = asyncio.Queue()

    async def read(self) -> bytes:
        """Return the next chunk written to the channel (``b""`` at EOF)."""
        return await self._q.get()

    async def write(self, data: bytes) -> None:
        """Write one chunk to the channel."""
        self._q.put_nowait(data)

    def eof(self) -> None:
        """Signal end-of-stream to the reader."""
        self._q.put_nowait(b"")


async def _connect_device(client: IndiClient) -> None:
    """Turn the demo device's CONNECTION switch on and wait for it to take.

    Every example driver guards its handlers with ``require_connected()``, so a
    client that skips this gets an ``ERROR`` message back instead of the write it
    asked for - exactly as a real client would.

    Parameters
    ----------
    client : IndiClient
        The connected client to drive.
    """
    await client.set_switch("Demo", "CONNECTION", {"CONNECT": True})
    # The built-in handler publishes Busy first and Ok once on_connect returns,
    # so wait for the settled state rather than the first set to arrive.
    await client.wait_for(
        "Demo",
        "CONNECTION",
        lambda v: v.element("CONNECT").value == ISState.ON and v.state == IPState.OK,
        timeout=2,
    )


def test_driver_and_client_interoperate():
    """A client drives the demo device end-to-end: enumerate, set, confirm."""

    async def scenario() -> None:
        to_client = _Pipe()  # driver -> client
        to_driver = _Pipe()  # client -> driver

        device = Demo()
        runtime = DriverRuntime(device, to_driver.read, to_client.write)
        driver_task = asyncio.create_task(runtime.serve())

        async def connect() -> tuple[object, object, object]:
            """Wire the client's read/write onto the two pipes."""

            async def close() -> None:
                """Nothing to release for the in-memory pipes."""

            return to_client.read, to_driver.write, close

        client = IndiClient(connect=connect)
        try:
            async with client:
                # getProperties (sent on connect) -> driver setup() -> defs arrive.
                power = await client.wait_for("Demo", "power", timeout=2)
                assert power is not None
                assert "Demo" in client.store

                await _connect_device(client)

                # Client turns the switch on; the driver's @on_new echoes it back.
                await client.set_switch("Demo", "power", {"on": True})
                confirmed = await client.wait_for(
                    "Demo",
                    "power",
                    lambda v: v.element("on").value == ISState.ON and v.state == IPState.OK,
                    timeout=2,
                )
                assert confirmed.element("on").value == ISState.ON
                assert confirmed.element("off").value == ISState.OFF  # OneOfMany cleared it
        finally:
            to_driver.eof()
            await asyncio.wait_for(driver_task, timeout=2)

    asyncio.run(scenario())


def test_bridge_relays_driver_to_a_browser_sink():
    """A browser (fake sink) drives the demo device through the full bridge stack."""

    async def scenario() -> None:
        to_client = _Pipe()  # driver -> client
        to_driver = _Pipe()  # client -> driver

        device = Demo()
        runtime = DriverRuntime(device, to_driver.read, to_client.write)
        driver_task = asyncio.create_task(runtime.serve())

        async def connect() -> tuple[object, object, object]:
            """Wire the client's read/write onto the two pipes."""

            async def close() -> None:
                """Nothing to release for the in-memory pipes."""

            return to_client.read, to_driver.write, close

        client = IndiClient(connect=connect)
        bridge = Bridge(client)
        frames: list[str] = []

        async def sink(text: str) -> None:
            """Stand in for a browser WebSocket, recording broadcast frames."""
            frames.append(text)

        await bridge.start()
        try:
            await client.wait_for("Demo", "power", timeout=2)
            await _connect_device(client)
            sub = bridge.attach(sink)

            # A browser turns the power switch on; it flows bridge -> client ->
            # driver -> @on_new -> back to the client and out to the sink.
            await bridge.handle_incoming(
                json.dumps(
                    {
                        "tag": "new",
                        "vector": {
                            "kind": "switch",
                            "device": "Demo",
                            "name": "power",
                            "elements": [{"kind": "switch", "name": "on", "value": "On"}],
                        },
                    }
                )
            )
            confirmed = await client.wait_for(
                "Demo",
                "power",
                lambda v: v.element("on").value == ISState.ON and v.state == IPState.OK,
                timeout=2,
            )
            assert confirmed.state == IPState.OK
            # The fake browser saw the confirming set for the power vector. The
            # bridge queues it and its pump task delivers it, so wait for that
            # rather than for the reader that queued it.
            async with asyncio.timeout(2):
                # Yielding is the wait: the condition is the pump task making
                # progress, and there is no event that announces it.
                while not any(  # noqa: ASYNC110
                    '"name":"power"' in f and '"tag":"set"' in f for f in frames
                ):
                    await asyncio.sleep(0)
        finally:
            await sub.aclose()
            await bridge.aclose()
            to_driver.eof()
            await asyncio.wait_for(driver_task, timeout=2)

    asyncio.run(scenario())
