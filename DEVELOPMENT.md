# Development guide

Everything needed to work on the INDINexus monorepo. For a user-facing tour, start with
the [README](README.md) and the [documentation site](https://indi-nexus.sidereal.software/).

## Setup

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12+) and [pnpm](https://pnpm.io)
(Node 20+):

```bash
uv venv --python 3.12                   # create the venv (first time)
uv pip install -e ".[dev]"              # install the package + dev deps
cd web && pnpm install && cd ..         # install the JS workspace deps
```

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

## Project layout

```
indi-nexus/
├── pyproject.toml           # packaging, dependencies, tool config (ruff/mypy/pytest)
├── src/indi_nexus/
│   ├── protocol/            # the INDI protocol core
│   │   ├── enums.py         #   IPState / IPerm / ISRule / ISState / BLOBPolicy (str enums)
│   │   ├── models.py        #   typed Pydantic vectors, elements, def/set/new + enableBLOB
│   │   └── xml.py           #   INDI XML codec + streaming pull-parser + sexagesimal
│   ├── driver/              # driver SDK (stdio under indiserver)
│   ├── client/              # reconnecting async client + property cache
│   ├── transport.py         # shared read/write byte-stream contract + TCP adapter
│   ├── web/                 # FastAPI bridge (WS + REST) + static/debug.html
│   └── cli.py               # Typer CLI (serve / run / monitor)
├── examples/                # runnable references: drivers, client, demo bridge
├── tests/                   # pytest suite
├── docs/ + mkdocs.yml       # the documentation site
└── web/                     # pnpm workspace (TypeScript frontend)
    ├── packages/client/     #   @indi-nexus/client - framework-agnostic transport + store
    ├── packages/react/      #   @indi-nexus/react  - hooks + shadcn/ui components + theme
    └── apps/panel/          #   the reference panel (built into web/static/panel)
```

## Backend commands

Run everything through `uv`:

```bash
uv run pytest                     # run the test suite
uv run pytest -k "name"           # run a single test by name
uv run ruff check src tests       # lint
uv run ruff format src tests      # auto-format
uv run mypy src                   # type-check (strict)
```

## Frontend commands

Run with `pnpm` from `web/`:

```bash
pnpm -r build                         # build the libraries + panel (into the Python package)
pnpm -r test                          # run all package tests (Vitest)
pnpm -r typecheck                     # type-check every package
pnpm lint                             # lint + format check (Biome)
pnpm --filter @indi-nexus/panel dev   # panel dev server with hot reload (proxies to :8000)
```

For panel development with hot reload, run a bridge (`python -m examples.demo_bridge`, or
`indi-nexus serve` against a real `indiserver`) and the Vite dev server, which proxies
`/ws` and `/api` to it.

## Running things

```bash
python -m examples.demo_bridge              # web panel + live demo device, no indiserver (open :8000)
indi-nexus new my_driver.py                 # scaffold a runnable driver file to start from
indi-nexus serve                            # web panel against a real indiserver (open :8000)
indi-nexus run examples.demo_device:Demo    # serve a driver over stdio (under indiserver)
indi-nexus monitor                          # print live INDI updates from indiserver
indi-nexus --help                           # all CLI commands and options
```

The bridge's HTTP surface (all served by `indi-nexus serve` / the demo bridge):

- `GET /` - the reference panel; `GET /debug` - the raw debug inspector.
- `GET /health` - liveness + upstream connection state.
- `GET /api/devices`, `GET /api/devices/{device}[/{name}]` - read-only JSON snapshot.
- `WS /ws` - live stream (snapshot on connect, then updates); browser frames are forwarded
  upstream. Messages are the protocol models as JSON, so the frontend contract is the
  backend model schema.

## Documentation

MkDocs Material, published from `main` to <https://indi-nexus.sidereal.software/> by
`.github/workflows/docs.yml`:

```bash
uv pip install -e ".[docs]"       # docs toolchain (first time)
cd web && pnpm run docs && cd ..  # generate the TS API reference + the live demo app
uv run mkdocs serve               # author locally
uv run mkdocs build --strict      # what CI runs
```

## Packaging

```bash
uv build                          # build sdist + wheel
```

The panel is bundled into the wheel, so `pip install indi-nexus` ships the UI. `uv build`
runs the frontend build automatically when Node/pnpm are available (via `hatch_build.py`);
to package offline, run `pnpm -r build` first and the pre-built panel is bundled as-is.
If neither is possible the wheel is built without the panel and the bridge falls back to
the debug page.

## Green baseline

Before committing: `ruff check` + `mypy src` + `pytest` clean, and in `web/`,
`pnpm lint` + `pnpm -r typecheck` + `pnpm -r test` + `pnpm -r build` clean. CI
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs all of these plus a check
that the wheel bundles the panel.
