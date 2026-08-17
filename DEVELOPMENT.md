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
│   ├── exceptions.py        # the error hierarchy: IndiError + a builtin base per type
│   ├── protocol/            # the INDI protocol core
│   │   ├── enums.py         #   IPState / IPerm / ISRule / ISState / BLOBPolicy + coerce_switch
│   │   ├── models.py        #   typed Pydantic vectors, elements, def/set/new + enableBLOB
│   │   ├── numbers.py       #   parse_number / format_number, incl. the %m sexagesimal form
│   │   ├── xml.py           #   INDI XML codec + streaming pull-parser
│   │   └── json.py          #   the browser codec: the same models, JSON on the wire
│   ├── driver/              # driver SDK (stdio under indiserver)
│   ├── testing.py           # DeviceHarness: drive a Device in a test, no indiserver
│   ├── client/              # reconnecting async client + property cache
│   ├── transport.py         # shared read/write byte-stream contract + TCP adapter
│   ├── hub.py               # InProcessHub: drivers in this process, for serve --device
│   ├── web/                 # FastAPI bridge (WS + REST) + static/debug.html
│   │   └── security.py      #   the /ws origin allowlist + the shared token
│   └── cli.py               # Typer CLI (new / serve / run / monitor)
├── examples/                # runnable references: drivers and a client
├── tests/                   # pytest suite (tests/interop needs a real libindi)
├── docs/ + mkdocs.yml       # the documentation site
├── docker/ + compose.yaml   # indiserver + the bridge in one image; also runs tests/interop
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
pnpm run lint:diagrams                # parse every Mermaid diagram in the repository
pnpm --filter @indi-nexus/panel dev   # panel dev server with hot reload (proxies to :8000)
```

`lint:diagrams` renders every diagram in the repository with Mermaid's own CLI, so a parse
error fails here instead of shipping an empty box. It needs a browser to render in; if it
cannot find one, point it at yours with `PUPPETEER_EXECUTABLE_PATH`, which is what CI does.

For panel development with hot reload, run a bridge (`indi-nexus serve --device examples.demo_device:Demo`, or
`indi-nexus serve` against a real `indiserver`) and the Vite dev server, which proxies
`/ws` and `/api` to it.

## Running things

```bash
indi-nexus serve --device examples.demo_device:Demo   # panel + a driver in one process, for development
indi-nexus new my_driver.py                 # scaffold a runnable driver file to start from
indi-nexus serve                            # web panel against a real indiserver (open :8000)
indi-nexus run examples.demo_device:Demo    # serve a driver over stdio (under indiserver)
indi-nexus monitor                          # print live INDI updates from indiserver
indi-nexus --help                           # all CLI commands and options
```

### Access control on `serve`

> **`serve` refuses to start on a non-loopback `--host` with no `--token`.** A
> `--host 0.0.0.0` that worked before now exits with a `BadParameter`, so a systemd unit
> or a container command carrying it fails at startup rather than quietly publishing the
> instrument. Add `--token`, or `--allow-insecure-bind` to accept the exposure.

`/ws` is the whole write surface - a frame there becomes an INDI `new*` that moves
hardware - so a bind anything but this machine can reach has to be a decision. Three
options on `serve` (they apply to `--device` too):

| Option | Env var | Effect |
|---|---|---|
| `--token TEXT` | `INDI_NEXUS_TOKEN` | Shared secret required on `/ws` and `/api`. Unset leaves both open, which is what a loopback development server wants. |
| `--allow-origin TEXT` | `INDI_NEXUS_ALLOWED_ORIGINS` | A browser origin to accept on `/ws` besides the server's own, e.g. `http://localhost:5173` for the Vite dev server. Repeatable; `*` accepts any. |
| `--allow-insecure-bind` | `INDI_NEXUS_ALLOW_INSECURE_BIND` | Permit the non-loopback bind with no token anyway. This exposes the instrument. |

`Authorization: Bearer <token>` everywhere, plus `?token=` **on `/ws` only**. A browser
cannot set a header on a WebSocket handshake, so the query parameter is the one form it
has there; `/api` takes the header alone, because a URL token ends up in reverse-proxy
and CDN access logs and in browser history.

### The bridge's HTTP surface

Served by `indi-nexus serve`, with or without `--device`:

- `GET /` - the reference panel; `GET /debug` - the raw debug inspector. Open.
- `GET /health` - `{"status", "connected", "dropped_slow_sinks"}`. Open on purpose: the
  Docker image's `HEALTHCHECK` calls it unauthenticated.
- `GET /api/devices`, `GET /api/devices/{device}[/{name}]` - read-only JSON snapshot.
  **Behind the token** when one is configured.
- `WS /ws` - live stream (snapshot on connect, then updates); browser frames are forwarded
  upstream. **Behind the token and an `Origin` check**, both applied before `accept()`, so
  a rejected handshake is closed with 1008. A browser sends only `new*Vector`,
  `getProperties` and `enableBLOB`; anything else comes back to that browser alone as
  `{"event": "error", "code": "not_permitted", ...}` with the socket left open.

The `/ws` INDI frames are the protocol models dumped to JSON, so for those the frontend
contract *is* the backend model schema. Two things on the wire are not:

- The bridge's own control frames, `{"event": "connection"}` and `{"event": "error"}`,
  which no Pydantic model backs - the protocol has no message for either.
- `/api`, which returns **bare vectors** (`Vector.model_dump()`), not tagged messages, so
  it has no `tag` field and is not a `IndiMessage` a client codec can parse.

Attach to the bridge in Python with `Bridge.attach(sink) -> Subscription` (a bounded queue
plus its own pump task); `Subscription.aclose()` detaches. There is no `snapshot()`,
`add_sink()` or `remove_sink()` - seeding and registration are one synchronous step inside
`attach` so no event can be lost between them.

## The interop suite

`tests/interop/` runs against a real `indiserver` and real libindi drivers, which is the
only thing here that can catch a deviation from the INDI spec. It is excluded from a
normal `pytest` run and skips itself when `indiserver` is not on the PATH, and CI runs it
nightly ([`.github/workflows/interop.yml`](.github/workflows/interop.yml)).

Nothing packages libindi for macOS, so run it in a container instead. The `test` target
of `docker/Dockerfile` carries libindi, the dev dependencies and a browser:

```bash
docker compose --profile interop run --rm --build interop
```

That is the same `pytest tests/interop` the nightly job runs, against the same distro
libindi (1.9.9, on Ubuntu 24.04), so a test that only fails against a real hub can now be
found before it is pushed. Pass a command to narrow it:

```bash
docker compose --profile interop run --rm interop pytest tests/interop/test_smoke.py -q
```

On a machine that does have libindi, `uv run pytest tests/interop` still works.
[docs/docker.md](docs/docker.md) covers the runtime image, which shares the same build.

## Documentation

MkDocs Material, published from `main` to <https://indi-nexus.sidereal.software/> by
`.github/workflows/docs.yml`:

```bash
brew install cairo                # macOS only, first time - see below
uv pip install -e ".[docs]"       # docs toolchain (first time)
cd web && pnpm run docs && cd ..  # generate the TS API reference + the live demo app
uv run mkdocs serve               # author locally
uv run mkdocs build --strict      # what CI runs
```

The social-card plugin renders each page's preview image with cairosvg, which dlopens
the system libcairo rather than shipping it. Ubuntu runners already have it, so CI needs
nothing; macOS does not, and without it every page emits a warning and `--strict` fails.
`CARDS=false uv run mkdocs build --strict` skips card generation if you would rather not
install it, at the cost of not seeing what the previews look like.

## Packaging

```bash
uv build                          # build sdist + wheel
```

The panel is bundled into the wheel, so `pip install indi-nexus` ships the UI. `uv build`
runs the frontend build automatically when Node/pnpm are available (via `hatch_build.py`);
to package offline, run `pnpm -r build` first and the pre-built panel is bundled as-is.
If neither is possible the wheel is built without the panel and the bridge falls back to
the debug page.

## Commit messages are the release notes

Release Please builds the changelog from the commits on `main`, so a commit subject is
read twice: once by whoever reviews it, and later by a stranger deciding whether to
upgrade. Write the subject for the second reader.

```
feat(web): show which switch member is live at a glance
fix(client): keep the reconnect loop alive when indiserver restarts
```

Not `fix: address review feedback`, and not `refactor: tidy element-controls`. Say what
changed for someone using the thing.

- **Type picks the section.** `feat` is Added, `fix` is Fixed, `docs` is Documentation,
  `build` is Packaging, `refactor` is Changed, `perf` is Performance. `chore`, `test`,
  `style` and `ci` are hidden, which is the right home for work nobody outside the
  repository can observe.
- **A `!` marks a breaking change** (`feat!:`), which is what bumps the major version.
  Below 1.0 it bumps the minor instead, so it still needs saying.
- **The path decides the changelog, but all three release together.** A commit touching
  `web/packages/react` lands in that package's changelog, not the Python one, so keep
  unrelated changes in separate commits when you want them filed separately. The version
  itself is shared: `linked-versions` moves `indi-nexus`, `@indi-nexus/client` and
  `@indi-nexus/react` to one number every time.

  That does mean a release sometimes bumps a package with nothing in its changelog, which
  is a real cost and was weighed rather than overlooked. `hatch_build.py` compiles the
  panel into the wheel, so a TypeScript change alters what `pip install indi-nexus` and
  the Docker image contain, and 28% of the commits in this repository touch only `web/`.
  Versioning the packages independently would ship those to npm while the wheel and the
  image quietly stayed behind, and the only guard against that would be remembering to
  pair every frontend change with a Python-visible commit. Forgotten conventions are the
  single most common defect in this repository's history. One version number also answers
  "which client works with which bridge" for free, which matters while `types.ts` is a
  hand-maintained mirror of the Pydantic models.

  Revisit it if the panel ever stops being bundled in the wheel, because that coupling is
  the whole argument.
- **Squash-merge pull requests.** The squashed subject becomes the release note, and it
  spares the changelog the "fix a bug I introduced two commits ago" entries that are true
  of the branch but meaningless on `main`.

Two escape hatches worth knowing. `Release-As: 1.2.3` in a commit body forces a version.
Editing a merged PR's body to add a `BEGIN_COMMIT_OVERRIDE` / `END_COMMIT_OVERRIDE` block
replaces the message Release Please uses, which is how you fix a release note after the
fact.

Purely internal work needs no thought here: `chore:` or `test:` and it stays out of the
changelog. Cutting a release is written up in [RELEASING.md](RELEASING.md).

## Green baseline

Before committing: `ruff check` + `mypy src` + `pytest` clean, and in `web/`, `pnpm lint` +
`pnpm -r typecheck` + `pnpm -r test` + `pnpm -r build` + `pnpm run lint:diagrams` clean. CI
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs all of these plus a check
that the wheel bundles the panel.
