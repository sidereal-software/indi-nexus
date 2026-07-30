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
uv venv --python 3.12           # create the venv (first time)
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
├── driver/       DONE   driver SDK: subclass a base device; stdio XML under indiserver
├── client/       DONE   reconnecting asyncio TCP client to indiserver + property cache
├── transport.py  DONE   shared ReadFn/WriteFn byte-stream contract + TCP adapter
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

- `enums.py` - `IPState`, `IPerm`, `ISRule`, `ISState`, `BLOBPolicy`. Each subclasses
  `enum.StrEnum`, so a member **is** its exact wire token (`IPState.OK == "Ok"`) and
  Pydantic serializes it directly.
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
  - Non-property messages: `GetProperties`, `DelProperty`, `Message`, and `EnableBLOB`
    (`BLOBPolicy` = `Never`/`Also`/`Only`) - a client must send `enableBLOB` before
    `indiserver` forwards any BLOB.
- `xml.py` - the codec.
  - `to_xml(msg)` serializes a message model to canonical INDI XML.
  - `parse_indi(data)` parses a complete chunk; `XMLStreamParser` is the incremental
    parser for a socket/stdio stream (feeds a synthetic root, emits depth-1 elements as
    they complete, clears consumed nodes to keep memory flat).
  - Number values honor the INDI printf `format`, including the `%m` sexagesimal form
    (`format_number` / `parse_number` mirror libindi's `fs_sexa` / `f_scansexa`). This
    matters for RA/Dec interop; `%9.6m` etc. are field-width padded like libindi.

### The driver SDK (`src/indi_nexus/driver/`)

What a driver author subclasses. It rebuilds pyINDI's `device.py` on the M1 models and
fixes its known warts (class-global `@repeat` registry, the hand-rolled
`etree.fromstring` retry loop, the `if/elif`-on-XML-tag `ISNew*` dispatch, and the
libindi-C surface `IUFind`/`IDSet*`/`IEAddTimer`).

- `device.py` - `Device`, the base class. Override `async def setup()` to declare
  properties with the `define_number/text/switch/light/blob(...)` helpers (each returns a
  `BoundProperty` and emits the `def`). Access later via `self["NAME"]`. `self.message()`
  / `self.log_error()` send INDI `message`s. `Device.run()` serves it over stdio.
- `property.py` - `BoundProperty`, the driver-side handle wrapping a (pure) protocol
  vector. `.set(RA=1.2, DEC=3.4, state=IPState.OK)` mutates elements **and** emits one
  `setXxxVector`; it honors `OneOfMany` switch rules (turning one On clears siblings). The
  protocol models stay behavior-free - this wrapper is where "and tell the client" lives.
- `scheduling.py` - `@every(seconds=…, minutes=…, hours=…)`, the modern replacement for
  pyINDI's `@device.repeat`. It only *tags* a method; discovery/execution is **per
  instance** (no shared class state), one supervised task each, with per-tick error
  isolation (a failing tick logs and continues, never kills the driver).
- `dispatch.py` - `@on_new("PROP")` tags the handler for client writes to a property; the
  device builds a per-instance name->handler map and passes the fully typed parsed vector.
  Unhandled writes fall through to `on_new_default`.
- `runtime.py` - `DriverRuntime` owns the stdio transport and the supervision loop. It
  takes plain `read`/`write` callables (the shared `ReadFn`/`WriteFn` from `transport.py`),
  so tests drive it through in-memory byte streams exactly as `indiserver` would; `run()`
  wires real stdin/stdout. Plain `asyncio`: an outbox `asyncio.Queue`, a writer task, and
  one task per periodic job, all driven by the reader until stdin EOF.

`examples/demo_device.py` is the reference driver (one of each vector kind, an `@every`
animation, and an `@on_new` handler).

### The client (`src/indi_nexus/client/`)

A reconnecting `asyncio` TCP client to `indiserver` that mirrors server state into a typed
cache and lets code watch it and send updates - always as M1 models, never raw XML. It
replaces pyINDI's `client.py`/`utils.py` (raw XML strings, subclass-override, singleton
hacks, a SAX handler, and *no* cache).

- `store.py` - `PropertyStore`, the pure cache (behavior-free w.r.t. sockets, so trivially
  testable). `apply(msg)` folds one message in following INDI semantics (`def` defines,
  `set` **merges** values/state onto the definition keeping def-only metadata, `del`
  removes a property or a whole device) and returns a `PropertyEvent`. It also holds the
  subscription registry; `matching(event)` returns the interested callbacks - the client
  does the actual (possibly async) dispatch, keeping the store pure.
- `client.py` - `IndiClient`. Async context manager (`async with IndiClient(host, port)`)
  or `run()` for monitors. A background loop connects, sends `getProperties` (+ replays any
  `enableBLOB` policies) on every (re)connect, runs a reader (folds into the store,
  dispatches to subscribers - sync **and** async callbacks) and a writer (outbox
  `asyncio.Queue`), and reconnects with a fixed delay. Reads: `get`, `store`,
  `client[device]`. Watch: `subscribe(cb, device=, name=)`, `on_message`, `on_connection`.
  Scripting: `await wait_for(device, name, predicate=, timeout=)`. Sends: `get_properties`,
  `enable_blob`, `set_number/text/switch/blob`. The transport is injectable (a `connect`
  coroutine returning `read`/`write`), so tests drive it over in-memory streams; the
  default uses `transport.open_tcp`.

`examples/monitor_client.py` is the reference client (subscribe to all events, print each).
`tests/test_integration.py` cross-wires a `DriverRuntime` and an `IndiClient` through
in-memory pipes - a full driver<->client round-trip with no `indiserver`.

## Conventions

- Python 3.12+ floor. Line length 100. Ruff rules: `E,F,I,UP,B,SIM,ASYNC`. Use the
  stdlib directly (`enum.StrEnum`, `asyncio.TaskGroup`, `asyncio.timeout`, ...); no
  back-compat shims or third-party async layers.
- Fully typed; `mypy --strict` must pass on `src`. Every public signature (in `src`) carries
  full type hints on params and return. Test code does **not** need type-hinted signatures.
- Docstrings are **Numpydoc style** (per the
  [LSST DM guide](https://developer.lsst.io/python/numpydoc.html)) on **every** module,
  class, and function - public, private (`_x`), dunder, and every test - so a future
  Sphinx + ReadTheDocs autodoc build renders the API reference straight from the source.
  (We'll enable ruff's `D` rules with `convention = "numpy"` when the docs site is wired up.)
  Follow these rules exactly - they are the ones most easily gotten wrong:
  - **Every parameter goes on its own entry. Never combine names** on one line
    (`label, group : ...` is wrong - write a separate entry for each).
  - Each entry is `name : type` with the type as **plain text, NOT in backticks**
    (`name : str`, not ``name : `str` ``). Use short type names (`IPState`, not
    `~indi_nexus.protocol.IPState`), `list of X` for lists, and `X or None` for unions.
    Then the description is indented on the following line(s). Append `, optional` after
    the type for any parameter that has a default, e.g. `timeout : float, optional`.
  - Types appear in docstrings **even though the signature is also annotated** - the
    signature is the checker's truth, the docstring type is what renders in the API docs.
  - `Returns` / `Yields` entries use the same `name : type` form. `Raises` lists the
    exception type then an indented description. Do **not** document `self`.
  - Inline references inside description prose may use backticks (e.g. `` `True` ``,
    `` `None` ``); the no-backticks rule is only about the `name : type` type field.
  - Use the imperative mood in the one-line summary ("Return ...", "Send ...").
- Inline comments explain only what the code and docstring can't - the local "why" behind a
  non-obvious line. Don't restate what the signature or docstring already says.
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
