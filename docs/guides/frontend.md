# Building a frontend

The TypeScript side is three layers, all speaking the same typed wire contract
as the Python models:

- **`@indi-nexus/client`** - a framework-agnostic reconnecting client for the
  bridge's WebSocket and a typed property store. No UI dependency.
- **`@indi-nexus/react`** - `IndiProvider`, hooks, INDI-aware components, and
  the themed shadcn/ui primitives.
- **The reference panel** - the batteries-included app that ships inside the
  `indi-nexus` wheel and serves at `/`.

## Hooks

Every hook subscribes through `useSyncExternalStore` over an immutable store,
so components re-render exactly when the data they read changes:

```tsx
useConnection()                       // { transport, upstream }
useDevices()                          // sorted device names
useDevice("Dome Simulator")           // all properties of one device
useProperty("Dome Simulator", "ABS_DOME_POSITION")   // one vector
useElement("Telescope Simulator", "EQUATORIAL_EOD_COORD", "RA")  // one element
useMessages(200)                      // the rolling INDI log
```

## Components

`DevicePanel` renders every property of a device as grouped cards;
`PropertyVectorCard` renders one property with the right control for its kind
(numbers and text with live readouts, switches as toggle groups honouring
their INDI rule, lights as status dots, BLOBs with download links);
`ConnectionStatus`, `StateBadge`, and `MessageLog` cover the rest of a
panel's chrome.

```tsx
import { IndiProvider, DevicePanel, MessageLog } from "@indi-nexus/react";
import "@indi-nexus/react/styles.css"; // batteries-included theme

export function App() {
  return (
    <IndiProvider url="ws://localhost:8000/ws">
      <DevicePanel device="Dome Simulator" />
      <MessageLog />
    </IndiProvider>
  );
}
```

Running Tailwind yourself? Import `@indi-nexus/react/theme.css` (the tokens
only) instead of the prebuilt stylesheet and let your build generate the
utilities.

## Sending writes

The client mirrors the Python surface:

```tsx
const client = useIndiClient();
client.setNumber("Dome Simulator", "ABS_DOME_POSITION", { DOME_ABSOLUTE_POSITION: 120 });
client.setSwitch("Dome Simulator", "DOME_SHUTTER", { SHUTTER_OPEN: "On" });
await client.waitFor("Dome Simulator", "ABS_DOME_POSITION", (v) => v.state === "Ok");
```

## Full API

See [`@indi-nexus/client`](../reference/typescript/client/index.md) and
[`@indi-nexus/react`](../reference/typescript/react/index.md).
