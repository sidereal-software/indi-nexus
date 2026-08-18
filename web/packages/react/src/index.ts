/**
 * `@indi-nexus/react` - React hooks and shadcn/ui-based components for building
 * INDINexus frontends.
 *
 * Three layers, all themed with the INDINexus shadcn theme:
 *
 * - {@link IndiProvider} + hooks ({@link useProperty}, {@link useDevice}, ...) to
 *   read and watch live INDI state;
 * - INDI-aware components ({@link PropertyVectorCard}, {@link VectorControl},
 *   {@link DevicePanel}, {@link DeviceConfigDialog}, {@link StateBadge},
 *   {@link ConnectionStatus}, {@link MessageLog}, {@link AlertAnnouncer});
 * - the underlying shadcn/ui primitives (Button, Card, Sidebar, ...).
 *
 * The whole `@indi-nexus/client` surface is re-exported too, so applications can
 * pull types, enums, and the client from this one package. Import the theme once
 * with `import "@indi-nexus/react/styles.css"`.
 *
 * A separate `@indi-nexus/react/testing` entry point (see `src/testing/`) renders
 * components against a fake socket; it is the one part of the package that needs
 * `@testing-library/react`, which is an optional peer dependency for that reason.
 */

// Re-export the framework-agnostic client (types, enums, IndiClient, ...).
export * from "@indi-nexus/client";
// INDI-aware components.
export * from "./components";
// Provider + hooks.
export * from "./context";
// Display settings (debug-info toggle for the INDI-aware components).
export * from "./display-settings";
export * from "./hooks";
// Themed shadcn/ui primitives.
export * from "./primitives";
