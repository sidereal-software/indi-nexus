"""Tests for the runnable examples, exercising their importable entrypoints."""

from __future__ import annotations

import asyncio

import pytest

from examples.ccd_device import AMBIENT_C, CCDSimulator
from examples.demo_device import Demo
from examples.dome_device import PARK_AZ, DomeSimulator
from examples.flat_panel import MAX_BRIGHTNESS, MIN_BRIGHTNESS, FlatPanel
from examples.monitor_client import format_event, monitor
from examples.telescope_device import TelescopeSimulator
from indi_nexus.client import IndiClient
from indi_nexus.client.store import PropertyEvent
from indi_nexus.protocol import (
    DefVector,
    IPState,
    ISRule,
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
    """The monitor helper collects a bounded number of events from a live client."""

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


def _switch_write(element: str, prop: str = "power") -> SwitchVector:
    """Build a panel-style OneOfMany write naming only the selected element."""
    return SwitchVector(device="Demo", name=prop, elements=[Switch(name=element, value=ISState.ON)])


async def _demo(*, connect: bool = True) -> tuple[Demo, list[object]]:
    """Build a set-up demo device with its emitted messages captured.

    Parameters
    ----------
    connect : bool, optional
        Whether to turn the CONNECTION switch on, as an operator would first.
    """
    captured: list[object] = []
    device = Demo()
    device._bind(captured.append)
    await device.setup()
    if connect:
        await device._dispatch_new(_switch_write("CONNECT", "CONNECTION"))
    return device, captured


def _counter_sets(captured: list[object]) -> list[SetVector]:
    """Return the captured ``set`` messages for the demo's counters property."""
    return [m for m in captured if isinstance(m, SetVector) and m.vector.name == "counters"]


def test_demo_animation_only_runs_while_power_is_on():
    """The demo's animation is gated on the power switch."""

    async def scenario() -> None:
        device, captured = await _demo()

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
        device, _ = await _demo()

        await device._dispatch_new(_switch_write("on"))
        await device._dispatch_new(_switch_write("off"))

        power = device["power"]
        assert power["on"].value is ISState.OFF
        assert power["off"].value is ISState.ON  # OneOfMany kept one member On
        # The animated properties were parked in Idle.
        assert device["status_light"].vector.state is IPState.IDLE
        assert device["status_text"]["value"].value == "Idle"

    asyncio.run(scenario())


def test_demo_defines_a_connection_and_starts_disconnected():
    """Every example driver exposes CONNECTION, and it starts off."""

    async def scenario() -> None:
        device, _ = await _demo(connect=False)

        assert "CONNECTION" in device
        assert not device.connected

    asyncio.run(scenario())


def test_demo_refuses_power_writes_while_disconnected():
    """A client write is rejected until the operator has pressed Connect."""

    async def scenario() -> None:
        device, captured = await _demo(connect=False)

        await device._dispatch_new(_switch_write("on"))

        assert device["power"]["on"].value is ISState.OFF
        assert any("not connected" in str(getattr(m, "message", "")) for m in captured)

    asyncio.run(scenario())


def test_demo_parks_its_properties_when_the_client_disconnects():
    """Disconnecting stops the animation and leaves nothing looking live."""

    async def scenario() -> None:
        device, _ = await _demo()
        await device._dispatch_new(_switch_write("on"))
        await device.animate()
        assert device["status_light"].vector.state is not IPState.IDLE

        await device._dispatch_new(_switch_write("DISCONNECT", "CONNECTION"))

        assert not device.connected
        assert device["status_light"].vector.state is IPState.IDLE
        assert device["status_text"]["value"].value == "Idle"
        assert device["power"]["off"].value is ISState.ON

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# The dome simulator example                                                   #
# --------------------------------------------------------------------------- #
async def _dome(*, connect: bool = True) -> tuple[DomeSimulator, list[object]]:
    """Build a set-up dome simulator with its emitted messages captured.

    Parameters
    ----------
    connect : bool, optional
        Whether to turn the CONNECTION switch on (as an operator would first).
    """
    captured: list[object] = []
    dome = DomeSimulator()
    dome._bind(captured.append)
    await dome.setup()
    if connect:
        await dome._dispatch_new(_dome_switch("CONNECTION", "CONNECT"))
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


def test_dome_rejects_commands_while_disconnected():
    """Motion and shutter commands are refused until CONNECTION is on."""

    async def scenario() -> None:
        dome, captured = await _dome(connect=False)
        await dome._dispatch_new(_dome_number("ABS_DOME_POSITION", "DOME_ABSOLUTE_POSITION", 90))
        await dome._dispatch_new(_dome_switch("DOME_SHUTTER", "SHUTTER_OPEN"))

        assert dome["ABS_DOME_POSITION"].vector.state is IPState.IDLE
        assert dome["DOME_SHUTTER"]["SHUTTER_CLOSE"].value is ISState.ON  # unchanged
        assert _has_message(captured, "Dome Simulator is not connected.")
        # (While served, @every(when_connected=True) also pauses the tick; that
        # runtime gating is covered in tests/test_driver.py.)

    asyncio.run(scenario())


def test_dome_connect_enables_commands_and_disconnect_halts_motion():
    """Connecting unlocks the dome; disconnecting mid-slew stops everything."""

    async def scenario() -> None:
        dome, captured = await _dome(connect=False)
        await dome._dispatch_new(_dome_switch("CONNECTION", "CONNECT"))
        assert dome["CONNECTION"]["CONNECT"].value is ISState.ON
        assert _has_message(captured, "Dome Simulator is connected.")

        await dome._dispatch_new(_dome_number("ABS_DOME_POSITION", "DOME_ABSOLUTE_POSITION", 90))
        await dome.tick()
        assert _az(dome) == 5.0

        await dome._dispatch_new(_dome_switch("CONNECTION", "DISCONNECT"))
        assert _has_message(captured, "Dome Simulator is disconnected.")
        assert dome["ABS_DOME_POSITION"].vector.state is IPState.IDLE  # nothing left Busy
        frozen = _az(dome)
        await dome.tick()
        assert _az(dome) == frozen

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# The telescope simulator example                                              #
# --------------------------------------------------------------------------- #
async def _scope(*, connect: bool = True) -> tuple[TelescopeSimulator, list[object]]:
    """Build a set-up telescope simulator with its emitted messages captured.

    Parameters
    ----------
    connect : bool, optional
        Whether to turn the CONNECTION switch on (as an operator would first).
    """
    captured: list[object] = []
    scope = TelescopeSimulator()
    scope._bind(captured.append)
    await scope.setup()
    if connect:
        await scope._dispatch_new(_scope_switch("CONNECTION", "CONNECT"))
    return scope, captured


def _scope_switch(prop: str, element: str) -> SwitchVector:
    """Build a panel-style switch write naming only the selected element."""
    return SwitchVector(
        device="Telescope Simulator",
        name=prop,
        elements=[Switch(name=element, value=ISState.ON)],
    )


def _scope_numbers(prop: str, **values: float) -> NumberVector:
    """Build a client number write for the named telescope property elements."""
    return NumberVector(
        device="Telescope Simulator",
        name=prop,
        elements=[Number(name=name, value=value) for name, value in values.items()],
    )


def _radec(scope: TelescopeSimulator) -> tuple[float, float]:
    """Return the scope's current (RA hours, Dec degrees)."""
    coords = scope["EQUATORIAL_EOD_COORD"]
    return coords["RA"].value, coords["DEC"].value


async def _sync_to(scope: TelescopeSimulator, ra: float, dec: float) -> None:
    """Sync the scope to the given coordinates, restoring goto-on-write mode."""
    await scope._dispatch_new(_scope_switch("ON_COORD_SET", "SYNC"))
    await scope._dispatch_new(_scope_numbers("EQUATORIAL_EOD_COORD", RA=ra, DEC=dec))
    await scope._dispatch_new(_scope_switch("ON_COORD_SET", "TRACK"))


def test_scope_goto_slews_stepwise_then_tracks():
    """A coordinate write slews at the selected rate and ends tracking."""

    async def scenario() -> None:
        scope, captured = await _scope()
        await scope._dispatch_new(_scope_numbers("EQUATORIAL_EOD_COORD", RA=6, DEC=0))
        assert scope["EQUATORIAL_EOD_COORD"].vector.state is IPState.BUSY

        await scope.tick()  # Max rate: 30 deg/s = 2h RA and 30 deg Dec per tick
        assert _radec(scope) == (2.0, 60.0)
        await scope.tick()
        await scope.tick()
        assert _radec(scope) == (6.0, 0.0)
        assert scope["EQUATORIAL_EOD_COORD"].vector.state is IPState.OK
        assert scope["TELESCOPE_TRACK_STATE"]["TRACK_ON"].value is ISState.ON
        assert _has_message(captured, "Telescope slew is complete. Tracking...")

    asyncio.run(scenario())


def test_scope_sync_jumps_without_slewing():
    """In Sync mode a coordinate write updates the pointing instantly."""

    async def scenario() -> None:
        scope, captured = await _scope()
        await scope._dispatch_new(_scope_switch("ON_COORD_SET", "SYNC"))
        await scope._dispatch_new(_scope_numbers("EQUATORIAL_EOD_COORD", RA=5.5, DEC=-20))
        assert _radec(scope) == (5.5, -20.0)
        assert scope["EQUATORIAL_EOD_COORD"].vector.state is IPState.OK
        assert _has_message(captured, "Sync is successful.")

    asyncio.run(scenario())


def test_scope_ra_wraps_the_shortest_way():
    """A goto across 0h RA rotates through the wrap, not the long way."""

    async def scenario() -> None:
        scope, _ = await _scope()
        await _sync_to(scope, 23.5, 0)
        await scope._dispatch_new(_scope_switch("TELESCOPE_SLEW_RATE", "SLEW_FIND"))
        await scope._dispatch_new(_scope_numbers("EQUATORIAL_EOD_COORD", RA=0.5, DEC=0))

        await scope.tick()  # Find rate: 5 deg/s = 1/3 h per tick, increasing
        ra, _dec = _radec(scope)
        assert ra == pytest.approx(23.5 + 1.0 / 3.0)
        for _ in range(3):
            await scope.tick()
        assert _radec(scope)[0] == 0.5

    asyncio.run(scenario())


def test_scope_ra_drifts_only_while_not_tracking():
    """Tracking holds RA still; with tracking off the sky drifts past."""

    async def scenario() -> None:
        scope, _ = await _scope()
        await _sync_to(scope, 12, 0)

        await scope.tick()  # tracking is off by default
        drift = 15.041 / 15.0 / 3600.0
        assert _radec(scope)[0] == pytest.approx(12 + drift)

        await scope._dispatch_new(_scope_switch("TELESCOPE_TRACK_STATE", "TRACK_ON"))
        before = _radec(scope)[0]
        await scope.tick()
        assert _radec(scope)[0] == before  # sidereal tracking follows exactly

    asyncio.run(scenario())


def test_scope_manual_motion_paddle_moves_until_released():
    """The N/S paddle moves at the slew rate while held, then stops."""

    async def scenario() -> None:
        scope, _ = await _scope()
        await _sync_to(scope, 12, 0)
        await scope._dispatch_new(_scope_switch("TELESCOPE_TRACK_STATE", "TRACK_ON"))
        await scope._dispatch_new(_scope_switch("TELESCOPE_SLEW_RATE", "SLEW_CENTERING"))

        await scope._dispatch_new(_scope_switch("TELESCOPE_MOTION_NS", "MOTION_NORTH"))
        await scope.tick()
        assert _radec(scope)[1] == pytest.approx(0.5)

        # Deselecting (the paddle released) sends the member Off.
        await scope._dispatch_new(
            SwitchVector(
                device="Telescope Simulator",
                name="TELESCOPE_MOTION_NS",
                elements=[Switch(name="MOTION_NORTH", value=ISState.OFF)],
            )
        )
        await scope.tick()
        assert _radec(scope)[1] == pytest.approx(0.5)  # no further motion

    asyncio.run(scenario())


def test_scope_park_slews_to_pole_and_locks_out_motion():
    """Parking slews to the pole, stops tracking, and refuses motion."""

    async def scenario() -> None:
        scope, captured = await _scope()
        await _sync_to(scope, 5, 20)
        await scope._dispatch_new(_scope_switch("TELESCOPE_PARK", "PARK"))
        assert scope["TELESCOPE_PARK"].vector.state is IPState.BUSY

        for _ in range(3):  # 20 -> 90 degrees at 30 deg/s
            await scope.tick()
        assert _radec(scope) == (5.0, 90.0)
        assert scope["TELESCOPE_PARK"]["PARK"].value is ISState.ON
        assert scope["TELESCOPE_TRACK_STATE"]["TRACK_OFF"].value is ISState.ON
        assert _has_message(captured, "Telescope slew is complete. Parked.")

        await scope._dispatch_new(_scope_numbers("EQUATORIAL_EOD_COORD", RA=1, DEC=1))
        assert _has_message(captured, "Please unpark the mount")
        assert _radec(scope) == (5.0, 90.0)

        await scope._dispatch_new(_scope_switch("TELESCOPE_PARK", "UNPARK"))
        assert _has_message(captured, "Telescope unparked.")

    asyncio.run(scenario())


def test_scope_abort_stops_the_slew():
    """Abort halts a slew mid-flight and leaves the scope where it was."""

    async def scenario() -> None:
        scope, captured = await _scope()
        await _sync_to(scope, 12, 0)
        await scope._dispatch_new(_scope_switch("TELESCOPE_TRACK_STATE", "TRACK_ON"))
        await scope._dispatch_new(_scope_numbers("EQUATORIAL_EOD_COORD", RA=18, DEC=45))
        await scope.tick()

        await scope._dispatch_new(_scope_switch("TELESCOPE_ABORT_MOTION", "ABORT"))
        frozen = _radec(scope)
        await scope.tick()
        assert _radec(scope) == frozen
        assert _has_message(captured, "Telescope motion aborted.")

    asyncio.run(scenario())


def test_scope_guide_pulse_nudges_and_completes():
    """A timed guide pulse offsets by rate x sidereal x duration, then resets."""

    async def scenario() -> None:
        scope, _ = await _scope()
        await _sync_to(scope, 12, 0)
        await scope._dispatch_new(_scope_switch("TELESCOPE_TRACK_STATE", "TRACK_ON"))

        await scope._dispatch_new(_scope_numbers("TELESCOPE_TIMED_GUIDE_NS", TIMED_GUIDE_N=1000))
        # 0.5 x 15.041 arcsec over one second, as degrees of declination.
        assert _radec(scope)[1] == pytest.approx(0.5 * 15.041 / 3600.0)
        guide = scope["TELESCOPE_TIMED_GUIDE_NS"]
        assert guide["TIMED_GUIDE_N"].value == 0.0
        assert guide.vector.state is IPState.OK

    asyncio.run(scenario())


def test_scope_rejects_commands_while_disconnected():
    """Motion commands are refused until CONNECTION is on."""

    async def scenario() -> None:
        scope, captured = await _scope(connect=False)
        await scope._dispatch_new(_scope_numbers("EQUATORIAL_EOD_COORD", RA=3, DEC=3))
        assert _has_message(captured, "Telescope Simulator is not connected.")
        assert _radec(scope) == (0.0, 90.0)  # the refused goto moved nothing
        # (While served, @every(when_connected=True) pauses the tick; that
        # runtime gating is covered in tests/test_driver.py.)

    asyncio.run(scenario())


def test_scope_location_update_is_stored():
    """A GEOGRAPHIC_COORD write is normalised, stored, and confirmed."""

    async def scenario() -> None:
        scope, captured = await _scope()
        await scope._dispatch_new(_scope_numbers("GEOGRAPHIC_COORD", LAT=-30.5, LONG=380.0))
        site = scope["GEOGRAPHIC_COORD"]
        assert site["LAT"].value == -30.5
        assert site["LONG"].value == 20.0  # wrapped into [0, 360)
        assert _has_message(captured, "Site location updated.")

    asyncio.run(scenario())


def test_hub_serves_several_drivers_on_one_client():
    """The in-process hub multiplexes drivers like a miniature indiserver.

    Both devices define over the shared stream, and a write is acted on only
    by the device it is addressed to.
    """

    async def scenario() -> None:
        from indi_nexus.web import InProcessHub

        hub = InProcessHub([DomeSimulator(), TelescopeSimulator()])
        tasks = [asyncio.create_task(runtime.serve()) for runtime in hub.runtimes]
        try:
            async with IndiClient(connect=hub.connect) as client:
                await client.wait_for("Dome Simulator", "DOME_SHUTTER", timeout=2)
                await client.wait_for("Telescope Simulator", "EQUATORIAL_EOD_COORD", timeout=2)

                # Connect only the dome; the broadcast write must not touch the
                # telescope's identically named CONNECTION property.
                await client.set_switch("Dome Simulator", "CONNECTION", {"CONNECT": True})
                await client.wait_for(
                    "Dome Simulator",
                    "CONNECTION",
                    lambda v: v.element("CONNECT").value is ISState.ON,
                    timeout=2,
                )
                scope_conn = client.get("Telescope Simulator", "CONNECTION")
                assert scope_conn is not None
                assert scope_conn.element("CONNECT").value is ISState.OFF
        finally:
            hub.shutdown()
            async with asyncio.timeout(2):
                await asyncio.gather(*tasks)

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# The CCD simulator example                                                    #
# --------------------------------------------------------------------------- #
async def _ccd(*, connect: bool = True) -> tuple[CCDSimulator, list[object]]:
    """Build a set-up CCD simulator with its emitted messages captured.

    Parameters
    ----------
    connect : bool, optional
        Whether to turn the CONNECTION switch on (as an operator would first).
    """
    captured: list[object] = []
    ccd = CCDSimulator()
    ccd._bind(captured.append)
    await ccd.setup()
    if connect:
        await ccd._dispatch_new(_ccd_switch("CONNECTION", "CONNECT"))
    return ccd, captured


def _ccd_number(prop: str, values: dict[str, float]) -> NumberVector:
    """Build a client number write for CCD property elements."""
    return NumberVector(
        device="CCD Simulator",
        name=prop,
        elements=[Number(name=name, value=value) for name, value in values.items()],
    )


def _ccd_switch(prop: str, element: str) -> SwitchVector:
    """Build a panel-style switch write naming only the selected element."""
    return SwitchVector(
        device="CCD Simulator", name=prop, elements=[Switch(name=element, value=ISState.ON)]
    )


def _fits_int(fits: bytes, key: str) -> int:
    """Read an integer header value from a FITS byte string."""
    header = fits[:2880].decode("ascii")
    for start in range(0, len(header), 80):
        card = header[start : start + 80]
        if card.startswith(f"{key:<8}="):
            return int(float(card[10:30]))
    raise KeyError(key)


def _fits_mean(fits: bytes) -> float:
    """Return the mean pixel value of a 16-bit FITS image."""
    import struct

    count = _fits_int(fits, "NAXIS1") * _fits_int(fits, "NAXIS2")
    values = struct.unpack(f">{count}h", fits[2880 : 2880 + count * 2])
    return sum(value + 32768 for value in values) / count


def _temp(ccd: CCDSimulator) -> float:
    """Return the CCD's current sensor temperature."""
    return ccd["CCD_TEMPERATURE"]["CCD_TEMPERATURE_VALUE"].value


def test_ccd_exposure_counts_down_and_delivers_a_fits_image():
    """An exposure runs Busy with a countdown and completes with a FITS blob."""

    async def scenario() -> None:
        ccd, captured = await _ccd()
        await ccd._dispatch_new(_ccd_number("CCD_BINNING", {"HOR_BIN": 2, "VER_BIN": 2}))
        await ccd._dispatch_new(_ccd_number("CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": 2}))
        assert ccd["CCD_EXPOSURE"].vector.state is IPState.BUSY
        assert _has_message(captured, "Starting 2.00 s exposure.")

        await ccd.tick()  # one second left
        assert ccd["CCD_EXPOSURE"].vector.state is IPState.BUSY
        assert ccd["CCD_EXPOSURE"]["CCD_EXPOSURE_VALUE"].value == 1.0

        await ccd.tick()  # completes and renders
        assert ccd["CCD_EXPOSURE"].vector.state is IPState.OK
        assert ccd["CCD_EXPOSURE"]["CCD_EXPOSURE_VALUE"].value == 0
        fits = ccd["CCD1"]["CCD1"].data
        assert fits is not None and fits.startswith(b"SIMPLE")
        assert _fits_int(fits, "NAXIS1") == 320  # 640 / bin 2
        assert _fits_int(fits, "NAXIS2") == 240
        assert len(fits) % 2880 == 0
        assert _has_message(captured, "Exposure complete.")

    asyncio.run(scenario())


def test_ccd_abort_cancels_the_running_exposure():
    """Abort ends the exposure Idle with no image delivered."""

    async def scenario() -> None:
        ccd, captured = await _ccd()
        await ccd._dispatch_new(_ccd_number("CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": 10}))
        await ccd.tick()
        await ccd._dispatch_new(_ccd_switch("CCD_ABORT_EXPOSURE", "ABORT"))

        assert ccd["CCD_EXPOSURE"].vector.state is IPState.IDLE
        assert ccd["CCD_EXPOSURE"]["CCD_EXPOSURE_VALUE"].value == 0
        assert _has_message(captured, "Exposure aborted.")

        await ccd.tick()  # nothing left to complete
        assert ccd["CCD1"]["CCD1"].data is None

    asyncio.run(scenario())


def test_ccd_bias_frames_stay_dark_and_light_frames_collect_signal():
    """A light frame accumulates sky glow and stars over the bias level."""

    async def scenario() -> None:
        ccd, _ = await _ccd()
        await ccd._dispatch_new(_ccd_number("CCD_BINNING", {"HOR_BIN": 4, "VER_BIN": 4}))

        await ccd._dispatch_new(_ccd_switch("CCD_FRAME_TYPE", "FRAME_BIAS"))
        await ccd._dispatch_new(_ccd_number("CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": 1}))
        await ccd.tick()
        bias_fits = ccd["CCD1"]["CCD1"].data
        assert bias_fits is not None
        bias_mean = _fits_mean(bias_fits)

        await ccd._dispatch_new(_ccd_switch("CCD_FRAME_TYPE", "FRAME_LIGHT"))
        await ccd._dispatch_new(_ccd_number("CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": 1}))
        await ccd.tick()
        light_fits = ccd["CCD1"]["CCD1"].data
        assert light_fits is not None

        # Bias sits at the offset (100 ADU); the light frame adds ~100 ADU of
        # sky glow plus stars, so it must be clearly brighter.
        assert bias_mean < 150
        assert _fits_mean(light_fits) > bias_mean + 50

    asyncio.run(scenario())


def test_ccd_binning_is_clamped_to_whole_steps():
    """Out-of-range binning writes are clamped into [1, 4]."""

    async def scenario() -> None:
        ccd, _ = await _ccd()
        await ccd._dispatch_new(_ccd_number("CCD_BINNING", {"HOR_BIN": 8, "VER_BIN": 0}))
        binning = ccd["CCD_BINNING"]
        assert binning["HOR_BIN"].value == 4
        assert binning["VER_BIN"].value == 1
        assert binning.vector.state is IPState.OK

    asyncio.run(scenario())


def test_ccd_tec_cools_stepwise_then_holds():
    """The TEC pulls half a degree per tick and reports Ok at the set point."""

    async def scenario() -> None:
        ccd, captured = await _ccd()
        await ccd._dispatch_new(_ccd_number("CCD_TEMPERATURE", {"CCD_TEMPERATURE_VALUE": 23}))
        assert ccd["CCD_TEMPERATURE"].vector.state is IPState.BUSY
        assert ccd["CCD_COOLER"]["COOLER_ON"].value is ISState.ON

        await ccd.tick()
        assert _temp(ccd) == 24.5
        for _ in range(3):
            await ccd.tick()
        assert _temp(ccd) == 23.0
        assert ccd["CCD_TEMPERATURE"].vector.state is IPState.OK
        assert _has_message(captured, "Temperature reached +23.0 C.")

        await ccd.tick()  # holding: nothing changes
        assert _temp(ccd) == 23.0

    asyncio.run(scenario())


def test_ccd_cooler_off_warms_back_toward_ambient():
    """Switching the cooler off relaxes the sensor exponentially to ambient."""

    async def scenario() -> None:
        ccd, _ = await _ccd()
        await ccd._dispatch_new(_ccd_number("CCD_TEMPERATURE", {"CCD_TEMPERATURE_VALUE": 23}))
        for _ in range(4):
            await ccd.tick()
        assert _temp(ccd) == 23.0

        await ccd._dispatch_new(_ccd_switch("CCD_COOLER", "COOLER_OFF"))
        assert ccd["CCD_TEMPERATURE"].vector.state is IPState.BUSY
        await ccd.tick()
        assert _temp(ccd) == pytest.approx(23.4)  # 20% of the 2-degree gap

        for _ in range(60):
            await ccd.tick()
        assert _temp(ccd) == AMBIENT_C
        assert ccd["CCD_TEMPERATURE"].vector.state is IPState.OK
        assert ccd["CCD_COOLER"]["COOLER_OFF"].value is ISState.ON

    asyncio.run(scenario())


def test_ccd_time_factor_stretches_the_exposure_clock():
    """SIM_TIME_FACTOR of 2 makes a one-second exposure take two ticks."""

    async def scenario() -> None:
        ccd, _ = await _ccd()
        await ccd._dispatch_new(_ccd_number("CCD_BINNING", {"HOR_BIN": 4, "VER_BIN": 4}))
        await ccd._dispatch_new(_ccd_number("SIMULATOR_SETTINGS", {"SIM_TIME_FACTOR": 2}))
        await ccd._dispatch_new(_ccd_number("CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": 1}))

        await ccd.tick()
        assert ccd["CCD_EXPOSURE"].vector.state is IPState.BUSY  # one tick left
        await ccd.tick()
        assert ccd["CCD_EXPOSURE"].vector.state is IPState.OK
        assert ccd["CCD1"]["CCD1"].data is not None

    asyncio.run(scenario())


def test_ccd_rejects_commands_while_disconnected():
    """Exposure and cooler commands are refused until CONNECTION is on."""

    async def scenario() -> None:
        ccd, captured = await _ccd(connect=False)
        await ccd._dispatch_new(_ccd_number("CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": 1}))
        await ccd._dispatch_new(_ccd_number("CCD_TEMPERATURE", {"CCD_TEMPERATURE_VALUE": 0}))

        assert ccd["CCD_EXPOSURE"].vector.state is IPState.IDLE
        assert ccd["CCD_TEMPERATURE"].vector.state is IPState.IDLE
        assert _has_message(captured, "CCD Simulator is not connected.")

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# The flat-field lamp example (the "Writing a driver" guide)                    #
# --------------------------------------------------------------------------- #
async def _flat(*, connect: bool = True) -> tuple[FlatPanel, list[object]]:
    """Build a set-up flat panel with its emitted messages captured.

    Parameters
    ----------
    connect : bool, optional
        Whether to turn the CONNECTION switch on (as an operator would first).
    """
    captured: list[object] = []
    panel = FlatPanel()
    panel._bind(captured.append)
    await panel.setup()
    if connect:
        await panel._dispatch_new(_flat_switch("CONNECTION", "CONNECT"))
    return panel, captured


def _flat_switch(prop: str, element: str) -> SwitchVector:
    """Build a panel-style switch write naming only the selected element."""
    return SwitchVector(
        device="Flat Panel", name=prop, elements=[Switch(name=element, value=ISState.ON)]
    )


def _flat_brightness(value: float) -> NumberVector:
    """Build a client brightness write."""
    return NumberVector(
        device="Flat Panel",
        name="LIGHT_BRIGHTNESS",
        elements=[Number(name="BRIGHTNESS", value=value)],
    )


def test_flat_panel_starts_off_with_a_declared_brightness_range():
    """Setup advertises a connection switch, an exclusive lamp, and a bounded dial."""

    async def scenario() -> None:
        panel, _ = await _flat(connect=False)
        assert panel["CONNECTION"]["DISCONNECT"].value is ISState.ON
        assert not panel.connected

        lamp = panel["LIGHT_CONTROL"].vector
        assert lamp.rule is ISRule.ONE_OF_MANY
        assert panel["LIGHT_CONTROL"]["OFF"].value is ISState.ON
        assert panel["LIGHT_CONTROL"]["ON"].value is ISState.OFF

        brightness = panel["LIGHT_BRIGHTNESS"]["BRIGHTNESS"]
        assert (brightness.min, brightness.max) == (MIN_BRIGHTNESS, MAX_BRIGHTNESS)

    asyncio.run(scenario())


def test_flat_panel_lamp_toggles_exclusively():
    """Turning the lamp on turns Off off, and back again, announcing each move."""

    async def scenario() -> None:
        panel, captured = await _flat()

        await panel._dispatch_new(_flat_switch("LIGHT_CONTROL", "ON"))
        assert panel["LIGHT_CONTROL"]["ON"].value is ISState.ON
        assert panel["LIGHT_CONTROL"]["OFF"].value is ISState.OFF
        assert panel["LIGHT_CONTROL"].vector.state is IPState.OK
        assert _has_message(captured, "Lamp turned on.")

        await panel._dispatch_new(_flat_switch("LIGHT_CONTROL", "OFF"))
        assert panel["LIGHT_CONTROL"]["OFF"].value is ISState.ON
        assert panel["LIGHT_CONTROL"]["ON"].value is ISState.OFF
        assert _has_message(captured, "Lamp turned off.")

    asyncio.run(scenario())


def test_flat_panel_brightness_is_clamped_to_its_range():
    """A brightness write outside the advertised range is clamped, not applied raw."""

    async def scenario() -> None:
        panel, _ = await _flat()

        await panel._dispatch_new(_flat_brightness(64))
        assert panel["LIGHT_BRIGHTNESS"]["BRIGHTNESS"].value == 64

        await panel._dispatch_new(_flat_brightness(1000))
        assert panel["LIGHT_BRIGHTNESS"]["BRIGHTNESS"].value == MAX_BRIGHTNESS

        await panel._dispatch_new(_flat_brightness(-5))
        assert panel["LIGHT_BRIGHTNESS"]["BRIGHTNESS"].value == MIN_BRIGHTNESS
        assert panel["LIGHT_BRIGHTNESS"].vector.state is IPState.OK

    asyncio.run(scenario())


def test_flat_panel_rejects_commands_while_disconnected():
    """Lamp and brightness writes are refused until CONNECTION is on."""

    async def scenario() -> None:
        panel, captured = await _flat(connect=False)

        await panel._dispatch_new(_flat_switch("LIGHT_CONTROL", "ON"))
        await panel._dispatch_new(_flat_brightness(200))

        assert panel["LIGHT_CONTROL"]["OFF"].value is ISState.ON
        assert panel["LIGHT_BRIGHTNESS"]["BRIGHTNESS"].value == 128
        assert _has_message(captured, "Flat Panel is not connected.")

    asyncio.run(scenario())


def test_flat_panel_turns_the_lamp_off_when_the_client_disconnects():
    """Disconnecting darkens the lamp, because a lit panel fogs the next exposure."""

    async def scenario() -> None:
        panel, captured = await _flat()
        await panel._dispatch_new(_flat_switch("LIGHT_CONTROL", "ON"))
        assert panel["LIGHT_CONTROL"]["ON"].value is ISState.ON

        await panel._dispatch_new(_flat_switch("CONNECTION", "DISCONNECT"))

        assert panel["LIGHT_CONTROL"]["ON"].value is ISState.OFF
        assert panel["LIGHT_CONTROL"]["OFF"].value is ISState.ON
        assert panel["LIGHT_CONTROL"].vector.state is IPState.IDLE
        assert _has_message(captured, "Lamp turned off on disconnect.")

    asyncio.run(scenario())
