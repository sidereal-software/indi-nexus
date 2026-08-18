---
search:
  boost: 2
---

# Writing a driver

A driver is the small program that sits between one instrument and everything else. It
answers two questions:

- What does this instrument have? A dome has a shutter and an azimuth. A camera has an
  exposure time. A weather station has a wind speed.
- What happens when someone reads or changes one of those?

In INDINexus a driver is a single Python class that answers both.

## The vocabulary

INDI has three words worth learning before any code:

| Word | What it means | Example |
|---|---|---|
| **Property** | One named thing an instrument exposes. Always a *group* of values, even when there is only one. | `ABS_DOME_POSITION` |
| **Element** | One value inside a property. | `DOME_ABSOLUTE_POSITION` = `120.0` |
| **State** | A traffic light on the property: `Idle`, `Ok`, `Busy`, `Alert`. | `Busy` while the dome turns |

Every property is one of five **kinds**, and the kind decides how a UI draws it:

| Kind | Holds | Drawn as |
|---|---|---|
| **Number** | numeric values | a field with units |
| **Text** | strings | a text field |
| **Switch** | on/off members | buttons, radio buttons or checkboxes |
| **Light** | read-only status | coloured dots |
| **BLOB** | binary data | a download link, or an image |

Properties also carry a **permission**: `ro` (the client can only look), `rw` (the client
can change it), `wo` (write only).

The model is that small. A driver defines properties, publishes new values for them, and
reacts when a client asks to change one.

## A complete driver

Here is a working driver for a flat-field lamp - a light panel with a brightness dial.
Every line is explained underneath.

```python
from indi_nexus.driver import Device, on_new
from indi_nexus.protocol import (
    IPState, ISRule, ISState, Number, NumberVector, Switch, SwitchVector,
)

class FlatPanel(Device):
    """A flat-field lamp: on/off, and a brightness dial."""

    name = "Flat Panel"                                            # (1)

    async def setup(self) -> None:                                 # (2)
        self.define_connection()                                   # (3)
        self.define_switch(
            "LIGHT_CONTROL",
            [Switch(name="ON", label="On"),
             Switch(name="OFF", label="Off", value=ISState.ON)],   # (4)
            rule=ISRule.ONE_OF_MANY,                               # (5)
            label="Lamp",
            group="Main Control",                                  # (6)
        )
        self.define_number(
            "LIGHT_BRIGHTNESS",
            [Number(name="BRIGHTNESS", label="Brightness",
                    format="%.0f", min=0, max=255, value=128)],    # (7)
            label="Brightness",
            group="Main Control",
        )
        self.message("Flat panel ready.")                          # (8)

    async def on_disconnect(self) -> None:                         # (9)
        self["LIGHT_CONTROL"].set({"OFF": ISState.ON}, state=IPState.IDLE)
        self.message("Lamp turned off on disconnect.")

    @on_new("LIGHT_CONTROL")                                       # (10)
    async def _switch_lamp(self, vector: SwitchVector) -> None:
        if not self.require_connected():                           # (11)
            return
        on = vector.selected() == "ON"                             # (12)
        self["LIGHT_CONTROL"].set(                                 # (13)
            {"ON" if on else "OFF": ISState.ON}, state=IPState.OK,
        )
        self.message(f"Lamp turned {'on' if on else 'off'}.")

    @on_new("LIGHT_BRIGHTNESS")
    async def _set_brightness(self, vector: NumberVector) -> None:
        if not self.require_connected():
            return
        wanted = vector.get("BRIGHTNESS", 0.0)                     # (14)
        self["LIGHT_BRIGHTNESS"].set(
            BRIGHTNESS=max(0, min(255, wanted)),                   # (15)
            state=IPState.OK,
        )

if __name__ == "__main__":
    FlatPanel.run()                                                # (16)
```

1. The name clients see. Omit it and the class name is used.
2. `setup()` runs once, when a client first asks what this device has. Everything the
   device exposes is declared here.
3. Every INDI device has a Connect button, and this one line is it. The
   [next section](#connecting-and-disconnecting) is what it brings with it.
4. Elements carry a `name` (what the protocol uses) and a `label` (what a human reads).
   This one starts Off.
5. `ONE_OF_MANY` means "exactly one of these is on" - a UI draws radio buttons. The other
   rules are `AT_MOST_ONE` (zero or one) and `ANY_OF_MANY` (independent checkboxes).
6. `group` is the section a UI files the property under.
7. Numbers can declare a display `format` and a valid range, and a UI will respect both.
8. `message()` sends a line to every client's log.
9. `on_disconnect()` runs when the operator disconnects. Leave the instrument safe here: a
   flat panel left lit fogs every exposure taken after the client went away.
10. `@on_new("NAME")` is called when a client asks to change that property. Nothing changes
    until you say so - the client is *requesting*.
11. Commands are refused while the link is down. `require_connected()` sends the standard
    "not connected" error to the client, so the guard is these two lines and nothing else.
12. `selected()` answers "which member did they turn on?". Use it rather than checking a
    specific element, because a client usually sends only the one it changed.
13. `set()` writes the values **and** tells every client, in one call. Turning one member
    on automatically turns the others off, because the rule says so.
14. `get(name, default)` reads a requested value without assuming it was sent.
15. A client may ask for anything. The `min`/`max` declared above is a promise about the
    hardware, so hold the request to it rather than passing it straight through.
16. `run()` serves the driver over standard input/output, which is how `indiserver`
    launches it.

That driver is [`examples/flat_panel.py`](https://github.com/sidereal-software/indi-nexus/blob/main/examples/flat_panel.py)
in the repository, and the test suite covers it, so it cannot quietly stop working. Run it
in the reference panel:

```bash
indi-nexus serve --device examples.flat_panel:FlatPanel
```

Or [try it in your browser](../flat-demo/flat.html): the same driver simulated in
JavaScript, driving the panel that ships in the wheel, with nothing to install. Press
Connect first, as you would with the real thing.

## Connecting and disconnecting

Instruments are not always plugged in, so INDI gives every device a standard Connect
button. `define_connection()` above is the whole of it: the switch, the two hooks that
run on each transition, and the guard the handlers use.

The flat panel has no link to open, so it overrides only `on_disconnect`. A driver with
hardware behind it overrides both:

```python
async def on_connect(self) -> None:
    self._port = serial.Serial("/dev/ttyUSB0")     # open the link here

async def on_disconnect(self) -> None:
    self._port.close()                             # and close it here
```

`on_disconnect` is for leaving the instrument safe, not only for dropping a handle. The
client is walking away; anything still running is going to keep running unattended, which
is why the panel puts the lamp out first.

Then:

- `self.require_connected()` is the one-line guard for a command handler.
- `@every(seconds=1, when_connected=True)` pauses polling (the next section) while
  disconnected.
- If `on_connect` raises, which is the usual way for hardware to say "I am not here", the
  button springs back to Disconnected and the property shows `Alert` with the reason.
  Let it raise; do not catch it.

## Properties that only exist while connected

Some properties describe the hardware rather than the driver: a cooler set point, a filter
count read off the wheel at startup. Define those in `on_connect` and withdraw them in
`on_disconnect`, so what the device publishes always matches what is actually readable.

```python
async def on_connect(self) -> None:
    self.define_number("CCD_COOLER", [Number(name="TEMPERATURE", value=25.0)])

async def on_disconnect(self) -> None:
    self.delete_property("CCD_COOLER", "only while connected")
```

`delete_property` removes the property and tells the client it has gone, so a client
connecting later is not offered a control that does nothing. Deleting a name that is not
defined does nothing at all, which is why the hook above needs no guard: it is correct on
the first disconnect and on every one after it.

Defining the same property again on the next connect is the normal cycle, not a special
case. Each `define_*` hands back a fresh handle; a handle whose property has been deleted
is dead, and publishing through it raises rather than sending an update for something the
client was told is gone.

## Reading the instrument on a timer

Real instruments have to be asked. `@every` runs a method on a schedule:

```python
@every(seconds=1)
async def poll(self) -> None:
    reading = self.read_hardware()
    self["LIGHT_BRIGHTNESS"].set(BRIGHTNESS=reading, state=IPState.OK)
```

A tick that fails is reported to the client and the driver carries on, so one bad reading
never kills a driver. Ticks are scheduled against a rolling deadline rather than by
sleeping the interval after each one, so a tick that takes 300 ms does not push the next
one out to 1.3 seconds.

### When the reading is not a number

The snippet above hands a sensor reading straight to `set()`, and a real sensor
eventually hands you `nan` or an infinity: a disconnected thermocouple, a divide by a
zero wind count, a `float()` of a field the vendor left blank.

**`set()` refuses those.** Neither wire format can carry a non-finite number - JSON has no
literal for one - so `Number.value` forbids them and `set()` raises `ProtocolError`
naming the element:

```
ProtocolError: T.TEMP.C cannot be set to nan
```

The raise happens before anything is written, so the property keeps its previous value
and nothing goes on the wire. In a `@every` job the runtime catches it, reports it to the
client and runs the next tick - but the property is then silently stale, still showing a
reading that is no longer being taken. That is the worst outcome, so handle it yourself.
Say the instrument is unwell:

```python
@every(seconds=1, when_connected=True)
async def poll(self) -> None:
    reading = await self.off_thread(self._station.read_temperature)
    if not math.isfinite(reading):
        # Keep the last good value on screen, but stop claiming it is current.
        self["WEATHER_PARAMETERS"].set(state=IPState.ALERT)
        return
    self["WEATHER_PARAMETERS"].set(TEMPERATURE=reading, state=IPState.OK)
```

That needs `import math`. Skipping the update entirely (`return` with no `set`) is the
other reasonable choice, and it is the wrong one whenever a client could mistake a stale
reading for a live one - which on a weather station deciding whether to open a roof is
always. Prefer `IPState.ALERT`.

The same rule applies to `min`, `max` and `step`, except that those *can* say "absent":
a non-finite one degrades to `None` rather than raising, because the wire has a
representation for a missing bound and none for `nan`.

## Talking to real hardware

The commonest way a real driver goes wrong is a blocking call inside an `async def`.
Instrument libraries are almost always synchronous: `pyserial`, a vendor SDK, a
`requests` session. Calling one directly looks fine:

```python
@every(seconds=1)
async def poll(self) -> None:
    reading = self._station.read_all()      # DON'T
```

...and it freezes the entire driver for as long as that call takes. The freeze is not
confined to that one property: the driver stops answering anything at all, and nothing
reports an error. Hand blocking calls to `off_thread` instead:

```python
@every(seconds=1, when_connected=True)
async def poll(self) -> None:
    reading = await self.off_thread(self._station.read_all)     # DO
    self["WEATHER_PARAMETERS"].set(reading, state=IPState.OK)
```

Only the blocking call goes to the thread. Keep `set()` where it is, on the main loop.

`examples/weather_device.py` is built this way from end to end, including what to do when
the instrument stops answering.

## Publishing an image

A BLOB element carries bytes plus a `format`: the file-name suffix chain telling a client
what it is receiving, `.fits` for a FITS frame. Publishing one is an ordinary `set` -
`self["IMAGE"].set(IMAGE=frame, state=IPState.OK)` - which writes the payload and fills in
`size` from it. `examples/ccd_device.py` is a worked camera.

`size` is where compression comes in. INDI defines it as the **uncompressed** length, so
`len(data)` is right only for a payload that is not compressed. If you want to deflate a
frame for the wire - the `.z` convention the
[protocol guide](protocol.md#compressed-payloads) describes - INDINexus will not do it for
you, and `set()` cannot supply a `size` it would have to inflate the bytes to learn. Write
the three fields yourself, then emit a `set` that names no element:

```python
async def publish_frame(self, frame: bytes) -> None:
    element = self.blob("IMAGE").vector.element("IMAGE")
    element.data = zlib.compress(frame)
    element.size = len(frame)               # the uncompressed length, by definition
    element.format = ".fits.z"
    self.blob("IMAGE").set(state=IPState.OK)  # names no element, so size stands
```

That needs `import zlib`. Naming the element works too - `set(IMAGE=zlib.compress(frame))`
is fine once `size` has been declared - because `set()` leaves a compressed element's
`size` alone rather than deriving it, which on a `.z` element would record deflate's output
length under an attribute the specification defines as the uncompressed one. What it cannot
do is invent that number, so a `.z` format with no `size` at all is refused outright: both
`to_xml` and `to_json` raise `ProtocolError` rather than write the wrong length.

Clients inflate on the way in, so nothing downstream ever sees the `.z`. Most drivers
should not bother - libindi's `CCD_COMPRESSION` defaults to off - and `.fits.fz` (fpack,
compression inside the FITS container) passes through untouched if that suits you better.

## Saving configuration

An operator who points your driver at a site, sets a focuser offset or names the filter in
slot 3 expects it to still know that after a reboot. `define_config()` publishes the
standard INDI `CONFIG_PROCESS` switch - Load, Save and Purge - which every libindi driver
has, so clients already know what the buttons do. Which properties it covers is declared
per property, at define time:

```python
async def setup(self) -> None:
    self.define_connection()
    self.define_config()
    ...
    try:
        await self.load_config()
    except ConfigError as exc:
        self.message(f"Using the built-in site: {exc}")
```

Two things there are deliberate.

`persist=True` on a `define_*` call is what marks a property as configuration; everything
else is left out. `examples/openmeteo_device.py` marks its `GEOGRAPHIC_COORD` and nothing
else, because a temperature reading is not a setting.

**`define_config()` does no file I/O.** Restoring is the separate `await self.load_config()`
above, which you write yourself, because reading a file is exactly the kind of blocking
work the rest of this page tells you to be deliberate about. Having nothing saved is the
ordinary first run, and it arrives as `ConfigError` (an `OSError`, from `indi_nexus`) - so
catch it, or a first start would look like a broken driver.

Where you put the call is not a correctness question - a load applies to every persisted
property already defined *and* waits for the ones defined after it, `on_connect`'s
included - but the two orders differ in one visible way. Load *before* the persisted
`define_*` calls and each property is announced once, already holding its saved value.
Load after them, as above, and each is announced with its built-in default and corrected a
moment later, in exchange for `on_config_loaded` being handed the names while the
properties are all there - which is what a driver that also keeps its settings in ordinary
Python attributes needs.

What is written is values, keyed by property, and nothing else:

```json
{"version": 1, "device": "Open-Meteo", "saved": "2026-08-17T21:14:03Z",
 "properties": {"GEOGRAPHIC_COORD": {"LAT": 47.6, "LONG": -122.3}}}
```

Definitions - labels, permissions, limits - stay in the code, which is the only thing that
knows what this version of the driver publishes. The file lives in
`$XDG_CONFIG_HOME/indi-nexus`, or wherever `INDI_NEXUS_CONFIG_DIR` says.

### The driver says what Save writes

Because `persist=True` is declared rather than decided inside a method, your driver can
answer a question no libindi driver can: which properties does pressing Save actually
write? A libindi driver chooses its subset in `saveConfigItems`, a C++ virtual nothing on
the wire exposes, which is why a panel can only warn that Save may not cover what is on
screen.

`define_config()` publishes the answer for you, as a read-only `NEXUS_CONFIG_PERSISTED`
text property whose `PROPERTIES` element holds the persisted property names separated by
spaces. You write nothing extra: it goes out once `setup()` returns, so it names the whole
set at once, and it is restated when the set really changes - a persisted property defined
in `on_connect`, or withdrawn in `on_disconnect`. The reference panel reads it and names
those properties in the configuration dialog instead of apologising.

Two consequences are worth knowing. A driver that calls `define_config()` and persists
nothing publishes the property **empty**, because "Save writes nothing" and "this driver
cannot tell you" are different answers and only the property's absence means the second.
And a `persist=True` property may not have whitespace in its name - INDI itself allows it,
the list's encoding does not - so that is a `ValueError` at define time.

### Acting on what was restored

Restoring a value is not the same as acting on it. A focuser that saved its position has to
physically move; a driver that saved a site has to start fetching for it. `on_config_loaded`
is where that happens, and it is handed the names of the properties the load applied to.

It hands you names rather than doing the work itself because the work is yours. The shape
that survives contact with a real driver is to keep the body of the corresponding `@on_new`
handler in a method of its own, and call it from both, so a value that arrives from a file
does exactly what one typed into the panel does:

```python
async def on_config_loaded(self, names: list[str]) -> None:
    if "GEOGRAPHIC_COORD" not in names:
        return
    site = self.number("GEOGRAPHIC_COORD")
    self._latitude = site.value("LAT")
    self._longitude = site.value("LONG")
    await self._apply_site()

@on_new("GEOGRAPHIC_COORD")
async def _move_site(self, vector: NumberVector) -> None:
    self._latitude = vector.get("LAT", self._latitude)
    self._longitude = vector.get("LONG", self._longitude)
    await self._apply_site()

async def _apply_site(self) -> None:
    ...
```

Saving needs no hook at all: `CONFIG_SAVE` reads the persisted properties itself. It also
writes the properties that are *not* defined at that moment - a connect-time property is
captured as it is withdrawn - so a Save taken while the instrument is disconnected does not
quietly erase half the configuration.

## Handy shortcuts

A bank of lights with exactly one lit is the commonest shape in status reporting.
`Light.from_labels` and `select` do it in two lines rather than a pile of near-identical
ones:

```python
self.define_light("state_message", Light.from_labels(["Idle", "Opening", "Open"]))
# names become idle, opening, open; labels stay as written

self["state_message"].select("opening", IPState.BUSY)
# that light goes Busy, the rest go Idle, and so does the property
```

Use `if reported not in self["state_message"]` to guard the `select` when the value comes
from hardware that might say something unexpected.

By default a driver that polls every second sends the same unchanged values every second,
forever. Declare the property `on_change` and it only speaks when something differs:

```python
self.define_number("WEATHER_PARAMETERS", [...], perm=IPerm.RO, emit="on_change")
```

Values are still recorded either way - only the notification is skipped.

## Serialised dispatch

A driver that both polls hardware and accepts commands has a subtle problem: a poll that
started before the operator pressed a button can finish afterwards and publish what it
read *before* the press, undoing it. The button springs back out, seemingly at random.

INDINexus prevents this: `@every` ticks and `@on_new` handlers never run at the same time
on one device. Each sees a settled device, and hardware access is serialised, which a
single serial port wants anyway. The trade is that a click waits for a poll already in
flight.

If you have a device where that is wrong, set `serialize_dispatch = False` on the class.

## Several devices in one driver

Some instruments are more than one INDI device: a camera with a guide chip, a focuser and
a rotator on one hub, three channels of a power box. One driver process announces them all.
Hand `run` a list instead of calling `Device.run()`:

```python
from indi_nexus.driver import run

if __name__ == "__main__":
    run([Camera(), GuideChip(), FilterWheel()])
```

Nothing else changes. `indiserver ./my_driver.py` launches it as before, and the three
devices appear as three devices on the first `getProperties`. From the command line,
`indi-nexus run my_driver:Camera my_driver:GuideChip` does the same with no `__main__`
block. Each device keeps its own name, properties, handlers and `@every` jobs; they are
ordinary independent objects that happen to share a process, which is the point - it is how
they share the one USB handle or serial port the hardware actually has.

`examples/guided_camera.py` is the worked version: a camera and its guide chip behind one
blocking link.

What they share, and what they do not:

- **`@every` jobs stay concurrent.** Each is its own task taking only its own device's
  lock, so the guider keeps reporting right through the camera's exposure.
- **Everything the devices publish goes out on one shared queue**, drained by a writer that
  is not waiting for any of them. A busy device does not delay another's updates.
- **Client writes are handled one at a time, across all of them.** The driver reads the
  next message only after the current handler returns, so a handler that takes two seconds
  delays the *next* write - for every device in the process, not only its own.

That last one is the trade, and it is what libindi has always done. It is usually right,
because devices sharing a process usually share hardware that has to take turns anyway.
Note what does *not* change it: `off_thread` keeps the event loop free but the handler
still waits for it, and `serialize_dispatch = False` drops a lock that the other device was
never waiting on. If two devices must never delay each other's commands, run them as two
drivers - `indiserver ./camera.py ./wheel.py` launches both, and that is the real answer.

## Testing without hardware

A driver is an ordinary object, so a test can drive it and check what it told its clients:

```python
from indi_nexus.testing import DeviceHarness

async def test_lamp_turns_on():
    harness = DeviceHarness(FlatPanel())
    await harness.setup()                           # what indiserver sends at startup
    await harness.write("CONNECTION", CONNECT=True) # the operator presses Connect

    await harness.write("LIGHT_CONTROL", ON=True)   # and then clicks the lamp on

    assert harness.latest("LIGHT_CONTROL").get("ON") is ISState.ON
    assert "turned on" in harness.messages[-1]
```

- `setup()` triggers the device's own `setup()`, capturing every property it defines.
- `write(name, **values)` sends exactly what a real client would and routes it through the
  device's real dispatch, so a handler that passes here works under `indiserver`.
- `tick(job)` runs one iteration of an `@every` method without waiting out its interval.
- `defs()`, `sets()`, `deletes()`, `messages` and `latest(name)` are what the device said;
  `clear()` forgets the history so far, to separate setup from the thing being tested.
  `deletes()` is how you assert a retraction: a `delete_property` in `on_disconnect`
  shows up there, and nowhere else.

`tests/test_weather_example.py` is a complete worked set, including a failing instrument
and a dropped connection.

## Full API

The [driver SDK reference](../reference/python/driver.md) and the
[testing reference](../reference/python/testing.md).
