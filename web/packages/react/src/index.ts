/**
 * `@indi-nexus/react` - React hooks and shadcn/ui-based components for building
 * INDINexus frontends.
 *
 * Three layers, all themed with the INDINexus shadcn theme:
 *
 * - {@link IndiProvider} + hooks ({@link useProperty}, {@link useDevice}, ...) to
 *   read and watch live INDI state;
 * - INDI-aware components ({@link PropertyVectorCard}, {@link DevicePanel},
 *   {@link StateBadge}, {@link ConnectionStatus}, {@link MessageLog});
 * - the underlying shadcn/ui primitives (Button, Card, Sidebar, ...).
 *
 * The whole `@indi-nexus/client` surface is re-exported too, so applications can
 * pull types, enums, and the client from this one package. Import the theme once
 * with `import "@indi-nexus/react/styles.css"`.
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
