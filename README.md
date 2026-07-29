# INDINexus

A modern, typed Python framework for [INDI](http://www.clearskyinstitute.com/INDI/INDI.pdf)
(Instrument Neutral Distributed Interface) astronomical instrument control.

INDINexus is the successor to [pyINDI](https://github.com/mmtobservatory/pyindi). It
keeps the proven INDI architecture - drivers running under the C `indiserver` hub - but
rebuilds the Python layers on a modern, fully-typed foundation: a Pydantic v2 protocol
core, an async client, a FastAPI + WebSocket web bridge, and a TypeScript/React frontend.

> Status: **early development.** The protocol core (Milestone 1) is complete and tested.
> See [Roadmap](#roadmap).

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
| Language (backend) | Python 3.10+ |
| Data model / validation | Pydantic v2 |
| XML | lxml |
| Web / API | FastAPI + Uvicorn, native WebSockets |
| CLI | Typer |
| Concurrency | asyncio + anyio |
| Packaging / env | uv, hatchling |
| Lint / format | Ruff |
| Type checking | mypy (strict) |
| Tests | pytest + pytest-asyncio |
| Language (frontend) | TypeScript + React (Vite) *(planned)* |
| JS packaging | pnpm workspace *(planned)* |

## Getting started

Requires [uv](https://docs.astral.sh/uv/) and Python 3.10+.

```bash
# Create the virtualenv and install the package with dev dependencies
uv venv --python 3.10
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
│   │   ├── enums.py         #   IPState / IPerm / ISRule / ISState (wire-token str enums)
│   │   ├── models.py        #   typed Pydantic vectors, elements, and def/set/new events
│   │   └── xml.py           #   INDI XML codec + streaming pull-parser + sexagesimal
│   ├── driver/              # planned: driver SDK (stdio under indiserver)
│   ├── client/              # planned: async client to indiserver
│   ├── web/                 # planned: FastAPI + WebSocket bridge
│   └── cli.py               # planned: Typer CLI
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

## Roadmap

- [x] **M1 - Protocol core**: enums, typed models, XML codec, streaming parser.
- [ ] **M2 - Driver SDK**: base device class, stdio transport under `indiserver`.
- [ ] **M3 - Async client**: reconnecting `indiserver` client with typed property cache.
- [ ] **M4 - Web bridge + CLI**: FastAPI WebSocket bridge (XML↔JSON), Typer CLI.
- [ ] **M5 - Frontend**: `@indi-nexus/client`, `@indi-nexus/react`, reference panel app.

## License

See [LICENSE](LICENSE).
