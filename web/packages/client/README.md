# @indi-nexus/client

Framework-agnostic TypeScript client and typed property store for the
[INDINexus](https://indi-nexus.sidereal.software/) web bridge.

Observatory instruments (telescopes, domes, cameras, focusers, weather stations) speak
[INDI](https://docs.indilib.org/protocol/). The INDINexus bridge puts that traffic behind a
WebSocket as typed JSON, and this package is the browser side of it: it handles the socket,
reconnects on its own, and mirrors everything the bridge reports into a property cache you
can read and subscribe to.

No framework or UI dependency. If you are building with React, use
[`@indi-nexus/react`](https://www.npmjs.com/package/@indi-nexus/react), which wraps this in
hooks and components and re-exports the whole surface.

## Install

```bash
npm install @indi-nexus/client
```

## Usage

```ts
import { IndiClient, IPState } from "@indi-nexus/client";

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
transitions through `onConnection`. `connectionState` carries three fields: `transport`,
the browser-to-bridge socket; `upstream`, the bridge's own link to `indiserver`; and
`protocol`, the contract version the bridge announced in its `hello` frame (`null` until
one arrives). Compare it with the exported `CLIENT_PROTOCOL_VERSION` if you want to know
whether the bridge and this build agree; a mismatch is never fatal, and the client only
logs one line.

## Documentation

Full guides and API reference: <https://indi-nexus.sidereal.software/>. The
[frontend guide](https://indi-nexus.sidereal.software/guides/frontend/) covers this package
and the React one together.

## Changelog

[CHANGELOG.md](CHANGELOG.md) in this directory records what changed in each
release of this package. All three INDINexus packages ship at the same version,
and the [releases page](https://github.com/sidereal-software/indi-nexus/releases)
carries the notes for every one of them together.

## License

MIT. See [LICENSE](LICENSE).
