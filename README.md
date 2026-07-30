# INDINexus

A modern, typed Python framework for [INDI](http://www.clearskyinstitute.com/INDI/INDI.pdf)
(Instrument Neutral Distributed Interface) astronomical instrument control.

INDINexus is the successor to [pyINDI](https://github.com/mmtobservatory/pyindi). It
keeps the proven INDI architecture - drivers running under the C `indiserver` hub - but
rebuilds the Python layers on a modern, fully-typed foundation: a Pydantic v2 protocol
core, an async client, a FastAPI + WebSocket web bridge, and a TypeScript/React frontend.

> Status: **early development.** The protocol core, driver SDK, and async client
> (Milestones 1-3) are complete and tested. See [Roadmap](#roadmap).

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
| Language (frontend) | TypeScript + React (Vite) *(planned)* |
| JS packaging | pnpm workspace *(planned)* |

## Getting started

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
# Create the virtualenv and install the package with dev dependencies
uv venv --python 3.12
uv pip install -e ".[dev]"
```

## Development

All commands run through `uv`, which uses the project virtualenv automatically.

```bash
# Run the test suite
uv run pytest

# Run a single test
uv run pytest -k "test_number_vector_def_roundtrip"

# Lint
uv run ruff check src tests

# Auto-format
uv run ruff format src tests

# Type-check (strict)
uv run mypy src
```

Before committing, the expected green baseline is: `ruff check` clean, `mypy src` clean,
and `pytest` passing.

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
├── examples/                # runnable reference driver + client
├── tests/                   # pytest suite
└── web/                     # planned: pnpm workspace (client lib, React bindings, app)
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

## Roadmap

- [x] **M1 - Protocol core**: enums, typed models, XML codec, streaming parser.
- [x] **M2 - Driver SDK**: base device class, `@every`/`@on_new`, stdio transport under
  `indiserver`.
- [x] **M3 - Async client**: reconnecting `indiserver` client with a typed property cache,
  subscriptions, `wait_for`, and `enableBLOB`.
- [x] **M4 - Web bridge + CLI**: FastAPI WebSocket bridge (XML↔JSON), REST snapshot, a
  built-in debug inspector page, and the Typer CLI.
- [ ] **M5 - Frontend**: pnpm workspace (client lib, React bindings, reference app).
- [ ] **M5 - Frontend**: `@indi-nexus/client`, `@indi-nexus/react`, reference panel app.

## License

See [LICENSE](LICENSE).
