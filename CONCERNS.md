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

Three commits since `indi-nexus-v0.2.0` carry a breaking change: the client refusing a
send while disconnected, the `/ws` guarding, and the removal of `DeviceConfigCard` from
`@indi-nexus/react`. `bump-minor-pre-major` is set, so the next release is 0.3.0 rather
than 0.2.1. The open release PR's checks sit at `action_required` and will not run until
approved.

**Resolved by:** reading the three `BREAKING CHANGE:` footers, approving the checks, and
merging - or deciding to hold the release, in which case say so here.

### The panel has no favicon

Nothing references one, so every page load 404s and logs a console error. It is cosmetic
and it is the only console noise the panel produces that is ours.

**Resolved by:** deciding what the icon is. That is a branding call, not an engineering
one, which is why it is still here.

---

## Known sharp edges

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

### Two vendored shadcn primitives are hand-edited

`web/packages/react/src/ui/button.tsx` and `ui/scroll-area.tsx` carry deliberate edits,
against the rule in `web/CLAUDE.md` that primitives come from the CLI untouched. Both are
marked `DEVIATION` in place with the measurement that forced them, and neither is fixable
from outside the file: `scroll-area` spreads props onto the root only, so nothing can reach
the scrolling element that has carried a focus-ring class all along, and `button` rings the
destructive variant at a fifth of the opacity every other control uses.

The next `shadcn add` for either component silently reverts them and the accessibility
failures come back.

**Resolved by:** upstreaming both to shadcn, or accepting them permanently and adding a
check that fails when the markers disappear. Doing neither is what makes this a concern.

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

### Two accessibility claims are unit-tested but never seen in a browser

The panel passes an axe sweep across eight states, but two of them were unreachable live
and rest on unit tests alone: the empty state, because the browser simulators define their
properties synchronously and leave no window to scan, and the distinctness of the write
buttons, because no shipped example publishes two writable properties at once.

**Resolved by:** a demo build that can be told to stay silent, or a run against a real
`indiserver` with a driver that has two writable properties.

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
