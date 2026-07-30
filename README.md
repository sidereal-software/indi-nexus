# INDINexus

A modern, typed Python framework for [INDI](http://www.clearskyinstitute.com/INDI/INDI.pdf)
(Instrument Neutral Distributed Interface) astronomical instrument control.

INDINexus keeps the proven INDI architecture - drivers running under the C `indiserver`
hub - and builds the Python layers on a modern, fully-typed foundation: a Pydantic v2
protocol core, an async client, a FastAPI + WebSocket web bridge, and a TypeScript/React
frontend.

**Documentation:** <https://indi-nexus.sidereal.software/> (guides, live demo, and the
full Python + TypeScript API reference). Working on the code? See
[DEVELOPMENT.md](DEVELOPMENT.md) for the full command reference.

> Status: **early development.** The backend (protocol core, driver SDK, async
> client, web bridge, CLI) and the frontend (framework-agnostic client library,
> React components, and the reference panel) - Milestones 1-5 - are complete and
> tested. See [Roadmap](#roadmap).

## What it is

INDINexus provides three things, all built on one shared, typed protocol model:

1. **Driver SDK** - subclass a base device to write an instrument driver. Drivers run as
   stdio children of the standard `indiserver` binary, speaking INDI 1.7 XML.
2. **Async client** - a reconnecting `asyncio` TCP client to `indiserver` with a typed
   property cache and watch callbacks.
3. **Web bridge + frontend** - a FastAPI app that bridges the browser to `indiserver` over
   a WebSocket, translating INDI XML to typed JSON, plus a TypeScript/React UI.

Design decisions: keep C `indiserver` as the hub (existing INDI drivers and clients
interoperate); canonical INDI 1.7 **XML** on the wire, typed **JSON** to browsers, one
Pydantic model as the shared contract; one monorepo for the Python package and the `pnpm`
frontend workspace so that contract stays in sync.

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12+) and, for the frontend,
[pnpm](https://pnpm.io) (Node 20+). The fastest way to see the **whole stack** - backend,
bridge, and the web panel - with **no `indiserver`** needed:

```bash
# 1. Backend: create the venv and install (first time)
uv venv --python 3.12
uv pip install -e ".[dev]"

# 2. Frontend: build the TypeScript panel into the package (first time / after UI changes)
cd web && pnpm install && pnpm -r build && cd ..

# 3. Run the demo bridge: the web app wired to a live in-process demo device
python -m examples.demo_bridge
```

Then open <http://localhost:8000/> for the reference panel (toggle the Demo device's switch and
watch state update), or <http://localhost:8000/debug> for the raw debug inspector. To serve the
dome simulator instead, add `--device examples.dome_device:DomeSimulator` - see
[The examples](#the-examples) for all the ways to run a driver.

## The examples

Runnable references live in `examples/`:

- **`demo_device.py`** - the reference driver: one of each INDI vector kind, a power switch
  gating a once-per-second animation.
- **`dome_device.py`** - a realistic device: libindi's classic Dome Simulator ported to the
  INDINexus SDK (connection, azimuth rotation, timed shutter, park/unpark, abort, speeds),
  using the standard INDI dome property names.
- **`telescope_device.py`** - libindi's Telescope Simulator ported to the INDINexus SDK:
  the standard goto/slew/sync interaction (`EQUATORIAL_EOD_COORD` + `ON_COORD_SET`),
  tracking modes with realistic sky drift, slew rates, motion paddles, park, abort, and
  timed guide pulses.
- **`ccd_device.py`** - libindi's CCD Simulator ported to the INDINexus SDK: exposures
  that count down and deliver a rendered 16-bit FITS star field as the `CCD1` BLOB,
  frame types, binning, gain/offset, and a TEC cooler with realistic cooling and
  warm-up physics.
- **`monitor_client.py`** - the reference client: subscribe to everything and print each event.
- **`demo_bridge.py`** - the whole stack in one process: one or more drivers wired straight
  into the web app through in-memory pipes (a miniature `indiserver`), no real `indiserver`
  needed.

A driver runs in one of **three modes** - pick the command for what you want to see:

```bash
# 1. The web panel (easiest): drivers + bridge + UI in one process, no indiserver.
#    Repeat --device to put several devices in one panel:
python -m examples.demo_bridge \
    --device examples.telescope_device:TelescopeSimulator \
    --device examples.ccd_device:CCDSimulator \
    --device examples.dome_device:DomeSimulator
# ...then open http://localhost:8000/  (Messages panel = the INDI log; /debug = raw frames)

# 2. Under a real C indiserver (the production arrangement), serving TCP :7624:
indiserver ./examples/telescope_device.py ./examples/ccd_device.py ./examples/dome_device.py
# ...then `indi-nexus serve` for the web panel, or `indi-nexus monitor` for a terminal feed.

# 3. Bare stdio (what indiserver itself launches) - for humans, only useful to pipe XML at:
echo '<getProperties version="1.7"/>' | python -m examples.dome_device
```

Mode 3 waits **silently** for a `getProperties` before saying anything - it is not hung,
it just has no client yet. For an interactive UI, use mode 1 or 2.

## Writing a driver

Subclass `Device`, declare properties in `setup()`, poll with `@every`, and handle client
writes with `@on_new`. Start from a working file with:

```bash
indi-nexus new my_driver.py     # scaffold a commented, runnable driver
python -m examples.demo_bridge --device my_driver:MyDriver   # ...and see it in the panel
```

```python
from indi_nexus.driver import Device, every, on_new
from indi_nexus.protocol import IPState, Number

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
    Mount.run()          # serves over stdio under indiserver
```

The SDK carries the standard INDI lifecycle so a driver is only its own behavior -
see the [driver guide](https://indi-nexus.sidereal.software/guides/writing-drivers/)
for the tour, and `examples/dome_device.py` / `examples/telescope_device.py` for
complete, realistic drivers.

## Building a frontend

Install `@indi-nexus/react`, import the theme once, and compose the hooks and components:

```tsx
import { IndiProvider, useProperty, PropertyVectorCard } from "@indi-nexus/react";
import "@indi-nexus/react/styles.css"; // batteries-included theme (no Tailwind needed)

function Exposure() {
  const vector = useProperty("CCD", "EXPOSURE");
  return vector ? <PropertyVectorCard vector={vector} /> : null;
}

export function App() {
  return (
    <IndiProvider url="ws://localhost:8000/ws">
      <Exposure />
    </IndiProvider>
  );
}
```

`@indi-nexus/client` is the framework-agnostic layer underneath (reconnecting WebSocket +
typed property store, no UI dependency), and the reference panel that ships in the wheel
is built entirely from `@indi-nexus/react` - see the
[frontend guide](https://indi-nexus.sidereal.software/guides/frontend/).

For the Python client, protocol concepts, and the bridge's HTTP/WebSocket surface, head
to the [documentation site](https://indi-nexus.sidereal.software/).

## Roadmap

- [x] **M1 - Protocol core**: enums, typed models, XML codec, streaming parser.
- [x] **M2 - Driver SDK**: base device class, `@every`/`@on_new`, stdio transport under
  `indiserver`.
- [x] **M3 - Async client**: reconnecting `indiserver` client with a typed property cache,
  subscriptions, `wait_for`, and `enableBLOB`.
- [x] **M4 - Web bridge + CLI**: FastAPI WebSocket bridge (XML↔JSON), REST snapshot, a
  built-in debug inspector page, and the Typer CLI.
- [x] **M5 - Frontend**: a `pnpm` workspace with `@indi-nexus/client` (framework-agnostic
  transport + typed property store), `@indi-nexus/react` (hooks + shadcn/ui components +
  the shared theme), and the reference panel app that ships with `indi-nexus`.

## License

See [LICENSE](LICENSE).
