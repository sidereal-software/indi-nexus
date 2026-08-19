/** Tests for the three-scheme theme hook: class pairing, cycling, persistence. */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useTheme } from "./use-theme";

beforeEach(() => {
  document.documentElement.classList.remove("dark", "night");
  localStorage.clear();
});
afterEach(cleanup);

describe("useTheme", () => {
  it("starts light when <html> carries neither class", () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("starts dark when <html> already has the dark class", () => {
    document.documentElement.classList.add("dark");
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("dark");
  });

  it("reads night from the night class, not from dark alone", () => {
    document.documentElement.classList.add("dark", "night");
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("night");
  });

  it("cycles light -> dark -> night -> light, persisting each", () => {
    const { result } = renderHook(() => useTheme());
    const classes = () => document.documentElement.classList;

    act(() => result.current.cycle());
    expect(result.current.theme).toBe("dark");
    expect(classes().contains("dark")).toBe(true);
    expect(classes().contains("night")).toBe(false);
    expect(localStorage.getItem("indi-theme")).toBe("dark");

    act(() => result.current.cycle());
    expect(result.current.theme).toBe("night");
    expect(localStorage.getItem("indi-theme")).toBe("night");

    act(() => result.current.cycle());
    expect(result.current.theme).toBe("light");
    expect(classes().contains("dark")).toBe(false);
    expect(classes().contains("night")).toBe(false);
    expect(localStorage.getItem("indi-theme")).toBe("light");
  });

  it("keeps `dark` on while night is on", () => {
    // Load bearing rather than incidental: the theme's `dark:` variant is
    // `&:is(.dark *)`, so a bare `.night` would silently drop every `dark:`
    // utility the shadcn primitives ship - the Input's fill, the Switch's
    // track, the destructive ring - while the tokens still looked right.
    const { result } = renderHook(() => useTheme());
    act(() => result.current.cycle());
    act(() => result.current.cycle());

    expect(result.current.theme).toBe("night");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.classList.contains("night")).toBe(true);
  });
});
