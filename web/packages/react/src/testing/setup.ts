/** Vitest setup: jest-dom matchers plus stubs for browser APIs jsdom lacks. */
import "@testing-library/jest-dom/vitest";

// Radix ScrollArea (used by MessageLog) observes element sizes; jsdom has no
// ResizeObserver, so install an inert stand-in.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

// The sidebar's mobile breakpoint hook (reached through DeviceConfigDialog's
// default trigger) needs matchMedia; jsdom has none.
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
