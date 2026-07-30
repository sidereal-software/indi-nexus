/** Tests for the `useIsMobile` breakpoint hook against a stubbed matchMedia. */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useIsMobile } from "./use-mobile";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Stub `matchMedia` and return the list of registered change listeners. */
function stubMatchMedia(): (() => void)[] {
  const listeners: (() => void)[] = [];
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    addEventListener: (_type: string, listener: () => void) => listeners.push(listener),
    removeEventListener: () => {},
  }));
  return listeners;
}

describe("useIsMobile", () => {
  it("reports mobile below the 768px breakpoint", () => {
    stubMatchMedia();
    vi.stubGlobal("innerWidth", 500);
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(true);
  });

  it("updates when the media query fires after a resize", () => {
    const listeners = stubMatchMedia();
    vi.stubGlobal("innerWidth", 1024);
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);

    vi.stubGlobal("innerWidth", 500);
    act(() => {
      for (const listener of listeners) listener();
    });
    expect(result.current).toBe(true);
  });
});
