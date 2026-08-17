# The frontend workspace

Detail for `web/`. The repository-wide rules are in the root `CLAUDE.md`.

A `pnpm` workspace holding a reusable library plus the reference panel that ships inside the
wheel. Tooling: **tsup** builds the libraries (ESM + `.d.ts`), **Vite** builds the apps,
**Vitest** runs tests, **Biome** lints and formats (`web/biome.json`; the vendored shadcn
`ui/` files are excluded). Run everything from `web/`: `pnpm -r build`, `pnpm -r typecheck`,
`pnpm -r test`, `pnpm lint`, `pnpm run lint:diagrams`. All five are CI gates.

## `packages/client/` - `@indi-nexus/client`

A faithful TS port of the Python client, framework-agnostic (it only needs a `WebSocket`).

- `types.ts` / `enums.ts` are the hand-authored wire contract mirroring `protocol/models.py`
  and `enums.py`. Keep them in step.
- `store.ts` is `PropertyStore` with the same `def` / `set`-merge / `del` semantics as
  `client/store.py`, except **merges are immutable** (a `set` replaces the vector and element
  objects) so React can detect changes by reference. A `set` that carried no `state`
  (`SetVector.state_present`) leaves the cached one alone, so a latched Alert stays. A
  **named** `delProperty` removes one property and leaves the device standing even when it
  was the last one - that is a driver defining on connect, seen while disconnected, and not
  the same as the device being gone, which only an unnamed `delProperty` means. Both wire
  rules have three implementations - here, `client/store.py` and `web/static/debug.html` -
  so a change to either belongs in all three. A **whole-device** `del` matches every
  subscriber for that device, including the name-filtered ones: its event carries no name
  because the deletion names no property, so filtering on it silenced the watchers with the
  most to lose (`client/store.py` draws the same line).
- `frames.ts` is the guard between a decoded frame and the store, the browser's half of what
  the Python parser refuses: a missing `device`/`name` drops the frame (`""` is an invented
  device, and it used to cache a phantom one), and so does a non-finite number, which JSON
  writes as `null` or as the string `"NaN"`/`"Infinity"` since it has no literal for one.
  Optional numeric metadata (`min`/`max`/`step`, `timeout`) degrades to `null` instead,
  because it can say absent - mirroring `_optfloat`. A rejected frame is dropped exactly
  where `client.ts` already drops non-object JSON. A frame reaches a browser without ever
  passing the Python parser (another bridge, a test, a driver emitting JSON), which is why
  the rule cannot live only there.
- `connection.ts` is a reconnecting WebSocket to the bridge's `/ws`; `client.ts` is
  `IndiClient` mirroring the Python surface. It tracks two connection states: `transport`
  (browser to bridge) and `upstream` (bridge to `indiserver`, from the bridge's `connection`
  control frame), plus `protocol` from the bridge's `hello`. `CLIENT_PROTOCOL_VERSION`
  mirrors `BRIDGE_PROTOCOL_VERSION`; a mismatch is **never** fatal in either direction
  (bumps are breaking-only, everything additive keeps working), so it logs one line and
  carries on, and `ConnectionStatus` shows it. Two traps live here:
  - `protocol` is `null` until a frame arrives and `0` once a **non-hello** frame arrives
    first, meaning a bridge older than the frame. The latch is evaluated **before**
    `acceptFrame`, so a first frame the frame guard rejects still trips it, and it resets in
    `handleClose` alongside `protocol` - without that a reconnect onto an older bridge sits
    at `null` for ever.
  - `setState` early-returns on an unchanged state, so **every** field has to be in that
    comparison. Leave one out and it is assigned and never notified, which no typecheck
    catches. For the same reason the state is written out in full at each site rather than
    spread from the previous one.
- The third control frame, `{"event":"error"}`, says a frame this
  browser sent did **not** go upstream; it lands in the message log, because nothing retries
  it and a browser that hears nothing would assume its write landed. An `event` the client
  does not know is still dropped. The default URL carries the page's own `?token=` across to
  `/ws`: a browser cannot put a token in a header on a WebSocket handshake, and the bridge
  requires one whenever it was started with `--token` (which the Docker image does).
- `readme-snippets.ts` is nothing but the code samples from this package's `README.md`, kept
  compiling by `pnpm typecheck` - verbatim apart from the import, which reaches for
  `./index` because a package cannot resolve its own published name from inside `src/`. So a
  diff between the two shows drift and nothing else; keep it that way. **Change a snippet in
  the README and change it there too**, or the npmjs.com front page silently rots (it
  already had: it shipped `IPState.OK`, Python's spelling, and a `vector.state` that ignored
  the `null` a `del` carries).

## `packages/react/` - `@indi-nexus/react`

`IndiProvider` + `useIndiClient`, the hooks (`useConnection`, `useDevices`, `useDevice`,
`useProperty`, `useElement`, `useMessages`, all via `useSyncExternalStore` over the immutable
store), the per-kind value hooks (`useNumber`/`useText`/`useSwitch`/`useLight`, which return
the value already narrowed - `useElement` hands back the element union, so reading `.value`
off it does not type-check), and the INDI-aware components (`PropertyVectorCard`,
`DevicePanel`, per-kind element controls, `StateBadge`, `ConnectionStatus`, `MessageLog`).

shadcn/ui primitives live in `src/ui/` (added via the shadcn CLI, `components.json`) and are
re-exported. Use semantic tokens, `FieldGroup`/`Field`, `ToggleGroup` and friends per the
shadcn rules; imports use the standard `@/` alias; **do not hand-edit `src/ui/`.**

The theme is the shadcn tokens in `src/theme.css` plus `--state-*` for INDI
Idle/Ok/Busy/Alert. The build emits a prebuilt `dist/styles.css`
(`@indi-nexus/react/styles.css`, batteries-included) and copies the source `theme.css`
(`@indi-nexus/react/theme.css`, for consumers running their own Tailwind).

`src/doc-snippets.tsx` is nothing but the code samples from `docs/guides/frontend.md`, kept
compiling by `pnpm typecheck`. **Change a snippet on that page and change it there too**, or
the guide silently rots (it already had once, which is how the value hooks got found).
`src/readme-snippets.tsx` is the same arrangement for this package's `README.md`, which had
rotted the same way: it rendered `useConnection()` straight into JSX, and the hook returns
the `{transport, upstream}` object, so the sample threw on paste. That one is the README's
fences verbatim apart from the imports - `./index` instead of the published name, and no
`styles.css`, which nothing in this program declares a type for - so a diff between the two
shows drift and nothing else; keep it that way.

`@indi-nexus/react/testing` (`src/testing/`) is the counterpart to `indi_nexus.testing`:
`renderConnected(ui)` renders under a provider wired to a `FakeSocket` **that has already
sent its `hello`**, as the bridge does - a harness that skipped it would put a "no hello
frame" entry at the head of every message log a consumer asserts on - and
`receive(socket, frame)` feeds it what a driver would send. It re-exports
`cleanup`/`screen`/`within` deliberately - importing those from a consumer's own copy of
`@testing-library/react` gives a second registry of mounted containers, and the DOM
accumulates between tests.

**Gotcha:** the root Python `.gitignore` ignores wheel artifacts with an **anchored**
`/lib/`. Keep it anchored. Unanchored it also matches `src/lib/`, the `cn` helper, so
`src/lib/utils.ts` drops from commits and every `@/lib/utils` import breaks in CI. Do not
fix that by un-ignoring (`!web/**/lib/`), which is what used to be there: the negation
re-includes every `lib/` inside `node_modules` when packaging, because git prunes an
ignored directory and hatchling does not.

## `apps/panel/` - the reference panel

Vite + `@tailwindcss/vite`, composed entirely from `@indi-nexus/react`: a device sidebar with
connection status and a light/dark toggle, a `DevicePanel` per device, and a docked message
strip. `vite build` emits into `src/indi_nexus/web/static/panel/`, where `web/app.py` serves
it at `/`. The wheel bundles that built panel (`hatch_build.py` build hook plus `artifacts`
in `pyproject.toml`, which rebuilds it with pnpm when missing), so `pip install` ships the UI.

**Tailwind source detection is rooted at the Vite root, not at the CSS file.** The demo
configs set `root: "demo"`, so without the explicit `@source "./**/*.{ts,tsx}"` in
`src/index.css` nothing in `src/` is scanned and every class used only by the app shell goes
missing from the demo stylesheets, while the app build still looks fine. Keep that line.

Arbitrary values that wrap `env()` in `calc()` need Tailwind's underscore spacing:
`h-[calc(3.5rem_+_env(safe-area-inset-top))]`. Without whitespace around the `+` the CSS is
invalid and the whole declaration is silently dropped.

## `apps/panel/demo/` - the documentation demos

`dome-sim.ts`, `weather-sim.ts` and `flat-panel-sim.ts` are TypeScript ports of
`examples/dome_device.py`, `examples/openmeteo_device.py` and `examples/flat_panel.py`
behind a fake `WebSocketLike`, so the docs' live demos run with no server. Each has its own
Vite config (`vite.demo.config.ts`, `vite.weather.config.ts`, `vite.flat.config.ts`) and
builds into `docs/` via `pnpm run docs`; the outputs are gitignored.

- **The simulators mirror real drivers.** Change a driver's properties or its safety rule and
  change its simulator too, or the demo stops being a demo of anything.
- **Every simulator has a `CONNECTION` property**, for the same reason every example driver
  does (see `src/indi_nexus/CLAUDE.md`): it is the first thing a client looks for, and a demo
  without one shows visitors a device shape that does not exist in the field. It has to
  behave, not just appear. Writes are refused while disconnected, and disconnecting leaves
  the instrument safe and its properties `Idle`. These demos are the first contact most
  people have with the project, so a panel whose Connect button does nothing is worse than
  no demo.
- **A simulator opens with the `hello`, before its connection frame and its `def`s**, the
  way the real bridge does. Skip it and the client logs "the bridge sent no hello frame"
  into the demo's own message panel, where a visitor reads it as a fault on a page that is
  most people's first contact with the project.
- **Construct a simulator lazily *inside* `webSocketFactory`.** It starts delivering frames
  the moment it exists, and a client that has not attached its handlers yet misses every
  `def`.
- The weather page shows the custom UI beside the **real panel `App`**, not a bare
  `DevicePanel`, so the demo looks like what ships. Both views stay mounted with the inactive
  one hidden: unmounting takes its `IndiProvider` with it, and the provider closes the client
  on unmount, which would reset the simulated driver on every switch.

`sky-report.tsx` and `sky-visuals.tsx` are the tutorial's custom UI: a **wallboard** (read at
4 m, no interaction, one screen, readings that blank rather than go stale) plus its drawn
figures. Below `lg` it reflows to a scrolling column, because a phone is not a wallboard and
clipping readings is worse than scrolling.

- Figures wear theme tokens only (`fill-state-*`, `fill-chart-3`, `stroke-border`) so they
  follow light and dark. The moon's unlit disc is `fill-foreground/20` deliberately: in dark
  mode `foreground` is light and would erase the phase.
- **Status colour never carries meaning alone** - the theme's Alert and Busy are ΔE 4.4 apart
  under deuteranopia - so every state is written out as well as coloured.
