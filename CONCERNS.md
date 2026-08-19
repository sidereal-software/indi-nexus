# Concerns

Things known to be wrong, unfinished, or deliberately deferred, with enough context to act
on without rediscovering them.

**A resolved concern is deleted, not annotated.** Do not mark one "done", do not strike it
through, do not move it to a "resolved" section at the bottom. Git already remembers; a
register that accumulates history stops being a list of what is open and becomes another
document nobody trusts. The file is correct when everything in it is still true. If that
leaves it empty, delete the file.

Each entry says what is wrong, why it matters, and what resolving it looks like. An entry
that cannot answer the third is not a concern, it is a complaint, and it does not belong
here.

---

## Needs a decision or an account you cannot make from a checkout

### The GHCR package is private

The first publish created `ghcr.io/sidereal-software/indi-nexus` as private, which is
GitHub's default. `docker pull` therefore asks strangers for credentials, and every
`docker run` line in `docs/docker.md` fails for anyone who is not you. The workflow
publishes correctly - `:edge` and `:sha-<commit>` reached the registry - so this is the
only thing standing between the image and a reader.

**Resolved by:** Settings -> Packages -> indi-nexus -> Change visibility -> Public. Then
run one of the quickstarts from `docs/docker.md` on a machine that is not logged in.

### The release pipeline has never run

`.github/workflows/release.yml` cuts tags and changelogs today, and publishes nothing,
because its one-time setup does not exist yet. Its own header lists it: a PyPI trusted
publisher (PyPI accepts a pending publisher before the project exists), a manual first
publish of `@indi-nexus/client` and `@indi-nexus/react` (npm cannot attach a trusted
publisher to a package that does not exist), and the `pypi` and `npm` GitHub environments.

Until then, merging the release PR produces a tagged version nobody can install, which is
worse than not releasing, because the tag claims otherwise.

**Resolved by:** doing that setup, then a `workflow_dispatch` run of `release.yml`, which
exists for the first publish and skips a version already on the registry.

### The next version is 0.3.0 and the release PR is waiting

Four commits since `indi-nexus-v0.2.0` carry a breaking change: the client refusing a
send while disconnected, the `/ws` guarding, the removal of `DeviceConfigCard` from
`@indi-nexus/react`, and the rename of `AlertAnnouncer` to `StatusAnnouncer`.
`bump-minor-pre-major` is set, so the next release is 0.3.0 rather than 0.2.1. The open
release PR's checks sit at `action_required` and will not run until approved.

The rename was taken deliberately at this moment rather than deferred: `AlertAnnouncer`
had grown to announce three things and only one of them is an alert, and renaming an
exported symbol is free only until the first publish. Nothing has published yet.

**Resolved by:** reading the four `BREAKING CHANGE:` footers, approving the checks, and
merging - or deciding to hold the release, in which case say so here. Note the two
entries above: a merged release PR still publishes nothing until the trusted publisher
and the manual npm first publish exist.

### The panel has no favicon

Nothing references one, so every page load 404s and logs a console error. It is cosmetic
and it is the only console noise the panel produces that is ours.

**Resolved by:** deciding what the icon is. That is a branding call, not an engineering
one, which is why it is still here.

---

## Known sharp edges

### One interop test fails on CI and passes locally

`interop` was green on 2026-08-17 (`40c9119`) and red on the 18th and 19th, on two tests.
One of them is fixed. The other is this entry.

`tests/interop/test_blob.py::test_the_only_policy_delivers_the_frame_and_nothing_else`
asserts that under `BLOBPolicy.ONLY` nothing but BLOBs arrives, and non-BLOB updates
arrive anyway - `CCD_STREAM_FRAME`, `FILTER_NAME`, `FILTER_SLOT`, `GUIDER_FRAME`,
`GUIDER_INFO` on the distro leg, and those plus `CCD_BINNING` and `CCD_INFO` on ppa.

**Two facts point the same way, and neither is about `ONLY` meaning something we misread.**
The two CI legs report *different* property sets, where a fixed libindi rule would produce
the same set on both. And the whole suite passes locally in the interop container - 39
passed, 2 skipped, twice - against the same Ubuntu 24.04 and the same distro libindi the
failing leg installs. The difference left is the machine: a shared CI runner is slower and
noisier than a laptop, so this reads as a race between the policy taking effect and
definitions already in flight, which a faster machine wins and a loaded one does not.

That makes it the harder kind of bug: the reproduction is the environment, not the code.

**Resolved by:** deciding what `enableBLOB` actually guarantees about frames already in
flight when the policy lands, and then either making the client hold them or rewriting the
assertion to say what the protocol really promises rather than what we hoped. Reproducing
it may need the container throttled (`--cpus`, or load) rather than a bisect - the suite
passing locally is evidence about timing, not evidence the client is right. Note it also
never fails the same way twice, so a fix has to be argued from the protocol rather than
confirmed by one green run.

### `DeviceHarness` needs `config_dir=` and says nothing when it is missing

`driver.run` and `serve --device` resolve `config_dir` from `Settings`; `DeviceHarness`
does not, because the harness deliberately reads no ambient environment. The consequence
is that a harness test written without the argument silently exercises the "nowhere to
save" path, and a persistence assertion fails in a way that reads as a bug in
persistence. It has cost two people a debugging round already, and a driver author
writing their first test for a `persist=True` property will hit it.

The no-ambient rule is right and should stay. The silence is the problem.

**Resolved by:** either an error from the persistence methods that names `config_dir=` when
the harness is the caller, or a line in `docs/guides/writing-drivers.md` where the harness
is introduced. The first is better; the second is cheap.

### `openmeteo_device.py` relabels its elements where no client will ever look

`_label_units` folds the API's unit strings into the `WEATHER_PARAMETERS` element labels
after the first fetch ("Temperature (°F)"). Nothing reads them. An element's label is
definition metadata: `client/store.py` says so in as many words - "Only values (and vector
status) are copied; element metadata such as a label" - and `store.ts` does the same, both
because INDI's own `oneNumber` carries no label attribute at all. Our JSON `set` happens to
serialise the whole vector, so the new label does reach a browser, and every conforming
client drops it on the floor.

It matters because the units are real information a UI wants and the driver looks like it
publishes them. The documentation demo's wallboard now carries its own `UNITS` table for
exactly this reason, with a comment pointing here; that table has to be kept in step with
`weather-sim.ts`'s fetch parameters by hand, which is the cost of the gap.

**Resolved by:** deciding where a unit belongs. Re-announcing the property (`_announce`)
once the labels change is the cheap answer and makes the existing code work, at the price of
a second `def` mid-session. Carrying units as their own property, or in the element label at
*definition* time with the driver naming the units it requests, are the other two. Whichever
is chosen, `_label_units` as it stands is dead effort and should not be left looking like it
works.

### A safe range never reaches a client, so a reading cannot be drawn against its limits

`openmeteo_device.py` judges every reading against a safe range - the low and high in its
`READINGS` table - and publishes the verdict as one light per element in `WEATHER_STATUS`.
The range itself is published nowhere. `WEATHER_PARAMETERS` defines its elements as
`Number(name=..., label=..., format="%.1f")`, and `min`/`max` default to `None`, so what a
browser gets for each reading is a number and one bit saying whether the driver likes it.

That is the whole reason the wallboard's per-tile bar carries the status light and nothing
else - a full-width bar for one bit, six times over. ISA's High Performance HMI guidance
asks for an analog representation of a measurement "relative to normal, abnormal, and alarm
conditions", and Las Cumbres draws min/max lines on every chart on its own board; a bar
showing where in its safe range a value sits would say far more for the same ink. It is not
drawn, because the numbers to draw it against do not exist on the wire, and a range invented
in the UI sits behind a readout an operator closes a dome on.

INDI's `min`/`max` would not be those numbers even if the driver set them: they bound what a
client may *write*, which is not a safe range and means nothing on a read-only vector.

**Resolved by:** the driver publishing the limits it judges against, rather than only its
verdict - a `WEATHER_LIMITS` number vector with a low and a high per element name would let
any client draw the reading against them, the panel included. This is the same "where does
this metadata belong" question as the units entry above, and probably wants the same answer.

### The light outline Button's hairline is 1.24:1

`--border` is `#e5e7eb`, which measures 1.24:1 against the white card. In light mode the
outline Button variant draws its edge with a bare `border` off that token, so the one thing
saying where that control is fails SC 1.4.11's 3:1 by a wide margin. `--input` was retuned
in the same batch and reaches 3.55:1, which fixes the Input, the switch-vector members and
the Switch - the outline Button in light mode is what is left, because it does not use
`--input` there (only `dark:border-input`).

The obvious fix was tried and measured in Chrome, and it is worse than the problem. An
unlayered `[data-variant="outline"] { border-color: var(--input) }` in `theme.css` also beats
`focus-visible:border-ring` and `aria-invalid:border-destructive`, so it destroys the focus
indicator it exists to strengthen; and `data-variant` is not scoped to buttons anyway
(`ui/badge.tsx` and `ui/toggle-group.tsx` set it too). Narrowing by `data-slot` does not work
either: `data-slot` does not survive `asChild`, so `AlertDialogCancel` would be missed. There
is no class hook to use instead, because in light mode the variant emits a bare `border`.

**Resolved by:** either raising `--border` itself - which is the token the base layer puts
on *every* element, so it has to be re-measured across every surface first - or adding a
light-mode `border-input` to the outline variant upstream, which gives the correction a
class to hook. Not by an unlayered `border-color` rule.

### The dark destructive button is nearly invisible until you focus it

`dark:bg-destructive/60` composites `#ef4444` over the card to `#973030`, which is **2.48:1**
against `#121212`. White on it is 7.60:1, so the *label* is fine and SC 1.4.11 is not failed -
a control identified by its text needs no boundary contrast - but the most dangerous button in
the product is the one whose presence reads weakest in dark mode, and an operator scanning a
modal at 3am finds "Cancel" before "Delete saved config".

The focus ring no longer depends on it: the correction in `theme.css` gives the destructive
ring a white offset so the indicator is two-tone (see DESIGN.md, The Ring Stands Off The
Control Rule). This entry is about the resting state.

Raising dark `--destructive` far enough to clear 3:1 was measured and rejected: the composite
needs roughly `#ff6b6b`, which is a hair from `--state-alert` `#f87171` and collapses the
CIEDE2000 11.3 the theme keeps between "danger" and "the instrument is in Alert".

**Resolved by:** dropping the `/60` from the dark destructive variant so the fill is the token
itself (5.00:1) - which is a registry edit, or an upstream change, not something `theme.css`
can reach, since `background-color` is a real property. Decide whether that is worth a third
`DEVIATION`.

### The panel's heading chain skips a level in the empty state

`DESIGN.md`'s Heading Chain Rule promises h1 → h2 → h3 with no step skipped. With no devices
connected the page emits `h1 "INDINexus"` and then `h3 "Messages"` - the message strip's
accordion trigger, which Radix wraps in an `<h3>` by default. axe reports `heading-order`
(moderate, best-practice tag; it is not one of the WCAG A/AA rules, and the panel has none of
those). Populated, the chain is unbroken because the property groups supply the `h2`.

**Resolved by:** giving `AccordionTrigger` a heading level the strip can set - another
`DEVIATION` in `src/ui/`, or a prop upstream - or accepting that a docked chrome strip is not
part of the content outline and saying so in `DESIGN.md` instead.

### The mobile drawer's `aria-hidden` background holds 14 focusable descendants

Opening the drawer has Radix call `hideOthers()`, which sets `aria-hidden="true"` on the whole
app wrapper. Fourteen focusable elements are inside it. ARIA says authors must not put
`aria-hidden` on content that is focusable, and what keeps focus out today is only Radix's JS
focus trap - behaviour, not structure. axe reports it as `aria-hidden-focus` needs-review
rather than a pass, which is the correct verdict: it is not a violation while the trap holds,
and nothing in the markup says so.

`inert` on the same wrapper would make the containment structural - it removes descendants from
the tab order and from the accessibility tree at once, so the guarantee survives the trap being
bypassed. This is upstream Radix behaviour, not something the panel introduces.

**Resolved by:** `inert` landing in `react-remove-scroll`/`aria-hidden` upstream and Radix
adopting it, or a deviation in `src/ui/` that adds it beside the `aria-hidden` - which would be
a third one in `sidebar.tsx` and has to be worth that. Not resolvable from `theme.css`: `inert`
is an attribute, not a style.

### A recovery speaks twice into one atomic region, 12ms apart

`role="status"` is implicitly `aria-atomic`, so each change re-reads the whole region. A
transport recovery announces "Reconnected to the bridge." and then, when the bridge's next
`connection` frame arrives, "The bridge is connected to indiserver again." - measured 12ms
apart. Some screen readers clip the first utterance when an atomic region is replaced that
fast, and the first is the one carrying the news.

Two sentences is the right content: they are two different links and the second is genuinely
new information. Only the timing is in question.

**Resolved by:** listening to it on a real screen reader - NVDA and VoiceOver disagree about
atomic re-reads and nothing in this repository can stand in for either. If the first is clipped,
the fix is to coalesce a recovery arriving inside some small window into one sentence, not to
drop either.

### A write the bridge refuses leaves `StatusAnnouncer` armed for ever

`onWrite` fires on the send, which is right - the socket buffers while offline and the operator
pressed the button regardless - so the announcer arms the property and waits for the state that
answers it. If the bridge refuses the frame instead (`{"event":"error"}`: no upstream
connection, a full outbox, a kind a client may not send), nothing ever answers, and the arming
survives until the property is deleted or the page is reloaded. A transition minutes later is
then announced as though it were the answer to that press.

The announcer cannot disarm from the `error` frame itself: `ErrorFrame` carries `code`,
`message` and the rejected `tag`, and no device or property name, so acting on it would have to
clear every pending write including the ones still legitimately waiting. This is much narrower
than it was - any non-`Busy` frame for the property now disarms, where a same-state frame used
to be swallowed - but it is not nothing.

**Resolved by:** `ErrorFrame` naming the device and property of the frame it rejected, which is
a `BRIDGE_PROTOCOL_VERSION` question and touches `control_frames.py`, `types.ts` and the golden
wire schema together. Then the announcer disarms exactly the write that failed.

### `InProcessHub` duplicates the multi-device runtime

`DriverRuntime` now serves several devices on one stream, which is exactly what
`src/indi_nexus/hub.py` already did for itself. The duplication was left deliberately so
the runtime change stayed additive, and it is the copy that will drift.

Collapsing it is not free: `hub.py` runs one reader per driver today, so a shared runtime
would make `serve --device` inherit the runtime's accepted head-of-line blocking across
co-located devices. That question has to be answered on its own terms rather than as a
rider.

**Resolved by:** either collapsing it with that question answered, or writing down that the
duplication is permanent and why.

### The panel ignores `prefers-color-scheme` at first paint

`web/apps/panel/src/use-theme.ts` seeds from the `.dark` class on `<html>` and nothing else, so
a browser set to dark that has never used the toggle gets a full-screen white page and then
whatever the operator picks. At a telescope that is a flash bright enough to cost the dark
adaptation the whole design exists for, and it happens on every fresh load.

The fix is not a one-liner, which is why it is here rather than done: reading
`prefers-color-scheme` at startup makes the OS a *third* input beside the stored choice and the
current class, and the interesting questions are what happens when an explicit choice disagrees
with the OS, whether the OS changing mid-session should move the page under the operator, and
whether an inline script has to set the class before first paint or the white flash simply
becomes a dark one. `PRODUCT.md` also records dark-adaptation preservation as a confirmed but
unbuilt requirement, and a red or luminance-ceiling mode would be a third scheme, so this
decision should not be taken twice.

**Resolved by:** answering those three questions and building the result, most likely as part
of the dark-adaptation work rather than ahead of it.

### A number input rejected by `max` says so only in the native bubble

The per-element number control carries `min`/`max`/`step` from the wire, so an out-of-range
value is refused by the browser with its own transient bubble. Nothing sets `aria-invalid` and
nothing associates a persistent message with the field through `aria-describedby`, so a screen
reader gets a validity state with no explanation attached to the control, and a sighted user
loses the bubble as soon as focus moves.

**Resolved by:** rendering the constraint as a real hint element wired with `aria-describedby`
and setting `aria-invalid` while the value is out of range. The shadcn `Field` primitives
already model this; the work is deciding whether the hint is always visible - which costs a
line per element on a card that can carry a dozen - or appears only on failure.

### The protocol-mismatch explanation is reachable only with a mouse

`ConnectionStatus` renders the mismatch line as a `<span title="...">`. A `title` needs hover,
which rules out touch, and the span is not focusable, which rules out the keyboard. The visible
text ("protocol 2, UI 1") is the summary; the sentence explaining what it means to the operator
is the part only a mouse user can read.

**Resolved by:** making it a real `Tooltip` on a focusable trigger, or simply rendering the
sentence beside the numbers - it appears only when the two halves are from different releases,
which is rare enough to afford the space.

### The panel has no skip link and no `banner`/`contentinfo` landmarks

There is a `main`, a `nav aria-label="Devices"` and an `aria-label="Messages"` region, but the
header bar and the sidebar's own chrome - the wordmark, the connection dots, the two footer
settings - sit outside every landmark, which axe's best-practice `region` rule flags. There is
also no skip link, so reaching the property grid by keyboard means tabbing past the whole
device list on every load.

**Resolved by:** wrapping the header in a `banner` (and deciding whether the sidebar footer is
`contentinfo` or simply part of the navigation region), and adding a visually-hidden-until-
focused skip link as the first tab stop. Both are shell-level; neither touches a primitive.

### A bare `.z` format inflates to no format at all

`_strip_suffix` returns `None` for a format of exactly `.z`, and the store reads `None` as
"this set carried no format" and keeps the cached one. Two different meanings, one value.

Nothing in the ecosystem sends a bare `.z` - a format is a suffix chain and libindi always
prefixes it - so pinning either reading today would be inventing a contract rather than
recording one.

**Resolved by:** finding a real producer that sends it, and then deciding. Until then this
entry exists so the next person to notice does not spend the afternoon on it.

### "POSIX everywhere" is Linux and macOS, not Windows

`config_dir` uses `click.get_app_dir("indi-nexus", force_posix=True)`, which gives
`~/.indi-nexus` on Linux and macOS. It does **not** apply on Windows: click's `WIN` branch
returns `%APPDATA%\indi-nexus` before `force_posix` is consulted. `force_posix=True` also
means `XDG_CONFIG_HOME` is ignored on Linux, which is the documented cost of one path per
operator. `INDI_NEXUS_CONFIG_DIR` overrides all of it.

The docs say "Linux and macOS alike" rather than "every platform", so nothing published is
false. This is recorded because the intent was one path everywhere and the implementation
delivers one path on two platforms.

**Resolved by:** deciding Windows does not matter and deleting this, or branching on
Windows ourselves.

### Two drivers with one device name share one config file

`<config_dir>/<device>.json` is keyed on the device name, so two processes exposing a
device of the same name overwrite each other, last writer winning. `DriverRuntime` rejects
duplicates within a process and nothing can arbitrate across processes.

libindi has the identical property with `$HOME/.indi/<device>_config.xml`, and two devices
answering to one name is unresolvable for a client regardless, so this is recorded as a
consequence rather than a defect.

**Resolved by:** nothing, unless it bites someone. Delete this entry if that never happens
and you stop wanting the reminder.
