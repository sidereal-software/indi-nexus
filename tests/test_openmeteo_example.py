"""Tests for the Open-Meteo driver, against a real recorded API response.

``tests/data/open_meteo_response.json`` is an actual Open-Meteo reply (Los
Angeles, 2026-08-03), with the ``hourly`` block - which the driver never asks
for - removed. Everything asserted here is therefore checked against field names
and value shapes the service really produces, not against a guess.

No network is used: the blocking client is replaced with one that returns the
recording.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from examples.openmeteo_device import OpenMeteo, describe, moon_phase_name
from indi_nexus.protocol import IPState, ISState
from indi_nexus.testing import DeviceHarness

RESPONSE = json.loads((Path(__file__).parent / "data" / "open_meteo_response.json").read_text())


class _FakeApi:
    """A stand-in for the blocking Open-Meteo client."""

    def __init__(self) -> None:
        """Start answering with the recorded response."""
        self.payload = json.loads(json.dumps(RESPONSE))
        self.raises = False
        self.calls: list[tuple[float, float]] = []

    def fetch(self, latitude: float, longitude: float) -> dict:
        """Record the requested site and return the recording."""
        self.calls.append((latitude, longitude))
        if self.raises:
            raise OSError("Open-Meteo request failed: [Errno -3] Temporary failure")
        return json.loads(json.dumps(self.payload))


@pytest.fixture
async def site():
    """Return a connected harness plus the fake API behind it."""
    api = _FakeApi()
    harness = DeviceHarness(OpenMeteo(client=api))
    await harness.setup()
    await harness.write("CONNECTION", CONNECT=True)
    harness.clear()
    return harness, api


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("code", "expected"),
    [(0, "Clear sky"), (1, "Mainly clear"), (3, "Overcast"), (65, "Heavy rain")],
)
def test_weather_codes_are_described(code, expected):
    """The WMO codes the API returns map to readable phrases."""
    assert describe(code) == expected


def test_an_unlisted_weather_code_says_so():
    """A code outside the table is reported rather than silently mislabelled."""
    assert describe(77) == "Unknown (77)"


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [(0.0, "New moon"), (0.25, "First quarter"), (0.5, "Full moon"), (0.659, "Waning gibbous")],
)
def test_moon_phase_names(fraction, expected):
    """Open-Meteo's 0-1 phase fraction becomes a phase name."""
    assert moon_phase_name(fraction) == expected


# --------------------------------------------------------------------------- #
# Connecting                                                                   #
# --------------------------------------------------------------------------- #
async def test_connecting_fetches_and_publishes() -> None:
    """Connect means "prove we can reach it", so it does one real fetch."""
    api = _FakeApi()
    harness = DeviceHarness(OpenMeteo(client=api))
    await harness.setup()

    await harness.write("CONNECTION", CONNECT=True)

    assert api.calls == [(34.0522, -118.2437)]
    assert harness.device.connected
    assert harness.latest("WEATHER_PARAMETERS").get("TEMPERATURE") == 66.9


async def test_an_unreachable_api_leaves_the_device_disconnected() -> None:
    """A site with no internet does not end up claiming live weather."""
    api = _FakeApi()
    api.raises = True
    harness = DeviceHarness(OpenMeteo(client=api))
    await harness.setup()

    await harness.write("CONNECTION", CONNECT=True)

    assert harness.device.connected is False
    assert harness.latest("CONNECTION").state is IPState.ALERT
    assert any("Temporary failure" in text for text in harness.messages)


# --------------------------------------------------------------------------- #
# Publishing the recorded response                                             #
# --------------------------------------------------------------------------- #
async def test_every_reading_lands(site) -> None:
    """Each requested field is published under its INDI element name."""
    harness, _ = site
    await harness.tick("poll")

    readings = harness.latest("WEATHER_PARAMETERS")
    assert readings.state is IPState.OK
    assert readings.values() == {
        "TEMPERATURE": 66.9,
        "HUMIDITY": 95.0,
        "CLOUD_COVER": 31.0,
        "WIND_SPEED": 2.4,
        "WIND_GUST": 2.5,
        "PRESSURE": 1008.2,
    }


async def test_labels_pick_up_the_units_the_api_reports(site) -> None:
    """The API says whether it sent °F or °C, so the labels say so too."""
    harness, _ = site
    await harness.tick("poll")

    parameters = harness.device.number("WEATHER_PARAMETERS")
    labels = {el.name: el.label for el in parameters.vector.elements}
    assert labels["TEMPERATURE"] == "Temperature (°F)"
    assert labels["WIND_SPEED"] == "Wind speed (mp/h)"
    assert labels["HUMIDITY"] == "Humidity (%)"


async def test_status_lights_flag_the_readings_that_are_out_of_range(site) -> None:
    """Each reading is judged on its own range; the vector takes the worst.

    In the recorded response: 66.9°F and 2.4 mph are fine, 95% humidity is
    damp, and 31% cloud cover is just over the 30% the driver calls clear.
    """
    harness, _ = site
    await harness.tick("poll")

    status = harness.latest("WEATHER_STATUS")
    assert status.get("TEMPERATURE") is IPState.OK
    assert status.get("WIND_SPEED") is IPState.OK
    assert status.get("HUMIDITY") is IPState.ALERT
    assert status.get("CLOUD_COVER") is IPState.ALERT
    assert status.state is IPState.ALERT


async def test_a_reading_inside_its_range_stays_ok(site) -> None:
    """Drop the cloud below the threshold and that light clears."""
    harness, api = site
    api.payload["current"]["cloud_cover"] = 12

    await harness.tick("poll")

    assert harness.latest("WEATHER_STATUS").get("CLOUD_COVER") is IPState.OK


async def test_rain_alerts_whatever_the_numbers_say(site) -> None:
    """A wet weather code is unsafe even when every reading looks fine."""
    harness, api = site
    api.payload["current"]["relative_humidity_2m"] = 40
    api.payload["current"]["weather_code"] = 63  # Rain

    await harness.tick("poll")

    assert harness.latest("WEATHER_STATUS").get("HUMIDITY") is IPState.OK
    assert harness.latest("WEATHER_STATUS").state is IPState.ALERT
    assert harness.latest("SKY").get("CONDITIONS") == "Rain"


async def test_sky_reports_conditions_and_daylight(site) -> None:
    """The recorded response is code 1 at night."""
    harness, _ = site
    await harness.tick("poll")

    sky = harness.latest("SKY")
    assert sky.get("CONDITIONS") == "Mainly clear"
    assert sky.get("DAYLIGHT") == "Night"


async def test_almanac_reports_todays_sun_and_moon(site) -> None:
    """Sunrise, sunset and the moon phase come from the daily block."""
    harness, _ = site
    await harness.tick("poll")

    almanac = harness.latest("ALMANAC")
    assert almanac.get("SUNRISE") == "2026-08-03 13:06"
    assert almanac.get("SUNSET") == "2026-08-04 02:52"
    assert almanac.get("MOON_PHASE") == "Waning gibbous (0.66)"


async def test_a_missing_field_is_skipped_rather_than_published_as_zero(site) -> None:
    """A field the API omits must not become a confident 0.0."""
    harness, api = site
    await harness.tick("poll")
    del api.payload["current"]["cloud_cover"]

    await harness.tick("poll")

    assert harness.latest("WEATHER_STATUS").get("CLOUD_COVER") is IPState.IDLE


# --------------------------------------------------------------------------- #
# Failure and recovery                                                         #
# --------------------------------------------------------------------------- #
async def test_a_dead_api_parks_the_readings_and_reports_once(site) -> None:
    """Lost connectivity drops to Idle and is reported once, not once per poll."""
    harness, api = site
    api.raises = True

    await harness.tick("poll")
    await harness.tick("poll")
    await harness.tick("poll")

    assert harness.latest("WEATHER_PARAMETERS").state is IPState.IDLE
    assert len([t for t in harness.messages if "not answering" in t]) == 1


async def test_recovery_is_announced(site) -> None:
    """When the API comes back, it says so."""
    harness, api = site
    api.raises = True
    await harness.tick("poll")
    api.raises = False

    await harness.tick("poll")

    assert any("answering again" in text for text in harness.messages)
    assert harness.latest("WEATHER_PARAMETERS").state is IPState.OK


async def test_steady_weather_goes_quiet(site) -> None:
    """Unchanged conditions are not republished every five minutes."""
    harness, _ = site
    await harness.tick("poll")
    harness.clear()

    await harness.tick("poll")
    await harness.tick("poll")

    assert harness.sets() == []


async def test_disconnecting_stops_claiming_the_readings_are_current(site) -> None:
    """The numbers go Idle rather than sitting there looking live."""
    harness, _ = site
    await harness.tick("poll")
    harness.clear()

    await harness.write("CONNECTION", DISCONNECT=True)

    assert harness.latest("WEATHER_PARAMETERS").state is IPState.IDLE
    assert harness.latest("CONNECTION").get("DISCONNECT") is ISState.ON


# --------------------------------------------------------------------------- #
# Moving the site                                                              #
# --------------------------------------------------------------------------- #
async def test_writing_a_new_site_refetches_for_it(site) -> None:
    """Changing latitude/longitude points the driver somewhere else."""
    harness, api = site

    await harness.write("GEOGRAPHIC_COORD", LAT=-30.2407, LONG=-70.7367)  # La Silla

    assert api.calls[-1] == (-30.2407, -70.7367)
    coord = harness.latest("GEOGRAPHIC_COORD")
    assert coord.state is IPState.OK
    assert coord.get("LAT") == -30.2407
    assert any("Now reporting for -30.2407" in text for text in harness.messages)


async def test_a_partial_site_write_keeps_the_other_half(site) -> None:
    """A client that sends only latitude must not zero the longitude."""
    harness, api = site

    await harness.write("GEOGRAPHIC_COORD", LAT=51.4779)

    assert api.calls[-1] == (51.4779, -118.2437)


async def test_moving_the_site_while_disconnected_does_not_fetch(site) -> None:
    """Editing the location offline is allowed; it just does not call out."""
    harness, api = site
    await harness.write("CONNECTION", DISCONNECT=True)
    before = len(api.calls)

    await harness.write("GEOGRAPHIC_COORD", LAT=51.4779, LONG=-0.0015)

    assert len(api.calls) == before
    assert harness.latest("GEOGRAPHIC_COORD").state is IPState.OK
