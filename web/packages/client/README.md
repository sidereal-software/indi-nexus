# @indikit/client

Framework-agnostic TypeScript client and typed property store for the
[INDIkit](https://indikit.sidereal.software/) web bridge.

Observatory instruments (telescopes, domes, cameras, focusers, weather stations) speak
[INDI](https://docs.indilib.org/protocol/). The INDIkit bridge puts that traffic behind a
WebSocket as typed JSON.

This package is the browser side of it. It handles the socket, reconnects on its own, and
mirrors everything the bridge reports into a property cache you can read and subscribe to.

No framework or UI dependency. If you are building with React, use
[`@indikit/react`](https://www.npmjs.com/package/@indikit/react), which wraps this in
hooks and components and re-exports the whole surface.

## Install

```bash
npm install @indikit/client
```

## Usage

```ts
import { IndiClient, IPState } from "@indikit/client";

const client = new IndiClient({ url: "ws://localhost:8000/ws" });
client.connect();

// React to any change on one property. `vector` is null on a del.
client.subscribe((event) => console.log(event.device, event.name, event.vector?.state), {
  device: "Mount",
  name: "EQUATORIAL_EOD_COORD",
});

// Wait until a property shows up and is settled, then command the instrument.
await client.waitFor("Mount", "CONNECTION", (v) => v.state === IPState.Ok);
client.setNumber("Mount", "EQUATORIAL_EOD_COORD", { RA: 5.59, DEC: -5.39 });
```

Reading cached state directly works too, which is what the React hooks are built on:

```ts
client.devices(); // known device names
client.device("Mount"); // one device's properties
client.get("Mount", "EQUATORIAL_EOD_COORD"); // a single vector, or undefined
```

The connection reconnects by itself, replays any BLOB policies you set, and reports
transitions through `onConnection`.

`connectionState` carries three fields:

- `transport` - the browser-to-bridge socket.
- `upstream` - the bridge's own link to `indiserver`.
- `protocol` - the contract version the bridge announced in its `hello` frame, `null`
  until one arrives.

Compare `protocol` with the exported `CLIENT_PROTOCOL_VERSION` to know whether the bridge
and this build agree. A mismatch is never fatal: the client logs one line and carries on.

## Knowing which changes you asked for

`onWrite` is the outbound counterpart to `subscribe`. It fires with the device and property
name of every `new` frame `send` puts on the wire, whether from the four `set*` helpers or
from a frame you built yourself, and returns an unsubscribe function like every other
listener here:

```ts
const stop = client.onWrite((device, name) => console.log("sent", device, name));
client.setSwitch("Dome", "DOME_SHUTTER", { SHUTTER_OPEN: "On" });
stop();
```

Nothing else can make that distinction. A vector going `Busy` and then `Ok` looks the same
on the wire whether this browser asked for it or another client did, so it has to be
recorded on the way out. That is what lets a UI treat an operator's own command as feedback
and the rest of the stream as telemetry.

`onWrite` fires on the send rather than on an acknowledgement, because the socket buffers
while the connection is down and the operator pressed the button either way. The callback
type is exported as `WriteCallback`.

## Documentation

Full guides and API reference: <https://indikit.sidereal.software/>. The
[frontend guide](https://indikit.sidereal.software/guides/frontend/) covers this package
and the React one together.

## Changelog

[CHANGELOG.md](CHANGELOG.md) in this directory records what changed in each
release of this package. All three INDIkit packages ship at the same version,
and the [releases page](https://github.com/sidereal-software/indikit/releases)
carries the notes for every one of them together.

## License

MIT. See [LICENSE](LICENSE).
