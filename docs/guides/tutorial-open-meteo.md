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

The stock `DevicePanel` renders *anything* - it builds itself from whatever the
device says it has, which is exactly right for commissioning and exactly wrong
at 3 a.m. When you know the device, you can build the screen the job wants.

The finished dashboard is `web/apps/panel/demo/sky-report.tsx` (the layout) and
`sky-visuals.tsx` (the drawn figures). It is built entirely from
`@indi-nexus/react`: the hooks for data, the shadcn primitives that package
re-exports for the chrome, and plain SVG for the rest.

### Reading a value and its verdict together

Almost every tile wants the same two things, so that is one small hook:

```tsx
function useReading(element: string) {
  const value = useNumber("Open-Meteo", "WEATHER_PARAMETERS", element);
  const state = useLight("Open-Meteo", "WEATHER_STATUS", element);
  return { value, state: state ?? "Idle" };
}
```

Then a tile is just markup:

```tsx
const cloud = useReading("CLOUD_COVER");
<Meter label="Cloud cover" value={cloud.value} max={100} limit={30} unit="%" state={cloud.state} />
```

### Choosing the form before the colour

The figures are not decoration, and each is the form its data asks for:

| Reading | Form | Why |
|---|---|---|
| Wind direction | **compass** | The one genuinely *angular* reading, which is the one case a dial beats a bar. The arrow sits on the bearing the wind comes from, like a weather vane. |
| Cloud cover, humidity | **meter** with the limit ticked | A ratio against a limit. Not a dial, and not a two-slice pie. |
| Pressure | **a number** | It has no meaningful 0-to-max, so a bar would just always look nearly full. |
| Temperature | **hero figure** | The one number the screen leads with. Exactly one per view. |
| Moon phase | **the moon**, at its real illuminated fraction | The lit limb is a semicircle; the terminator is a half-ellipse of radius `r·cos 2πp`, which is what makes a crescent bow one way and a gibbous the other. |
| Site | **a projected graticule** | Straight parallels, meridians curving to the poles, so it reads as a globe rather than a grid - and the marker uses the same projection, so its position is right rather than approximately right. |

### Three rules the dashboard follows

- **Status is never colour alone.** The theme's Alert red and Busy amber are
  only ΔE 4.4 apart under deuteranopia, so every state is also written out -
  `StateBadge` carries the word, not just the colour.
- **Colour comes from theme tokens, never hex.** The figures use
  `fill-state-*`, `fill-chart-3`, `stroke-border`, so they follow light and dark
  and any retheme for free. One trap: the moon's unlit disc is
  `fill-foreground/20`, not `fill-foreground` - in dark mode `foreground` is
  *light*, which would erase the phase entirely.
- **The verdict is the driver's, not the UI's.** "Safe to open" reads
  `WEATHER_STATUS.state`, the state the driver computed. The safety rule lives
  in one place, so this screen, the stock panel and any script all agree.

### And it stays live

Every hook re-renders only its own reading, so a change to the cloud cover
repaints one meter rather than the page; and every hook returns `undefined`
until the driver has published, so the whole screen renders correctly before any
data has arrived.

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
