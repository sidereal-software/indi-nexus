# INDINexus

INDINexus is a Python toolkit for writing INDI instrument drivers. If you have written
one before, what is different here is that the plumbing is already done: a driver is one
Python class, it runs under the `indiserver` you already have, you can test all of it
with nothing plugged in, and a browser control panel comes with it. If INDI itself is new
to you, [the protocol page](guides/protocol.md) has the vocabulary.

To see it running first, [drive a simulated dome in your browser](demo-app/index.html):
the real panel, with nothing installed. [Two more demos are below](#demos-in-your-browser).

Here is a complete driver for a flat-field lamp - a switch and a brightness dial:

```python title="examples/flat_panel.py, trimmed for this page"
from indi_nexus.driver import Device, on_new
from indi_nexus.protocol import (
    IPState, ISRule, ISState, Number, NumberVector, Switch, SwitchVector,
)

MIN_BRIGHTNESS = 0
MAX_BRIGHTNESS = 255


class FlatPanel(Device):
    """A flat-field lamp: on/off, and a brightness dial."""

    name = "Flat Panel"

    async def setup(self) -> None:
        """Define the connection switch, the lamp and the dial."""
        self.define_connection()
        self.define_switch(
            "LIGHT_CONTROL",
            [
                Switch(name="ON", label="On"),
                Switch(name="OFF", label="Off", value=ISState.ON),
            ],
            # Exactly one of these is on, so a client draws radio
            # buttons, and turning one on turns the other off
            # without the driver saying so.
            rule=ISRule.ONE_OF_MANY,
            label="Lamp",
            group="Main Control",
        )
        self.define_number(
            "LIGHT_BRIGHTNESS",
            [
                Number(
                    name="BRIGHTNESS",
                    label="Brightness",
                    format="%.0f",
                    min=MIN_BRIGHTNESS,
                    max=MAX_BRIGHTNESS,
                    value=128,
                )
            ],
            label="Brightness",
            group="Main Control",
        )
        self.message("Flat panel ready.")

    async def on_disconnect(self) -> None:
        """Turn the lamp off: a panel left lit fogs the next exposure."""
        self["LIGHT_CONTROL"].set({"OFF": ISState.ON}, state=IPState.IDLE)
        self.message("Lamp turned off on disconnect.")

    @on_new("LIGHT_CONTROL")
    async def _switch_lamp(self, vector: SwitchVector) -> None:
        """Turn the lamp on or off in response to a client write."""
        if not self.require_connected():
            return
        on = vector.selected() == "ON"
        self["LIGHT_CONTROL"].set(
            {"ON" if on else "OFF": ISState.ON},
            state=IPState.OK,
        )
        self.message(f"Lamp turned {'on' if on else 'off'}.")

    @on_new("LIGHT_BRIGHTNESS")
    async def _set_brightness(self, vector: NumberVector) -> None:
        """Clamp a requested brightness to the advertised range."""
        if not self.require_connected():
            return
        wanted = vector.get("BRIGHTNESS", 0.0)
        # The advertised min/max is a promise about the hardware.
        clamped = max(MIN_BRIGHTNESS, min(MAX_BRIGHTNESS, wanted))
        self["LIGHT_BRIGHTNESS"].set(BRIGHTNESS=clamped, state=IPState.OK)


if __name__ == "__main__":
    FlatPanel.run()
```

That is
[`examples/flat_panel.py`](https://github.com/sidereal-software/indi-nexus/blob/main/examples/flat_panel.py),
shown trimmed for this page - the file in the repository carries its module header and
fuller docstrings, and folds nothing. It is covered
by the test suite, it is the driver the [driver guide](guides/writing-drivers.md) builds
one property at a time, and you can [drive it in your browser](flat-demo/flat.html)
without installing anything.

## The plumbing it replaces

What INDINexus stands in for is the driver you would otherwise hand-roll: the read loop
over stdin, the XML parser that has to survive a start tag split across two reads, the
dispatch chain on property name, the timer whose period drifts by the length of each
tick, and the poll that lands on top of a command that arrived while it was out.

The last two are handled explicitly. `@every` runs against a rolling deadline, so a job's
period does not drift by the tick's own duration, and
[ticks and client writes never overlap](guides/writing-drivers.md#serialised-dispatch),
so a slow poll cannot publish pre-write state over a button the operator just pressed.

## Install and run

```bash
pip install indi-nexus
indi-nexus new my_driver.py
indi-nexus serve --device my_driver:MyDriver
```

Open <http://localhost:8000/>. The driver `new` just wrote is in the sidebar with a
control panel in front of it: press Connect and its telemetry starts counting.

Python 3.12 or newer is the only requirement. The panel is compiled into the wheel, so
there is no Node build, and `--device` runs the driver in-process, so there is no
`indiserver` to install first.

[Getting started, a step at a time](getting-started.md){ .md-button .md-button--primary }

## Demos in your browser

Each one runs the real panel against a driver simulated inside your browser, speaking
the same JSON the FastAPI bridge speaks. The simulation runs in the page itself, so there
is nothing to download and no server or account involved.

<div class="grid cards" markdown>

-   **A dome you can move**

    Press Connect, open the shutter, send it to an azimuth, park it, hit Abort
    mid-slew. The message log narrates what the driver is saying, the way it would at
    a real site.

    [Open the dome demo](demo-app/index.html){ .md-button }

-   **The driver at the top of this page**

    The same flat panel: same property names, same exclusive switch rule, same clamped
    brightness range. Press Connect, light the lamp, then disconnect and watch it go
    out.

    [Open the lamp demo](flat-demo/flat.html){ .md-button }

-   **Live data, one device, two UIs**

    Real readings fetched from Open-Meteo, shown twice from a single client: the panel
    that generates itself, and a hand-built operator screen. The
    [tutorial](guides/tutorial-open-meteo.md) writes both.

    [Open the weather demo](weather-demo/weather.html){ .md-button }

</div>

## Testing without hardware

A driver is an ordinary Python object, so a test can drive it and read back what it told
its clients:

```python
from indi_nexus.protocol import ISState
from indi_nexus.testing import DeviceHarness

from flat_panel import FlatPanel


async def test_lamp_turns_on():
    harness = DeviceHarness(FlatPanel())
    await harness.setup()  # what indiserver sends at startup
    await harness.write("CONNECTION", CONNECT=True)  # the operator presses Connect

    await harness.write("LIGHT_CONTROL", ON=True)  # and clicks On

    assert harness.latest("LIGHT_CONTROL").get("ON") is ISState.ON
    assert "turned on" in harness.messages[-1]
```

Nothing in that test opens a socket, starts a subprocess, parses XML or touches an
instrument. `write()` builds the partial vector a real client sends and routes it through
the device's real dispatch (the `@on_new` map, the device-name guard, the serialisation
lock), so a handler that passes here works under `indiserver`. `tick(job)` runs one
iteration of an `@every` job without waiting out its interval.

Every example in the repository is covered this way, the flat panel above included. The
driver guide's [testing section](guides/writing-drivers.md#testing-without-hardware) is
the full account.

!!! note "Running that test"

    It is written for `pytest` with [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
    in `asyncio_mode = "auto"`. Without that, wrap the body in `asyncio.run`.

## The generated control panel

Every INDI device says what it has - properties, kinds, ranges, labels - so the UI can
be generated from the device rather than written per instrument:

```tsx
import { IndiProvider, DevicePanel } from "@indi-nexus/react";
import "@indi-nexus/react/styles.css";

export function App() {
  return (
    <IndiProvider url="ws://localhost:8000/ws">
      <DevicePanel device="Flat Panel" />
    </IndiProvider>
  );
}
```

Numbers get their units and limits, switches become radio buttons or checkboxes according
to the INDI rule, lights become a coloured dot with its state written beside it, BLOBs
become download links, and read-only properties are not editable. For a purpose-built
screen instead, the same data is on hooks. [Building a frontend](guides/frontend.md)
covers both.

## How the pieces fit

INDINexus does not replace `indiserver`, the hub program observatories already run - it
plugs into it. Your driver is an ordinary INDI driver, so existing INDI software
(KStars/Ekos, PHD2, other drivers) works with it unchanged.

```mermaid
flowchart LR
    subgraph py["Python (indi_nexus)"]
        drv["Driver SDK<br/>driver/"]
        cli["IndiClient<br/>client/"]
        web["FastAPI bridge<br/>web/"]
    end
    hw(["Instrument"]) --- drv
    drv -- "stdio<br/>INDI 1.7 XML" --> hub["indiserver<br/>C hub, :7624"]
    hub -- "TCP<br/>INDI 1.7 XML" --> cli
    drv -. "in-memory pipes<br/>serve --device: no hub" .-> cli
    cli --> web
    web -- "WebSocket<br/>typed JSON" --> ui["React panel<br/>or your UI"]

    %% No colours here on purpose: GitHub and the docs site each theme the diagram
    %% for their own light and dark modes, and a hardcoded light palette turns into
    %% unreadable text on a dark page. Ownership rides on the border instead - thick
    %% solid is ours, thin dashed is not - which survives any theme and never leans
    %% on colour alone.
    classDef ours stroke-width:3px
    classDef ext stroke-width:1px,stroke-dasharray:4 4
    class drv,cli,web ours
    class hub,hw,ui ext
```

- Your driver talks to the instrument and speaks INDI to `indiserver`.
- The client connects to that hub and mirrors everything into a typed cache you can read
  and watch from Python.
- The bridge puts that cache behind a WebSocket so a browser can show it.

You do not need all three; writing only a driver is the common case.

## What this does not do

- It does not reimplement `indiserver`. The C hub stays the hub and your driver runs as
  its child, which is what keeps the rest of the INDI ecosystem working against it. Only
  the Python and browser layers are new here.
- `--device` is not a hub. It runs drivers inside the web process: one client, and it
  stops when you stop the command. It exists so that trying this out needs one install
  instead of two. Run anything real under `indiserver`. (It is not an unguarded surface:
  `--token` and `--allow-origin` apply the same as without `--device`, and a non-loopback
  `--host` with no token is refused either way.)
- It does not talk to your instrument for you. There is no vendor library in here. You
  write the link to the hardware; `await self.off_thread(...)` keeps a blocking vendor
  call from stalling the event loop, and that is the extent of the help.

## Pick a starting point

<div class="grid cards" markdown>

-   **Writing a driver**

    Defining properties, polling with `@every`, handling client writes with `@on_new`,
    the connection lifecycle, and testing the result. Builds the flat panel above.

    [Write a driver](guides/writing-drivers.md)

-   **Coming from pyINDI**

    A row-by-row mapping from `ISGetProperties`, the four `ISNew*` methods, `IUFind`,
    `IDSet` and `@device.repeat` to their equivalents here. Property names, element
    names, labels and groups all stay as they are, so your existing clients see the same
    device before and after the port.

    [Port a pyINDI driver](guides/porting-from-pyindi.md)

-   **Drivers that talk to real hardware**

    A blocking vendor-style client behind `off_thread`, hardware that stops answering,
    and `emit="on_change"` readbacks. `weather_device.py` is the one to copy.

    [Read the examples](guides/examples.md)

-   **The API**

    Every public signature, generated from the source.

    [Driver SDK](reference/python/driver.md) ·
    [Testing](reference/python/testing.md) ·
    [Client](reference/python/client.md) ·
    [Protocol](reference/python/protocol.md)

</div>
