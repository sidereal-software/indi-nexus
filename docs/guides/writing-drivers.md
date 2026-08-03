# Writing a driver

A driver is a `Device` subclass: properties declared in `setup()`, periodic
work in `@every` methods, client writes handled by `@on_new` methods. The SDK
carries the standard INDI machinery so your driver is only its own behavior.

Start from a working file:

```bash
indi-nexus new my_driver.py
```

## The shape of a driver

```python
from indi_nexus.driver import Device, every, on_new
from indi_nexus.protocol import IPState, ISState, Number, Switch, SwitchVector

class Mount(Device):
    name = "Mount"

    async def setup(self) -> None:
        self.define_connection()
        self.define_number(
            "EQUATORIAL_EOD_COORD",
            [Number(name="RA", format="%9.6m"), Number(name="DEC", format="%9.6m")],
        )

    async def on_connect(self) -> None:
        await self.open_serial_link()

    @every(seconds=1, when_connected=True)
    async def poll(self) -> None:
        ra, dec = await self.read_mount()
        self["EQUATORIAL_EOD_COORD"].set(RA=ra, DEC=dec, state=IPState.OK)

    @on_new("EQUATORIAL_EOD_COORD")
    async def _goto(self, vector) -> None:
        if not self.require_connected():
            return
        await self.slew_to(vector.get("RA", 0.0), vector.get("DEC", 0.0))

if __name__ == "__main__":
    Mount.run()
```

## The pieces

**Properties** - `define_number/text/switch/light/blob(...)` each return a
[`BoundProperty`][indi_nexus.driver.property.BoundProperty] handle and emit the
`def` to clients. Later, `self["NAME"].set(ELEMENT=value, state=...)` updates
elements *and* notifies every client in one call; the exclusive switch rules
(`OneOfMany`, `AtMostOne`) are honoured automatically.

The handle is typed by what you defined, so `define_switch(...)` gives back a
`BoundProperty[SwitchVector]` whose `.vector.elements` is a `list[Switch]`.
A lookup by name cannot know the kind, so `self["NAME"]` is untyped in its
vector; when you need to read elements back, use the typed getter instead:

```python
for switch in self.switch("DOME_SHUTTER").vector.elements:   # list[Switch]
    ...
```

`self.number/text/switch/light/blob(name)` all work this way and raise
`TypeError` if the property turns out to be another kind.

For repetitive properties - a group of status lights, a table of readbacks -
`Element.from_labels()` builds one element per label and names each with
`slugify`, and `prop.set_all(value)` writes every element in one emit:

```python
self.define_light("WEATHER_STATUS", Light.from_labels(["Wind Speed", "Cloud Cover"]))
self["WEATHER_STATUS"].set_all(IPState.IDLE, state=IPState.IDLE)
```

**One of N is the current one** - a bank of lights where exactly one shows the
state the instrument is in is the most common shape in INDI status reporting.
`select()` is the whole idiom:

```python
self["state_message"].select("domeslit_opening", IPState.BUSY)
```

The named light goes Busy, every sibling goes Idle, and so does the vector (a
light's state *is* the vector's state, so it does not need repeating). Guard it
with `in` when the value comes from hardware that might report something you
have no light for:

```python
if reported not in self["state_message"]:
    self.log_error(f"Unknown state {reported!r}")
    self["state_message"].set_all(IPState.IDLE, state=IPState.ALERT)
    return
self["state_message"].select(reported, ...)
```

**Quiet properties** - a polling driver publishes the same values over and
over. Declare a readback `emit="on_change"` and its `set` only reaches the wire
when a value, the state or the message actually differs from what clients were
last told:

```python
self.define_number("WEATHER_PARAMETERS", [...], perm=IPerm.RO, emit="on_change")
```

The values are still written either way - only the emit is suppressed. Pass
`force=True` to a `set` to re-announce anyway.

**Connection** - `define_connection()` adds the standard `CONNECTION` switch.
The built-in handler flips it, calls your `on_connect()` / `on_disconnect()`
hooks (open and close your hardware link there), and announces the transition.
A hook that *raises* - the usual way for hardware to report it is not there -
rolls the switch back and leaves the property in `Alert` with the reason
attached, so the device never sits claiming a link it does not have. Let it
raise rather than catching it. `self.connected` reads the state;
`self.require_connected()` is the one-line guard for handlers;
`@every(..., when_connected=True)` pauses polling while disconnected.

**Client writes** - an `@on_new("NAME")` method receives the parsed, typed
vector the client sent. Two accessors answer the questions every handler asks:

- `vector.selected()` - which switch member did the client turn On? (A
  `OneOfMany` write often carries *only* the selected member.)
- `vector.get(name, default)` - what value did they send? (Tolerates partial
  writes; never raises.)

**Robustness for free** - a raising handler or a failing poll tick is reported
to the client as an INDI message and *isolated*: one bad write or bug never
kills the driver. Writes addressed to other devices are ignored, matching
libindi semantics.

**Messages** - `self.message("...")` and `self.log_error("...")` send INDI
`message`s; they land in the panel's log and every connected client.

## Talking to real hardware

Instrument libraries are overwhelmingly **synchronous** - `pyserial`, a vendor
SDK, a `requests` session. Calling one directly from an `async def` compiles,
reads perfectly well, and blocks the event loop for the whole call:

```python
@every(seconds=1)
async def poll(self) -> None:
    reading = self._station.read_all()      # DON'T: stalls the whole driver
```

While that runs, your driver answers nothing - not `indiserver`, not another
property, not a client write - and nothing reports an error. Route the blocking
call through `off_thread`:

```python
@every(seconds=1, when_connected=True)
async def poll(self) -> None:
    reading = await self.off_thread(self._station.read_all)
    self["WEATHER_PARAMETERS"].set(reading, state=IPState.OK)
```

Only the blocking call belongs in the thread. Keep the `set` on the event loop,
as above - the outbox behind it is an `asyncio.Queue`, which is not thread-safe.

A blocking call cannot be cancelled, so `asyncio.timeout` around it bounds how
long the *driver* waits, not how long the thread runs. That is still worth
doing: the property stops claiming to be current on time, and the orphaned read
finishes into nothing.

`examples/weather_device.py` is built end to end this way, with lost-comms
handling and its own tests.

## Ticks and writes do not interleave

Any tick that awaits - and a tick that talks to hardware should - yields the
event loop mid-flight. Without help, a client write can land between a tick's
read and the properties it publishes from that read, and the tick then
overwrites the write with state gathered *before* it: a button springs back
out, a target reverts. It is intermittent, invisible, and a bug every polling
driver would otherwise have to solve for itself.

So the SDK solves it: `@every` ticks and `@on_new` handlers run under a
per-device lock, and each sees a settled device. It also serialises hardware
access, which a single serial port or socket wants anyway. The cost is that a
client write waits for an in-flight tick.

Set `serialize_dispatch = False` on your `Device` subclass to opt out - for a
device whose ticks and handlers provably share no state, or one that must
answer writes during a long tick.

`@every` schedules against a deadline rather than sleeping the interval after
each tick, so a job's period stays at what you declared instead of drifting out
by however long each tick takes.

## Testing your driver

[`DeviceHarness`][indi_nexus.testing.DeviceHarness] drives a device the way a
client would - no `indiserver`, no sockets, no hardware:

```python
from indi_nexus.testing import DeviceHarness

async def test_reset_reaches_the_station():
    device = WeatherStation()
    device._station = FakeStation()          # the one thing worth faking
    harness = DeviceHarness(device)
    await harness.setup()                    # runs the device's setup()

    await harness.write("CONNECTION", CONNECT=True)
    await harness.tick("poll")               # one iteration of the @every job

    assert harness.latest("WEATHER_PARAMETERS").state is IPState.OK
    assert "ready" in harness.messages[0]
```

- `setup()` sends the `getProperties` that `indiserver` would.
- `write(name, **values)` builds the partial vector a real client sends and
  routes it through the device's actual dispatch - the `@on_new` map, the
  device-name guard, the serialisation lock. A handler that works here works
  under `indiserver`.
- `tick(job)` runs one iteration of an `@every` method by name, without waiting
  out its interval.
- `defs()`, `sets()`, `deletes()`, `messages` and `latest(name)` report what
  the device told clients; `clear()` separates arrange from act.

To cover the wire itself - framing, chunk boundaries, the codec - drive a
`DriverRuntime` over byte streams instead; see `tests/test_driver.py`.

## Full API

See the [driver SDK reference](../reference/python/driver.md) and the
[testing reference](../reference/python/testing.md).
