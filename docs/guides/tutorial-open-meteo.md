# Tutorial: a driver for real data, and a UI for it

The simulators are useful for learning the shape of a driver, but they never
surprise you. This tutorial builds a driver for something that actually exists -
[Open-Meteo](https://open-meteo.com), a free weather API with no account and no
key - and then a custom screen for it.

At the end you will have real sky conditions for your own site, in a panel you
designed.

**[See it running first](../weather-demo/weather.html)** - the finished driver and
the custom screen, both in your browser, with no install. Press Connect.

The finished code is `examples/openmeteo_device.py`, and its tests are
`tests/test_openmeteo_example.py`.

## What we are building

A weather device that reports:

- **Conditions** - temperature, humidity, cloud cover, wind, gusts, pressure.
- **Status** - one light per reading, `Ok` inside its safe range and `Alert`
  outside it, so an operator can glance rather than read.
- **Sky** - a plain-language description, and whether it is day or night.
- **Almanac** - today's sunrise, sunset and moon phase.
- **Site** - the latitude and longitude, which the operator can change.

## 1. Ask for only what you need

Open-Meteo will return a wall of data if you ask for it. Ask for less:

```
https://api.open-meteo.com/v1/forecast
  ?latitude=34.0522&longitude=-118.2437
  &current=temperature_2m,relative_humidity_2m,cloud_cover,wind_speed_10m,
           wind_gusts_10m,pressure_msl,is_day,weather_code
  &daily=sunrise,sunset,moon_phase
  &forecast_days=1&timezone=GMT
```

The reply's interesting parts:

```json
{
  "current_units": { "temperature_2m": "°F", "wind_speed_10m": "mp/h" },
  "current": {
    "temperature_2m": 66.9, "relative_humidity_2m": 95, "cloud_cover": 31,
    "wind_speed_10m": 2.4, "wind_gusts_10m": 2.5, "pressure_msl": 1008.2,
    "is_day": 0, "weather_code": 1
  },
  "daily": {
    "sunrise": ["2026-08-03T13:06"], "sunset": ["2026-08-04T02:52"],
    "moon_phase": [0.659]
  }
}
```

Two things to notice, because they shape the driver:

- **The API tells you its units.** `current_units` says whether you are getting
  °F or °C. The driver uses that for its labels instead of guessing.
- **`daily` is a list per field**, one entry per forecast day. We ask for one
  day, so index `0` is today.

## 2. One table drives everything

Rather than repeating field names across the definitions, the readings, and the
safety checks, put them in one place:

```python
#: (API field, element name, label, safe low, safe high)
READINGS = [
    ("temperature_2m",       "TEMPERATURE",  "Temperature", -20.0, 110.0),
    ("relative_humidity_2m", "HUMIDITY",     "Humidity",      0.0,  90.0),
    ("cloud_cover",          "CLOUD_COVER",  "Cloud cover",   0.0,  30.0),
    ("wind_speed_10m",       "WIND_SPEED",   "Wind speed",    0.0,  25.0),
    ("wind_gusts_10m",       "WIND_GUST",    "Wind gust",     0.0,  35.0),
    ("pressure_msl",         "PRESSURE",     "Pressure",    900.0, 1100.0),
]
```

Now the properties build themselves, and the safe ranges cannot drift out of
step with the readings:

```python
self.define_number(
    "WEATHER_PARAMETERS",                     # the standard INDI name for this
    [Number(name=element, label=label, format="%.1f")
     for _field, element, label, *_range in READINGS],
    perm=IPerm.RO,
    emit="on_change",                         # the weather is not news every tick
)
self.define_light(
    "WEATHER_STATUS",
    [Light(name=element, label=label) for _f, element, label, *_r in READINGS],
    emit="on_change",
)
```

## 3. The network call is a blocking call

`urllib` blocks. So does `requests`, and so does every serial library. Wrap it in
a small client and keep it off the event loop:

```python
class OpenMeteoClient:
    def fetch(self, latitude: float, longitude: float) -> dict[str, Any]:
        ...                                    # plain blocking urllib
```

```python
payload = await self.off_thread(self._client.fetch, self._latitude, self._longitude)
```

Without `off_thread`, a slow API freezes the whole driver until it answers.

## 4. Connecting means "prove you can reach it"

For hardware, Connect opens a port. For a web service, it means: can I actually
get an answer? So `on_connect` does one real fetch and publishes it:

```python
async def on_connect(self) -> None:
    payload = await self.off_thread(self._client.fetch, self._latitude, self._longitude)
    self._publish(payload)
    self._offline = False
```

There is no error handling here on purpose. If the fetch raises, the SDK puts
the Connect switch back to Disconnected and shows the reason - which is exactly
what should happen at a site whose internet is down.

## 5. Poll slowly, and cope with silence

```python
@every(minutes=5, when_connected=True)
async def poll(self) -> None:
    try:
        payload = await self.off_thread(self._client.fetch, self._latitude, self._longitude)
    except OSError as exc:
        self._go_offline(exc)
        return
    if self._offline:
        self._offline = False
        self.message("Open-Meteo is answering again.")
    self._publish(payload)
```

Five minutes, not one second - it is a forecast service, and hammering a free
public API is bad manners. `when_connected=True` means it stops on its own when
disconnected.

When the API goes quiet, the readings drop to `Idle` rather than sitting there
looking current, and the driver says so **once**:

```python
def _go_offline(self, exc: BaseException) -> None:
    self["WEATHER_PARAMETERS"].set(state=IPState.IDLE)
    self["WEATHER_STATUS"].set_all(IPState.IDLE, state=IPState.IDLE)
    if not self._offline:
        self._offline = True
        self.log_error(f"Open-Meteo is not answering: {exc}")
```

## 6. Turn readings into a verdict

Numbers are for reading; lights are for glancing. Each reading gets its own
light, and the vector takes the worst of them - plus one override, because if it
is raining nothing else matters:

```python
lights[element] = IPState.OK if low <= value <= high else IPState.ALERT
...
raining = int(current.get("weather_code", 0)) in WET_CODES
worst = IPState.ALERT if raining or IPState.ALERT in lights.values() else IPState.OK
self["WEATHER_STATUS"].set(lights, state=worst)
```

## 7. Let the operator move the site

Latitude and longitude are a writable property, so the device is not nailed to
one place:

```python
@on_new("GEOGRAPHIC_COORD")
async def _move_site(self, vector: NumberVector) -> None:
    self._latitude = vector.get("LAT", self._latitude)
    self._longitude = vector.get("LONG", self._longitude)
    ...
```

`get(name, default)` matters here: a client that changes only the latitude sends
only the latitude, and the longitude must survive that.

## 8. Run it

```bash
python -m examples.demo_bridge --device examples.openmeteo_device:OpenMeteo
```

Open <http://localhost:8000/>, press **Connect**, and it is real weather. Edit
the Site latitude and longitude and it follows you.

## 9. A screen of your own

The stock `DevicePanel` shows everything, which is right for commissioning and
wrong for 3 a.m. Here is a purpose-built screen, using the hooks: the numbers an
operator checks before opening, and a single verdict.

```tsx
import {
  IndiProvider, StateBadge, useLight, useNumber, useProperty, useText,
} from "@indi-nexus/react";
import "@indi-nexus/react/styles.css";

/** One reading: its value, and the safety light beside it. */
function Reading({ element, label }: { element: string; label: string }) {
  const value = useNumber("Open-Meteo", "WEATHER_PARAMETERS", element);
  const status = useLight("Open-Meteo", "WEATHER_STATUS", element);
  return (
    <div className="flex items-baseline justify-between gap-4 border-b py-2">
      <span className="text-muted-foreground text-sm">{label}</span>
      <span className="flex items-center gap-2">
        <span className="font-mono text-2xl tabular-nums">{value ?? "--"}</span>
        <StateBadge state={status ?? "Idle"} />
      </span>
    </div>
  );
}

export function SkyReport() {
  const conditions = useText("Open-Meteo", "SKY", "CONDITIONS");
  const daylight = useText("Open-Meteo", "SKY", "DAYLIGHT");
  const sunset = useText("Open-Meteo", "ALMANAC", "SUNSET");
  const moon = useText("Open-Meteo", "ALMANAC", "MOON_PHASE");
  const overall = useProperty("Open-Meteo", "WEATHER_STATUS");

  return (
    <section className="mx-auto max-w-md space-y-4 p-6">
      <header className="space-y-1">
        <h1 className="font-semibold text-3xl">{conditions || "Waiting for data"}</h1>
        <p className="text-muted-foreground text-sm">
          {daylight || "--"} &middot; sunset {sunset || "--"} &middot; {moon || "--"}
        </p>
      </header>

      <div>
        <Reading element="CLOUD_COVER" label="Cloud cover" />
        <Reading element="WIND_SPEED" label="Wind" />
        <Reading element="WIND_GUST" label="Gusts" />
        <Reading element="HUMIDITY" label="Humidity" />
        <Reading element="TEMPERATURE" label="Temperature" />
      </div>

      <p className="text-sm">{overall?.state === "Ok" ? "Safe to open." : "Not safe to open."}</p>
    </section>
  );
}

export const App = () => (
  <IndiProvider url="ws://localhost:8000/ws">
    <SkyReport />
  </IndiProvider>
);
```

Points worth noticing:

- **Nothing polls.** Each `useNumber` / `useText` re-renders only when *that*
  value changes. Change the cloud cover and the cloud cover line updates; the
  rest of the screen does not re-render.
- **Placeholders everywhere.** The hooks return `undefined` until the driver has
  published, so the screen renders correctly before any data arrives. Note the
  two different operators: numbers use `?? "--"` (because `0` is a real reading
  and must not be replaced), text uses `|| "--"` (because the driver defines
  those elements as empty strings, which `??` would happily print).
- **The verdict comes from the driver, not the UI.** `WEATHER_STATUS.state` is
  the driver's judgement. The safety rule lives in one place, and every client -
  this screen, the stock panel, a script - agrees about it.

## 10. Test both halves

The driver is tested against a **recorded real response**, so the field names
are not guesses:

```python
async def test_status_lights_flag_the_readings_that_are_out_of_range(site):
    harness, _ = site
    await harness.tick("poll")

    status = harness.latest("WEATHER_STATUS")
    assert status.get("TEMPERATURE") is IPState.OK
    assert status.get("HUMIDITY") is IPState.ALERT     # 95% - damp
    assert status.state is IPState.ALERT               # the vector takes the worst
```

And the UI is tested against the vectors that driver really emits, so the two
halves are checked where they meet - see
`web/packages/react/src/doc-snippets.test.tsx`.

## The same thing, running

Everything above is on the [weather demo page](../weather-demo/weather.html): the
driver ported to TypeScript so it runs in the browser, the stock panel, and the
custom screen, switchable. It calls the real Open-Meteo API from your browser,
and falls back to a recorded response if it cannot reach it.

## Where to take it

- Add a **safety switch** the dome driver can watch, so it closes itself when
  this device goes to `Alert`.
- Swap Open-Meteo for your own weather station: everything except
  `OpenMeteoClient.fetch` stays as it is.
- Add the hourly forecast as a second property, so the screen can show what is
  coming as well as what is here.
