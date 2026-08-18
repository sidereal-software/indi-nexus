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

### What the panel puts where

Not every property is equally interesting, so three of them are treated differently
from the alphabetical run of groups.

**Configuration is not on the panel at all.** Every libindi driver publishes
`CONFIG_PROCESS`, but it is a set of actions on the device rather than something to
read, and one of them deletes a file with no undo, so it does not belong beside live
instrument readings. `DeviceConfigDialog` offers it from the sidebar instead, and
`DevicePanel` leaves it out rather than drawing it as four anonymous buttons. The same
goes for `NEXUS_CONFIG_PERSISTED`, the list an INDINexus driver publishes of what Save
writes: the dialog renders it as a sentence, and a read-only card full of wire names says
less in more space.

**`Main Control` comes first**, because that is where a driver puts the controls an
operator came for. Everything else follows alphabetically, so the layout is the same
every time you open the page.

**The driver's own machinery folds away last.** `DEBUG`, `SIMULATION`, `ACTIVE_DEVICES`,
the logging levels and `FILE_DEBUG` are about the driver process rather than the
instrument, and drivers scatter them through whichever group they chose - usually
`Options`, next to settings you do want. They collect in a collapsed **Driver
internals** section instead, one click away rather than gone. The set is exported as
`DRIVER_MACHINERY` if your own layout wants to ask the same question. `CONNECTION` is
deliberately not in it: Ekos hides `CONNECTION` because it drives connection from its own
toolbar, and the panel has no second home for the button an operator reaches for first.

Because the fold is worked out from what the device has right now, a driver that
defines `DEBUG_LEVEL` when you switch debugging on, and deletes it again when you switch
it off, moves it in and out on its own.

### What `DeviceConfigDialog` does and does not promise

`CONFIG_PROCESS` persists a device's settings on the observatory computer - to
`$HOME/.indi/<device>_config.xml` for a libindi driver, to JSON under
`$XDG_CONFIG_HOME/indi-nexus` for an INDINexus one. `DeviceConfigDialog` is the entry
that offers it: give it the
selected device and it renders a sidebar item that opens the actions in a modal, or
nothing at all when no device is selected or the selected one has no `CONFIG_PROCESS`.
Give it a child element and that becomes the trigger instead, so a screen with its own
shell opens the same modal from wherever suits it.

Three things about the property are not what the INDI names suggest, and the dialog says
so on screen rather than in a manual nobody has open at 2am:

- **"Restore first saved", not "Default".** `CONFIG_DEFAULT` reads a `.default` file,
  which libindi writes as a copy of the *first* configuration ever saved for that device.
  It is not the factory settings, and on a driver that was misconfigured before its first
  save it restores the misconfiguration.
- **Purging cannot be undone.** `CONFIG_PURGE` is a bare file deletion in libindi, with no
  backup and no confirmation anywhere in the library. It is behind a second confirmation
  that names the device, and nothing is sent until you confirm. Dismissing that
  confirmation leaves the configuration modal open and sends nothing.
- **Save does not necessarily save what you see.** Each driver chooses which properties it
  persists. A libindi driver makes that choice in `saveConfigItems`, which nothing on the
  wire exposes, so the dialog says outright that it cannot tell you rather than letting the
  screen imply "everything". An INDINexus driver declares persistence at define time and
  publishes the list as `NEXUS_CONFIG_PERSISTED`, and for those the dialog names the
  properties Save writes - or says plainly that Save writes none of them, which is a
  different statement from not knowing.

Loading a configuration - `CONFIG_LOAD` or `CONFIG_DEFAULT` - replays every saved value
through the driver as though it had just been sent, so on a connected instrument it is a
hardware command and can move the mount, the focuser or the filter wheel. Those confirm
while the device is connected, and do not bother you while it is not.

Feedback is the property's own Idle/Ok/Busy/Alert state, as everywhere else: the driver
answering is what says the action happened.

## Letting your app connect

Your app is served from its own origin - `http://localhost:5173` under Vite - and the
bridge accepts its own by default, so name yours when you start it:

```bash
indi-nexus serve --allow-origin http://localhost:5173
```

Repeat the flag for more, or set `INDI_NEXUS_ALLOWED_ORIGINS` to a space-separated list
(the flag wins if you do both). Skipping it is not an
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

`ConnectionStatus` and `MessageLog` are two of the pieces the reference panel adds around
that, and they take no props. The third is `DeviceConfigDialog`, which takes the device
your own shell has selected.

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
| `useConnection()` | `{ transport, upstream, protocol }` - your link to the bridge, the bridge's link to the observatory, and the bridge's [contract version](protocol.md#versioning-the-browser-contract) |
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
| `DeviceConfigDialog` | a sidebar entry opening one device's `CONFIG_PROCESS`, with the guards libindi lacks |
| `PropertyVectorCard` | one property as a card: title, state badge and the control below |
| `VectorControl` | the control alone, picked from the vector's kind |
| `ValueVectorControl` | a number or text vector, as editable fields or read-only values |
| `SwitchVectorControl` | a switch vector, as a group of toggle buttons honouring its INDI rule |
| `LightVectorControl` | a light vector, as labelled state dots |
| `BlobVectorControl` | a BLOB vector, as format and size per element, with a download link once a payload has arrived |
| `StateBadge` | the Idle/Ok/Busy/Alert badge |
| `StateDot` | the same state where there is no room for a badge |
| `ConnectionStatus` | both connection states, plus a badge when the bridge announces a [protocol version](protocol.md#versioning-the-browser-contract) this build was not written against |
| `MessageLog` | the rolling INDI message log, **and the bridge's write rejections** |
| `AlertAnnouncer` | announces a property entering `Alert` to a screen reader |

Mix them with your own markup: `PropertyVectorCard` on the two properties that matter,
hand-built widgets around them. `VectorControl` is the seam to reach through when your own
markup already supplies the heading and the badge - hand it any vector from `useProperty`
and it renders the right control, which is what keeps a hand-laid screen working against
an instrument you have not seen. The four per-kind controls underneath it are exported for
the case where you already know the kind and want to skip the dispatch.

!!! important "`AlertAnnouncer` is the only thing that speaks"

    Everything on this page arrives over a socket, and a screen reader announces none of
    it on its own: a property going `Ok` to `Alert` redraws a badge and says nothing.
    `AlertAnnouncer` is the live region that fixes that. Render it once, anywhere.

    It deliberately announces **only** a transition into `Alert`, not every value. A
    driver polling once a second would otherwise talk over itself continuously, and a
    temperature changing is not a status message while an instrument faulting is. A UI
    that leaves it out is silent for a blind operator, which is the failure mode with no
    workaround: there is nothing to click and nothing to re-read.

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
