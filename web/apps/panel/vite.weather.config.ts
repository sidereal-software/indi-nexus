import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The documentation site's weather demo: the tutorial's custom UI and the stock
// panel, both driven by an in-browser Open-Meteo driver (see demo/weather-sim.ts).
// Built into docs/weather-demo/, which MkDocs copies verbatim; relative base so
// it serves from any sub-path.
export default defineConfig({
  root: "demo",
  base: "./",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../../../../docs/weather-demo",
    emptyOutDir: true,
    rollupOptions: { input: "demo/weather.html" },
  },
});
