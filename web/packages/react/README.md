# @indikit/react

React hooks and [shadcn/ui](https://ui.shadcn.com/) components for building
[INDIkit](https://indikit.sidereal.software/) frontends.

Observatory instruments (telescopes, domes, cameras, focusers, weather stations) speak
[INDI](https://docs.indilib.org/protocol/). The INDIkit bridge puts that traffic behind a
WebSocket as typed JSON.

This package turns that into a UI. Point a provider at a bridge, name a device, and you
have a working control panel.

It builds on [`@indikit/client`](https://www.npmjs.com/package/@indikit/client) and
re-exports all of it, so this is the only package an application needs.

## Install

```bash
npm install @indikit/react
```

`react` and `react-dom` (18.3+ or 19) are peer dependencies.

## Usage

```tsx
import { StatusAnnouncer, IndiProvider, DevicePanel } from "@indikit/react";
import "@indikit/react/styles.css";

export const App = () => (
  <IndiProvider url="ws://localhost:8000/ws">
    <StatusAnnouncer />
    <DevicePanel device="Mount" />
  </IndiProvider>
);
```

`DevicePanel` builds itself from whatever the device reports it has, so it works for
instruments INDIkit has never seen.

`StatusAnnouncer` is in that first example on purpose. Render it once, anywhere under the
provider. It watches every device, including the ones your layout is not currently
showing.

Everything on the screen arrives over a socket, and a screen reader announces none of it:
a property going `Ok` to `Alert` redraws a badge silently. `StatusAnnouncer` is the live
region that speaks.

It speaks for three things and stays silent for everything else. INDI `set` frames are
telemetry, a driver can emit them once a second, and reading them aloud would bury the one
that matters:

- **A vector entering `Alert`.** Entering, not being: a latched Alert re-emits with every
  later `set`, and only the transition is announced.
- **A vector this browser wrote to, until it settles.** Press Open and you hear the shutter
  go `Busy` and then `Ok`. That is the answer to your own press, not the stream. The first
  state that is not `Busy` disarms it, so one press buys at most two sentences.
- **The connection.** The socket dropping, or the bridge losing `indiserver`, and the
  matching recovery. A recovery is announced only if the loss was, which is what keeps a
  freshly opened session quiet.

A UI without it is silent for a blind operator, which is the one failure here with no
workaround.

The middle rule works because the client reports its own sends, through
`client.onWrite((device, name) => ...)`. Nothing else can: the frames coming back from the
driver are identical whether this browser asked for the change or another client did.

For your own layout, the same live state is available through hooks:

```tsx
import { useNumber, useSwitch, useConnection } from "@indikit/react";

export const Readout = () => {
  const { transport } = useConnection(); // also `upstream` and `protocol`
  const ra = useNumber("Mount", "EQUATORIAL_EOD_COORD", "RA");
  const tracking = useSwitch("Mount", "TELESCOPE_TRACK_STATE", "TRACK_ON");

  return (
    <p>
      {transport ? "connected" : "offline"}: RA {ra ?? "-"} {tracking ? "(tracking)" : ""}
    </p>
  );
};
```

Ten hooks in all: one per property kind, already narrowed to that kind's type
(`useNumber`, `useText`, `useSwitch`, `useLight`); one for a single element with its type
intact (`useElement`); the structural ones (`useProperty`, `useDevice`, `useDevices`,
`useConnection`); and the bridge's message log (`useMessages`). Each subscribes narrowly
enough that a changing number re-renders the component showing that number and nothing
else.

All ten are read-only. Writes go through `useIndiClient()` and its `setNumber`, `setText`,
`setSwitch` and `setBlob` - so the call that moves an instrument is visible where it
happens, rather than hidden behind a setter that looks like local state.

## The components

| Component | Renders |
|---|---|
| `DevicePanel` | every property of a device, grouped |
| `DeviceConfigDialog` | a sidebar entry opening one device's `CONFIG_PROCESS` |
| `PropertyVectorCard` | one property as a card, titled and badged |
| `VectorControl` | the right control for any vector, whatever its kind |
| `ValueVectorControl`, `SwitchVectorControl`, `LightVectorControl`, `BlobVectorControl` | one kind each, when you already know which |
| `StateBadge`, `StateDot` | the Idle/Ok/Busy/Alert state, as a badge or as a dot |
| `ConnectionStatus` | both connection states, and a bridge protocol mismatch |
| `MessageLog` | the rolling INDI message log, and the bridge's write rejections |
| `StatusAnnouncer` | the spoken status region: a fault, your own write settling, the connection |

`VectorControl` is the one to reach for when mixing these with your own markup. Hand it a
vector from `useProperty` and it picks the control, so a screen you laid out yourself
still renders an instrument you have never seen. The underlying themed shadcn/ui
primitives are exported too, so the rest of your screens match without extra setup.

`MessageLog` earns its place for the same reason `StatusAnnouncer` does. The bridge answers
that browser alone whenever it refuses to forward a frame: `indiserver` is down, the queue
is full, or the frame is not one a client may send.

Nothing retries it, no control changes appearance, and the log line is the only surface the
failure has. Leaving it out leaves a user watching a control that never moves.

`DeviceConfigDialog` is the one that is more than a rendering of a property. It offers
`CONFIG_PROCESS`, which every libindi driver carries, from a sidebar entry that opens a
modal. It also names what those members really do:

- Purging a saved configuration is behind a confirmation, because libindi deletes the file
  with no backup.
- Loading one confirms while the instrument is connected, because the saved values are
  replayed through the driver.
- "Default" is labelled "Restore first saved", because that is what libindi's `.default`
  file holds.

The component takes the selected device, or `null`, and renders nothing when that device
has no `CONFIG_PROCESS`. Give it a child element to open the same modal from your own shell
instead of the sidebar entry.

`DevicePanel` therefore leaves `CONFIG_PROCESS` out, and folds the driver's own machinery
(`DRIVER_MACHINERY`: debug plumbing, snooping) into a collapsed section at the bottom.

## Testing your own components

`@indikit/react/testing` is a second entry point holding the harness this package's own
tests use, so a component you build on these hooks can be tested without a bridge:

- `renderConnected(ui)` renders `ui` under a provider wired to a fake socket that has
  already sent its `hello`, exactly as the real bridge does;
- `receive(socket, frame)` feeds that socket a frame a driver would have sent;
- `cleanup`, `screen` and `within` are re-exported from it deliberately. Importing them
  from your own copy of `@testing-library/react` gives a second registry of mounted
  containers, and the DOM then accumulates between tests.

That entry point needs `@testing-library/react` 16+, an **optional** peer dependency.
Install it if you import the entry point, and ignore it otherwise. Nothing in the main
entry point pulls it in.

## Styling

Import `@indikit/react/styles.css` once for the full stylesheet. If you already run
Tailwind and only want the INDIkit theme variables, import
`@indikit/react/theme.css` instead.

## Documentation

Full guides, a live in-browser demo, and the API reference:
<https://indikit.sidereal.software/>. Start with the
[frontend guide](https://indikit.sidereal.software/guides/frontend/).

## Changelog

[CHANGELOG.md](CHANGELOG.md) in this directory records what changed in each
release of this package. All three INDIkit packages ship at the same version,
and the [releases page](https://github.com/sidereal-software/indikit/releases)
carries the notes for every one of them together.

## License

MIT. See [LICENSE](LICENSE).
