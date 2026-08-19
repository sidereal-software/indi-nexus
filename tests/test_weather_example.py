"""Tests for the hardware-shaped weather example - the pattern to copy.

Everything here goes through :class:`~indikit.testing.DeviceHarness`: no
``indiserver``, no sockets, no station. The station client is the one thing
stubbed out, because it is the one thing that would be real hardware.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from examples.weather_device import CONDITIONS, WeatherError, WeatherStation
from indikit.protocol import IPState, ISState
from indikit.testing import DeviceHarness

NOMINAL = {
    "temperature": 11.0,
    "humidity": 60.0,
    "wind_speed": 6.0,
    "cloud_cover": 20.0,
}


class _FakeStation:
    """A scriptable stand-in for the blocking station client."""

    def __init__(self) -> None:
        """Start closed, answering nominally, recording nothing."""
        self.readings = dict(NOMINAL)
        self.fail_open = False
        self.fail_read = False
        self.fail_reset = False
        self.read_delay = 0.0
        self.calls: list[str] = []
        self.is_open = False

    def open(self) -> None:
        """Open the link, or fail the way an absent serial port does."""
        self.calls.append("open")
        if self.fail_open:
            raise WeatherError("no such port")
        self.is_open = True

    def close(self) -> None:
        """Close the link."""
        self.calls.append("close")
        self.is_open = False

    def identify(self) -> dict[str, str]:
        """Return the station's scripted identification."""
        self.calls.append("identify")
        return {"MODEL": "Fake WS-1", "FIRMWARE": "0.1"}

    def read_all(self) -> dict[str, float]:
        """Return the scripted readings, blocking for the scripted delay."""
        self.calls.append("read")
        if self.read_delay:
            time.sleep(self.read_delay)
        if self.fail_read:
            raise WeatherError("no reply")
        return dict(self.readings)

    def reset(self) -> None:
        """Record a sensor reset, or fail it."""
        self.calls.append("reset")
        if self.fail_reset:
            raise WeatherError("sensors busy")


@pytest.fixture
async def station():
    """Return a connected harness plus the fake station behind it."""
    device = WeatherStation()
    fake = _FakeStation()
    device._station = fake
    harness = DeviceHarness(device)
    await harness.setup()
    await harness.write("CONNECTION", CONNECT=True)
    harness.clear()
    return harness, fake


# --------------------------------------------------------------------------- #
# Connection lifecycle                                                         #
# --------------------------------------------------------------------------- #
async def test_connecting_opens_the_link() -> None:
    """A successful connect opens the station and leaves CONNECTION Ok."""
    device = WeatherStation()
    device._station = fake = _FakeStation()
    harness = DeviceHarness(device)
    await harness.setup()

    await harness.write("CONNECTION", CONNECT=True)

    assert fake.is_open
    assert device.connected
    assert harness.latest("CONNECTION").state is IPState.OK


async def test_a_station_that_is_not_there_leaves_the_device_disconnected() -> None:
    """A failing on_connect rolls CONNECTION back rather than faking a link."""
    device = WeatherStation()
    device._station = fake = _FakeStation()
    fake.fail_open = True
    harness = DeviceHarness(device)
    await harness.setup()

    await harness.write("CONNECTION", CONNECT=True)

    assert device.connected is False
    assert harness.latest("CONNECTION").state is IPState.ALERT
    assert any("no such port" in text for text in harness.messages)


async def test_disconnecting_stops_claiming_the_readings_are_current(station) -> None:
    """Closing the link parks the readbacks at Idle instead of freezing them."""
    harness, fake = station
    await harness.tick("poll")
    harness.clear()

    await harness.write("CONNECTION", DISCONNECT=True)

    assert "close" in fake.calls
    assert harness.latest("WEATHER_PARAMETERS").state is IPState.IDLE
    lights = harness.latest("WEATHER_STATUS")
    assert all(light.value is IPState.IDLE for light in lights.elements)


async def test_the_station_identifies_itself_only_while_connected() -> None:
    """SENSOR_INFO is defined on connect and retracted again on disconnect.

    The property is read off the station, so it has no honest value with the
    link down. `deletes()` is where the retraction shows up, and nowhere else.
    """
    device = WeatherStation()
    device._station = _FakeStation()
    harness = DeviceHarness(device)
    await harness.setup()
    assert "SENSOR_INFO" not in {vector.name for vector in harness.defs()}

    await harness.write("CONNECTION", CONNECT=True)

    info = harness.latest("SENSOR_INFO")
    assert info.get("MODEL") == "Fake WS-1"
    assert info.get("FIRMWARE") == "0.1"

    await harness.write("CONNECTION", DISCONNECT=True)

    assert [msg.name for msg in harness.deletes()] == ["SENSOR_INFO"]


async def test_reconnecting_defines_the_station_info_again(station) -> None:
    """Define, delete and define again is the normal life of the property."""
    harness, _fake = station
    await harness.write("CONNECTION", DISCONNECT=True)
    harness.clear()

    await harness.write("CONNECTION", CONNECT=True)

    assert harness.latest("SENSOR_INFO").get("MODEL") == "Fake WS-1"


async def test_disconnecting_settles_a_latched_reset(station) -> None:
    """A reset left at Alert does not survive the link going down.

    Nothing is going to clear it once the station is unreachable, so the hook
    settles it with everything else rather than leaving a red control behind.
    """
    harness, fake = station
    fake.fail_reset = True
    await harness.write("STATION_RESET", RESET=True)
    assert harness.latest("STATION_RESET").state is IPState.ALERT

    await harness.write("CONNECTION", DISCONNECT=True)

    assert harness.latest("STATION_RESET").state is IPState.IDLE


# --------------------------------------------------------------------------- #
# Polling                                                                      #
# --------------------------------------------------------------------------- #
async def test_a_poll_publishes_the_conditions(station) -> None:
    """Nominal conditions land on the property and light every status Ok."""
    harness, _ = station

    await harness.tick("poll")

    conditions = harness.latest("WEATHER_PARAMETERS")
    assert conditions.state is IPState.OK
    assert conditions.get("temperature") == 11.0
    status = harness.latest("WEATHER_STATUS")
    assert status.state is IPState.OK
    assert all(light.value is IPState.OK for light in status.elements)


async def test_an_out_of_range_condition_raises_its_own_light(station) -> None:
    """One unsafe reading alerts its light and the vector, not the others."""
    harness, fake = station
    fake.readings["wind_speed"] = 65.0

    await harness.tick("poll")

    status = harness.latest("WEATHER_STATUS")
    assert status.state is IPState.ALERT
    assert status.get("wind_speed") is IPState.ALERT
    assert status.get("temperature") is IPState.OK


async def test_steady_conditions_go_quiet_on_the_wire(station) -> None:
    """emit="on_change" stops a steady station republishing every second."""
    harness, _ = station
    await harness.tick("poll")
    harness.clear()

    await harness.tick("poll")
    await harness.tick("poll")

    assert harness.sets("WEATHER_PARAMETERS") == []
    assert harness.sets("WEATHER_STATUS") == []


async def test_a_changed_condition_still_publishes(station) -> None:
    """Going quiet must not mean going deaf: real movement is still published."""
    harness, fake = station
    await harness.tick("poll")
    harness.clear()

    fake.readings["temperature"] = 30.0
    await harness.tick("poll")

    assert len(harness.sets("WEATHER_PARAMETERS")) == 1


async def test_a_silent_station_parks_the_readbacks_and_reports_once(station) -> None:
    """Lost comms drop to Idle and are reported once, not once per poll."""
    harness, fake = station
    fake.fail_read = True

    await harness.tick("poll")
    await harness.tick("poll")
    await harness.tick("poll")

    assert harness.latest("WEATHER_PARAMETERS").state is IPState.IDLE
    assert len([t for t in harness.messages if "not answering" in t]) == 1


async def test_recovery_is_announced(station) -> None:
    """A station that comes back says so, once."""
    harness, fake = station
    fake.fail_read = True
    await harness.tick("poll")
    fake.fail_read = False

    await harness.tick("poll")

    assert any("answering again" in text for text in harness.messages)
    assert harness.latest("WEATHER_PARAMETERS").state is IPState.OK


async def test_a_slow_station_does_not_stall_the_event_loop(station) -> None:
    """The blocking read runs in a thread, so the reactor keeps turning."""
    harness, fake = station
    fake.read_delay = 0.15
    turns = 0

    async def spin() -> None:
        """Count event-loop turns while the read is in flight."""
        nonlocal turns
        while True:
            await asyncio.sleep(0.01)
            turns += 1

    spinner = asyncio.create_task(spin())
    await harness.tick("poll")
    spinner.cancel()

    assert turns > 3


# --------------------------------------------------------------------------- #
# Client writes                                                                #
# --------------------------------------------------------------------------- #
async def test_reset_reaches_the_station(station) -> None:
    """The reset button commands the station and releases itself on success."""
    harness, fake = station

    await harness.write("STATION_RESET", RESET=True)

    assert "reset" in fake.calls
    reset = harness.latest("STATION_RESET")
    assert reset.state is IPState.OK
    assert reset.get("RESET") is ISState.OFF
    assert any("sensors reset" in text for text in harness.messages)


async def test_a_refused_reset_alerts(station) -> None:
    """A reset the station refuses releases the button and raises the Alert."""
    harness, fake = station
    fake.fail_reset = True

    await harness.write("STATION_RESET", RESET=True)

    reset = harness.latest("STATION_RESET")
    assert reset.state is IPState.ALERT
    assert reset.get("RESET") is ISState.OFF
    assert any("sensors busy" in text for text in harness.messages)


async def test_commands_are_refused_while_disconnected() -> None:
    """require_connected() stops a command reaching a link that is not open."""
    device = WeatherStation()
    device._station = fake = _FakeStation()
    harness = DeviceHarness(device)
    await harness.setup()
    harness.clear()

    await harness.write("STATION_RESET", RESET=True)

    assert "reset" not in fake.calls
    assert any("not connected" in text for text in harness.messages)


# --------------------------------------------------------------------------- #
# Definition                                                                   #
# --------------------------------------------------------------------------- #
async def test_conditions_are_named_from_their_labels() -> None:
    """from_labels/slugify keep element names in step with the client's keys."""
    device = WeatherStation()
    device._station = _FakeStation()
    harness = DeviceHarness(device)
    await harness.setup()

    status = harness.defs("WEATHER_STATUS")[0]
    assert [light.name for light in status.elements] == list(NOMINAL)
    assert [light.label for light in status.elements] == [label for label, *_ in CONDITIONS]
