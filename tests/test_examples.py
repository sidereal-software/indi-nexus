"""Tests for the runnable examples, exercising their importable entrypoints."""

from __future__ import annotations

import asyncio

from examples.demo_device import Demo
from examples.monitor_client import format_event, monitor
from indi_nexus.client import IndiClient
from indi_nexus.client.store import PropertyEvent
from indi_nexus.protocol import (
    DefVector,
    IPState,
    ISState,
    Number,
    NumberVector,
    SetVector,
    Switch,
    SwitchVector,
    to_xml,
)


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
        """Return a connect factory yielding this server's read/write/close trio."""

        async def _close() -> None:
            """Nothing to release for the in-memory transport."""

        async def _connect() -> tuple[object, object, object]:
            return self.read, self.write, _close

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


def _switch_write(element: str) -> SwitchVector:
    """Build a panel-style OneOfMany write naming only the selected element."""
    return SwitchVector(
        device="Demo", name="power", elements=[Switch(name=element, value=ISState.ON)]
    )


def _counter_sets(captured: list[object]) -> list[SetVector]:
    """Return the captured ``set`` messages for the demo's counters property."""
    return [m for m in captured if isinstance(m, SetVector) and m.vector.name == "counters"]


def test_demo_animation_only_runs_while_power_is_on():
    """The demo's animation is gated on the power switch."""

    async def scenario() -> None:
        captured: list[object] = []
        device = Demo()
        device._bind(captured.append)
        await device.setup()

        await device.animate()  # power starts Off
        assert _counter_sets(captured) == []

        await device._dispatch_new(_switch_write("on"))
        await device.animate()
        assert len(_counter_sets(captured)) == 1

        await device._dispatch_new(_switch_write("off"))
        before = len(_counter_sets(captured))
        await device.animate()
        # Only the power-off "park to Idle" set arrived, no further ticks.
        assert len(_counter_sets(captured)) == before

    asyncio.run(scenario())


def test_demo_power_off_accepts_partial_write_and_parks_idle():
    """A `{off: On}` write - the panel's exact frame - turns the demo off cleanly.

    Regression test for the freeze: the old handler indexed ``vector["on"]``,
    which raised ``KeyError`` when only the "off" element was sent.
    """

    async def scenario() -> None:
        captured: list[object] = []
        device = Demo()
        device._bind(captured.append)
        await device.setup()

        await device._dispatch_new(_switch_write("on"))
        await device._dispatch_new(_switch_write("off"))

        power = device["power"]
        assert power["on"].value is ISState.OFF
        assert power["off"].value is ISState.ON  # OneOfMany kept one member On
        # The animated properties were parked in Idle.
        assert device["status_light"].vector.state is IPState.IDLE
        assert device["status_text"]["value"].value == "Idle"

    asyncio.run(scenario())
