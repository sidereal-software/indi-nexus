---
search:
  boost: 2
---

# Writing a driver

A driver is the small program that sits between one instrument and everything else. It
answers two questions:

- **What does this instrument have?** A dome has a shutter and an azimuth. A camera has an
  exposure time. A weather station has a wind speed.
- **What happens when someone reads or changes one of those?**

In INDINexus a driver is a single Python class that answers both.

## The vocabulary, in one picture

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

That is the whole model. A driver defines properties, publishes new values for them, and
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
        self.define_switch(
            "LIGHT_CONTROL",
            [Switch(name="ON", label="On"),
             Switch(name="OFF", label="Off", value=ISState.ON)],   # (3)
            rule=ISRule.ONE_OF_MANY,                               # (4)
            label="Lamp",
            group="Main Control",                                  # (5)
        )
        self.define_number(
            "LIGHT_BRIGHTNESS",
            [Number(name="BRIGHTNESS", label="Brightness",
                    format="%.0f", min=0, max=255, value=128)],    # (6)
            label="Brightness",
            group="Main Control",
        )
        self.message("Flat panel ready.")                          # (7)

    @on_new("LIGHT_CONTROL")                                       # (8)
    async def _switch_lamp(self, vector: SwitchVector) -> None:
        on = vector.selected() == "ON"                             # (9)
        self["LIGHT_CONTROL"].set(                                 # (10)
            {"ON" if on else "OFF": ISState.ON}, state=IPState.OK,
        )
        self.message(f"Lamp turned {'on' if on else 'off'}.")

    @on_new("LIGHT_BRIGHTNESS")
    async def _set_brightness(self, vector: NumberVector) -> None:
        wanted = vector.get("BRIGHTNESS", 0.0)                     # (11)
        self["LIGHT_BRIGHTNESS"].set(
            BRIGHTNESS=max(0, min(255, wanted)),                   # (12)
            state=IPState.OK,
        )

if __name__ == "__main__":
    FlatPanel.run()                                                # (13)
```

1. The name clients see. Omit it and the class name is used.
2. `setup()` runs once, when a client first asks what this device has. Everything the
   device exposes is declared here.
3. Elements carry a `name` (what the protocol uses) and a `label` (what a human reads).
   This one starts Off.
4. `ONE_OF_MANY` means "exactly one of these is on" - a UI draws radio buttons. The other
   rules are `AT_MOST_ONE` (zero or one) and `ANY_OF_MANY` (independent checkboxes).
5. `group` is the section a UI files the property under.
6. Numbers can declare a display `format` and a valid range, and a UI will respect both.
7. `message()` sends a line to every client's log.
8. `@on_new("NAME")` is called when a client asks to change that property. Nothing changes
   until you say so - the client is *requesting*.
9. `selected()` answers "which member did they turn on?". Use it rather than checking a
   specific element, because a client usually sends only the one it changed.
10. `set()` writes the values **and** tells every client, in one call. Turning one member
    on automatically turns the others off, because the rule says so.
11. `get(name, default)` reads a requested value without assuming it was sent.
12. A client may ask for anything. The `min`/`max` declared above is a promise about the
    hardware, so hold the request to it rather than passing it straight through.
13. `run()` serves the driver over standard input/output, which is how `indiserver`
    launches it.

That driver is [`examples/flat_panel.py`](https://github.com/sidereal-software/indi-nexus/blob/main/examples/flat_panel.py)
in the repository, and the test suite covers it, so it cannot quietly stop working. Run it
in the reference panel:

```bash
indi-nexus serve --device examples.flat_panel:FlatPanel
```

Or [try it in your browser](../flat-demo/flat.html): the same driver simulated in
JavaScript, driving the panel that ships in the wheel, with nothing to install.

## Reading the instrument on a timer

Real instruments have to be asked. `@every` runs a method on a schedule:

```python
@every(seconds=1)
async def poll(self) -> None:
    reading = self.read_hardware()
    self["LIGHT_BRIGHTNESS"].set(BRIGHTNESS=reading, state=IPState.OK)
```

A tick that fails is reported to the client and the driver carries on - one bad reading
never kills a driver. The interval is a real interval: a tick that takes 300 ms does not
push the next one out to 1.3 seconds.

## Connecting and disconnecting

Instruments are not always plugged in, so INDI gives every device a standard Connect
button. One line adds it, along with the two hooks that go with it:

```python
async def setup(self) -> None:
    self.define_connection()          # adds the standard CONNECTION switch

async def on_connect(self) -> None:
    self._port = serial.Serial("/dev/ttyUSB0")     # open the link here

async def on_disconnect(self) -> None:
    self._port.close()                             # and close it here
```

Then:

- `@every(seconds=1, when_connected=True)` pauses polling while disconnected.
- `self.require_connected()` is the one-line guard for a command handler.
- If `on_connect` **raises** - the usual way for hardware to say "I am not here" - the
  button springs back to Disconnected and the property shows `Alert` with the reason.
  Let it raise; do not catch it.

## Talking to real hardware

This is the one thing that catches everyone out.

Instrument libraries are almost always **synchronous** - `pyserial`, a vendor SDK, a
`requests` session. Calling one directly looks completely fine:

```python
@every(seconds=1)
async def poll(self) -> None:
    reading = self._station.read_all()      # DON'T
```

...and it freezes the entire driver for as long as that call takes. Not just this
property - the driver stops answering anything at all, and nothing reports an error. Hand
blocking calls to `off_thread` instead:

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

**A bank of lights, one of which is lit.** The commonest shape in status reporting, and
two lines rather than a pile of near-identical ones:

```python
self.define_light("state_message", Light.from_labels(["Idle", "Opening", "Open"]))
# names become idle, opening, open; labels stay as written

self["state_message"].select("opening", IPState.BUSY)
# that light goes Busy, the rest go Idle, and so does the property
```

Use `if reported not in self["state_message"]` to guard the `select` when the value comes
from hardware that might say something unexpected.

**Stop repeating yourself on the wire.** A driver that polls every second otherwise sends
the same unchanged values every second, forever. Declare the property `on_change` and it
only speaks when something actually differs:

```python
self.define_number("WEATHER_PARAMETERS", [...], perm=IPerm.RO, emit="on_change")
```

Values are still recorded either way - only the notification is skipped.

## Timers and clicks never overlap

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
    await harness.setup()                          # what indiserver sends at startup

    await harness.write("LIGHT_CONTROL", ON=True)  # what the operator clicks

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
