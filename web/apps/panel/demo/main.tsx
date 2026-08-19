/**
 * Entry for the documentation site's live demo.
 *
 * Two views of one observatory, sharing a single client: the stock panel that
 * INDINexus ships, and the custom {@link ObservatoryBoard} from the tutorial.
 * Behind both is {@link ObservatorySimSocket} - a simulated dome and the
 * Open-Meteo driver, multiplexed onto one fake bridge - so the whole page works
 * with no server.
 */

import { IndiClient } from "@indi-nexus/client";
import { IndiProvider, ToggleGroup, ToggleGroupItem } from "@indi-nexus/react";
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import App from "../src/App";
import "../src/index.css";
import { ObservatoryBoard } from "./observatory-board";
import { ObservatorySimSocket } from "./observatory-sim";
import { fetchOpenMeteo } from "./weather-sim";

/** Where the weather readings came from, once a fetch has been attempted. */
type Source = "unknown" | "live" | "recorded";

/**
 * The page: the real panel and the wallboard, switchable.
 *
 * The stock view is the actual `App` that ships in the wheel - the same sidebar,
 * theme toggle and message sheet an operator sees - not a `DevicePanel` in a
 * bare page, so what the demo shows is what you get. It is also the default
 * view, because both simulated drivers start disconnected the way real ones do
 * and the panel is where a visitor presses Connect.
 */
function ObservatoryDemo() {
  const [view, setView] = useState<"panel" | "custom">("panel");
  const [source, setSource] = useState<Source>("unknown");

  // Built once. The socket is constructed lazily *inside* the factory: the
  // simulators start delivering the moment they exist, so they must not exist
  // until the client has attached its handlers.
  const [client] = useState(
    () =>
      new IndiClient({
        url: "ws://demo.invalid/ws",
        webSocketFactory: () =>
          new ObservatorySimSocket((lat, lon) =>
            fetchOpenMeteo(lat, lon, (fromNetwork) => setSource(fromNetwork ? "live" : "recorded")),
          ),
      }),
  );

  return (
    <>
      {/*
       * One control over whichever view is showing, so the panel below is
       * pixel-for-pixel the shipped app - but `position: fixed` is only
       * harmless where nothing scrolls under it.
       *
       * The stock panel pins itself to the viewport and scrolls inside its own
       * region, so a floating pill sits on the empty right-hand end of its
       * header bar and stays there. The wallboard above `lg` is one locked
       * screen, same story. Below `lg` the wallboard is a scrolling column, and
       * there a fixed pill parks itself on whatever passes underneath: at
       * 390x844 that is the dome plan, which is a reading. So on that one view,
       * at that one size, the switcher takes a row of its own above the board
       * and covers nothing - demo chrome should lose the argument with an
       * instrument, not win it.
       */}
      <div
        className={`flex items-center justify-end gap-2 bg-background/95 backdrop-blur ${
          view === "custom"
            ? "border-b px-4 py-2 lg:fixed lg:top-3 lg:right-3 lg:z-50 lg:rounded-lg lg:border lg:px-2 lg:py-1.5 lg:shadow-sm"
            : "fixed top-3 right-3 z-50 rounded-lg border px-2 py-1.5 shadow-sm"
        }`}
      >
        {source !== "unknown" && (
          <span className="hidden text-muted-foreground text-xs sm:inline">
            {source === "live" ? "live data" : "recorded data"}
          </span>
        )}
        <ToggleGroup
          type="single"
          size="sm"
          variant="outline"
          value={view}
          onValueChange={(next) => next && setView(next as "panel" | "custom")}
        >
          {/* Short labels on a phone: over the panel the switcher still floats,
              on that view's own header, and the full ones cover its device
              title. They stay short in the board's row too - a control that
              renames itself when it moves is a second thing to recognise. */}
          <ToggleGroupItem value="panel">
            <span className="sm:hidden">Panel</span>
            <span className="hidden sm:inline">Stock panel</span>
          </ToggleGroupItem>
          <ToggleGroupItem value="custom">
            <span className="sm:hidden">Board</span>
            <span className="hidden sm:inline">Wallboard</span>
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      {/* Both views stay mounted and the inactive one is hidden. Unmounting
          would take its IndiProvider with it, and the provider closes the
          client on unmount - which would drop the simulated drivers and reset
          them every time the reader flipped the switch. `start()` is guarded, so
          two providers sharing one client open exactly one socket. */}
      <div hidden={view !== "panel"}>
        <App client={client} />
      </div>
      <div hidden={view !== "custom"}>
        <IndiProvider client={client}>
          <ObservatoryBoard />
        </IndiProvider>
      </div>
    </>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("missing #root element");

createRoot(container).render(
  <StrictMode>
    <ObservatoryDemo />
  </StrictMode>,
);
