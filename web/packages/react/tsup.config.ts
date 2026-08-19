import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts", "src/testing/index.ts"],
  format: ["esm"],
  target: "es2022",
  dts: true,
  clean: true,
  sourcemap: true,
  treeshake: true,
  // React, react-dom, @indikit/client, and the shadcn runtime deps are all
  // declared as (peer)dependencies, so tsup externalises them automatically.
  // Keep the JSX runtime external too so React is never bundled in.
  external: ["react", "react-dom", "react/jsx-runtime"],
});
