import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The documentation site's live demo: the stock panel and the custom wallboard,
// both driven by a simulated dome and a simulated weather station multiplexed
// onto one in-browser bridge (see demo/observatory-sim.ts). Built into
// docs/demo-app/, which MkDocs copies verbatim; relative base so it serves from
// any sub-path.
export default defineConfig({
  root: "demo",
  base: "./",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../../../../docs/demo-app",
    emptyOutDir: true,
  },
});
