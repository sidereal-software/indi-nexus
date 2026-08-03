/**
 * Entry for the documentation site's weather demo.
 *
 * Two views of one device, sharing a single client: the custom `SkyReport`
 * screen from the tutorial, and the stock `DevicePanel` that INDINexus ships.
 * Behind both is {@link WeatherSimSocket}, the Open-Meteo driver running in the
 * browser - so the whole page works with no server.
 */

import { IndiClient } from "@indi-nexus/client";
import { ConnectionStatus, DevicePanel, IndiProvider, MessageLog } from "@indi-nexus/react";
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import "../src/index.css";
import { SkyReport } from "./sky-report";
import { fetchOpenMeteo, WeatherSimSocket } from "./weather-sim";

/** Where the readings came from, once a fetch has been attempted. */
type Source = "unknown" | "live" | "recorded";

/** The page: a view switcher, the two views, and the driver's log. */
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
    <IndiProvider client={client}>
      <div className="mx-auto flex min-h-dvh max-w-3xl flex-col gap-4 p-4">
        <header className="space-y-2">
          <h1 className="font-semibold text-xl">Open-Meteo, live in your browser</h1>
          <p className="text-muted-foreground text-sm">
            The driver from <code>examples/openmeteo_device.py</code>, ported to TypeScript and
            running here with no server at all. Press <strong>Connect</strong> to fetch, then switch
            between the two views - same device, same data, two ways of showing it.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setView("panel")}
              className={`rounded-md border px-3 py-1.5 text-sm ${
                view === "panel" ? "bg-primary text-primary-foreground" : "bg-background"
              }`}
            >
              Stock panel
            </button>
            <button
              type="button"
              onClick={() => setView("custom")}
              className={`rounded-md border px-3 py-1.5 text-sm ${
                view === "custom" ? "bg-primary text-primary-foreground" : "bg-background"
              }`}
            >
              Custom UI
            </button>
            <ConnectionStatus />
            {source !== "unknown" && (
              <span className="text-muted-foreground text-xs">
                {source === "live"
                  ? "live from api.open-meteo.com"
                  : "recorded response - the live API could not be reached from here"}
              </span>
            )}
          </div>
        </header>

        <main className="rounded-lg border bg-card p-2">
          {view === "custom" ? <SkyReport /> : <DevicePanel device="Open-Meteo" />}
        </main>

        <MessageLog />
      </div>
    </IndiProvider>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("missing #root element");

createRoot(container).render(
  <StrictMode>
    <WeatherDemo />
  </StrictMode>,
);
