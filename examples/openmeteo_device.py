#!/usr/bin/env python3
"""A weather driver for a real public data source: Open-Meteo.

Most example drivers simulate their hardware. This one talks to something that
actually exists - the free `Open-Meteo <https://open-meteo.com>`_ forecast API,
which needs no account and no API key - so you can run it right now and see real
sky conditions for your own site.

It is also the shape almost every real driver has:

* a **blocking** client (``urllib``, standing in for ``pyserial`` or a vendor
  SDK) kept off the event loop with :meth:`~indi_nexus.driver.device.Device.off_thread`;
* the standard Connect lifecycle, where connecting means "prove we can reach it";
* readings that go ``Idle`` - not stale - when the source stops answering;
* a writable site location, so the operator can point it anywhere;
* ``emit="on_change"`` throughout, because the weather does not change every tick.

Run it in the web panel::

    indi-nexus serve --device examples.openmeteo_device:OpenMeteo

or under ``indiserver``::

    indiserver ./examples/openmeteo_device.py

The guide that builds this driver step by step is
``docs/guides/tutorial-open-meteo.md``.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from indi_nexus.driver import Device, every, on_new
from indi_nexus.protocol import (
    IPerm,
    IPState,
    Light,
    Number,
    NumberVector,
    Text,
)

#: The API. No key, no account, no rate limit worth worrying about at 1 poll/5 min.
API_URL = "https://api.open-meteo.com/v1/forecast"

#: How long to wait for the API before giving up on a single poll.
TIMEOUT_S = 10.0

#: The readings we ask for, publish **and judge**, as
#: (API field, element name, label, safe low, safe high). The safe range drives
#: that reading's status light: outside it, the light goes Alert.
READINGS = [
    ("temperature_2m", "TEMPERATURE", "Temperature", -20.0, 110.0),
    ("relative_humidity_2m", "HUMIDITY", "Humidity", 0.0, 90.0),
    ("cloud_cover", "CLOUD_COVER", "Cloud cover", 0.0, 30.0),
    ("wind_speed_10m", "WIND_SPEED", "Wind speed", 0.0, 25.0),
    ("wind_gusts_10m", "WIND_GUST", "Wind gust", 0.0, 35.0),
    ("pressure_msl", "PRESSURE", "Pressure", 900.0, 1100.0),
]

#: Readings published but not judged, as (API field, element name, label).
#: A compass bearing has no "safe range", and apparent temperature is context
#: for the real one rather than a limit of its own - so neither gets a light.
CONTEXT: list[tuple[str, str, str]] = [
    ("wind_direction_10m", "WIND_DIRECTION", "Wind from"),
    ("apparent_temperature", "FEELS_LIKE", "Feels like"),
]

#: Every reading published, judged or not, as (API field, element, label).
PUBLISHED: list[tuple[str, str, str]] = [
    (field, element, label) for field, element, label, *_range in READINGS
] + CONTEXT

#: WMO weather codes, condensed to the distinctions an observer cares about.
#: https://open-meteo.com/en/docs has the full table.
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Freezing fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Light showers",
    81: "Showers",
    82: "Violent showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Severe thunderstorm with hail",
}

#: Codes that mean water is falling out of the sky. The dome should be shut.
WET_CODES = frozenset(range(51, 100))


def describe(code: Any) -> str:
    """Return the human description of a WMO weather code.

    Parameters
    ----------
    code : object
        The ``weather_code`` value from the API.

    Returns
    -------
    description : str
        A short phrase, or ``"Unknown (<code>)"`` for a code not in the table.
    """
    return WEATHER_CODES.get(int(code), f"Unknown ({code})")


def moon_phase_name(fraction: float) -> str:
    """Return the name of a moon phase given Open-Meteo's 0-1 fraction.

    Parameters
    ----------
    fraction : float
        0 and 1 are new moon, 0.5 is full.

    Returns
    -------
    name : str
        The phase name, e.g. ``"Waxing gibbous"``.
    """
    names = [
        "New moon",
        "Waxing crescent",
        "First quarter",
        "Waxing gibbous",
        "Full moon",
        "Waning gibbous",
        "Last quarter",
        "Waning crescent",
    ]
    # Eight phases around the cycle, each centred on its eighth.
    return names[int((fraction % 1.0) * 8 + 0.5) % 8]


class OpenMeteoClient:
    """A blocking Open-Meteo client. Every call here blocks its thread.

    Deliberately plain ``urllib``: it stands in for the synchronous instrument
    library a real driver talks to, and keeps the example dependency-free.
    """

    def fetch(self, latitude: float, longitude: float) -> dict[str, Any]:
        """Fetch the current conditions and today's almanac (blocking).

        Parameters
        ----------
        latitude : float
            Site latitude in degrees, positive north.
        longitude : float
            Site longitude in degrees, positive east.

        Returns
        -------
        payload : dict
            The decoded JSON response.

        Raises
        ------
        OSError
            Raised if the request fails or the response is not JSON.
        """
        query = urllib.parse.urlencode(
            {
                "latitude": f"{latitude:.4f}",
                "longitude": f"{longitude:.4f}",
                "current": ",".join(
                    [field for field, *_rest in PUBLISHED] + ["is_day", "weather_code"]
                ),
                "daily": "sunrise,sunset,moon_phase",
                "forecast_days": 1,
                "timezone": "GMT",
            }
        )
        try:
            with urllib.request.urlopen(f"{API_URL}?{query}", timeout=TIMEOUT_S) as response:
                payload: dict[str, Any] = json.load(response)
        except Exception as exc:  # urllib raises a zoo of types; they all mean "no data"
            raise OSError(f"Open-Meteo request failed: {exc}") from exc
        if "current" not in payload:
            raise OSError(f"Open-Meteo returned no current conditions: {payload}")
        return payload


class OpenMeteo(Device):
    """Sky conditions for one site, from the Open-Meteo public API."""

    name = "Open-Meteo"

    def __init__(self, name: str | None = None, *, client: OpenMeteoClient | None = None) -> None:
        """Initialise the device pointing at Los Angeles until told otherwise."""
        super().__init__(name)
        self._client = client if client is not None else OpenMeteoClient()
        self._latitude = 34.0522
        self._longitude = -118.2437
        # Set while the API is unreachable, so a lost source is reported once
        # rather than on every poll.
        self._offline = False

    async def setup(self) -> None:
        """Define the site, the readings, their status lights and the almanac."""
        self.define_connection()
        self.define_number(
            "GEOGRAPHIC_COORD",  # the standard INDI name for "where the site is"
            [
                Number(
                    name="LAT",
                    label="Latitude",
                    format="%.4f",
                    min=-90,
                    max=90,
                    value=self._latitude,
                ),
                Number(
                    name="LONG",
                    label="Longitude",
                    format="%.4f",
                    min=-180,
                    max=180,
                    value=self._longitude,
                ),
            ],
            label="Site",
            group="Site",
        )
        self.define_number(
            "WEATHER_PARAMETERS",  # the standard INDI name for weather readings
            [
                Number(name=element, label=label, format="%.1f")
                for _field, element, label in PUBLISHED
            ],
            label="Conditions",
            group="Main Control",
            perm=IPerm.RO,
            emit="on_change",
        )
        self.define_light(
            "WEATHER_STATUS",
            [Light(name=element, label=label) for _f, element, label, *_r in READINGS],
            label="Status",
            group="Main Control",
            emit="on_change",
        )
        self.define_text(
            "SKY",
            [
                Text(name="CONDITIONS", label="Conditions"),
                Text(name="DAYLIGHT", label="Daylight"),
            ],
            label="Sky",
            group="Main Control",
            perm=IPerm.RO,
            emit="on_change",
        )
        self.define_text(
            "ALMANAC",
            [
                Text(name="SUNRISE", label="Sunrise (UTC)"),
                Text(name="SUNSET", label="Sunset (UTC)"),
                Text(name="MOON_PHASE", label="Moon phase"),
            ],
            label="Almanac",
            group="Almanac",
            perm=IPerm.RO,
            emit="on_change",
        )
        self.message("Open-Meteo driver ready. Press Connect to fetch.")

    # -- connection lifecycle ----------------------------------------------- #
    async def on_connect(self) -> None:
        """Prove the API is reachable, and publish the first reading.

        Connecting to a web service means "can I actually reach it?", so this
        does one real fetch. If it raises, the SDK rolls the Connect switch back
        and shows the reason - which is exactly right for a site that is offline.
        """
        payload = await self.off_thread(self._client.fetch, self._latitude, self._longitude)
        self._publish(payload)
        self._offline = False

    async def on_disconnect(self) -> None:
        """Stop claiming the last readings are current."""
        self["WEATHER_PARAMETERS"].set(state=IPState.IDLE, force=True)
        self["WEATHER_STATUS"].set_all(IPState.IDLE, state=IPState.IDLE, force=True)
        self["SKY"].set(state=IPState.IDLE, force=True)

    # -- polling ------------------------------------------------------------ #
    @every(minutes=5, when_connected=True)
    async def poll(self) -> None:
        """Refetch the conditions.

        Five minutes, not one second: this is a forecast service updating on the
        quarter hour, and hammering a free public API is bad manners. The
        interval is the only thing that changes for a slow source - everything
        else about the driver is the same.
        """
        try:
            payload = await self.off_thread(self._client.fetch, self._latitude, self._longitude)
        except OSError as exc:
            self._go_offline(exc)
            return
        if self._offline:
            self._offline = False
            self.message("Open-Meteo is answering again.")
        self._publish(payload)

    def _go_offline(self, exc: BaseException) -> None:
        """Park the readings at Idle and report the loss exactly once.

        Parameters
        ----------
        exc : BaseException
            The failure, quoted in the report.
        """
        self["WEATHER_PARAMETERS"].set(state=IPState.IDLE)
        self["WEATHER_STATUS"].set_all(IPState.IDLE, state=IPState.IDLE)
        if not self._offline:
            self._offline = True
            self.log_error(f"Open-Meteo is not answering: {exc}")

    # -- publishing --------------------------------------------------------- #
    def _publish(self, payload: dict[str, Any]) -> None:
        """Turn one API response into property updates.

        Parameters
        ----------
        payload : dict
            A decoded Open-Meteo response.
        """
        current = payload.get("current", {})
        units = payload.get("current_units", {})

        readings = {
            element: float(current[field])
            for field, element, _label in PUBLISHED
            if current.get(field) is not None
        }
        self["WEATHER_PARAMETERS"].set(readings, state=IPState.OK)
        self._label_units(units)
        self._update_status(readings, current)
        self._publish_sky(current)
        self._publish_almanac(payload.get("daily", {}))

    def _label_units(self, units: dict[str, Any]) -> None:
        """Fold the API's unit strings into the element labels, once.

        The API reports whether it is sending Fahrenheit or Celsius, mph or km/h,
        so the labels can say so rather than the driver guessing.

        Parameters
        ----------
        units : dict
            The response's ``current_units`` block.
        """
        parameters = self.number("WEATHER_PARAMETERS")
        for field, element, label in PUBLISHED:
            unit = units.get(field)
            if not unit:
                continue
            wanted = f"{label} ({unit})"
            member = parameters.vector.element(element)
            if member.label != wanted:
                member.label = wanted

    def _update_status(self, readings: dict[str, float], current: dict[str, Any]) -> None:
        """Light one status light per reading, Ok inside its safe range else Alert.

        Parameters
        ----------
        readings : dict
            The published values, keyed by element name.
        current : dict
            The response's ``current`` block, for the weather code.
        """
        lights: dict[str, IPState] = {}
        for _field, element, _label, low, high in READINGS:
            value = readings.get(element)
            if value is None:
                lights[element] = IPState.IDLE
            else:
                lights[element] = IPState.OK if low <= value <= high else IPState.ALERT
        # Precipitation overrides everything: if it is raining, it is not safe,
        # whatever the individual numbers say.
        raining = int(current.get("weather_code", 0)) in WET_CODES
        worst = IPState.ALERT if raining or IPState.ALERT in lights.values() else IPState.OK
        self["WEATHER_STATUS"].set(lights, state=worst)

    def _publish_sky(self, current: dict[str, Any]) -> None:
        """Publish the plain-language sky description and day/night flag.

        Parameters
        ----------
        current : dict
            The response's ``current`` block.
        """
        conditions = describe(current.get("weather_code", 0))
        daylight = "Day" if int(current.get("is_day", 0)) else "Night"
        self["SKY"].set(CONDITIONS=conditions, DAYLIGHT=daylight, state=IPState.OK)

    def _publish_almanac(self, daily: dict[str, Any]) -> None:
        """Publish sunrise, sunset and the moon phase.

        The daily block is a list per field, one entry per forecast day, and we
        ask for one day - so index 0 is today.

        Parameters
        ----------
        daily : dict
            The response's ``daily`` block.
        """

        def first(field: str) -> Any:
            """Return today's value for one daily field, or None."""
            values = daily.get(field) or []
            return values[0] if values else None

        sunrise, sunset, phase = first("sunrise"), first("sunset"), first("moon_phase")
        if sunrise is None or sunset is None or phase is None:
            return
        self["ALMANAC"].set(
            SUNRISE=str(sunrise).replace("T", " "),
            SUNSET=str(sunset).replace("T", " "),
            MOON_PHASE=f"{moon_phase_name(float(phase))} ({float(phase):.2f})",
            state=IPState.OK,
        )

    # -- client writes ------------------------------------------------------ #
    @on_new("GEOGRAPHIC_COORD")
    async def _move_site(self, vector: NumberVector) -> None:
        """Point the driver at a different site and refetch immediately.

        The sanctioned exception to "every handler opens with
        ``require_connected()``": the site is the driver's own configuration
        rather than a command to hardware, so an operator may move it while
        disconnected. The connection is still checked - below, and only around
        the part that actually goes out to the network.
        """
        self._latitude = vector.get("LAT", self._latitude)
        self._longitude = vector.get("LONG", self._longitude)
        site = self["GEOGRAPHIC_COORD"]
        site.set(LAT=self._latitude, LONG=self._longitude, state=IPState.BUSY)

        if not self.connected:
            site.set(state=IPState.OK)
            return
        try:
            payload = await self.off_thread(self._client.fetch, self._latitude, self._longitude)
        except OSError as exc:
            site.set(state=IPState.ALERT)
            self._go_offline(exc)
            return
        site.set(state=IPState.OK)
        self._publish(payload)
        self.message(f"Now reporting for {self._latitude:.4f}, {self._longitude:.4f}.")


if __name__ == "__main__":
    OpenMeteo.run()
