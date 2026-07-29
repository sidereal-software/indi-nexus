# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Project overview

INDINexus (`indi-nexus`) is a modern, typed Python framework for the
[INDI protocol](http://www.clearskyinstitute.com/INDI/INDI.pdf) (astronomical instrument
control). It is the successor to [pyINDI](https://github.com/mmtobservatory/pyindi),
which is used in production at MMT Observatory and Steward Observatory. The legacy pyINDI
source is available in the sibling `../pyINDI` directory for reference.

INDINexus rebuilds pyINDI's Python layers - the driver SDK, the async client, and the web
bridge - on a fully-typed Pydantic v2 + FastAPI foundation, with a TypeScript/React
frontend. It does **not** reimplement the C `indiserver` binary.

## Locked architectural decisions

These were decided at project start; do not revisit them without explicit direction.

1. **Keep C `indiserver` as the hub.** Drivers run as stdio children of `indiserver`; the
   web layer is a TCP client of it. We modernize only the Python and frontend layers.
2. **Dual protocol.** Canonical INDI 1.7 **XML** on the `indiserver` wire (interop with the
   wider INDI ecosystem); typed **JSON** to browsers.
3. **Monorepo.** Python package under `src/indi_nexus/` plus a planned `pnpm` JS workspace
   under `web/`. The wire contract is shared across the boundary (types generated from the
   backend models).
4. **Frontend is TypeScript + React (Vite), over WebSockets.** Distribution is three
   layers: `@indi-nexus/client` (framework-agnostic transport + property store),
   `@indi-nexus/react` (hooks + components), and a reference panel app. Both
   "batteries-included app" and "build your own UI on the library" are first-class.

## Commands

This project uses [uv](https://docs.astral.sh/uv/). Run everything through it.

```bash
uv venv --python 3.10           # create the venv (first time)
uv pip install -e ".[dev]"      # install package + dev deps

uv run pytest                   # run tests
uv run pytest -k "name"         # run one test
uv run ruff check src tests     # lint
uv run ruff format src tests    # format
uv run mypy src                 # type-check (strict)
```

**Green baseline before any commit:** `ruff check` clean, `mypy src` clean, `pytest`
passing. Each milestone lands with its own tests; keep that discipline.

## Architecture

```
src/indi_nexus/
├── protocol/     DONE   the INDI protocol core (see below)
├── driver/       planned  driver SDK: subclass a base device; stdio XML under indiserver
├── client/       planned  reconnecting asyncio TCP client to indiserver + property cache
├── web/          planned  FastAPI app: WebSocket bridge translating INDI XML <-> JSON
└── cli.py        planned  Typer CLI (run driver, serve web, scan)
```

Data flow (unchanged from the INDI model):

```
Driver (driver/) <-stdin/stdout XML-> indiserver:7624 <-TCP-> client/  ->  web/ (FastAPI)
                                                                              | WebSocket (JSON)
                                                                           Browser (React/TS)
```

### The protocol layer (`src/indi_nexus/protocol/`)

The single source of truth for the INDI 1.7 wire format. It replaces three fragile pieces
of pyINDI: runtime DTD reflection, `int`-subclass enums that compared against wire strings,
and the "accumulate stdin and retry `etree.fromstring`" framing loop.

- `enums.py` - `IPState`, `IPerm`, `ISRule`, `ISState`. These mix in `str` so a member
  **is** its exact wire token (`IPState.OK == "Ok"`) and Pydantic serializes it directly.
  (`enum.StrEnum` would be idiomatic but is 3.11+; we target 3.10.)
- `models.py` - typed Pydantic models. Key design choices:
  - A **vector** (`NumberVector`, `TextVector`, `SwitchVector`, `LightVector`,
    `BLOBVector`) is the canonical in-memory representation of a property. Discriminated on
    the `kind` field.
  - `def` / `set` / `new` are a wire **intent**, not different data shapes, so they are thin
    event wrappers (`DefVector`, `SetVector`, `NewVector`) around a vector - not five
    duplicated classes each.
  - Element metadata (number `format`/`min`/`max`/`step`, switch `rule`) is optional with
    defaults, because `set`/`one` messages carry only `name` + value. Clients merge `set`
    values onto the previously-defined vector (standard INDI behavior).
  - `LightVector` has no `perm` (lights are always read-only in INDI).
- `xml.py` - the codec.
  - `to_xml(msg)` serializes a message model to canonical INDI XML.
  - `parse_indi(data)` parses a complete chunk; `XMLStreamParser` is the incremental
    parser for a socket/stdio stream (feeds a synthetic root, emits depth-1 elements as
    they complete, clears consumed nodes to keep memory flat).
  - Number values honor the INDI printf `format`, including the `%m` sexagesimal form
    (`format_number` / `parse_number` mirror libindi's `fs_sexa` / `f_scansexa`). This
    matters for RA/Dec interop; `%9.6m` etc. are field-width padded like libindi.

## Conventions

- Python 3.10+ floor. Line length 100. Ruff rules: `E,F,I,UP,B,SIM,ASYNC`.
- Fully typed; `mypy --strict` must pass on `src`. Prefer PEP 604 unions (`X | Y`).
- New wire behavior gets a round-trip test in `tests/test_protocol.py` (serialize ->
  parse -> assert), and streaming behavior gets a chunk-boundary test.
- When touching the protocol, keep XML and JSON serialization consistent - the models are
  the shared contract with the frontend.

## Git

- Conventional Commits (`type(scope): summary`). Keep commits small and scoped to a
  section of work.
- Do not commit or push unless explicitly asked. Never `git add .`; stage only relevant
  files. Do not add a Claude/agent commit co-author.
- Run the green baseline (tests, ruff, mypy) before proposing a commit.
