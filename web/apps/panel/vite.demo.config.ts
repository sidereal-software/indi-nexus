import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The documentation site's live demo: the stock panel driven by an in-browser
// simulated dome driver (see demo/dome-sim.ts). Built into docs/demo/, which
// MkDocs copies verbatim; relative base so it serves from any sub-path.
export default defineConfig({
  root: "demo",
  base: "./",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../../../../docs/demo-app",
    emptyOutDir: true,
  },
});
