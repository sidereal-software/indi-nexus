/**
 * Display settings shared by the INDI-aware components.
 *
 * Components read these through context with clean defaults, so a plain tree
 * needs no provider: cards show human labels only. An app offering a "debug
 * info" toggle (raw INDI property names, permissions) wraps its tree in
 * {@link DisplaySettingsProvider} and flips `showDebug`.
 */

import { createContext, type ReactNode, useContext, useMemo } from "react";

/** Presentation preferences consumed by the INDI-aware components. */
export interface DisplaySettings {
  /** Show technical INDI detail (raw property names, permissions) on cards. */
  showDebug: boolean;
}

const DisplaySettingsContext = createContext<DisplaySettings>({ showDebug: false });

/** Props for {@link DisplaySettingsProvider}. */
export interface DisplaySettingsProviderProps {
  /** Show technical INDI detail on cards; off by default. */
  showDebug?: boolean;
  children: ReactNode;
}

/**
 * Provide display settings to descendant INDI-aware components.
 *
 * @param props - The settings plus children.
 * @returns The context provider element.
 */
export function DisplaySettingsProvider({
  showDebug = false,
  children,
}: DisplaySettingsProviderProps): ReactNode {
  const value = useMemo(() => ({ showDebug }), [showDebug]);
  return (
    <DisplaySettingsContext.Provider value={value}>{children}</DisplaySettingsContext.Provider>
  );
}

/**
 * Return the current display settings (defaults apply without a provider).
 *
 * @returns The active settings.
 */
export function useDisplaySettings(): DisplaySettings {
  return useContext(DisplaySettingsContext);
}
