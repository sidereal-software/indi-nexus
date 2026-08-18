#!/usr/bin/env python3
"""A driver shaped like a real one: a weather station behind a blocking client.

The other examples simulate their hardware in-process, so nothing in them has to
survive a device that is slow, absent, or lying. This one is built the way a site
driver actually is, and exists to be copied:

* the instrument is a **synchronous** client (:class:`_WeatherStationClient`
  below stands in for ``pyserial``, a vendor SDK, or a ``requests`` session),
  reached through :meth:`~indi_nexus.driver.device.Device.off_thread` so a slow
  read never stalls the driver's event loop;
* ``define_connection()`` gives it the standard INDI connect/disconnect
  lifecycle, and ``@every(..., when_connected=True)`` stops polling the moment
  the link goes down;
* a read that fails does not kill the driver or leave stale numbers looking
  live - the readbacks drop to ``Idle`` and the driver says so *once*, not once
  per second;
* the readbacks are declared ``emit="on_change"``, so a station reporting steady
  conditions goes quiet on the wire instead of republishing identical vectors
  forever;
* ``SENSOR_INFO`` is read off the station and therefore defined in
  ``on_connect`` and withdrawn with ``delete_property`` in ``on_disconnect`` -
  the shape every property that only exists while the hardware is reachable
  wants;
* and the whole thing is tested without hardware in
  ``tests/test_weather_example.py``, using
  :class:`~indi_nexus.testing.DeviceHarness`.

Run it under ``indiserver``::

    indiserver ./examples/weather_device.py

or in the web panel without ``indiserver``::

    indi-nexus serve --device examples.weather_device:WeatherStation
"""

from __future__ import annotations

import asyncio
import math
import time

from indi_nexus.driver import Device, every, on_new
from indi_nexus.protocol import (
    IPerm,
    IPState,
    ISState,
    Light,
    Number,
    Switch,
    SwitchVector,
    Text,
    slugify,
)

#: The conditions the station reports, as (label, format, safe low, safe high).
#: Element names are derived from the labels and match the client's dictionary
#: keys, so a reading maps onto the property by name with no translation table.
#: ``slugify`` yields lowercase names (``wind_speed``), which is why this driver
#: reads differently from the rest of the suite; ``openmeteo_device.py`` spells
#: the same readings ``WIND_SPEED`` by hand and shows that alternative.
CONDITIONS = [
    ("Temperature", "%.1f", -40.0, 50.0),
    ("Humidity", "%.0f", 0.0, 90.0),
    ("Wind Speed", "%.1f", 0.0, 40.0),
    ("Cloud Cover", "%.0f", 0.0, 70.0),
]

#: How long the driver waits for a station read before giving up on it.
READ_TIMEOUT_S = 5.0


class WeatherError(RuntimeError):
    """Raised by the station client when a reading cannot be taken."""


class _WeatherStationClient:
    """A blocking stand-in for a vendor library. **Not** part of the SDK.

    Every method here blocks the calling thread, exactly as a serial read or an
    HTTP request would. That is the point: it is what
    :meth:`~indi_nexus.driver.device.Device.off_thread` exists to keep off the
    event loop.

    Parameters
    ----------
    port : str
        The device path or URL the station lives at.
    """

    def __init__(self, port: str) -> None:
        """Record the port; nothing is opened until :meth:`open`."""
        self._port = port
        self._open = False

    def open(self) -> None:
        """Open the link to the station (blocking)."""
        time.sleep(0.05)  # a real link handshakes
        self._open = True

    def close(self) -> None:
        """Close the link to the station (blocking)."""
        self._open = False

    def read_all(self) -> dict[str, float]:
        """Return one full set of readings (blocking).

        Returns
        -------
        readings : dict
            Every condition keyed by its element name.

        Raises
        ------
        WeatherError
            Raised if the link is closed or the station does not answer.
        """
        if not self._open:
            raise WeatherError("station link is not open")
        time.sleep(0.05)  # a real read waits on the wire
        phase = time.time() / 60.0
        return {
            "temperature": 12.0 + 8.0 * math.sin(phase),
            "humidity": 55.0 + 20.0 * math.sin(phase / 2),
            "wind_speed": max(0.0, 8.0 + 12.0 * math.sin(phase / 3)),
            "cloud_cover": max(0.0, 40.0 + 45.0 * math.sin(phase / 5)),
        }

    def identify(self) -> dict[str, str]:
        """Return what the station says it is (blocking).

        Returns
        -------
        info : dict
            The model and firmware revision the station reports.

        Raises
        ------
        WeatherError
            Raised if the link is closed.
        """
        if not self._open:
            raise WeatherError("station link is not open")
        time.sleep(0.05)
        return {"MODEL": "Acme WS-2000", "FIRMWARE": "2.4.1"}

    def reset(self) -> None:
        """Ask the station to restart its own sensors (blocking).

        Raises
        ------
        WeatherError
            Raised if the link is closed.
        """
        if not self._open:
            raise WeatherError("station link is not open")
        time.sleep(0.1)


class WeatherStation(Device):
    """A weather station: conditions, per-condition safety lights, sensor reset."""

    name = "Weather Station"

    def __init__(self, name: str | None = None) -> None:
        """Initialise the device with a closed station link."""
        super().__init__(name)
        self._station = _WeatherStationClient(port="/dev/ttyUSB0")
        # Set while the station is unreachable, so a lost link is reported once
        # rather than on every failed poll.
        self._offline = False

    async def setup(self) -> None:
        """Define the connection switch, the readbacks and the reset button."""
        self.define_connection()
        self.define_number(
            "WEATHER_PARAMETERS",
            [
                Number(name=slugify(label), label=label, format=fmt, min=low, max=high)
                for label, fmt, low, high in CONDITIONS
            ],
            label="Conditions",
            group="Main Control",
            perm=IPerm.RO,
            emit="on_change",
        )
        self.define_light(
            "WEATHER_STATUS",
            Light.from_labels(label for label, *_rest in CONDITIONS),
            label="Status",
            group="Main Control",
            emit="on_change",
        )
        self.define_switch(
            "STATION_RESET",
            [Switch(name="RESET", label="Reset sensors")],
            label="Reset",
            group="Options",
        )
        self.message("Weather station driver ready.")

    # -- connection lifecycle ----------------------------------------------- #
    async def on_connect(self) -> None:
        """Open the station link and publish what the station says it is.

        No error handling here on purpose: if the hardware is not there, the
        raise propagates and the SDK rolls ``CONNECTION`` back to disconnected
        with the reason attached.

        ``SENSOR_INFO`` is defined here rather than in :meth:`setup` because it
        is *read off the station*: with the link down there is nothing to read
        and nothing honest to publish, so the property should not exist. Its
        counterpart is the ``delete_property`` in :meth:`on_disconnect`.
        """
        await self.off_thread(self._station.open)
        self._offline = False
        info = await self.off_thread(self._station.identify)
        self.define_text(
            "SENSOR_INFO",
            [
                Text(name="MODEL", label="Model", value=info["MODEL"]),
                Text(name="FIRMWARE", label="Firmware", value=info["FIRMWARE"]),
            ],
            label="Station",
            group="Options",
            perm=IPerm.RO,
        )

    async def on_disconnect(self) -> None:
        """Close the link and stop claiming the last readings are current."""
        await self.off_thread(self._station.close)
        # Withdraw what only exists while the station is reachable. Deleting a
        # name that is not defined is a no-op, so this is correct on the first
        # disconnect and on every one after it - no guard needed.
        self.delete_property("SENSOR_INFO", "only while connected")
        self["WEATHER_PARAMETERS"].set(state=IPState.IDLE, force=True)
        self["WEATHER_STATUS"].set_all(IPState.IDLE, state=IPState.IDLE, force=True)
        # A failed reset latches STATION_RESET at Alert; nothing is going to
        # clear it now that the link is down, so settle it with the rest.
        self["STATION_RESET"].set(state=IPState.IDLE)

    # -- polling ------------------------------------------------------------ #
    @every(seconds=1, when_connected=True)
    async def poll(self) -> None:
        """Read the station and publish the conditions and their safety lights.

        ``when_connected=True`` stops this by itself while disconnected, so the
        only failure left to handle is a station that is connected but silent.
        The timeout bounds how long the *driver* waits, not how long the worker
        thread runs - a blocking call cannot be cancelled - which is the honest
        guarantee: the properties stop claiming to be current on time, and the
        orphaned read finishes into nothing.
        """
        try:
            async with asyncio.timeout(READ_TIMEOUT_S):
                readings = await self.off_thread(self._station.read_all)
        except (WeatherError, TimeoutError) as exc:
            self._go_offline(exc)
            return

        if self._offline:
            self._offline = False
            self.message("Station is answering again.")
        self["WEATHER_PARAMETERS"].set(readings, state=IPState.OK)
        self._update_status(readings)

    def _go_offline(self, exc: BaseException) -> None:
        """Park the readbacks at Idle and report the loss exactly once.

        Parameters
        ----------
        exc : BaseException
            The failure from the station client, quoted in the report.
        """
        self["WEATHER_PARAMETERS"].set(state=IPState.IDLE)
        self["WEATHER_STATUS"].set_all(IPState.IDLE, state=IPState.IDLE)
        if not self._offline:
            self._offline = True
            self.log_error(f"Station is not answering: {exc}")

    def _update_status(self, readings: dict[str, float]) -> None:
        """Light one status light per condition and roll them up to the vector.

        Parameters
        ----------
        readings : dict
            One full set of readings, keyed by element name.
        """
        lights: dict[str, IPState] = {}
        for label, _fmt, low, high in CONDITIONS:
            key = slugify(label)
            reading = readings.get(key)
            if reading is None:
                lights[key] = IPState.IDLE
            else:
                lights[key] = IPState.OK if low <= reading <= high else IPState.ALERT
        worst = IPState.ALERT if IPState.ALERT in lights.values() else IPState.OK
        self["WEATHER_STATUS"].set(lights, state=worst)

    # -- client writes ------------------------------------------------------ #
    @on_new("STATION_RESET")
    async def _reset(self, vector: SwitchVector) -> None:
        """Restart the station's sensors, reporting whether the command took."""
        if not self.require_connected():
            return
        if vector.selected() != "RESET":
            return
        reset = self.switch("STATION_RESET")
        reset.set(RESET=ISState.ON, state=IPState.BUSY)
        try:
            await self.off_thread(self._station.reset)
        except WeatherError as exc:
            reset.set(RESET=ISState.OFF, state=IPState.ALERT)
            self.log_error(f"Sensor reset failed: {exc}")
            return
        reset.set(RESET=ISState.OFF, state=IPState.OK)
        self.message("Station sensors reset.")


if __name__ == "__main__":
    WeatherStation.run()
