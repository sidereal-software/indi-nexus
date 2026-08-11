/**
 * Entry for the documentation site's flat-panel demo.
 *
 * The stock panel App, wired to a {@link FlatPanelSimSocket} instead of a real
 * bridge WebSocket - so the driver taught in the "Writing a driver" guide runs in
 * the reader's browser, with no install and no server.
 */

import { IndiClient } from "@indi-nexus/client";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "../src/App";
import "../src/index.css";
import { FlatPanelSimSocket } from "./flat-panel-sim";

// The socket is constructed lazily inside the factory: the simulator starts
// delivering the moment it exists, so it must not exist until the client has
// attached its handlers.
const client = new IndiClient({
  url: "ws://demo.invalid/ws",
  webSocketFactory: () => new FlatPanelSimSocket(),
});

const container = document.getElementById("root");
if (!container) throw new Error("missing #root element");

createRoot(container).render(
  <StrictMode>
    <App client={client} />
  </StrictMode>,
);
