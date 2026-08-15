/**
 * The code samples from this package's README, kept compiling.
 *
 * `README.md` is the npmjs.com front page for `@indi-nexus/client`, and it shipped
 * TypeScript that did not compile: `IPState.OK` (only the Python enum shouts; the TS
 * one is `IPState.Ok`) and an `event.vector.state` that ignored the `null` a `del`
 * carries. `pnpm typecheck` covers those now, the same way `doc-snippets.tsx` in
 * `@indi-nexus/react` covers `docs/guides/frontend.md`. **Change a snippet in the
 * README and change it here too**, or the front page silently rots.
 *
 * The bodies below are the README's fences verbatim. Only the import differs: a
 * package cannot resolve its own published name from inside its own `src/` without
 * a built `dist/`, so this reaches for `./index`.
 */
import { IndiClient, IPState } from "./index";

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

client.devices(); // known device names
client.device("Mount"); // one device's properties
client.get("Mount", "EQUATORIAL_EOD_COORD"); // a single vector, or undefined
