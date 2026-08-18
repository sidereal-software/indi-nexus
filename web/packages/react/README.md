# @indi-nexus/react

React hooks and [shadcn/ui](https://ui.shadcn.com/) components for building
[INDINexus](https://indi-nexus.sidereal.software/) frontends.

Observatory instruments (telescopes, domes, cameras, focusers, weather stations) speak
[INDI](https://docs.indilib.org/protocol/). The INDINexus bridge puts that traffic behind a
WebSocket as typed JSON, and this package turns it into a UI: point a provider at a bridge,
name a device, and you have a working control panel.

It builds on [`@indi-nexus/client`](https://www.npmjs.com/package/@indi-nexus/client) and
re-exports all of it, so this is the only package an application needs.

## Install

```bash
npm install @indi-nexus/react
```

`react` and `react-dom` (18.3+ or 19) are peer dependencies.

## Usage

```tsx
import { AlertAnnouncer, IndiProvider, DevicePanel } from "@indi-nexus/react";
import "@indi-nexus/react/styles.css";

export const App = () => (
  <IndiProvider url="ws://localhost:8000/ws">
    <AlertAnnouncer />
    <DevicePanel device="Mount" />
  </IndiProvider>
);
```

`DevicePanel` builds itself from whatever the device reports it has, so it works for
instruments INDINexus has never seen.

`AlertAnnouncer` is in that first example on purpose. Everything on the screen arrives
over a socket, and a screen reader announces none of it: a property going `Ok` to `Alert`
redraws a badge silently. `AlertAnnouncer` is the live region that speaks it. Render it
once, anywhere under the provider - it watches every device, and it announces only a
transition *into* `Alert`, so a driver polling once a second does not talk over itself. A
UI without it is silent for a blind operator, which is the one failure here with no
workaround.

For your own layout, the same live state is available through hooks:

```tsx
import { useNumber, useSwitch, useConnection } from "@indi-nexus/react";

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

There are hooks for each property kind (`useNumber`, `useText`, `useSwitch`, `useLight`),
for whole properties and devices (`useProperty`, `useDevice`, `useDevices`), and for the
bridge's message log (`useMessages`).

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
| `AlertAnnouncer` | announces a property entering `Alert` to a screen reader |

`VectorControl` is the one to reach for when mixing these with your own markup: hand it a
vector from `useProperty` and it picks the control, so a screen you laid out yourself
still renders an instrument you have never seen. The underlying themed shadcn/ui
primitives are exported too, so the rest of your screens match without extra setup.

`MessageLog` earns its place for the same reason `AlertAnnouncer` does. When the bridge
refuses to forward a frame - `indiserver` is down, the queue is full, the frame is not one
a client may send - it answers that browser alone and nothing retries, no control changes
appearance, and the log line is the only surface the failure has. Leaving it out leaves a
user watching a control that simply does not move.

`DeviceConfigDialog` is the one that is more than a rendering of a property. It offers
`CONFIG_PROCESS`, which every libindi driver carries, from a sidebar entry that opens a modal,
and names what its members really do: purging a saved configuration is behind a confirmation
because libindi deletes the file with no backup, loading one confirms while the instrument is
connected because the saved values are replayed through the driver, and "Default" is labelled
"Restore first saved" because that is what libindi's `.default` file holds. It takes the
selected device (or `null`) and renders nothing when that device has no `CONFIG_PROCESS`; give
it a child element to open the same modal from your own shell instead of the sidebar entry.
`DevicePanel` therefore leaves `CONFIG_PROCESS` out, and folds the driver's own machinery
(`DRIVER_MACHINERY`: debug plumbing, snooping) into a collapsed section at the bottom.

## Testing your own components

`@indi-nexus/react/testing` is a second entry point holding the harness this package's own
tests use, so a component you build on these hooks can be tested without a bridge:

- `renderConnected(ui)` renders `ui` under a provider wired to a fake socket that has
  already sent its `hello`, exactly as the real bridge does;
- `receive(socket, frame)` feeds that socket a frame a driver would have sent;
- `cleanup`, `screen` and `within` are re-exported from it deliberately - importing them
  from your own copy of `@testing-library/react` gives a second registry of mounted
  containers, and the DOM then accumulates between tests.

It needs `@testing-library/react` 16+, which is an **optional** peer dependency: install it
if you import this entry point, and ignore it otherwise. Nothing in the main entry point
pulls it in.

## Styling

Import `@indi-nexus/react/styles.css` once for the full stylesheet. If you already run
Tailwind and only want the INDINexus theme variables, import
`@indi-nexus/react/theme.css` instead.

## Documentation

Full guides, a live in-browser demo, and the API reference:
<https://indi-nexus.sidereal.software/>. Start with the
[frontend guide](https://indi-nexus.sidereal.software/guides/frontend/).

## Changelog

[CHANGELOG.md](CHANGELOG.md) in this directory records what changed in each
release of this package. All three INDINexus packages ship at the same version,
and the [releases page](https://github.com/sidereal-software/indi-nexus/releases)
carries the notes for every one of them together.

## License

MIT. See [LICENSE](LICENSE).
