/**
 * The three schemes, toggling classes on `<html>` and persisting the choice.
 *
 * The classes on `<html>` are the only state there is - `index.html` sets them
 * from `localStorage` before first paint, so they are already correct when React
 * mounts. The hook therefore reads them rather than shadowing them in
 * `useState`: a copy would be one per mount, and a page with **two** controls on
 * it (the demo shows the stock panel and the wallboard at once, both mounted)
 * would leave the one nobody pressed showing the wrong icon and doing nothing
 * when pressed.
 *
 * `night` carries `dark` as well, and that pairing is load bearing. The theme's
 * `dark:` variant is `&:is(.dark *)`, so every `dark:` utility the shadcn
 * primitives ship would stop resolving under a bare `.night` - the Input's fill,
 * the Switch's track, the destructive ring. `.night` exists only to move token
 * values on top of `.dark`, which is also why it is written after it in
 * `theme.css`: same specificity, so source order decides.
 */

import { useCallback, useSyncExternalStore } from "react";

/** The three schemes: an absorption spectrum, an emission one, and a capped one. */
export type Theme = "light" | "dark" | "night";

/**
 * What each scheme advances to.
 *
 * A record rather than an array walked by index: `noUncheckedIndexedAccess`
 * makes every index read `Theme | undefined`, and a cycle that can produce
 * `undefined` is a cycle with a fourth state nobody wrote a scheme for.
 */
const NEXT: Record<Theme, Theme> = { light: "dark", dark: "night", night: "light" };

/** Everything currently mounted that reads the theme. */
const listeners = new Set<() => void>();

/** The theme as `<html>` currently has it. */
function snapshot(): Theme {
  const c = document.documentElement.classList;
  if (c.contains("night")) return "night";
  return c.contains("dark") ? "dark" : "light";
}

/** Register a consumer for the next change. */
function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Put a scheme on `<html>`.
 *
 * Exported so the pre-paint script and the hook cannot drift apart on what
 * "night" means in class terms.
 *
 * @param theme - The scheme to apply.
 */
export function applyTheme(theme: Theme): void {
  const c = document.documentElement.classList;
  c.toggle("dark", theme !== "light");
  c.toggle("night", theme === "night");
}

/** Read, apply, and persist the scheme; `cycle` advances light -> dark -> night. */
export function useTheme(): { theme: Theme; cycle: () => void } {
  const theme = useSyncExternalStore(subscribe, snapshot);

  const cycle = useCallback(() => {
    const next = NEXT[snapshot()];
    applyTheme(next);
    try {
      localStorage.setItem("indi-theme", next);
    } catch {
      // Ignore storage errors (private mode, etc.).
    }
    for (const listener of listeners) listener();
  }, []);

  return { theme, cycle };
}
