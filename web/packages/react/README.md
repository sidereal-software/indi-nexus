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
import { IndiProvider, DevicePanel } from "@indi-nexus/react";
import "@indi-nexus/react/styles.css";

export const App = () => (
  <IndiProvider url="ws://localhost:8000/ws">
    <DevicePanel device="Mount" />
  </IndiProvider>
);
```

`DevicePanel` builds itself from whatever the device reports it has, so it works for
instruments INDINexus has never seen.

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

Alongside the INDI-aware components (`DevicePanel`, `PropertyVectorCard`, `StateBadge`,
`ConnectionStatus`, `MessageLog`) the underlying themed shadcn/ui primitives are exported
too, so your own screens match without extra setup.

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
