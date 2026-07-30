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
