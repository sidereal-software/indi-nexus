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
elements *and* notifies every client in one call; `OneOfMany` switch rules are
honoured automatically.

**Connection** - `define_connection()` adds the standard `CONNECTION` switch.
The built-in handler flips it, calls your `on_connect()` / `on_disconnect()`
hooks (open and close your hardware link there), and announces the transition.
`self.connected` reads the state; `self.require_connected()` is the one-line
guard for handlers; `@every(..., when_connected=True)` pauses polling while
disconnected.

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

## Testing your driver

Drive the runtime over in-memory pipes, exactly as `indiserver` would - no
sockets, no processes (see `tests/test_driver.py` and `tests/test_examples.py`
for the patterns used to test the built-in examples):

```python
runtime = DriverRuntime(MyDriver(), read, write)   # your in-memory callables
```

## Full API

See the [driver SDK reference](../reference/python/driver.md).
