/**
 * Entry for the documentation site's weather demo.
 *
 * Two views of one device, sharing a single client: the custom `SkyReport`
 * screen from the tutorial, and the stock `DevicePanel` that INDINexus ships.
 * Behind both is {@link WeatherSimSocket}, the Open-Meteo driver running in the
 * browser - so the whole page works with no server.
 */

import { IndiClient } from "@indi-nexus/client";
import { IndiProvider, ToggleGroup, ToggleGroupItem, TooltipProvider } from "@indi-nexus/react";
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import App from "../src/App";
import "../src/index.css";
import { SkyReport } from "./sky-report";
import { fetchOpenMeteo, WeatherSimSocket } from "./weather-sim";

/** Where the readings came from, once a fetch has been attempted. */
type Source = "unknown" | "live" | "recorded";

/**
 * The page: the real panel and the custom screen, switchable.
 *
 * The stock view is the actual `App` that ships in the wheel - the same
 * sidebar, theme toggle and message sheet an operator sees - not a `DevicePanel`
 * in a bare page, so what the demo shows is what you get.
 */
function WeatherDemo() {
  const [view, setView] = useState<"panel" | "custom">("panel");
  const [source, setSource] = useState<Source>("unknown");

  // Built once. The socket is constructed lazily *inside* the factory: the
  // simulator starts delivering the moment it exists, so it must not exist
  // until the client has attached its handlers.
  const [client] = useState(
    () =>
      new IndiClient({
        url: "ws://demo.invalid/ws",
        webSocketFactory: () =>
          new WeatherSimSocket((lat, lon) =>
            fetchOpenMeteo(lat, lon, (fromNetwork) => setSource(fromNetwork ? "live" : "recorded")),
          ),
      }),
  );

  return (
    <>
      {/* One floating control over whichever view is showing, so the panel
          below is pixel-for-pixel the shipped app. */}
      <div className="fixed top-3 right-3 z-50 flex items-center gap-2 rounded-lg border bg-background/95 px-2 py-1.5 shadow-sm backdrop-blur">
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
          {/* Short labels on a phone: the switcher floats over the panel's own
              header, and the full ones cover its device title. */}
          <ToggleGroupItem value="panel">
            <span className="sm:hidden">Panel</span>
            <span className="hidden sm:inline">Stock panel</span>
          </ToggleGroupItem>
          <ToggleGroupItem value="custom">
            <span className="sm:hidden">Custom</span>
            <span className="hidden sm:inline">Custom UI</span>
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      {/* Both views stay mounted and the inactive one is hidden. Unmounting
          would take its IndiProvider with it, and the provider closes the
          client on unmount - which would drop the simulated driver and reset
          it every time the reader flipped the switch. `start()` is guarded, so
          two providers sharing one client open exactly one socket. */}
      <div hidden={view !== "panel"}>
        <App client={client} />
      </div>
      <div hidden={view !== "custom"}>
        <IndiProvider client={client}>
          <TooltipProvider delayDuration={150}>
            <SkyReport />
          </TooltipProvider>
        </IndiProvider>
      </div>
    </>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("missing #root element");

createRoot(container).render(
  <StrictMode>
    <WeatherDemo />
  </StrictMode>,
);
