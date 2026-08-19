/**
 * Light/dark theme, toggling the `dark` class on `<html>` and persisting it.
 *
 * The class on `<html>` is the only state there is - `index.html` sets it from
 * `localStorage` before first paint, so it is already correct when React mounts.
 * The hook therefore reads it rather than shadowing it in `useState`: a copy
 * would be one per mount, and a page with **two** toggles on it (the demo shows
 * the stock panel and the wallboard at once, both mounted) would leave the one
 * nobody pressed showing the wrong icon and doing nothing when pressed.
 */

import { useCallback, useSyncExternalStore } from "react";

/** The two schemes the theme has. */
type Theme = "light" | "dark";

/** Everything currently mounted that reads the theme. */
const listeners = new Set<() => void>();

/** The theme as `<html>` currently has it. */
function snapshot(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

/** Register a consumer for the next toggle. */
function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Read, apply, and persist the light/dark theme. */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const theme = useSyncExternalStore(subscribe, snapshot);

  const toggle = useCallback(() => {
    const next: Theme = snapshot() === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    try {
      localStorage.setItem("indi-theme", next);
    } catch {
      // Ignore storage errors (private mode, etc.).
    }
    for (const listener of listeners) listener();
  }, []);

  return { theme, toggle };
}
