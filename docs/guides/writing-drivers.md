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
from indi_nexus.driver import Device, every, on_new
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
- `defs()`, `sets()`, `messages` and `latest(name)` are what the device said;
  `clear()` forgets the history so far, to separate setup from the thing being tested.

`tests/test_weather_example.py` is a complete worked set, including a failing instrument
and a dropped connection.

## Full API

The [driver SDK reference](../reference/python/driver.md) and the
[testing reference](../reference/python/testing.md).
