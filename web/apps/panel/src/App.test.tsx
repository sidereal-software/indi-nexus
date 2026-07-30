/**
 * Smoke tests for the assembled panel app.
 *
 * `App` hardwires its own `IndiProvider` (which derives the bridge URL from
 * `location` and uses the global `WebSocket`), so these tests stub the global
 * `WebSocket` with a controllable fake and drive the whole UI - sidebar, header,
 * and device panel - through real JSON frames.
 */

import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

/** A controllable WebSocket stand-in; instances register themselves. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  readyState = 0;
  onopen: ((event: unknown) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  readonly sent: string[] = [];

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.readyState = 3;
    this.onclose?.({});
  }

  /** Transition to OPEN and fire `onopen`. */
  open(): void {
    this.readyState = 1;
    this.onopen?.({});
  }

  /** Deliver one inbound text frame. */
  receive(data: string): void {
    this.onmessage?.({ data });
  }
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  FakeWebSocket.instances = [];
});

/** Render the app, open its socket, and return the socket for driving frames. */
function renderApp() {
  vi.stubGlobal("WebSocket", FakeWebSocket);
  const result = render(<App />);
  const socket = FakeWebSocket.instances[0];
  if (!socket) throw new Error("the app did not open a WebSocket");
  act(() => socket.open());
  return { socket, ...result };
}

describe("App", () => {
  it("connects to the bridge /ws and shows the empty state", () => {
    const { socket } = renderApp();
    expect(socket.url).toMatch(/\/ws$/);
    expect(screen.getByText("No devices connected.")).toBeInTheDocument();
    expect(screen.getByText(/Waiting for devices/)).toBeInTheDocument();
  });

  it("lists an arriving device, auto-selects it, and renders its properties", () => {
    const { socket } = renderApp();
    act(() =>
      socket.receive(
        JSON.stringify({
          tag: "def",
          vector: {
            kind: "number",
            device: "CCD Simulator",
            name: "EXPOSURE",
            label: "Exposure",
            group: "Main",
            state: "Idle",
            perm: "rw",
            elements: [{ kind: "number", name: "secs", value: 1.5 }],
          },
        }),
      ),
    );

    // Sidebar entry and auto-selected header title.
    expect(screen.getByRole("button", { name: /CCD Simulator/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("CCD Simulator");

    // The device panel shows the property card with its editable element.
    expect(screen.getByText("Exposure")).toBeInTheDocument();
    expect(screen.getByLabelText("secs")).toHaveValue(1.5);
  });
});
