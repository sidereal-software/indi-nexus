---
search:
  boost: 2
---

# Building a frontend

Every INDI device describes itself: its properties, their kinds, their ranges and their
labels. A UI can therefore be generated from what the device reports instead of written
per instrument.

There are two ways to build one, and they mix freely. `DevicePanel` renders a whole
device, including instruments INDINexus has never seen. The same live data is on hooks,
so you can lay out exactly the screen your observatory wants.

## Rendering a whole device

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

That is a working control panel: every property of the dome, under a heading for its INDI
group, each drawn with the right control for its kind. Numbers come with their units and
limits, switches render as radio buttons or checkboxes depending on the INDI rule, lights
as coloured dots, BLOBs as download links. Writable properties get editable controls and
read-only ones do not. Status badges update live.

Two components do the work. `IndiProvider` opens a WebSocket to the bridge, keeps it open
(reconnecting if the observatory restarts), and mirrors everything it hears into a store.
`DevicePanel` subscribes to that store and re-renders the parts that changed.

## Letting your app connect

Your app is served from its own origin - `http://localhost:5173` under Vite - and the
bridge accepts its own by default, so name yours when you start it:

```bash
indi-nexus serve --allow-origin http://localhost:5173
```

Repeat the flag for more, or set `INDI_NEXUS_ALLOWED_ORIGINS`. Skipping it is not an
option the bridge can quietly take for you: `/ws` is its whole write surface, a frame
sent there becomes an INDI `new*` that moves hardware, and a WebSocket is exempt from
both the same-origin policy and CORS - so without the check, any page an operator
happens to have open can drive the instrument. The panel the bridge itself serves, and
the Vite dev proxy in `web/apps/panel/vite.config.ts`, are same-origin and need
nothing.

If the bridge was started with `--token` (which the Docker image does by default), pass
it as `?token=` on the URL: `ws://localhost:8000/ws?token=...`. A browser cannot put a
token in a header on a WebSocket handshake, so the query parameter is the only form
available.

The stylesheet is prebuilt, so you do not need Tailwind. If you *are* running Tailwind,
import `@indi-nexus/react/theme.css` instead - just the design tokens - and let your own
build generate the utilities.

## Showing several devices

`useDevices()` returns every device the hub knows about, so a whole observatory is one
`map` with no instrument named in it. A device plugged in later appears on its own:

```tsx
function Observatory() {
  const devices = useDevices();
  return devices.map((name) => <DevicePanel key={name} device={name} />);
}
```

`ConnectionStatus` and `MessageLog` are the other two pieces the reference panel adds
around that, and they take no props.

## Building your own layout

For a purpose-built screen, such as the few numbers a night operator needs at a size
readable across the room, use the hooks and write your own markup:

```tsx
import { useNumber } from "@indi-nexus/react";

function DomeAzimuth() {
  const azimuth = useNumber("Dome Simulator", "ABS_DOME_POSITION", "DOME_ABSOLUTE_POSITION");
  return <h1>{azimuth ?? "--"}°</h1>;
}
```

That component re-renders when that one number changes, and not otherwise.

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
re-renders when the data it reads changes rather than on every frame that arrives.

## Sending commands

Get the client from `useIndiClient()` and ask for a change. It mirrors the Python client,
so the names transfer:

```tsx
function ShutterButtons() {
  const client = useIndiClient();
  return (
    <>
      <button
        type="button"
        onClick={() => client.setSwitch("Dome Simulator", "DOME_SHUTTER", { SHUTTER_OPEN: "On" })}
      >
        Open
      </button>
      <button
        type="button"
        onClick={() =>
          client.setNumber("Dome Simulator", "ABS_DOME_POSITION", { DOME_ABSOLUTE_POSITION: 120 })
        }
      >
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

!!! note "Commands are requests"

    `setSwitch` asks for a change. The button moves when the driver accepts the request
    and publishes the new value, not when you click it, so the screen shows what the
    hardware reports rather than what was asked of it.

## The components

| Component | Renders |
|---|---|
| `DevicePanel` | every property of a device, grouped |
| `PropertyVectorCard` | one property, with the right control for its kind |
| `StateBadge` | the Idle/Ok/Busy/Alert badge |
| `ConnectionStatus` | both connection states |
| `MessageLog` | the rolling INDI message log, **and the bridge's write rejections** |

Mix them with your own markup: `PropertyVectorCard` on the two properties that matter,
hand-built widgets around them.

!!! important "`MessageLog` is where a refused write shows up"

    When the bridge will not forward a frame - the upstream `indiserver` is down, its
    queue is full, or the frame is not one a client may send - it answers that browser
    alone with an error frame, and the client turns it into a log line reading
    `newNumberVector was not sent: not connected to indiserver; the write was not sent`.

    Nothing retries it and no control changes appearance, because the driver never
    published anything. So a UI that drops `MessageLog` has no surface at all for a
    failed command, and a user is left watching a control that simply does not move. If
    you build your own, subscribe with `client.onMessage(...)` and show it somewhere.

## Without React

`@indi-nexus/client` is the layer underneath: a reconnecting WebSocket and a typed
property store, with no UI dependency. Use it from Svelte, Vue, or plain TypeScript:

```ts
import { IndiClient } from "@indi-nexus/client";

const client = new IndiClient({ url: "ws://localhost:8000/ws" });
client.subscribe((event) => console.log(event.device, event.name, event.vector?.state));
client.connect();
```

`@indi-nexus/react` re-exports all of it, so a React app needs only the one package. The
same origin rule applies: start the bridge with `--allow-origin` naming wherever this
code is served from. A peer that is not a browser - Node, a script, a test - sends no
`Origin` at all and needs nothing.

## Full API

[`@indi-nexus/client`](../reference/typescript/client/index.md) and
[`@indi-nexus/react`](../reference/typescript/react/index.md).
