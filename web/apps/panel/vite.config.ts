import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, proxy the bridge's HTTP + WebSocket endpoints to a locally running
// `indi-nexus serve` (or `examples/demo_bridge.py`) on :8000. In production the
// panel is served by that same FastAPI app, so these paths are same-origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/ws": { target: "ws://localhost:8000", ws: true },
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  build: {
    // Emit into the Python package so FastAPI serves the built panel at `/`.
    outDir: "../../../src/indi_nexus/web/static/panel",
    emptyOutDir: true,
  },
});
