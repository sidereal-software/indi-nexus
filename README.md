# INDINexus

A modern, typed Python framework for [INDI](http://www.clearskyinstitute.com/INDI/INDI.pdf)
(Instrument Neutral Distributed Interface) astronomical instrument control.

INDINexus is the successor to [pyINDI](https://github.com/mmtobservatory/pyindi). It
keeps the proven INDI architecture - drivers running under the C `indiserver` hub - but
rebuilds the Python layers on a modern, fully-typed foundation: a Pydantic v2 protocol
core, an async client, a FastAPI + WebSocket web bridge, and a TypeScript/React frontend.

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

### Design decisions

- **Keep C `indiserver` as the hub.** INDINexus modernizes the Python driver SDK, client,
  and web layers; it does not replace `indiserver`. Existing INDI drivers and clients
  interoperate.
- **Dual protocol.** Canonical INDI 1.7 **XML** on the `indiserver` wire (for
  interoperability with the wider INDI ecosystem); typed **JSON** to browsers.
- **Monorepo.** One repository holds the Python package and a `pnpm` JavaScript workspace
  (a framework-agnostic client library, React bindings, and a reference app), so the wire
  contract stays in sync across the language boundary.

## Software stack

| Layer | Technology |
|---|---|
| Language (backend) | Python 3.12+ |
| Data model / validation | Pydantic v2 |
| XML | lxml |
| Web / API | FastAPI + Uvicorn, native WebSockets |
| CLI | Typer |
| Concurrency | asyncio (stdlib) |
| Packaging / env | uv, hatchling |
| Lint / format | Ruff |
| Type checking | mypy (strict) |
| Tests | pytest + pytest-asyncio |
| Language (frontend) | TypeScript + React (Vite) |
| UI components / theme | shadcn/ui + Tailwind CSS v4 |
| JS packaging | pnpm workspace, tsup, Biome, Vitest |

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
watch state update), or <http://localhost:8000/debug> for the raw debug inspector.

## Command reference

**Backend** (Python, run through `uv`):

```bash
uv run pytest                     # run the test suite
uv run pytest -k "name"           # run a single test by name
uv run ruff check src tests       # lint
uv run ruff format src tests      # auto-format
uv run mypy src                   # type-check (strict)
```

**Frontend** (TypeScript, run with `pnpm` from `web/`):

```bash
pnpm install                          # install workspace deps (first time)
pnpm -r build                         # build the libraries + panel (into the Python package)
pnpm -r test                          # run all package tests (Vitest)
pnpm -r typecheck                     # type-check every package
pnpm lint                             # lint + format check (Biome)
pnpm --filter @indi-nexus/panel dev   # panel dev server with hot reload (proxies to :8000)
```

**Run it**:

```bash
python -m examples.demo_bridge              # bridge + live demo device, no indiserver (open :8000)
indi-nexus serve                            # bridge against a real indiserver (open :8000)
indi-nexus run examples.demo_device:Demo    # serve a driver over stdio (under indiserver)
indi-nexus monitor                          # print live INDI updates from indiserver
indi-nexus --help                           # all CLI commands and options
```

**Package**:

```bash
uv build                          # build sdist + wheel; the panel is bundled, so pip install ships the UI
```

The expected green baseline before committing: `ruff check` + `mypy src` + `pytest` clean, and
in `web/`, `pnpm lint` + `pnpm -r typecheck` + `pnpm -r test` + `pnpm -r build` clean. CI
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs all of these plus a check that the
wheel bundles the panel.

## Project layout

```
indi-nexus/
├── pyproject.toml           # packaging, dependencies, tool config (ruff/mypy/pytest)
├── src/indi_nexus/
│   ├── protocol/            # DONE: the INDI protocol core
│   │   ├── enums.py         #   IPState / IPerm / ISRule / ISState / BLOBPolicy (str enums)
│   │   ├── models.py        #   typed Pydantic vectors, elements, def/set/new + enableBLOB
│   │   └── xml.py           #   INDI XML codec + streaming pull-parser + sexagesimal
│   ├── driver/              # DONE: driver SDK (stdio under indiserver)
│   ├── client/              # DONE: reconnecting async client + property cache
│   ├── transport.py         # DONE: shared read/write byte-stream contract + TCP adapter
│   ├── web/                 # DONE: FastAPI bridge (WS + REST) + static/debug.html
│   └── cli.py               # DONE: Typer CLI (serve / run / monitor)
├── examples/                # runnable reference driver, client, and demo bridge
├── tests/                   # pytest suite
└── web/                     # DONE: pnpm workspace (TypeScript frontend)
    ├── packages/client/     #   @indi-nexus/client - framework-agnostic transport + store
    ├── packages/react/      #   @indi-nexus/react  - hooks + shadcn/ui components + theme
    └── apps/panel/          #   the reference panel (built into web/static/panel)
```

## The protocol core

`indi_nexus.protocol` is the single source of truth for the INDI 1.7 wire format. Every
property is a validated Pydantic model that serializes to both INDI XML and JSON.

```python
from indi_nexus.protocol import (
    NumberVector, Number, IPState, IPerm, DefVector, to_xml, parse_indi,
)

vec = NumberVector(
    device="CCD", name="EXPOSURE", state=IPState.OK, perm=IPerm.RW,
    elements=[Number(name="CCD_EXP", format="%.2f", min=0, max=3600, value=1.5)],
)

xml = to_xml(DefVector(vector=vec))     # -> canonical <defNumberVector> bytes
(msg,) = parse_indi(xml)                # -> DefVector model, fully typed
assert msg.vector["CCD_EXP"].value == 1.5
```

For a continuous socket/stdio stream, use `XMLStreamParser`, which emits complete messages
as top-level elements arrive (reassembling across arbitrary chunk boundaries).

## Writing a driver

Subclass `Device`, declare properties in `setup()`, poll with `@every`, and handle client
writes with `@on_new`. See `examples/demo_device.py`.

```python
from indi_nexus.driver import Device, every, on_new
from indi_nexus.protocol import Number, IPState, IPerm

class Mount(Device):
    name = "Mount"

    async def setup(self) -> None:
        self.define_number(
            "EQUATORIAL_EOD_COORD",
            [Number(name="RA", format="%9.6m"), Number(name="DEC", format="%9.6m")],
            perm=IPerm.RO,
        )

    @every(seconds=1)
    async def poll(self) -> None:
        ra, dec = await self.read_mount()
        self["EQUATORIAL_EOD_COORD"].set(RA=ra, DEC=dec, state=IPState.OK)

if __name__ == "__main__":
    Mount.run()          # serves over stdio under indiserver
```

## Using the client

`IndiClient` keeps a typed cache of `indiserver` state, lets you watch it, and sends
updates - reconnecting automatically. See `examples/monitor_client.py`.

```python
from indi_nexus.client import IndiClient
from indi_nexus.protocol import IPState

async with IndiClient("localhost", 7624) as client:
    client.subscribe(lambda e: print(e.type, e.device, e.name))  # sync or async
    await client.set_number("CCD", "EXPOSURE", {"secs": 1.5})
    image = await client.wait_for(
        "CCD", "EXPOSURE", lambda v: v.state == IPState.OK, timeout=30
    )
```

## Run the web bridge

The bridge connects to `indiserver`, keeps a typed cache, and relays it to browsers as
JSON over a WebSocket. Everything runs through the `indi-nexus` CLI:

```bash
indi-nexus serve --indi-host localhost --indi-port 7624 --port 8000
```

Then open `http://localhost:8000/` for the built-in **debug inspector** - a live,
color-coded property tree, a streaming message feed, and clickable/editable controls to
send writes (handy for exercising a driver's `@on_new` handlers). Other endpoints:

- `GET /health` - liveness + upstream connection state.
- `GET /api/devices`, `GET /api/devices/{device}[/{name}]` - read-only JSON snapshot.
- `WS /ws` - live stream (snapshot on connect, then updates); browser frames are forwarded
  upstream. Messages are the protocol models as JSON, so the frontend contract is the
  backend model schema.

Other CLI commands: `indi-nexus run examples.demo_device:Demo` (serve a driver over stdio),
`indi-nexus monitor` (print live updates).

## Frontend

The TypeScript frontend lives in `web/` as a `pnpm` workspace with three layers, all built
on one shared wire contract and themed with [shadcn/ui](https://ui.shadcn.com):

- **`@indi-nexus/client`** - a framework-agnostic, reconnecting client for the bridge's
  WebSocket and a typed property store (a TS port of the Python client). No UI dependency.
- **`@indi-nexus/react`** - `IndiProvider`, hooks (`useProperty`, `useDevice`,
  `useConnection`, ...), INDI-aware components (`PropertyVectorCard`, `DevicePanel`,
  `StateBadge`, `ConnectionStatus`, `MessageLog`), and the themed shadcn/ui primitives.
- **`apps/panel`** - the reference panel that ships with `indi-nexus`.

### Build and run the reference panel

```bash
cd web
pnpm install
pnpm -r build          # builds the libraries + panel into src/indi_nexus/web/static/panel/
```

Once built, the FastAPI app serves the panel at `/` (the debug inspector stays at `/debug`).

**Packaging:** the panel is bundled into the wheel, so `pip install indi-nexus` ships the UI.
Building a distribution (`uv build`) runs the frontend build automatically when Node/pnpm are
available (via `hatch_build.py`); to package offline, run `pnpm -r build` first and the
pre-built panel is bundled as-is. If neither is possible the wheel is built without the panel
and the bridge falls back to the debug page.

To see it end-to-end with **no `indiserver`**, run the in-process demo bridge - it wires the
demo driver straight into the web app:

```bash
python -m examples.demo_bridge      # then open http://localhost:8000/
```

For panel development with hot reload, run the bridge (above, or `indi-nexus serve` against a
real `indiserver`) and the Vite dev server, which proxies `/ws` and `/api` to it:

```bash
pnpm --filter @indi-nexus/panel dev
```

### Build your own UI on the library

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

If you run Tailwind yourself, `@import "@indi-nexus/react/theme.css"` instead of the prebuilt
stylesheet and let your own build generate the utilities.

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
