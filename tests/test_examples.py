"""Tests for the runnable examples, exercising their importable entrypoints."""

from __future__ import annotations

import asyncio

from examples.demo_device import Demo
from examples.dome_device import PARK_AZ, DomeSimulator
from examples.monitor_client import format_event, monitor
from indi_nexus.client import IndiClient
from indi_nexus.client.store import PropertyEvent
from indi_nexus.protocol import (
    DefVector,
    IPState,
    ISState,
    Message,
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


# --------------------------------------------------------------------------- #
# The dome simulator example                                                   #
# --------------------------------------------------------------------------- #
async def _dome() -> tuple[DomeSimulator, list[object]]:
    """Build a set-up dome simulator with its emitted messages captured."""
    captured: list[object] = []
    dome = DomeSimulator()
    dome._bind(captured.append)
    await dome.setup()
    return dome, captured


def _dome_number(prop: str, element: str, value: float) -> NumberVector:
    """Build a client number write for one dome property element."""
    return NumberVector(
        device="Dome Simulator", name=prop, elements=[Number(name=element, value=value)]
    )


def _dome_switch(prop: str, element: str) -> SwitchVector:
    """Build a panel-style switch write naming only the selected element."""
    return SwitchVector(
        device="Dome Simulator", name=prop, elements=[Switch(name=element, value=ISState.ON)]
    )


def _az(dome: DomeSimulator) -> float:
    """Return the dome's current azimuth."""
    return dome["ABS_DOME_POSITION"]["DOME_ABSOLUTE_POSITION"].value


def _texts(captured: list[object]) -> list[str]:
    """Return the text of every INDI message emitted so far."""
    return [str(m.message) for m in captured if isinstance(m, Message)]


def _has_message(captured: list[object], text: str) -> bool:
    """Return whether any emitted INDI message contains ``text``.

    Messages carry a severity prefix (e.g. ``[INFO] ``), so match by substring.
    """
    return any(text in emitted for emitted in _texts(captured))


def test_dome_slews_stepwise_and_arrives_exactly():
    """An absolute move steps at the dome speed and lands on the target."""

    async def scenario() -> None:
        dome, captured = await _dome()
        await dome._dispatch_new(_dome_number("ABS_DOME_POSITION", "DOME_ABSOLUTE_POSITION", 12))
        assert dome["ABS_DOME_POSITION"].vector.state is IPState.BUSY

        await dome.tick()
        assert _az(dome) == 5.0
        await dome.tick()
        assert _az(dome) == 10.0
        await dome.tick()
        assert _az(dome) == 12.0
        assert dome["ABS_DOME_POSITION"].vector.state is IPState.OK
        assert _has_message(captured, "Dome reached requested azimuth angle.")

    asyncio.run(scenario())


def test_dome_takes_the_shortest_way_around():
    """A target across 0 degrees rotates through the wrap, not the long way."""

    async def scenario() -> None:
        dome, _ = await _dome()
        dome["ABS_DOME_POSITION"].set(DOME_ABSOLUTE_POSITION=350.0)
        await dome._dispatch_new(_dome_number("ABS_DOME_POSITION", "DOME_ABSOLUTE_POSITION", 10))

        await dome.tick()
        assert _az(dome) == 355.0  # increasing through 360, not turning back
        await dome.tick()
        assert _az(dome) == 0.0
        await dome.tick()
        await dome.tick()
        assert _az(dome) == 10.0

    asyncio.run(scenario())


def test_dome_snaps_when_target_is_within_one_step():
    """A target closer than one second of travel completes immediately."""

    async def scenario() -> None:
        dome, _ = await _dome()
        await dome._dispatch_new(_dome_number("ABS_DOME_POSITION", "DOME_ABSOLUTE_POSITION", 3))
        assert _az(dome) == 3.0
        assert dome["ABS_DOME_POSITION"].vector.state is IPState.OK

    asyncio.run(scenario())


def test_dome_relative_move_offsets_from_current_position():
    """A relative write rotates by the offset from the current azimuth."""

    async def scenario() -> None:
        dome, _ = await _dome()
        dome["ABS_DOME_POSITION"].set(DOME_ABSOLUTE_POSITION=10.0)
        await dome._dispatch_new(_dome_number("REL_DOME_POSITION", "DOME_RELATIVE_POSITION", 30))
        for _ in range(6):
            await dome.tick()
        assert _az(dome) == 40.0

    asyncio.run(scenario())


def test_dome_shutter_opens_over_time():
    """Opening the shutter takes travel/speed ticks, then reports open."""

    async def scenario() -> None:
        dome, captured = await _dome()
        await dome._dispatch_new(_dome_switch("DOME_SHUTTER", "SHUTTER_OPEN"))
        shutter = dome["DOME_SHUTTER"]
        assert shutter.vector.state is IPState.BUSY
        assert shutter["SHUTTER_OPEN"].value is ISState.ON  # OneOfMany cleared Close

        for _ in range(4):  # 0.5 m at 0.1 m/s: not done after 4 seconds
            await dome.tick()
        assert shutter.vector.state is IPState.BUSY
        await dome.tick()
        assert shutter.vector.state is IPState.OK
        assert _has_message(captured, "Shutter is open.")

    asyncio.run(scenario())


def test_dome_park_closes_shutter_and_rotates_to_park_azimuth():
    """Parking closes the shutter and slews to the park position."""

    async def scenario() -> None:
        dome, captured = await _dome()
        await dome._dispatch_new(_dome_switch("DOME_SHUTTER", "SHUTTER_OPEN"))
        for _ in range(5):
            await dome.tick()

        await dome._dispatch_new(_dome_switch("DOME_PARK", "PARK"))
        assert dome["DOME_SHUTTER"]["SHUTTER_CLOSE"].value is ISState.ON
        assert dome["DOME_PARK"].vector.state is IPState.BUSY

        for _ in range(int(PARK_AZ) // 5):  # 90 degrees at 5 deg/s
            await dome.tick()
        assert _az(dome) == PARK_AZ
        assert dome["DOME_PARK"]["PARK"].value is ISState.ON
        assert dome["DOME_PARK"].vector.state is IPState.OK
        assert _has_message(captured, "Dome parked.")

    asyncio.run(scenario())


def test_dome_unpark_opens_shutter_and_completes_with_it():
    """Unparking opens the shutter and finishes when the shutter does."""

    async def scenario() -> None:
        dome, captured = await _dome()
        await dome._dispatch_new(_dome_switch("DOME_PARK", "UNPARK"))
        assert dome["DOME_PARK"].vector.state is IPState.BUSY
        assert dome["DOME_SHUTTER"]["SHUTTER_OPEN"].value is ISState.ON

        for _ in range(5):
            await dome.tick()
        assert dome["DOME_PARK"]["UNPARK"].value is ISState.ON
        assert dome["DOME_PARK"].vector.state is IPState.OK
        assert _has_message(captured, "Dome unparked.")

    asyncio.run(scenario())


def test_dome_abort_stops_rotation_and_alerts_a_moving_shutter():
    """Abort halts the slew and leaves an interrupted shutter in Alert."""

    async def scenario() -> None:
        dome, captured = await _dome()
        await dome._dispatch_new(_dome_number("ABS_DOME_POSITION", "DOME_ABSOLUTE_POSITION", 180))
        await dome._dispatch_new(_dome_switch("DOME_SHUTTER", "SHUTTER_OPEN"))
        await dome.tick()

        await dome._dispatch_new(_dome_switch("DOME_ABORT_MOTION", "ABORT"))
        frozen = _az(dome)
        await dome.tick()
        await dome.tick()
        assert _az(dome) == frozen
        assert dome["ABS_DOME_POSITION"].vector.state is IPState.IDLE
        assert dome["DOME_SHUTTER"].vector.state is IPState.ALERT
        assert _has_message(captured, "aborted")

    asyncio.run(scenario())


def test_dome_speeds_are_clamped_to_their_range():
    """A speed write outside the advertised range is clamped, not applied raw."""

    async def scenario() -> None:
        dome, _ = await _dome()
        await dome._dispatch_new(_dome_number("SPEEDS", "DOME", 50))
        assert dome["SPEEDS"]["DOME"].value == 10.0  # max
        await dome._dispatch_new(_dome_number("SPEEDS", "SHUTTER", 0.0))
        assert dome["SPEEDS"]["SHUTTER"].value == 0.01  # min

    asyncio.run(scenario())
