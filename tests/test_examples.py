"""Tests for the runnable examples, exercising their importable entrypoints."""

from __future__ import annotations

import asyncio

from examples.monitor_client import format_event, monitor
from indi_nexus.client import IndiClient
from indi_nexus.client.store import PropertyEvent
from indi_nexus.protocol import DefVector, IPState, Number, NumberVector, to_xml


class _Server:
    """A fake indiserver end feeding scripted bytes to the client."""

    def __init__(self) -> None:
        """Create the inbound queue and output sink."""
        self._inbox: asyncio.Queue[bytes] = asyncio.Queue()
        self.written: list[bytes] = []

    def feed(self, msg: object) -> None:
        """Queue a message model as bytes for the client to read."""
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


def _def(name: str) -> DefVector:
    """Build a def message for a one-element number property."""
    vec = NumberVector(
        device="CCD", name=name, state=IPState.OK, elements=[Number(name="v", value=1.0)]
    )
    return DefVector(vector=vec)


def test_format_event_is_compact():
    """format_event renders type, device.name, and state on one line."""
    vec = NumberVector(device="CCD", name="EXPOSURE", state=IPState.BUSY)
    line = format_event(PropertyEvent("set", "CCD", "EXPOSURE", vec))
    assert "CCD.EXPOSURE" in line
    assert "Busy" in line
    assert line.startswith("[set]")


def test_monitor_consumes_updates():
    """monitor collects a bounded number of events from a live client."""

    async def scenario() -> None:
        server = _Server()
        collected: list[str] = []
        async with IndiClient(connect=server.connect()) as client:

            async def feed_later() -> None:
                await asyncio.sleep(0.01)
                server.feed(_def("EXPOSURE"))
                server.feed(_def("TEMPERATURE"))

            asyncio.create_task(feed_later())
            await asyncio.wait_for(monitor(client, limit=2, sink=collected.append), timeout=2)
        assert len(collected) == 2
        assert any("EXPOSURE" in line for line in collected)

    asyncio.run(scenario())
