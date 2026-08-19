---
search:
  boost: 2
---

# Tutorial: a driver for real data, and a UI for it

This tutorial builds a driver against [Open-Meteo](https://open-meteo.com), a
free weather API that needs no account or key, and then a custom screen for it.
At the end you will have real sky conditions for your own site, on a screen you
laid out yourself.

The simulators elsewhere in these guides show the shape of a driver, but their
readings are invented. These readings are not.

The [finished version runs in your browser](../demo-app/index.html), driver and
custom screen both, with nothing to install. Press Connect and it calls the real
API, falling back to a recorded reply if it cannot reach it. That page runs a
simulated dome alongside this driver, because the custom screen at the end of
this tutorial is a board for a whole observatory rather than for one device.

The finished code is `examples/openmeteo_device.py`, and its tests are
`tests/test_openmeteo_example.py`. Following every step below leaves you with
that file.

## What we are building

A weather device that reports:

- **Conditions** - temperature and what it feels like, humidity, cloud cover,
  wind speed, direction and gusts, pressure.
- **Status** - one light per reading, `Ok` inside its safe range and `Alert`
  outside it, so an operator can glance rather than read.
- **Sky** - a plain-language description, and whether it is day or night.
- **Almanac** - today's sunrise, sunset and moon phase.
- **Site** - the latitude and longitude, which the operator can change, and the
  one thing here that survives a restart.

## 1. Ask for only what you need

Open-Meteo returns everything you ask it for, so ask for a short list:

```
https://api.open-meteo.com/v1/forecast
  ?latitude=34.0522&longitude=-118.2437
  &current=temperature_2m,relative_humidity_2m,cloud_cover,wind_speed_10m,
           wind_gusts_10m,pressure_msl,wind_direction_10m,apparent_temperature,
           is_day,weather_code
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
    "wind_direction_10m": 304, "apparent_temperature": 71.6,
    "is_day": 0, "weather_code": 1
  },
  "daily": {
    "sunrise": ["2026-08-03T13:06"], "sunset": ["2026-08-04T02:52"],
    "moon_phase": [0.659]
  }
}
```

Two things to notice, because they shape the driver:

- `current_units` says whether you are getting °F or °C, so the driver takes its
  labels from the reply instead of guessing.
- `daily` holds a list per field, one entry per forecast day. The request asks
  for one day, so index `0` is today.

## 2. Declare the readings once

Put the field names in one place, rather than repeating them across the
definitions, the readings, and the safety checks:

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

Two of the published fields have nothing to judge them against. A compass bearing
has no safe range, and apparent temperature is context for the real temperature
rather than a limit of its own, so those two go in a second list:

```python
#: (API field, element name, label) - published, but not judged.
CONTEXT = [
    ("wind_direction_10m",   "WIND_DIRECTION", "Wind from"),
    ("apparent_temperature", "FEELS_LIKE",     "Feels like"),
]

#: Everything published, judged or not.
PUBLISHED = [
    (field, element, label) for field, element, label, *_range in READINGS
] + CONTEXT
```

The properties are then built from those lists, so the safe ranges cannot drift
out of step with the readings: a number for everything published, and a light
for each reading that has a range to fall outside of.

```python
self.define_number(
    "WEATHER_PARAMETERS",                     # the standard INDI name for this
    [Number(name=element, label=label, format="%.1f")
     for _field, element, label in PUBLISHED],
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

`urllib` blocks, as do `requests` and every serial library. Wrap the call in a
small client and keep it off the event loop:

```python
class OpenMeteoClient:
    def fetch(self, latitude: float, longitude: float) -> dict[str, Any]:
        ...                                    # plain blocking urllib
```

```python
payload = await self.off_thread(self._client.fetch, self._latitude, self._longitude)
```

Without `off_thread`, a slow API freezes the whole driver until it answers.

## 4. Connect by proving the service answers

For hardware, Connect opens a port. For a web service the equivalent is a
request that comes back, so `on_connect` does one real fetch and publishes it:

```python
async def on_connect(self) -> None:
    payload = await self.off_thread(self._client.fetch, self._latitude, self._longitude)
    self._publish(payload)
    self._offline = False
```

There is no error handling here on purpose. A fetch that raises puts the Connect
switch back to Disconnected and shows the reason, which is the right outcome at
a site whose internet is down.

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

Five minutes rather than one second: it is a forecast service, and hammering a
free public API is bad manners. `when_connected=True` stops the job while the
device is disconnected.

When the API goes quiet, the readings drop to `Idle` rather than sitting there
looking current, and the driver reports it once instead of on every failed poll:

```python
def _go_offline(self, exc: BaseException) -> None:
    self["WEATHER_PARAMETERS"].set(state=IPState.IDLE)
    self["WEATHER_STATUS"].set_all(IPState.IDLE, state=IPState.IDLE)
    if not self._offline:
        self._offline = True
        self.log_error(f"Open-Meteo is not answering: {exc}")
```

## 6. Turn readings into a verdict

Numbers are for reading and lights are for glancing. Each reading gets its own
light and the vector takes the worst of them, with one override: rain sets the
vector to `Alert` whatever the other readings say.

```python
lights[element] = IPState.OK if low <= value <= high else IPState.ALERT
...
raining = int(current.get("weather_code", 0)) in WET_CODES
worst = IPState.ALERT if raining or IPState.ALERT in lights.values() else IPState.OK
self["WEATHER_STATUS"].set(lights, state=worst)
```

## 7. Let the operator move the site

Latitude and longitude are a writable property, so an operator can point the
device at a different site:

```python
@on_new("GEOGRAPHIC_COORD")
async def _move_site(self, vector: NumberVector) -> None:
    self._latitude = vector.get("LAT", self._latitude)
    self._longitude = vector.get("LONG", self._longitude)
    await self._apply_site()

async def _apply_site(self) -> None:
    ...
```

`get(name, default)` matters here: a client that changes only the latitude sends
only the latitude, and the longitude must survive that.

The handler holds no logic of its own. It reads the request, then hands over to
`_apply_site`, which republishes the site and refetches for it. That split looks
like ceremony until the next step, where a second caller needs exactly the same
work done.

## 8. Remember the site across restarts

An operator who points the driver at their own site expects it to still be there
tomorrow.

`define_config()` publishes the standard INDI `CONFIG_PROCESS` switch: Load,
Save, Purge. Every libindi driver has it, and `persist=True` says which
properties those buttons cover:

```python
async def setup(self) -> None:
    self.define_connection()
    self.define_config()
    self.define_number(
        "GEOGRAPHIC_COORD",
        [Number(name="LAT", label="Latitude"), Number(name="LONG", label="Longitude")],
        label="Site",
        group="Site",
        persist=True,             # the one thing here worth surviving a restart
    )
    ...
    try:
        await self.load_config()
    except ConfigError as exc:
        self.message(f"Using the built-in site: {exc}")
```

Two lines in there look like boilerplate and are not.

`define_config()` does no file I/O. It only defines the property. Restoring is
the explicit `await self.load_config()`, because reading a file is the blocking
work step 3 told you to be deliberate about.

Having nothing saved is the ordinary first run rather than a failure, so it
arrives as `ConfigError` (an `OSError`, imported from `indikit`) and gets
caught. Without the `except`, a first start would look like a broken driver.

Restoring a value is not the same as acting on it. `load_config()` puts the saved
numbers into `GEOGRAPHIC_COORD`, but the driver is still fetching for wherever it
was pointed before. `on_config_loaded` is handed the names the load applied to,
and it finishes the job by calling the method the client write already calls:

```python
async def on_config_loaded(self, names: list[str]) -> None:
    if "GEOGRAPHIC_COORD" not in names:
        return
    site = self.number("GEOGRAPHIC_COORD")
    self._latitude = site.value("LAT")
    self._longitude = site.value("LONG")
    await self._apply_site()
```

That is why `_move_site` kept its body in `_apply_site`. A site that arrives from
a file does exactly what one typed into the panel does, and there is one place to
fix when that changes.

[Saving configuration](writing-drivers.md#saving-configuration) covers the rest,
including `INDIKIT_CONFIG_PERSISTED`: the property this driver publishes to tell a
panel which settings Save writes.

## 9. Run it

```bash
indikit serve --device examples.openmeteo_device:OpenMeteo
```

Open <http://localhost:8000/> and press Connect. The readings are live weather.
Edit the Site latitude and longitude and the driver follows.

Then open Configuration in the sidebar, press Save, and restart the driver. It
comes back already showing the site you chose, with `Restored 1 property.` in the
message log.

On the very first run, before anything is saved, the same log reads
`Using the built-in site: ...`. That is the `except ConfigError` above, not a
fault.

## 10. A screen of your own

The stock `DevicePanel` renders anything, because it builds itself from whatever
the device says it has. That is what you want for commissioning and the wrong
thing for the screen above the control-room door.

The custom UI here is a wallboard: the display an observer glances at from
across the room to answer one question. The code is
`web/apps/panel/demo/observatory-board.tsx` for the layout and
`board-visuals.tsx` for the drawn figures, built entirely from
`@indikit/react`.

It reads two devices, not one. This driver supplies the weather half and a
simulated dome supplies the other, both arriving through a single client. That
is the ordinary case - an observatory is several instruments on one connection -
and it changes nothing about how the screen is written, because every hook below
takes a device name and a second device is more calls to the same hooks. What it
does change is what the board leads with.

### What a wallboard has to do differently

| A desktop panel | A wallboard |
|---|---|
| Read at 40 cm | Read at 4 m - type sized in viewport units, not pixels, so the board fills whatever it is plugged into |
| You can hover, click, scroll | Nobody touches it. One screen, no tooltips |
| A stale number is a nuisance | A stale number is dangerous - it must blank out |
| Ratios suit thin meters | A 2 px track with a 1 px limit tick is invisible; use a big number and a thick state bar |
| Everything the device has, because you asked for it | Only what earns its space, because nobody asked for any of it |

### Leading with the decision

Something has to be the largest thing on the screen, and picking it is the
design. Here it is the dome shutter - `OPEN`, `CLOSED` or `UNKNOWN` - first,
ahead of the instrument names and every measurement. Las Cumbres Observatory's
public site board is laid out the same way, with a column headed `OPEN?` before
any reading.

The weather is what argues for or against that word, so it comes second, and the
readings currently in Alert are named rather than left for the reader to work
out: **Alert: Humidity · Cloud cover**.

Notice what the board does *not* do: it never decides what counts as too windy.
Each tile shows the light the driver published for that reading, and step 6 is
where the safe ranges live. One place to change them, and the stock panel, this
board and any script all agree.

### Reading a value and its state together

Almost every tile needs the same two values, so they come from one small hook:

```tsx
function useReading(element: string) {
  const value = useNumber("Open-Meteo", "WEATHER_PARAMETERS", element);
  const state = useLight("Open-Meteo", "WEATHER_STATUS", element);
  return { value, state: state ?? "Idle" };
}
```

### Naming the readings that are out of range

A row of coloured bars leaves the reader hunting for which one went red. The
driver publishes one light per reading, so the board can just say.

```tsx
function useAlerting(): string[] {
  const status = useProperty("Open-Meteo", "WEATHER_STATUS");
  if (status?.kind !== "light") return [];
  return status.elements.filter((light) => light.value === "Alert").map(displayLabel);
}
```

`displayLabel` is what gives an element a name to show. INDI's `label` is
optional, and libindi drivers really do publish elements whose label is the empty
string, so `label ?? name` prints a blank where a reading should be.

The board then carries **Alert: Humidity · Cloud cover** under the shutter word.

### Saying "I do not know"

When Open-Meteo stops answering, the driver parks its readings at `Idle` rather
than leaving stale numbers looking current. The board honours that: every value
becomes `--`, its state bar goes grey, its state word becomes `no data`, and the
header says the weather source is not answering. A wallboard showing last hour's
wind speed as though it were current is worse than a blank one.

```tsx
const live = parameters !== undefined && parameters.state !== "Idle";
```

The dome half needs the same honesty and cannot use the same mechanism, because
a shutter has no `--`. So `UNKNOWN` is a first-class third state beside open and
closed, and the board reaches it for real: aborting a shutter move leaves
`DOME_SHUTTER` in `Alert` with `Shutter operation aborted. Status: unknown.`,
and at that moment the switch still reports the position that was *commanded*.
A disconnected driver is in the same position - repeating its last reading
rather than reporting hardware.

It is styled neutrally rather than as an alarm, which every real observatory
board does too: Las Cumbres prints `?` in the same weight as its yes and its no.
"I do not know" is not a fault, and dressing it as one teaches the room to stop
believing the colour.

### Picking a form for each reading

| Reading | Form | Why |
|---|---|---|
| Shutter open or closed | **the word itself, largest on the screen** | The board's whole question. Nothing else is that size. |
| Dome azimuth | **plan view from above** | The dome drawn as a circle with the aperture cut out of the wall, rotated to the true bearing. That is the established idiom rather than an invention - MaxIm DL and Rubin's control interface both draw it - so an observer already knows how to read it. |
| Temperature, humidity, wind, gust, cloud, pressure | **big number + state bar** | At four metres, distance beats precision. Six of them at one size: none outranks the others until one goes into Alert, and then the header says which. |
| Wind direction | **compass** | The one genuinely *angular* reading - the case where a dial beats a bar. |
| Moon phase, sunrise and sunset | **drawn figures** | See `board-visuals.tsx`; each is a pure function of its props. |

There is no map of the site. The latitude and longitude are on the board's own
device and would have drawn nicely, and they never change while the board is up
- so on a screen nobody asked for, they are a picture that costs space and says
nothing new. Constant facts belong on the panel, where somebody went looking for
them.

### Two rules the board follows

- Status is never colour alone. In this theme Alert and Busy are ΔE 14.6 apart
  for a reader with full colour vision and 5.7 under protanopia, so across a
  room they are the same colour. Every state is therefore also a word: `ALERT`,
  `OK`, in type you can read from the door. The dome's three shutter readings go
  further and differ in *shape* before they differ in hue - a band, a solid
  panel, a dashed span.
- The judgement belongs to the driver rather than the UI. Every state the board
  shows is one a device published, so the safety rule lives in one place and
  this board, the stock panel and any script all agree about it.

Colour comes from theme tokens rather than hex, so the board follows light and
dark mode without extra work. Anything whose colour is an INDI state carries
`data-indi-state={state}` and paints with `var(--indi-state)`; the stylesheet
does the mapping, so no component holds a four-way switch on `Idle`/`Ok`/`Busy`/
`Alert`. Everything else is an ordinary token: `stroke-muted-foreground`,
`fill-chart-3`.

## 11. Test it

The driver is tested against a recorded real response, so the field names are
checked against what the service sends rather than guessed:

```python
async def test_status_lights_flag_the_readings_that_are_out_of_range(site):
    harness, _ = site
    await harness.tick("poll")

    status = harness.latest("WEATHER_STATUS")
    assert status.get("TEMPERATURE") is IPState.OK
    assert status.get("HUMIDITY") is IPState.ALERT     # 95% - damp
    assert status.state is IPState.ALERT               # the vector takes the worst
```

`tests/test_openmeteo_example.py` is the whole set: every reading landing, a
context reading getting no status light, rain overriding the numbers, the site
surviving a restart, and a dead API parking the readings and saying so once.

A screen built on these hooks is tested the same way, against the frames a
driver really sends. `@indikit/react/testing` is what makes that cheap:
`renderConnected(ui)` mounts your component under a provider wired to a fake
socket that has already sent its `hello`, and `receive(socket, frame)` feeds it
what the driver would have said. The
[React package README](https://github.com/sidereal-software/indikit/blob/main/web/packages/react/README.md#testing-your-own-components)
has the details.

## Where to take it

- Add a safety switch the dome driver can watch, so it closes itself when this
  device goes to `Alert`.
- Swap Open-Meteo for your own weather station: everything except
  `OpenMeteoClient.fetch` stays as it is.
- Add the hourly forecast as a second property, so the screen can show what is
  coming as well as what is here.
