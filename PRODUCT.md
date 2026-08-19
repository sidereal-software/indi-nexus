# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary: observatory operators.** The people running instruments, usually at night. They
connect a device, watch telemetry, send a command, and react when something enters Alert.
They did not write the driver and do not care about the Python API. When an operator's needs
and a developer's needs conflict, the operator wins.

Two secondary audiences are real and served, but they yield:

- **Driver authors** - Python developers wiring an instrument into INDI. They live in the
  docs site, the README, `indikit new`, and the generated starter file, and they use the
  panel mostly to confirm the driver they just wrote does what they meant.
- **Frontend builders** - developers composing `@indikit/client` and `@indikit/react`
  into their own observatory UI. The reference panel is a worked example they will replace,
  and "build your own UI" is a first-class path, not a fallback.

Worth recording because it is a live tension rather than a task: the shipped documentation
addresses driver authors first. `README.md` and `docs/index.md` both open on writing a
driver. That ordering predates the decision above and is not itself a product commitment.

## Product Purpose

INDIkit is a Python toolkit for controlling astronomical instruments over the
[INDI protocol](https://docs.indilib.org/protocol/), plus the web UI operators work from.
Telescopes, domes, cameras, focusers and weather stations at an observatory all speak INDI
through a per-instrument driver; INDIkit is how you write those drivers in modern typed
Python, how you talk to them from Python, and how you put them on a screen.

Three parts ship together and are independently useful: a driver SDK, an async client, and
a web bridge with a ready-made control panel plus React components. Writing only a driver is
a normal way to use it.

Success is an operator who can run their instruments through the panel without needing to
know INDI, and an author who can add an instrument without reimplementing INDI's machinery.

## Positioning

**It plugs into the observatory that already exists rather than replacing it.** The C
`indiserver` binary stays the hub; a driver written here is an ordinary INDI driver, so
KStars/Ekos, PHD2 and third-party drivers keep working against it unchanged. INDIkit
modernizes the Python and browser layers only, and does not reimplement `indiserver`.

What a neighboring project would have to copy to match it:

- A driver is one Python class with declarative property definitions, `@every` timers and
  `@on_new` handlers. The connection lifecycle, dispatch, wire format and error handling
  come from the framework.
- The whole thing is typed and checked: `mypy --strict` on the package, Pydantic v2 models
  as the single wire contract, and hand-authored TypeScript mirroring those models.
- A driver is testable with nothing plugged in. `DeviceHarness` drives a `Device` directly,
  with no instrument, no `indiserver` and no socket.
- The panel builds itself from whatever a device declares, so it renders hardware INDIkit
  has never seen.
- One install gets you a running UI. The compiled panel is bundled into the Python wheel, so
  `pip install` needs no Node toolchain, and `serve --device` runs a driver in-process so
  trying it out needs no `indiserver` either.

## Operating Context

All four of these scenes are real and future work has to survive every one of them:

- **Amateur / backyard rig.** One person, a few instruments, a laptop or phone beside the
  scope. Dark-adapted eyes, cold hands, no second operator, no one to ask.
- **Remote-hosted rig.** The instruments sit at a dark site far away; the operator checks a
  browser tab from indoors or from a phone. Connectivity is not guaranteed, which is why the
  client reconnects and the bridge reports transport and upstream state separately.
- **Research / professional observatory.** A control room, several instruments, possibly
  shift handovers, and a display someone reads from across the room.
- **Developer's desk.** Daylight, a desk, a driver being written, and the panel used to
  confirm it behaves.

The consequences that follow from the scenes rather than from taste: night is the ordinary
condition and not an edge case; a phone is a supported operating console and not a courtesy
breakpoint; readings may need to be legible at several metres; and the operator is often
alone, so the interface has to be the thing that tells them something went wrong.

## Capabilities and Constraints

**What exists today.** A driver SDK (declarative property definitions, timers, handlers,
per-device config persistence). An async reconnecting client with a property cache. A
FastAPI bridge exposing INDI over a WebSocket as typed JSON, with REST and debug surfaces.
A Typer CLI (`new`, `serve`, `run`, `monitor`). A reference React panel bundled into the
wheel. Two published-intent npm libraries, `@indikit/client` and `@indikit/react`.

**Product direction: the panel grows toward observing sessions.** Today it is generic and
property-level - it renders whatever a device declares and has no notion of a target, a run,
or a history. The intended direction is a session-aware operator surface: targets, runs,
history, and orchestration across several devices. Future design should leave room for that
rather than hard-coding a one-device, one-screen model. Session concepts layer on top of
declared properties; they never substitute for them or fabricate a capability a device has
not published.

**Explicitly undecided.** Whether standard INDI properties (`EQUATORIAL_EOD_COORD`,
`DOME_SHUTTER`, `CCD_EXPOSURE`) get purpose-built controls instead of generic number and
switch rendering is an open decision, distinct from the session direction above. Do not
assume either answer.

**Locked technical constraints** (from `CLAUDE.md`; not revisitable without direction):

- `indiserver` stays the hub. Drivers run as its stdio children; the web layer is a TCP
  client of it.
- Dual protocol: INDI 1.7 XML on the `indiserver` wire, typed JSON to browsers.
- Monorepo. INDI 1.7 is frozen, so browser wire types are hand-authored TypeScript mirroring
  the Pydantic models, kept in step by a golden wire schema.
- Frontend is TypeScript + React (Vite) over WebSockets, styled with shadcn/ui, in three
  layers: `@indikit/client`, `@indikit/react`, and the reference panel. Both
  "batteries-included app" and "build your own UI" are first-class.
- Python 3.12+. MIT licensed.
- A WebSocket is exempt from same-origin and CORS, so the bridge's origin allow-list and
  optional `--token` are the only guard on `/ws`. Any surface that connects has to carry
  that through.

**Terminology** is INDI's and is not ours to rename: device, property (a *vector* of
elements), the four element kinds (Number, Text, Switch, Light, plus BLOB), the four states
(Idle, Ok, Busy, Alert), the switch rules (OneOfMany, AtMostOne, AnyOfMany), `def` / `set` /
`del` frames, and the standard property names libindi already established. Operator-facing
copy may translate a concept, but the wire names remain the truth and the panel can show
them on request (the Debug info toggle).

`CONCERNS.md` is the live register of what is known broken, unfinished, or deliberately
deferred. Read it before starting, and delete an entry in the commit that resolves it.

## Brand Commitments

**Name:** INDIkit, package `indikit`. **Owner:** Sidereal Software (MIT, © 2026).
**Home:** <https://indikit.sidereal.software/>.

**A visual identity is now committed: "The Emission Spectrum".** It replaced a palette this
section used to describe as a sensible default rather than a decision, and `DESIGN.md`
records it from the built world.

Its governing rule is one line, and it is a product rule before it is an aesthetic one:
**the brand spends no chroma, so hue on the panel only ever means instrument state.**
`--primary`, `--secondary` and `--ring` are neutrals in all three schemes. The one reserved
non-state hue is the documentation site's link cyan, which never appears in the panel,
because a Read surface's primary interaction is following a link and an uncoloured,
un-underlined link is not an affordance.

The world is a spectrum, rendered three ways: light is an absorption spectrum (dark marks on
a bright continuum), dark is emission (bright marks on a dark one), and `night` is emission
under the luminance ceiling above. The wordmark separates its halves by weight, never by hue,
for the same reason - a coloured wordmark in the corner of every page would be the single
exception that unmakes the rule.

Still open: there is no logo, and the panel has no favicon at all. `CONCERNS.md` records the
favicon as a branding call rather than an engineering gap, and that is still true.

One binding rule that is technical rather than aesthetic: **architecture diagrams carry no
colour.** Every diagram renders on GitHub and on the docs site, each in light and dark, and
each themes the diagram itself, so meaning rides on border weight (`classDef ours` thick and
solid, `classDef ext` thin and dashed). Node labels take no HTML beyond `<br/>`.

## Evidence on Hand

**Real and usable:**

- Eleven runnable example drivers and clients in `examples/`, every one covered by tests -
  including `openmeteo_device.py`, which drives a live public weather API.
- One in-browser [live demo](https://indikit.sidereal.software/demo-app/index.html)
  running a simulated dome and weather station through a single client, with a toggle
  between the shipping panel and a custom observatory wallboard built on the same library.
- A published docs site with guides, a porting guide from pyINDI, and generated API
  reference for both Python and TypeScript.
- Measured accessibility work, verified in a real browser rather than only in unit tests: an
  axe-core sweep across every reachable panel state, keyboard walks of the whole interface,
  contrast composited against the real ancestor stack and measured against the AAA target,
  and colour separation checked under simulated deuteranopia.

**Absences that future work must not paper over.** The project is pre-release and has no
public users. As of this writing it has never been published to PyPI or npm, its container
image is still private, and the release pipeline has never run. There are therefore **no
users, no observatories, no testimonials, no case studies, no press, no download counts, and
no benchmarks**. Do not invent any of them, and do not imply adoption, deployment at a named
observatory, or performance numbers that were never measured. The two accessibility claims
that were once unit-tested only - the empty state, and the distinctness of several
simultaneous write buttons - have since been observed live and both are covered.

## Product Principles

1. **The operator outranks the author.** Where the docs' audience and the panel's audience
   pull in different directions, the panel's audience wins.
2. **Draw from what the device declares.** The interface is generated from what a driver
   publishes, so it works for hardware nobody anticipated. Higher-level concepts may sit on
   top of declared properties; nothing may invent a capability a device never claimed.
3. **Stay a citizen of the INDI ecosystem.** Existing tools and drivers keep working. Where
   libindi already established a name, a shape, or a behaviour, match it rather than improve
   on it, and say so when a deviation is deliberate.
4. **Night is the operating condition, not an edge case.** Dark, cold, remote, alone, on a
   phone, at a distance - these are the normal cases, and a design that only works at a
   desk in daylight has not shipped.
5. **Truth about state is the product.** An operator alone at 3am learns what is wrong only
   from this interface. Report state faithfully, including staleness, disconnection, refusal
   and failure, and never let a stale reading pass as a live one.

## Accessibility & Inclusion

**Committed standard: WCAG 2.2 AAA where reachable**, with AA as the floor the code already
meets, and any shortfall recorded rather than left implicit.

Established practice that binds future work:

- **Colour never carries meaning alone.** This holds independently of how well the states
  separate, and they now separate far better than they did: the palette keeps every pair at
  least ΔE 11.9 apart in the worst of normal, deuteranopic and protanopic vision, where the
  set before it put dark Ok and dark Alert ΔE 2.3 apart - "fine" and "in Alert" nearly one
  colour for a deuteranope, in the scheme used at night. Separation is the floor to fall back
  on, never the message; every state is written out as well as coloured.
- **Contrast is fixed on the foreground, not the fill.** The four INDI state fills are tuned
  for separation from each other; darkening them enough for white text collapses exactly the
  separation they were chosen for.
- **Motion must not cost contrast.** Busy pulses with a ring rather than opacity, because
  fading the badge takes its text down with it (1.75:1 at the dimmest frame).
- Every scroll container is reachable by keyboard, and the page announces through exactly
  two live regions: the message log (polite, additions-only) and a separate page-level
  status region. That region speaks for three things and nothing else - a vector *entering*
  Alert on any device, including one not currently on screen; a vector this browser wrote
  to, until it settles; and the connection dropping or returning. Everything else arriving
  over the socket is telemetry and stays silent.

**A luminance ceiling for night use - built, as a third scheme.** Operators at a backyard rig
or watching a remote rig at night are dark-adapted, and a light/dark toggle does not address
that. The panel now carries `night` alongside `light` and `dark`, and the research below is
what decided its shape.

This entry previously said the requirement was a red mode, on the reasoning that dark mode
is not night vision. Research corrected it, and the correction changes what to build:

- **Scotopic vision operates below 10⁻³ cd/m².** A screen legible at arm's length, let alone
  at four metres, runs three to five orders of magnitude above that. Nobody reading this
  interface is dark-adapted *while* they read it, whatever colour it is. The honest claim is
  narrower: a dim screen costs the room less, and costs less re-adaptation afterwards.
- **The citable requirement is luminance, not hue.** MIL-STD-1472F §5.2.1.5.6.3, under the
  heading "Dark adaptation": where colour coding is used, luminance shall be no more than
  10 cd/m².
- **Red is actively hostile to some readers.** The same standard, §5.2.1.5.6.2: wavelengths
  above 650 nm should be avoided where users include protanopes. A monochrome red interface
  also spends the entire colour channel, leaving text, shape and brightness to carry every
  distinction.
- **The field splits by audience.** KStars and Stellarium ship red night modes for someone
  standing at an eyepiece. Rubin Observatory's operator interface ships a very dark
  desaturated blue with full colour coding and no night mode at all, for someone in a
  control room. Our operators are described in Operating Context as being in both places.

So the thing built is a luminance-capped scheme, not a red one, and the existing dark theme
is not it. Do not treat "preserves dark adaptation" as something a readable screen can claim.

**What `night` actually does, and the part CSS cannot do.** The cap and WCAG contrast are
incompatible at full backlight: 10 cd/m2 on a 400-nit panel is a relative luminance of 0.025,
and contrast is (L1+0.05)/(L2+0.05), so even pure black against that ceiling yields 1.5:1.
Chasing the cap with dim colours loses the contrast and still misses the ceiling. Real
instrument panels dim the *display*, and contrast ratios are relative, so they survive dimming
untouched. `night` therefore holds AAA for text on a pure-black ground - almost no pixels
emitting at all - and the operator's brightness control does the rest; its brightest token lands on
10 cd/m2 at a display peak near 12 cd/m2, roughly 3% of a 400-nit panel. The four state hues
are unchanged in it, which is the whole reason the ceiling is a luminance rule and not a hue
one.

**Recorded shortfall: four badge labels reach AA, not AAA.**
In dark and night, Alert tops out at 5.80:1 and Idle at 5.50:1; in light, Idle tops out at
4.74:1 and Busy at 4.62:1. All four are ceilings rather than choices - the best ink available,
black or white, measures exactly that, so no foreground reaches 7:1 on those fills. Getting there needs
the *fill* darkened, and the four fills were derived together so every pair separates by at
least 11.94 CIEDE2000 under both dichromacies; compressing Alert down the lightness axis is
what put the previous palette's dark Ok and dark Alert 2.3 apart. Two labels at AA is the
price of four states a colour-blind operator can tell apart at a glance, and no badge carries
its meaning by colour alone in any case. Recorded rather than left implicit, as the standard
above requires.
