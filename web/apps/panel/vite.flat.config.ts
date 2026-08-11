import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The documentation site's flat-panel demo: the stock panel driven by an in-browser
// port of examples/flat_panel.py (see demo/flat-panel-sim.ts), which is the driver the
// "Writing a driver" guide builds. Built into docs/flat-demo/, which MkDocs copies
// verbatim; relative base so it serves from any sub-path.
export default defineConfig({
  root: "demo",
  base: "./",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../../../../docs/flat-demo",
    emptyOutDir: true,
    rollupOptions: { input: "demo/flat.html" },
  },
});
