/**
 * Entry for the documentation site's live demo build.
 *
 * The stock panel App, wired to an {@link DomeSimSocket} instead of a real
 * bridge WebSocket - the whole "observatory" runs in the browser.
 */

import { IndiClient } from "@indi-nexus/client";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "../src/App";
import "../src/index.css";
import { DomeSimSocket } from "./dome-sim";

const client = new IndiClient({
  url: "ws://demo.invalid/ws",
  webSocketFactory: () => new DomeSimSocket(),
});

const container = document.getElementById("root");
if (!container) throw new Error("missing #root element");

createRoot(container).render(
  <StrictMode>
    <App client={client} />
  </StrictMode>,
);
