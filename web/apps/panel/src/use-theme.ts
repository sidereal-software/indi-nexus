import { useCallback, useEffect, useState } from "react";

/** Light/dark theme, toggling the `.dark` class on <html> and persisting it. */
type Theme = "light" | "dark";

/** Read, apply, and persist the light/dark theme. */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.classList.contains("dark") ? "dark" : "light",
  );

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem("indi-theme", theme);
    } catch {
      // Ignore storage errors (private mode, etc.).
    }
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  }, []);

  return { theme, toggle };
}
