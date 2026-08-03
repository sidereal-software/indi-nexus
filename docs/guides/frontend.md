# Building a frontend

Every instrument tells you what it has - its properties, their kinds, their ranges, their
labels. So a UI does not have to be written per instrument: it can be *generated* from
what the device says. That is what makes this part short.

There are two ways to use it, and they mix freely:

- **Take the panel.** `DevicePanel` renders a whole device, and works for instruments
  INDINexus has never seen.
- **Build your own.** The same live data is available through hooks, so you can lay out
  exactly the screen your observatory wants.

## A complete panel, in nine lines

```tsx
import { IndiProvider, DevicePanel } from "@indi-nexus/react";
import "@indi-nexus/react/styles.css";

export function App() {
  return (
    <IndiProvider url="ws://localhost:8000/ws">
      <DevicePanel device="Dome Simulator" />
    </IndiProvider>
  );
}
```

That is a working control panel: every property of the dome, grouped into tabs, each drawn
with the right control for its kind - numbers with their units and limits, switches as
radio buttons or checkboxes depending on the INDI rule, lights as coloured dots, BLOBs as
download links. Editable properties are editable; read-only ones are not. Status badges
update live.

Two things are happening:

- **`IndiProvider`** opens a WebSocket to the bridge, keeps it open (reconnecting if the
  observatory restarts), and mirrors everything it hears into a store.
- **`DevicePanel`** subscribes to that store and re-renders the parts that changed.

The stylesheet is prebuilt, so you do not need Tailwind. If you *are* running Tailwind,
import `@indi-nexus/react/theme.css` instead - just the design tokens - and let your own
build generate the utilities.

## Showing several devices

`useDevices()` returns every device the hub knows about, so a whole observatory is one
`map` - and nothing in it names an instrument. Plug a new one in and it appears:

```tsx
function Observatory() {
  const devices = useDevices();
  return devices.map((name) => <DevicePanel key={name} device={name} />);
}
```

`ConnectionStatus` and `MessageLog` are the other two pieces the reference panel adds
around that, and they take no props.

## Building your own layout

When you want a purpose-built screen - the three numbers a night operator actually needs,
big enough to read across the room - use the hooks and write your own markup:

```tsx
import { useNumber } from "@indi-nexus/react";

function DomeAzimuth() {
  const azimuth = useNumber("Dome Simulator", "ABS_DOME_POSITION", "DOME_ABSOLUTE_POSITION");
  return <h1>{azimuth ?? "--"}°</h1>;
}
```

That component re-renders when *that one number* changes, and not otherwise.

The full set:

| Hook | Gives you |
|---|---|
| `useConnection()` | `{ transport, upstream }` - your link to the bridge, and the bridge's link to the observatory |
| `useDevices()` | the device names currently known, sorted |
| `useDevice(device)` | every property of one device |
| `useProperty(device, name)` | one property, or `undefined` if it does not exist yet |
| `useNumber` / `useText` / `useSwitch` / `useLight` | one value, already the right type (`number`, `string`, `boolean`, `IPState`) |
| `useElement(device, name, element)` | one element with its metadata, when you need the format or the limits |
| `useMessages(limit?)` | the rolling log, newest last |
| `useIndiClient()` | the client itself, for sending commands |

The four typed hooks all return `undefined` when the property does not exist yet, so a
component can render before the observatory has answered.

Each subscribes through `useSyncExternalStore` over an immutable store, so a component
re-renders exactly when the data it reads changes - not on every frame that arrives.

## Sending commands

Get the client from `useIndiClient()` and ask for a change. It mirrors the Python client,
so the names transfer:

```tsx
function ShutterButtons() {
  const client = useIndiClient();
  return (
    <>
      <button onClick={() => client.setSwitch("Dome Simulator", "DOME_SHUTTER", { SHUTTER_OPEN: "On" })}>
        Open
      </button>
      <button onClick={() => client.setNumber("Dome Simulator", "ABS_DOME_POSITION", { DOME_ABSOLUTE_POSITION: 120 })}>
        Go to 120°
      </button>
    </>
  );
}
```

Also available: `setText`, `setBlob`, `getProperties`, `enableBlob`, and

```tsx
await client.waitFor("Dome Simulator", "ABS_DOME_POSITION", (v) => v.state === "Ok");
```

for scripting a sequence.

!!! note "Nothing changes until the instrument says so"

    `setSwitch` is a *request*. The button does not move because you clicked it - it moves
    because the driver accepted the request and published the new value. That is exactly
    what you want from an observatory: the screen shows what the hardware is doing, never
    what you hoped it would do.

## The components

| Component | Renders |
|---|---|
| `DevicePanel` | every property of a device, grouped |
| `PropertyVectorCard` | one property, with the right control for its kind |
| `StateBadge` | the Idle/Ok/Busy/Alert badge |
| `ConnectionStatus` | both connection states |
| `MessageLog` | the rolling INDI message log |

Mix them with your own markup freely - `PropertyVectorCard` on the two properties that
matter, hand-built widgets around them.

## Without React

`@indi-nexus/client` is the layer underneath: a reconnecting WebSocket and a typed
property store, with no UI dependency at all. Use it from Svelte, Vue, or plain
TypeScript:

```ts
import { IndiClient } from "@indi-nexus/client";

const client = new IndiClient({ url: "ws://localhost:8000/ws" });
client.subscribe((event) => console.log(event.device, event.name, event.vector?.state));
client.connect();
```

`@indi-nexus/react` re-exports all of it, so a React app only ever needs the one package.

## Full API

[`@indi-nexus/client`](../reference/typescript/client/index.md) and
[`@indi-nexus/react`](../reference/typescript/react/index.md).
