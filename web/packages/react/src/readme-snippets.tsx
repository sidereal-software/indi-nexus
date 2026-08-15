/**
 * The code samples from this package's README, kept compiling.
 *
 * `README.md` is the npmjs.com front page for `@indi-nexus/react`, and it shipped a
 * `useConnection()` rendered straight into JSX - the hook returns the
 * `{ transport, upstream }` object, so that throws "Objects are not valid as a React
 * child" the moment anybody pastes it. `pnpm typecheck` covers the front page now, the
 * same way `doc-snippets.tsx` covers `docs/guides/frontend.md`. **Change a snippet in
 * the README and change it here too**, or the front page silently rots.
 *
 * The bodies below are the README's fences verbatim, bar two things the compiler
 * cannot take: the import reaches for `./index`, because a package cannot resolve its
 * own published name from inside its own `src/` without a built `dist/`, and the
 * README's `import "@indi-nexus/react/styles.css"` is dropped, because nothing in this
 * program declares CSS modules. Neither line is the kind that breaks.
 */
import { DevicePanel, IndiProvider, useConnection, useNumber, useSwitch } from "./index";

export const App = () => (
  <IndiProvider url="ws://localhost:8000/ws">
    <DevicePanel device="Mount" />
  </IndiProvider>
);

export const Readout = () => {
  const { transport } = useConnection(); // also `upstream`: the bridge's own link
  const ra = useNumber("Mount", "EQUATORIAL_EOD_COORD", "RA");
  const tracking = useSwitch("Mount", "TELESCOPE_TRACK_STATE", "TRACK_ON");

  return (
    <p>
      {transport ? "connected" : "offline"}: RA {ra ?? "-"} {tracking ? "(tracking)" : ""}
    </p>
  );
};
