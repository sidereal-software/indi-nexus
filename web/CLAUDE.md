# The frontend workspace

Detail for `web/`. The repository-wide rules are in the root `CLAUDE.md`.

A `pnpm` workspace holding the two published libraries (`@indikit/client` and
`@indikit/react`, each with its own heading below), the reference panel that ships
inside the wheel, and the `scripts/` package that typechecks the documentation's code
fences. Tooling: **tsup** builds the libraries (ESM + `.d.ts`), **Vite** builds the apps,
**Vitest** runs tests, **Biome** lints and formats (`web/biome.json`; the vendored shadcn
`ui/` files are excluded). Run everything from `web/`: `pnpm -r build`, `pnpm -r typecheck`,
`pnpm -r test`, `pnpm lint`, `pnpm run lint:diagrams`. All five are CI gates.

**Both libraries typecheck as two projects, and the split is load bearing.** `tsconfig.json`
excludes `*.test.ts(x)` (and `src/testing/setup.ts` in the React package) so that
`"types": []` actually means something: that field only stops TypeScript *auto-including*
`@types/*`, and a `/// <reference types="node" />` inside a `.d.ts` the program already reads
still brings the globals in - vite's does, and every test file reaches it through `vitest`. So
`process` was in scope for both browser libraries despite the `types: []` that was there to
prevent exactly that, and `skipLibCheck` meant a stray `process.env` in library source would
have compiled in silence. `tsconfig.test.json` compiles the tests with the exclusions lifted,
and each package's `typecheck` script runs both. Probe it the way it was found: append
`export const _probe = process.env.HOME` to a library source file and check that
`tsc --noEmit` fails.

## `packages/client/` - `@indikit/client`

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
- `format.ts` holds the display helpers. `displayLabel` is the **only** way to turn an
  element or vector into text: INDI's `label` is optional in practice as well as in the
  schema, and libindi ships properties whose element labels are the empty string
  (`DEVICE_BAUD_RATE` is the one everybody meets), so `label ?? name` renders a row of blank
  controls. It is not in `types.ts` on purpose - that file mirrors the Pydantic models and a
  display choice is not part of the wire contract.
- `connection.ts` is a reconnecting WebSocket to the bridge's `/ws`; `client.ts` is
  `IndiClient` mirroring the Python surface. It tracks two connection states: `transport`
  (browser to bridge) and `upstream` (bridge to `indiserver`, from the bridge's `connection`
  control frame), plus `protocol` from the bridge's `hello`. `CLIENT_PROTOCOL_VERSION`
  mirrors `BRIDGE_PROTOCOL_VERSION`; a mismatch is **never** fatal in either direction
  (bumps are breaking-only, everything additive keeps working), so it logs one line and
  carries on, and `ConnectionStatus` shows it. Three traps live here:
  - `protocol` is `null` until a frame arrives and `0` once a **non-hello** frame arrives
    first, meaning a bridge older than the frame. The latch is evaluated **before**
    `acceptFrame`, so a first frame the frame guard rejects still trips it, and it resets in
    `handleClose` alongside `protocol` - without that a reconnect onto an older bridge sits
    at `null` for ever.
  - `setState` early-returns on an unchanged state, so **every** field has to be in that
    comparison. Leave one out and it is assigned and never notified, which no typecheck
    catches. For the same reason the state is written out in full at each site rather than
    spread from the previous one.
  - **`current()` protects the socket we let go of; the timer has to protect the one we
    hold.** `open()` overwrites `this.socket`, so any socket that loses that assignment is
    orphaned - still `OPEN`, never closed, and every one of its events filtered out by a
    guard written for sockets we discarded deliberately. Three paths reached it, and each
    was independently reachable: the deferred reconnect never asked whether a socket had
    arrived while it waited; `start()` left a booked `reconnectTimer` running, which also
    handed the *next* close a part-spent timer and silently shortened its backoff; and
    `onclose` calls `onClose` **before** `scheduleReconnect`, so a consumer reconnecting
    from its own close handler re-enters `start()` when there is no timer to cancel yet.
    The symptom is the worst one this client has: `connected` reports `true`, the socket
    genuinely is open, and frames land nowhere. Still latent and deliberately not changed:
    `scheduleReconnect` declines to replace an existing timer, so the first booked deadline
    wins if two closes ever land inside one delay window.
- `onWrite` is the outbound counterpart to `subscribe`: it fires with `(device, name)` for
  every `new` frame `send` puts on the wire, and it exists so a consumer can tell a state
  change it asked for from telemetry it did not. Nothing else can make that distinction - the
  frames coming back are identical either way - so it lives on the sender. It fires on the
  send rather than on the acknowledgement, because the socket buffers while offline and the
  operator pressed the button regardless. `StatusAnnouncer` is the one consumer.
- The third control frame, `{"event":"error"}`, says a frame this
  browser sent did **not** go upstream; it lands in the message log, because nothing retries
  it and a browser that hears nothing would assume its write landed. An `event` the client
  does not know is still dropped. The default URL carries the page's own `?token=` across to
  `/ws`: a browser cannot put a token in a header on a WebSocket handshake, and the bridge
  requires one whenever it was started with `--token` (which the Docker image does).
- This package's `README.md` is the npmjs.com front page, and its `ts` fences are compiled
  straight out of the markdown by `pnpm typecheck` - see `scripts/` below. That front page
  had rotted before the check existed: it shipped `IPState.OK`, Python's spelling, and a
  `vector.state` that ignored the `null` a `del` carries.

## `packages/react/` - `@indikit/react`

`IndiProvider` + `useIndiClient`, the hooks (`useConnection`, `useDevices`, `useDevice`,
`useProperty`, `useElement`, `useMessages`, all via `useSyncExternalStore` over the immutable
store), the per-kind value hooks (`useNumber`/`useText`/`useSwitch`/`useLight`, which return
the value already narrowed - `useElement` hands back the element union, so reading `.value`
off it does not type-check), and the INDI-aware components (`PropertyVectorCard`,
`DevicePanel`, `DeviceConfigDialog`, per-kind element controls, `StateBadge`,
`ConnectionStatus`, `MessageLog`, `StatusAnnouncer`).

### Two live regions, and why they are two

Everything arriving over the socket used to reach sighted operators only. The page now has
exactly two announcing surfaces, and the split between them is the whole design:

- **`MessageLog`'s scrolling viewport is `role="log"`** - polite, additions-only - so each
  new driver message is read once instead of the panel being re-read. That viewport also
  carries `tabIndex={0}`: it is a scroll container, the view follows the newest entry, and
  without a tab stop the history above it is reachable only with a wheel.
- **`StatusAnnouncer` is a separate `role="status"`**, mounted once at the top of the app. It
  watches **every** device on purpose: a fault on the device that is not on screen is the one
  an operator most needs to be told about, which is why it is mounted page-level and not
  inside `DevicePanel`.

**What that region may speak, and the rule for each.** Volume is why it cannot just be more of
the log: `set` frames are telemetry, a CCD simulator emits them continuously, and a five-minute
poll updating a temperature is not a status message. Three things qualify, and each qualifies
for a reason that does not generalise into "announce state changes":

1. **A vector entering Alert.** "Entering" is the whole point. It keeps the last state per
   property, so a latched Alert re-emitting (which it does with every subsequent `set`, since a
   `set` with no `state` leaves the cached one alone) is silent.
2. **A vector this browser wrote to, until it settles.** A state change is telemetry only when
   nobody asked for it. The operator presses Open, the shutter goes Busy and then Ok, and a
   sighted operator reads both off the badge - so this is feedback on their own action, not the
   stream. `IndiClient.onWrite` is what separates the two, and only the sender can: it fires on
   each `new` frame the client sends. The property is disarmed by the first state that is not
   Busy, so one press buys at most two sentences and a driver still emitting afterwards is back
   to being telemetry. Verified live against `examples/dome_device.py`: pressing Open produced
   exactly "Shutter on Dome Simulator is Busy." and then "...is Ok.", and nothing across the
   thirteen seconds of position telemetry between them.
3. **The connection.** A lost socket is not telemetry under any reading - every number on
   screen stops being true and nothing else says so out loud. A recovery is announced only if
   this region announced the loss before it, which is also what keeps a freshly opened session
   silent: without that guard, the first `connection` frame (sent while `upstream` is still
   false from the socket opening) would announce a fault that never happened.

**The last state seen on the wire belongs to rule 1, and no other rule may read it.** Treat
that as the invariant rather than as a description, because the region has had **two** bugs of
one shape and the shape is the point: *the answer to a press carried a state that did not
change.*

- First, a `previous === state` early return above everything. A write answered with an
  unchanged state was read as telemetry - silent, and still armed, so an unrelated transition
  minutes later was announced as the answer to it.
- Then, once that was split out, a `state === "Busy" && previous === "Busy"` guard left on the
  write side. It suppressed the dome's position telemetry correctly and also swallowed the
  acknowledgement whenever the property was **already Busy when the operator pressed** - so the
  press bought nothing for thirteen seconds, which is exactly when an operator presses again.

Neither is an edge case: most libindi writes go straight to Ok or Idle with no intermediate
Busy, onto a property frequently already at that state. And the live verification above walks
Idle→Busy→Ok, the one path that touches neither. Nor did any of the tests, which reasoned from
the same model as the code.

So the two rules now ask two questions and neither borrows the other's state:

- **Telemetry** asks *has it changed*, against `seen` - the last state on the wire. Entering
  Alert is news; a latched Alert re-emitting is not.
- **A press** asks *what have I already said about this write*, against the state that write was
  last announced at. `awaiting` is therefore a `Map<name, IPState | null>` and not a `Set`, with
  `null` meaning armed-but-unacknowledged. One line, `announcedFor !== state`, replaces three
  guards: every press is acknowledged exactly once whatever the driver answers with and whatever
  the property was doing beforehand, and a driver repeating itself is silent. `onWrite` re-arms
  to `null` even on a property already pending, because a second press is a second thing the
  operator is owed an answer to.

That bounds it both ways, which is the property to preserve if these rules are ever touched: it
cannot become a firehose (one sentence per entry into Alert; per press at most one
acknowledgement plus the settle that disarms) and it cannot go silent (an armed property
announces its very next frame unconditionally). The one write it cannot recover from is one the
bridge refuses outright - see `CONCERNS.md`.

Three mutations are pinned by `status-announcer.test.tsx`, and they are the three ways this goes
wrong: reading `previous` on the write side, announcing every armed frame, and failing to re-arm
on a second press.

**`role="status"`, not `role="alert"`, and that includes the connection sentences.** Assertive
would interrupt whatever is being read out; a region that talks over a screen reader is one an
operator turns off. Losing the socket is the strongest case for interrupting - every reading on
screen has stopped being true - and it is still not a frequent event, so it can wait its turn.
Decided rather than defaulted.

### A momentary command is a push button, not a toggle

`SwitchVectorControl` draws a **one-member `AtMostOne`** vector as a `Button` rather than a
`Toggle`, and that shape test is the whole rule - no list of property names. INDI has one
switch type for two different objects, a selection the driver reports back and a command
that fires once, and only the second can have a lone member under the rule that permits
none-on: there is nothing to select instead of it, so "on" is not a position a driver leaves
it in. libindi's stop commands are all built that way, this project's SDK puts
`CONFIG_PROCESS` straight back to Off (`Device._handle_config`), and `dome-sim.ts` does the
same with `ABORT`. A lone `OneOfMany` member is on for ever by definition and a lone
`AnyOfMany` one is a checkbox, so neither is caught.

Drawn as a toggle it was wrong twice over. `aria-pressed="false"` claims a second position
the control does not have, which is the same false claim the radio group made below. And the
appearance that goes with it is an *unselected* member's transparent outline, so on the
dome's Main Control the one control that stops the instrument sat beside the genuinely
unpressed `Connect` and `Park`, indistinguishable from them and the palest thing on the tab,
while `--primary` went to `Unpark` reporting that nothing was happening.

**There is one variant and no element is special.** `Abort` shipped as `destructive` for one
release, and the argument for it was true - aborting a shutter move is exactly what leaves
`DOME_SHUTTER` in Alert with "Status: unknown" - and still wrong. Red on this panel is the
enumerated hue of a destructive button *in a dialog*; on an instrument card that can carry an
Alert badge two inches away it asks an operator to separate "the instrument is in Alert" from
"this button stops it" by hue at 3am. `--destructive` now has exactly one wearer in the
product, `Purge`, and that is the list. Feedback stays the card's state badge; a push button
has no on-state and needs none, and an abort that put the instrument into Alert says so
there, in the state hue, where a state belongs.

The button keeps the vector's `fieldset aria-label`, so two instruments with a stop command
do not offer a reader two controls both called "Abort".

### The switch control is a group of toggle buttons, not a radio group

`SwitchVectorControl` deliberately does **not** use `ToggleGroup`. `type="single"` is a
Radix radio group (`role="radiogroup"` with `role="radio"` children), and the ARIA radio
pattern is selection-follows-focus - so arrowing from Disconnect to Connect told a screen
reader the selection had moved while nothing had gone on the wire. The two-step behaviour
is right for a control that connects hardware; the claim was what was wrong. It is now a
`fieldset` of `Toggle`s (`aria-pressed`, `data-state`), and `SWITCH_MEMBER_CLASSES`
reproduces the segmented look the primitive used to supply. Do not "simplify" it back.

`DeviceConfigDialog` is the one component that is more than a rendering. `CONFIG_PROCESS` is
universal in libindi and three of its facts are traps, so the copy **is** the component and
changing it changes what the panel promises:

- `CONFIG_DEFAULT` reads a `.default` file that libindi writes as a copy of the *first*
  configuration ever saved, so the button reads "Restore first saved" and never "Default".
  A test asserts that string; it is the regression, not a wording preference.
- `CONFIG_PURGE` is an unguarded `remove()` - no backup, no undo, no confirmation anywhere
  in libindi - so it is behind an `AlertDialog` that sends **nothing** until confirmed, and
  the confirming button names the consequence ("Delete saved config", never "OK").
- `CONFIG_SAVE` writes a subset, and the dialog always carries a line about it, because
  silence would read as "everything you see". Which line depends on what the driver says.
  A libindi driver picks the subset in `saveConfigItems`, which nothing on the wire
  exposes, so it gets the fallback apology. An INDIkit driver declares persistence at
  define time and publishes `INDIKIT_CONFIG_PERSISTED` (a read-only text vector, element
  `PROPERTIES`, names separated by spaces), and then `SaveScope` names the properties -
  as their own labels where the device still publishes them, since `GEOGRAPHIC_COORD` is
  the wire's word for what the panel calls "Site". An **empty** list is a third statement,
  not the fallback: the driver saying Save writes none of its properties. All three
  strings are asserted, and `SaveScope` is a child of `DialogContent` on purpose - Radix
  mounts that only while the dialog is open, so the whole-device subscription it needs for
  those labels is not live behind a closed modal.
  `DevicePanel` excludes `INDIKIT_CONFIG_PERSISTED` alongside `CONFIG_PROCESS` (and it is in
  `DRIVER_MACHINERY` for a consumer's own layout): drawn as a card it is a read-only field
  of wire names saying less than the sentence does.

`CONFIG_LOAD` and `CONFIG_DEFAULT` replay saved values through the driver's handlers, so on
a connected device they can move hardware: both confirm while `CONNECTION`'s `CONNECT` is
On, and neither does otherwise (including when the device has no `CONNECTION` at all).

Configuration is **not** a property group: it is a per-device action surface an operator
visits deliberately and rarely, and one of its members is that unguarded delete, so it does
not belong permanently on screen beside live instrument readings. It lives in the sidebar,
which is also what owns device selection, and opens in a `Dialog`. So the component takes
`device: string | null` and renders **nothing at all** when nothing is selected or the
selected device has no `CONFIG_PROCESS` - an entry that opens an empty modal is worse than
no entry. Pass `children` and that element becomes the trigger, for a consumer's own shell.
The purge confirmation is now an `AlertDialog` **inside** the `Dialog`: Radix stacks
dismissable layers, so Escape takes the confirmation and leaves the configuration modal
standing, and a test asserts exactly that in both directions.

**The default trigger is nested under its device, and the placement has been wrong twice.**
There is no server-wide configuration in INDI - `indiserver` publishes no properties at all,
and every driver saves its own file - so this entry always belongs to exactly one device.
It began as a sibling `<li>` of the device buttons, inside `nav aria-label="Devices"`, where
it was announced as a third device and read as one. Moving it to its own `SidebarGroup`
under a heading carrying the device's name left the landmark but kept the devices' indent
and printed that name a second time directly under the row that already had it. It is now a
`SidebarMenuSubButton` inside a `SidebarMenuSub` that the component brings itself, dropped
into the device's own `SidebarMenuItem` by the shell: the indent, its guide line and the list
nesting carry ownership, and the heading goes away. Three things about that are load bearing:

- **It owns the `<ul>` as well as the `<li>`.** A device with no `CONFIG_PROCESS` has to
  leave no indented rule hanging under its row, and only the component knows there is
  nothing to show. The demo's dome is exactly that case; every libindi driver is not.
- **The sub-list is `aria-label`led with the device**, which is what a reader hears in place
  of the heading it replaced: "Open-Meteo, list, one item, Configuration".
- **`asChild` down to a real `<button>`**, because `SidebarMenuSubButton` renders an `<a>`
  and this trigger carries no href - taking the primitive as it comes puts the only way into
  a device's configuration outside the tab order. `h-8` restores the 32px of the device rows
  over the primitive's own 28px.

It still needs a `SidebarProvider` and a `TooltipProvider` above it, which its tests supply.

`DevicePanel` excludes `CONFIG_PROCESS` from the generic grid entirely, so it is neither
pinned nor drawn as four anonymous switches, puts `Main Control` first, then the remaining
groups alphabetically, and folds `DRIVER_MACHINERY` (`components/machinery.ts`, Ekos' own
skip list) into a collapsed "Driver internals" section. `CONNECTION` is on Ekos' list and
deliberately **not** on ours: Ekos drives connection from its own toolbar and the panel has
no second home for the button an operator reaches for first. The fold is recomputed per
render, because libindi defines and deletes `DEBUG_LEVEL`/`LOGGING_LEVEL`/`LOG_OUTPUT` at
runtime as `DEBUG` is toggled.

shadcn/ui primitives live in `src/ui/` (added via the shadcn CLI, `components.json`) and are
re-exported. Use semantic tokens, `FieldGroup`/`Field`, `ToggleGroup` and friends per the
shadcn rules; imports use the standard `@/` alias; **do not hand-edit `src/ui/`.**

**Two** files break that rule, and both break it for the same reason: what is wrong with
them is *behaviour*, which no stylesheet can reach. The test before adding a third is exactly
that - if a rule in `theme.css` could fix it, it does not belong in `src/ui/`.

`scroll-area.tsx` grows a `viewportProps` passthrough, marked `DEVIATION` in place and to be
re-applied after a `shadcn add scroll-area`: upstream spreads props onto the Root only, so
nothing can reach the scrolling element - and a scroll container outside the tab order cannot
be scrolled by keyboard at all. The viewport's class list has carried `focus-visible:ring`
since the component was added, so the styling was already waiting for a tabindex nobody could
supply. `message-log.test.tsx` asserts `role="log"`, `data-slot="scroll-area-viewport"` and
`tabindex="0"` - exactly what the passthrough exists to deliver - so the marker disappearing
fails a test rather than a browser.

`sidebar.tsx` carries two numbered `DEVIATION` blocks, both in the mobile drawer, both
reproduced at 390x844 before they were touched:

- **Focus restoration.** The drawer is a Sheet with no `Dialog.Trigger` - it is opened by
  `SidebarTrigger`, which renders outside it, or by Cmd/Ctrl+B. Radix's modal close handler
  calls `preventDefault()` on FocusScope's own restore and then focuses `context.triggerRef`,
  which is `null` here, so the keyboard landed on `<body>` and the tab order restarted at the
  top of the document (SC 2.4.3). `SidebarProvider` therefore remembers what had focus when
  the drawer opened and `SheetContent`'s `onCloseAutoFocus` puts it back. Doing *nothing* is
  not the same as leaving Radix alone, which is why the handler only stands aside when the
  opener has left the document.
- **The tooltip that ate Escape.** `SidebarMenuButton` mounted a Radix `Tooltip` and hid the
  content with `hidden={state !== "collapsed" || isMobile}`. A hidden tooltip is still an
  *open* dismissable layer sitting above the drawer's, so the first Escape closed something
  nobody could see and the drawer needed a second. It has nothing to say in either hidden case
  anyway, so the wrapper is not mounted rather than mounted invisible.

**There was a third, and it is the worked example of the test above.** The registry passes
`[&>button]:hidden` to the drawer's `SheetContent`, which renders the Sheet's close and then
sets `display: none` on it - leaving an overlay tap and Escape as the only ways out of an 18rem
drawer, on a phone with no Escape key whose overlay is `aria-hidden` and so unreachable by a
VoiceOver swipe. Dropping the class in place was the obvious fix and the wrong one: the utility
compiles into `@layer utilities`, so an unlayered `display: revert` in `theme.css` outranks it
and the vendored line went back to registry-exact. It hangs off `[data-mobile="true"]`, the same
hook that grows the button to a 44px target, because this element spreads `data-slot="sidebar"`
over the primitive's own `sheet-content` and the sheet hook cannot see it. `revert` rather than
a display value, because the registry sets none - and the close is `absolute`, which blockifies,
so the only thing the rule has to achieve is "not `none`".

**`aria-modal` was considered and is deliberately absent**, which is Radix's decision and not
an oversight: `DialogContentModal` calls `hideOthers()` from the `aria-hidden` package instead,
and that was confirmed in a production build - opening the drawer sets `aria-hidden="true"` on
the whole app wrapper, leaving only sonner's `aria-live` region reachable. Adding `aria-modal`
would be a second, weaker mechanism for a job already done.

Everything else the registry gets wrong is corrected **from `theme.css`, not in place**.
See the next section.

The theme is the shadcn tokens in `src/theme.css` plus `--state-*` for INDI
Idle/Ok/Busy/Alert. The build emits a prebuilt `dist/styles.css`
(`@indikit/react/styles.css`, batteries-included) and copies the source `theme.css`
(`@indikit/react/theme.css`, for consumers running their own Tailwind).

Five things in that file are load bearing and easy to undo by accident:

- **The four `--state-*` fills are tuned for separation, so contrast is fixed on the
  foreground.** Light mode was white-on-colour and all four failed AA at the badge's 12px.
  Darkening the fills enough for white text squeezes them into one narrow band of lightness
  and collapses exactly the separation they were picked for - Busy against Alert fell from
  CIEDE2000 7.0 to 3.3 under simulated deuteranopia when tried - so the light `-foreground`
  tokens became near-black instead, as the dark palette already did. Change a foreground,
  not a fill.
- **Busy pulses with a ring on a pseudo-element, not with opacity on the badge.** Tailwind's
  `animate-pulse` fades the element to 0.5, which takes the badge's text down with its
  fill: 1.75:1 at the dimmest frame, and no fill colour survives that - solid black faded
  to 0.5 over white reaches only 3.95:1. The mechanism is `[data-indi-pulse]::after`
  carrying an `outline` (not a border, not a box-shadow) that scales and fades: an outline
  paints entirely outside the pseudo-element's box, so at rest not one animated pixel lands
  on the badge or its line box, whatever padding a consumer passes. `state-badge.tsx` sets
  `data-indi-pulse` and the `relative` the ring is positioned against; the theme owns the
  rest, including the `prefers-reduced-motion` gate.
- **Everything below the `[data-indi-state]` mapping is outside every `@layer`, on
  purpose.** That is what lets `theme.css` overrule a vendored primitive that
  `shadcn add` will rewrite. The hook is always the utility class the registry emits,
  never `data-slot`, because `data-slot` does not survive `asChild` while `className`
  concatenates. And the constraint that governs the whole section: an unlayered rule
  setting a **real** property beats every layered rule on that element, so it must either
  restate every variant of that property the element can be in, or be narrowed to something
  that cannot be in those states. A custom property (`--tw-ring-color`) is always safe;
  `border-color`, `position` and `background-color` are not - a `border-color` rule was
  tried there and destroyed the `focus-visible:border-ring` shift it existed to strengthen.
  `theme-cascade.test.ts` compiles the stylesheet **twice** and asserts each correction is
  outside every layer, because jsdom implements neither cascade layers nor `color-mix` and
  every other test would stay green while these silently died. Twice, because only the
  `--minify` build ships (`build:css`) and Lightning CSS is a different code path: it drops
  quotes from simple attribute selectors, shortens `::before` to `:before`, and un-nests the
  `@supports` fallback it generates around `color-mix` into a sibling rule - so a selector
  legitimately appears both at the top level and one block deep, and the minified assertion is
  "inside no `@layer`" rather than "at depth zero". `theme-contract.test.tsx` guards the class
  hooks against a rename.
- **The focus ring is offset, and the offset is half the fix.** The 75% opacity is the ring
  against the *surface*; on a filled control its other neighbour is the control's own fill, and
  the ring is a tinted version of the same token - destructive 1.38:1 light and 1.32:1 dark,
  checked switch 2.05 / 1.60, primary button 2.11. So the corrections also set
  `--tw-ring-offset-width: 2px` and restate `--tw-ring-offset-shadow`, which only the
  `ring-offset-*` utility would otherwise set. All three are custom properties, so the offset
  costs nothing under the rule above. The destructive ring's offset colour is **white, not the
  surface**: `dark:bg-destructive/60` composites to `#973030` on a near-black card, 2.48:1 from
  it, so a card-coloured gap is invisible against the fill; white is the variant's own hardcoded
  text colour and makes the indicator two-tone (7.55 / 5.74 / 3.27). In light mode white *is*
  the surface, so one declaration covers both schemes.
- **`--input` is one token doing two jobs and is deliberately not split.** It is a control's
  border *and* the 30% fill of that same control *and* the whole of the Switch's off-state
  track, and those pull opposite ways: at `#6e6e6e` the dark border reads 3.71:1 against the
  card but only 2.68:1 against its own `bg-input/30` fill. Splitting it into a border token
  and a fill token abandons the Switch, whose track *is* `bg-input` - back to 1.13:1 against
  the sidebar in light and 1.13:1 at `/80` against the card in dark. The comment beside each
  value carries the full set of measurements.

The `tsx` fences in this package's `README.md`, in `docs/guides/frontend.md`, in
`docs/index.md`, in the root `README.md` and in `docs/guides/tutorial-open-meteo.md` are
compiled out of the markdown by `pnpm typecheck` - see `scripts/` below. Both pages had
rotted before that existed: the guide's examples outran the API (which is how the value
hooks got found), and the README rendered `useConnection()` straight into JSX, when the
hook returns the `{transport, upstream}` object, so the sample threw on paste.

`@indikit/react/testing` (`src/testing/`) is the counterpart to `indikit.testing`:
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

## `scripts/` - the documentation fence extractor

`scripts/extract-doc-snippets.mjs` is what keeps the documented TypeScript honest. It reads
the `ts`/`tsx` fences out of the six markdown files that carry them - the two package
`README.md`s, the root `README.md`, `docs/index.md`, `docs/guides/frontend.md` and
`docs/guides/tutorial-open-meteo.md` - and writes one module per fence into the owning
package's `src/__generated__/docs/`, where that package's existing `tsc --noEmit` picks it
up. Each package's `typecheck` script runs it first, the output is gitignored, and Biome
skips `__generated__`. It replaced three hand-copied mirror files, which compiled but were
tied to the markdown by nothing at all.

- **Every fence is claimed by exactly one manifest entry, or the extractor fails.** Entries
  are keyed by a distinctive substring of the fence body, never by index, so inserting a
  fence above another does not silently re-point an entry. Add a fence and the build stops
  until somebody says which package compiles it - that refusal is the whole feature. A
  markdown file anywhere in the repo that grows a TypeScript fence without joining the
  manifest fails the same way.
- **The fence body is verbatim.** The only transforms are the ones the compiler forces:
  `@indikit/react` / `@indikit/client` becomes `../../index` (a package cannot resolve
  its own published name from inside `src/`), `import "@indikit/react/styles.css"` is
  dropped (nothing declares a type for it), and a top-level declaration the fence never uses
  is exported past `noUnusedLocals`. A fence that is a fragment rather than a module gets
  `imports` and a `wrap` from the manifest, so `await client.waitFor(...)` has a real
  `IndiClient` in scope rather than an `any`.
- `extract-doc-snippets.test.mjs` covers the parse and the manifest check - the half `tsc`
  cannot witness. `tsc` proves the snippets compile; the test proves an unclaimed fence
  still fails.

## `apps/panel/` - the reference panel

Vite + `@tailwindcss/vite`, composed entirely from `@indikit/react`: a device sidebar with
connection status, a `DeviceConfigDialog` entry for the selected device and a light/dark
toggle, a `DevicePanel` per device, and a docked message strip. `vite build` emits into `src/indikit/web/static/panel/`, where `web/app.py` serves
it at `/`. The wheel bundles that built panel (`hatch_build.py` build hook plus `artifacts`
in `pyproject.toml`, which rebuilds it with pnpm when missing), so `pip install` ships the UI.

The shell owns the page's structure, which the primitives cannot: the sidebar's markup is
all `div`s, so the device menu is wrapped in a `nav aria-label="Devices"` (without it the
only means of moving between devices sits outside every landmark), and `StatusAnnouncer` is
mounted here rather than inside `DevicePanel` so it covers every device and not just the
selected one.

Two smaller things the shell owns for the same reason, both found by an axe sweep of the state
nothing else reaches - `indikit serve` with no `--device`:

- **The empty state is a sentence, not a list.** "No devices connected." was a `<p>` directly
  inside `SidebarMenu`'s `<ul>`, where the only legal child is an `<li>`. The menu is now
  rendered only when there is a menu; `DeviceConfigDialog` needs no separate guard, because
  nothing can be selected while nothing is connected.
- **The group heading names its colour.** `SidebarGroupLabel` draws in
  `text-sidebar-foreground/70` (6.29:1 light, 5.61:1 dark), and `DESIGN.md` puts body-size
  secondary text on the AAA tier, so the shell passes `text-muted-foreground` (7.63 / 8.64).
  Not corrected in `theme.css`: `color` is a real property and an unlayered rule on it would
  beat every state variant the element can be in.
- **Configuration is nested inside its device's menu item**, rendered only for the selected
  device, since the panel shows one device at a time and an entry under every device would
  be a second row each. The shell no longer asks `useProperty(active, "CONFIG_PROCESS")` for
  itself: `DeviceConfigDialog` brings its own `SidebarMenuSub`, so "renders nothing" now
  covers the wrapper too and there is no group left that could stand there empty. See the
  `@indikit/react` section above for why this is the third placement and what each of the
  first two got wrong.

**The docked message strip is `h-auto max-h-56`, and the `h-auto` is load bearing.** It was
`h-56`, which charged the strip 224px whether it held two lines or two hundred - and the
instrument grid pays for that out of its own scroll area. At 1440x950 the grid was cut to
613px against 1089px of content, and the cut landed on a group heading: `ALMANAC` sat one
pixel above the strip with its card below the fold, reading as a label for the log rather
than for the instrument. `MessageLog` carries `h-full` for consumers who give it a sized
box, so overriding the height needs `h-auto` and not merely a `max-h-*` beside it.

**Tailwind source detection is rooted at the Vite root, not at the CSS file.** The demo
configs set `root: "demo"`, so without the explicit `@source "./**/*.{ts,tsx}"` in
`src/index.css` nothing in `src/` is scanned and every class used only by the app shell goes
missing from the demo stylesheets, while the app build still looks fine. Keep that line.

Arbitrary values that wrap `env()` in `calc()` need Tailwind's underscore spacing:
`h-[calc(3.5rem_+_env(safe-area-inset-top))]`. Without whitespace around the `+` the CSS is
invalid and the whole declaration is silently dropped.

## `apps/panel/demo/` - the documentation demo

**There is one demo page.** `demo/index.html` builds through `vite.demo.config.ts` into
`docs/demo-app/` via `pnpm run docs:demo`; the output is gitignored. It runs **two**
simulated devices through **one** `IndiClient` and offers two views of them: the stock panel
`App` and the custom wallboard.

`dome-sim.ts` and `weather-sim.ts` are TypeScript ports of `examples/dome_device.py` and
`examples/openmeteo_device.py` behind a fake `WebSocketLike`, so the demo runs with no
server. Each owns exactly one device, because each stands in for one driver.

**`observatory-sim.ts` is the bridge above them, and that layer is the point.** A real
bridge is not per-driver: `indiserver` multiplexes every driver onto one stream and the
bridge puts that whole stream on one WebSocket. `ObservatorySimSocket` owns both simulators,
interleaves their frames onto one `onmessage`, and fans every client write out to both
(each ignores what is not addressed to it). Three properties are load bearing:

- **Exactly one `hello`, and it leads.** Every control frame (`hello`, `connection`) a child
  emits is dropped and this class sends its own, because the control frames are the
  *bridge's* and here it is the bridge. See the `hello` rule below.
- **The children are constructed inside the opening timer, not in the constructor**, so
  their own opening bursts are booked after the `hello` and land behind it. They are
  attached *before* `onopen`, because a client with anything buffered flushes it from that
  callback and a write with nowhere to go would vanish.
- **Both simulators keep their own `CONNECTION` lifecycle.** Nothing in the multiplexer
  connects, disconnects or filters a device write.

`observatory-sim.test.ts` pins the frame ordering, which is wire contract rather than
rendering and is therefore the one thing tested at this level.

- **The simulators mirror real drivers.** Change a driver's properties or its safety rule and
  change its simulator too, or the demo stops being a demo of anything.
- **`weather-sim.ts` also carries `CONFIG_PROCESS`**, libindi's universal configuration
  property (four members, AtMostOne, group "Options"), so the published demo exercises
  `DeviceConfigDialog` rather than leaving it visible only in tests. It answers every action
  with all members **Off**, because `CONFIG_PROCESS` is a momentary action and not state: a
  member left On renders as a button stuck in its pressed position.
  - It carries **four** members where `openmeteo_device.py`'s `define_config()` publishes
    three: the SDK does not implement `CONFIG_DEFAULT`, and libindi does. That is the one
    deliberate divergence from the driver it mirrors, and it is the right way round - the
    panel meets libindi drivers far more often than ours, so the demo is what proves
    `DeviceConfigDialog` renders a four-member property. Do not "fix" it by dropping the
    member.
  - For the same reason it publishes **no `INDIKIT_CONFIG_PERSISTED`**, even though the
    driver it mirrors now does, so the published demo exercises the fallback apology.
    Adding it would make the simulator a device that exists nowhere: libindi's four-member
    `CONFIG_PROCESS` *and* a property no libindi driver has. The demo is already committed
    to the libindi shape, and it is the shape whose copy is easiest to get wrong. The
    INDIkit side is covered where it is real - `DeviceConfigDialog`'s tests, and
    `indikit serve --device examples.openmeteo_device:OpenMeteo`.
- **Every simulator has a `CONNECTION` property**, for the same reason every example driver
  does (see `src/indikit/CLAUDE.md`): it is the first thing a client looks for, and a demo
  without one shows visitors a device shape that does not exist in the field. It has to
  behave, not just appear. Writes are refused while disconnected, and disconnecting leaves
  the instrument safe and its properties `Idle`. This demo is the first contact most people
  have with the project, so a panel whose Connect button does nothing is worse than no demo.
  It is also why the page **opens on the stock panel**: both devices start disconnected, and
  the panel is where a visitor presses Connect.
- **The connection opens with the `hello`, before the connection frame and any `def`**, the
  way the real bridge does, and there is exactly one of each per socket. Skip it and the
  client logs "the bridge sent no hello frame" into the demo's own message panel, where a
  visitor reads it as a fault on a page that is most people's first contact with the project;
  send two and the bridge has introduced itself mid-stream.
- **Construct a simulator lazily *inside* `webSocketFactory`.** It starts delivering frames
  the moment it exists, and a client that has not attached its handlers yet misses every
  `def`.
- The page shows the custom UI beside the **real panel `App`**, not a bare `DevicePanel`, so
  the demo looks like what ships. Both views stay mounted with the inactive one hidden:
  unmounting takes its `IndiProvider` with it, and the provider closes the client on unmount,
  which would reset both simulated drivers on every switch.

`observatory-board.tsx` and `board-visuals.tsx` are the tutorial's custom UI: a **wallboard**
(read at 4 m, no interaction beyond a light/dark toggle, one screen, readings that blank
rather than go stale) plus its drawn figures. Below `lg` it reflows to a scrolling column,
because a phone is not a wallboard and clipping readings is worse than scrolling.

- Figures wear theme tokens only (`fill-state-*`, `fill-chart-3`, `stroke-muted-foreground`)
  so they follow light and dark. Two of those choices are not interchangeable: the moon's
  unlit disc is `fill-foreground/20` because in dark mode `foreground` is light and would
  erase the phase, and `DomePlan`'s wall is `muted-foreground` rather than `border` because
  in dark mode `--border` and `--muted` are the same value, so a bordered wall around a muted
  floor vanishes and takes the aperture's "gap in the wall" reading with it.
- **`UNKNOWN` is a first-class third state on the board**, styled neutrally rather than as an
  alarm, and it is not decorative: aborting a shutter move leaves `DOME_SHUTTER` in Alert
  with "Status: unknown.", and a disconnected driver is repeating its last reading rather
  than reporting hardware. Both land on `UNKNOWN`, and the dome figure draws it as a dashed
  band rather than guessing a position.
- **`DomePlan`'s rotation takes the shortest angle.** `ABS_DOME_POSITION` wraps and CSS does
  not know that, so 359° to 1° would animate 358° backwards. `useContinuousBearing` in the
  board adds the shortest signed step to a running total, and the figure takes that total -
  which is legitimately outside [0, 360). It writes a ref during render and is safe only
  because the update is idempotent; keep it that way or `StrictMode` double-counts.
- **The board's units are its own, and that is forced.** An element's label belongs to its
  `def`; a `set` carries values and the store merges nothing else, so the unit
  `openmeteo_device.py` folds into its labels after the first fetch never reaches a browser.
  The `UNITS` table mirrors what `weather-sim.ts` asks the API for; change the request and
  change the table.
- **Status colour never carries meaning alone** - the closest pair is now ΔE 11.9 apart in
  the worst of normal, deuteranopic and protanopic vision, where the set before it put dark
  Ok and dark Alert at 2.3 - so every state is written out as well as coloured, and each of
  the dome figure's three shutter readings differs in *shape* before it differs in hue.
