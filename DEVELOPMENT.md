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
│   ├── settings.py          # the INDI_NEXUS_* environment, read once at an entrypoint
│   ├── logging_config.py    # configure_logging + the shared indi_nexus.wire logger
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
uv run ruff check src tests examples hatch_build.py    # lint (the set CI checks)
uv run ruff format src tests examples hatch_build.py   # auto-format
uv run mypy src                   # type-check (strict)

# Regenerate the browser wire schema after an intentional model change, and
# update web/packages/client/src/types.ts in the same commit.
INDI_NEXUS_UPDATE_GOLDEN=1 uv run pytest tests/test_wire_contract.py
```

`tests/data/wire_schema.json` is a committed snapshot of the JSON schema a browser is
written against: the `IndiMessage` union, the `Vector` union and the bridge's own control
frames. It is a speed bump, not a guarantee - it cannot check that `types.ts` followed,
only make sure a model change and the hand-authored mirror land in front of the same
reviewer.

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
indi-nexus run mod:A mod:B                  # several devices from one driver process
indi-nexus monitor                          # print live INDI updates from indiserver
indi-nexus --help                           # all CLI commands and options
```

### Configuration and logging

Every knob lives under one prefix, `INDI_NEXUS_`, everything is optional, and
`indi_nexus.settings.Settings` reads all of it. There is one reader and one story: a
variable means what the table says wherever INDINexus runs, and no flag carries its own
environment lookup.

| Variable | Flag | Default | Effect |
|---|---|---|---|
| `INDI_NEXUS_LOG_LEVEL` | `--log-level`, `-v` | `INFO` | Level for `indi_nexus.*` **and** uvicorn. One of `CRITICAL`/`ERROR`/`WARNING`/`INFO`/`DEBUG`, case-insensitive; anything else is a usage error rather than a traceback out of `uvicorn.Config`. |
| `INDI_NEXUS_WIRE_LOG` | `--wire` | off | One line per INDI message per direction, on the `indi_nexus.wire` logger. |
| `INDI_NEXUS_CONNECT_TIMEOUT` | - | `10.0` | Seconds the client waits per connection attempt. |
| `INDI_NEXUS_RECONNECT_DELAY` | - | `2.0` | Seconds between a lost connection and the next attempt. |
| `INDI_NEXUS_MESSAGE_HISTORY` | - | `100` | INDI `message` frames replayed to a newly attached browser. |
| `INDI_NEXUS_MAX_BACKLOG` | - | `512` | Live frames a browser may fall behind by before it is dropped. |
| `INDI_NEXUS_TOKEN` | `--token` | unset | See [Access control on `serve`](#access-control-on-serve). |
| `INDI_NEXUS_ALLOWED_ORIGINS` | `--allow-origin` | unset | Same. **Space separated** in the environment, repeatable as a flag. |
| `INDI_NEXUS_ALLOW_INSECURE_BIND` | `--allow-insecure-bind` | off | Same. |

Where a setting has both forms, **the flag wins and its absence defers to the
environment**. A flag that names a variable has no default of its own - the table's
default is the model's, in one place - and the command resolves the two when it runs
rather than in its option defaults, which is what stops the first environment a process
ever saw from being frozen into every later invocation. `--token ""` is a value like any
other, so it turns a configured token back off for one run.

`LOG_LEVEL` and `WIRE_LOG` also have to work with **no CLI in the loop**, since a driver
launched by `indiserver` as `./my_driver.py` reaches `indi_nexus.driver.run` and never
`indi-nexus`; that entrypoint reads the same two fields.

In the Docker image the last three are also spelled `WEB_TOKEN`, `WEB_ALLOWED_ORIGINS` and
`WEB_ALLOW_ANONYMOUS`, because the entrypoint generates a token when none was given and
prints the URL with it; either spelling works there. See [docs/docker.md](docs/docker.md).

Three rules hold everywhere:

- **Only entrypoints configure logging**, and each does it exactly once: the Typer app
  callback for a CLI invocation, `driver.run` for a driver. `serve_stdio` deliberately does
  not - it is a coroutine tests and embedders await, and configuring inside it would have
  every one of them mutate global logging as a side effect.
- **Nothing reads the environment implicitly.** `IndiClient`, `Bridge` and `create_app`
  take explicit parameters with today's defaults; the entrypoints read `Settings` and pass
  the values down. That is what keeps `create_app(client=...)` injectable.
- **Logs go to stderr, never stdout.** A driver's stdout *is* the INDI wire, so a line
  written there corrupts the stream `indiserver` parses. `indiserver` relays a driver's
  stderr into its own log, which is where an operator will look anyway.

`--wire` is one switch for "show me the wire" across all four sites - the client's reader
and writer and the driver runtime's reader and writer - which is why they do not log it on
their own module loggers:

```
DEBUG    indi_nexus.wire: <- set CCD.CCD_TEMPERATURE
DEBUG    indi_nexus.wire: -> new CCD.CONNECTION (142 bytes)
```

A BLOB's payload is never printed; the line reports its size (`[1048576 byte payload]`),
read off the model. Every call site is guarded by `isEnabledFor`, so a run with wire
logging off pays one flag check per message.

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
| `--allow-origin TEXT` | `INDI_NEXUS_ALLOWED_ORIGINS` | A browser origin to accept on `/ws` besides the server's own, e.g. `http://localhost:5173` for the Vite dev server. Repeatable as a flag, space separated in the variable; `*` accepts any. |
| `--allow-insecure-bind` | `INDI_NEXUS_ALLOW_INSECURE_BIND` | Permit the non-loopback bind with no token anyway. This exposes the instrument. |

The flag wins over the variable, and the refusal above is checked against whichever of the
two applies - a token set in the environment authenticates the bind exactly as `--token`
does, and `--token ""` un-sets one for the run and is refused again.

`Authorization: Bearer <token>` everywhere, plus `?token=` **on `/ws` only**. A browser
cannot set a header on a WebSocket handshake, so the query parameter is the one form it
has there; `/api` takes the header alone, because a URL token ends up in reverse-proxy
and CDN access logs and in browser history.

### The bridge's HTTP surface

Served by `indi-nexus serve`, with or without `--device`:

- `GET /` - the reference panel; `GET /debug` - the raw debug inspector. Open.
- `GET /health` - open on purpose: the Docker image's `HEALTHCHECK` calls it
  unauthenticated. **The body only ever grows**; `status`, `connected` and
  `dropped_slow_sinks` keep their names at the top level, because a monitoring check
  somewhere already reads them.

  ```json
  {
    "status": "ok",
    "protocol": 1,
    "connected": true,
    "dropped_slow_sinks": 0,
    "sinks_attached": 3,
    "upstream": {"uptime_seconds": 4211.3, "reconnects": 2, "last_message_age_seconds": 0.8},
    "parser": {"dropped": 0, "resets": 0, "bytes_since_last_message": 1204,
               "dropped_total": 0, "resets_total": 0}
  }
  ```

  `protocol` is `BRIDGE_PROTOCOL_VERSION`, the same integer the `hello` frame carries, so
  a deployment check can ask "will my pinned client understand this bridge" without
  opening a WebSocket. `uptime_seconds` is the **current upstream connection**, not the
  process, and is `null` while disconnected; `reconnects` counts successful
  re-establishments only, so a bridge that has never reached `indiserver` reports `0` with
  `connected: false`; `last_message_age_seconds` is the age of the last *parsed* INDI
  message, so a peer dribbling malformed bytes does not read as healthy. While
  disconnected the `parser` block reports the last connection's final counters, and the two
  `_total` fields are the durable ones - they include the connection in progress, so
  `dropped_total` is never behind `dropped`. There is deliberately **no release version**:
  it would hand an unauthenticated caller the exact build to look up advisories against,
  and `protocol` already answers the only compatibility question a caller has.
- `GET /api/devices`, `GET /api/devices/{device}[/{name}]` - read-only JSON snapshot.
  **Behind the token** when one is configured.
- `WS /ws` - live stream (`hello`, then the snapshot, then updates); browser frames are
  forwarded upstream. **Behind the token and an `Origin` check**, both applied before
  `accept()`, so a rejected handshake is closed with 1008. A browser sends only
  `new*Vector`, `getProperties` and `enableBLOB`; anything else comes back to that browser
  alone as `{"event": "error", "code": "not_permitted", ...}` with the socket left open.

The `/ws` INDI frames are the protocol models dumped to JSON, so for those the frontend
contract *is* the backend model schema. Two things on the wire are not:

- The bridge's own control frames - `{"event": "hello"}`, `{"event": "connection"}` and
  `{"event": "error"}` - which INDI has no message for. They are modelled all the same, in
  `indi_nexus/web/control_frames.py`, and the `hello` carries `BRIDGE_PROTOCOL_VERSION`:
  the version of the browser contract itself, bumped only on a breaking change.
- `/api`, which returns **bare vectors**, not tagged messages, so it has no `tag` field and
  is not an `IndiMessage` a client codec can parse. The routes are annotated with
  `dict[str, Vector]` and `Vector`, so FastAPI serialises through the real schema and
  OpenAPI documents it.

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

### Every code fence is checked

No snippet in the documentation is untested prose. Both halves read the fences **out of
the markdown at test time**, so there is no second copy to fall out of step, and a page
cannot rot without a build going red.

- **Python** - `tests/test_docs_snippets.py`. Its `CLAIMS` table names every Python fence
  on every page and says what is true of it: `RUNS` (executed, usually through
  `DeviceHarness`, with the page's own claims asserted), `EXCERPT` (a trimmed quotation of
  a real file, matched statement by statement against it), `COMPILES` (a fragment, so it
  is compiled and its `indi_nexus` imports resolved) or `PROSE` (not our code, or code the
  page is warning against, with the reason recorded). **A fence with no claim fails the
  suite**, so a new snippet has to be classified rather than ignored. The same module
  checks the `indi-nexus` commands and flags the pages tell people to type, the
  `module:Class` driver targets they name, the Docker variables they advertise, and the
  tutorial's quoted request and reply against `tests/data/open_meteo_response.json`.
- **TypeScript** - `web/scripts/extract-doc-snippets.mjs`, run by each package's
  `typecheck`. It writes one module per fence into `src/__generated__/docs/` (gitignored)
  where `tsc --noEmit` compiles it. A fence outside its manifest, or a markdown file with
  a TypeScript fence that no manifest covers, fails the extractor.

Adding a fence to a page therefore means adding it to the claims table or the manifest.
Neither takes a copy of the code.

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
