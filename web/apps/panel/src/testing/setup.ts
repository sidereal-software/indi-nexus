/** Vitest setup: jest-dom matchers plus stubs for browser APIs jsdom lacks. */
import "@testing-library/jest-dom/vitest";

// The sidebar's mobile breakpoint hook needs matchMedia; jsdom has none.
globalThis.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
})) as unknown as typeof matchMedia;

// Radix ScrollArea observes element sizes; jsdom has no ResizeObserver.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
