/**
 * Smoke tests for the assembled panel app.
 *
 * `App` hardwires its own `IndiProvider` (which derives the bridge URL from
 * `location` and uses the global `WebSocket`), so these tests stub the global
 * `WebSocket` with a controllable fake and drive the whole UI - sidebar, header,
 * and device panel - through real JSON frames.
 */

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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
  localStorage.clear();
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

  // A driver that defines its properties on connect retracts them all on
  // disconnect, which used to erase the device from the panel as though the
  // driver had gone. It has not: it is still there with nothing to show, and
  // the operator needs to be able to tell those two apart.
  it("keeps a device that has retracted its last property, showing it as empty", () => {
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
    expect(screen.getByText("Exposure")).toBeInTheDocument();

    act(() =>
      socket.receive(
        JSON.stringify({ tag: "delProperty", device: "CCD Simulator", name: "EXPOSURE" }),
      ),
    );

    expect(screen.getByRole("button", { name: /CCD Simulator/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("CCD Simulator");
    expect(screen.getByText(/No properties for CCD Simulator right now/)).toBeInTheDocument();
    expect(screen.queryByText("No devices connected.")).not.toBeInTheDocument();
    expect(screen.queryByText("Exposure")).not.toBeInTheDocument();
  });
});

describe("messages panel", () => {
  it("is docked open by default and streams the INDI log", () => {
    const { socket } = renderApp();
    expect(screen.getByRole("complementary", { name: "Messages" })).toBeInTheDocument();
    expect(screen.getByText("No messages yet.")).toBeInTheDocument();

    act(() =>
      socket.receive(
        JSON.stringify({ tag: "message", device: "Dome", message: "[INFO] Dome parked." }),
      ),
    );
    expect(screen.getByText("[INFO] Dome parked.")).toBeInTheDocument();
  });

  it("collapses and reopens from its own title bar, remembering the choice", () => {
    renderApp();
    const trigger = screen.getByRole("button", { name: /messages/i });
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("No messages yet.")).not.toBeInTheDocument();
    expect(localStorage.getItem("indi-messages")).toBe("closed");

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("No messages yet.")).toBeInTheDocument();
    expect(localStorage.getItem("indi-messages")).toBe("open");
  });

  it("starts collapsed when the last session closed it, title bar still shown", () => {
    localStorage.setItem("indi-messages", "closed");
    renderApp();
    // The title bar (the disclosure) is always visible; only the log is hidden.
    expect(screen.getByRole("complementary", { name: "Messages" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /messages/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByText("No messages yet.")).not.toBeInTheDocument();
  });

  it("counts unseen messages on the collapsed bar and clears the badge on open", () => {
    localStorage.setItem("indi-messages", "closed");
    const { socket } = renderApp();
    const bar = screen.getByRole("complementary", { name: "Messages" });
    expect(within(bar).queryByText("1")).not.toBeInTheDocument();

    act(() =>
      socket.receive(
        JSON.stringify({ tag: "message", device: "Dome", message: "[INFO] Dome parked." }),
      ),
    );
    act(() =>
      socket.receive(
        JSON.stringify({ tag: "message", device: "Dome", message: "[INFO] Shutter open." }),
      ),
    );
    expect(within(bar).getByText("2")).toBeInTheDocument();

    // Opening the log marks everything seen; the badge disappears and stays
    // away while messages stream in with the log in view.
    fireEvent.click(screen.getByRole("button", { name: /messages/i }));
    expect(within(bar).queryByText("2")).not.toBeInTheDocument();
    act(() =>
      socket.receive(
        JSON.stringify({ tag: "message", device: "Dome", message: "[INFO] Dome slewing." }),
      ),
    );
    expect(within(bar).queryByText("1")).not.toBeInTheDocument();
  });
});

describe("debug info", () => {
  /** Prime the app with one defined device property. */
  function primeExposure(socket: FakeWebSocket) {
    act(() =>
      socket.receive(
        JSON.stringify({
          tag: "def",
          vector: {
            kind: "number",
            device: "CCD Simulator",
            name: "EXPOSURE",
            label: "Exposure",
            state: "Idle",
            perm: "rw",
            elements: [{ kind: "number", name: "secs", value: 1.5 }],
          },
        }),
      ),
    );
  }

  it("hides raw INDI names by default and reveals them via the toggle", () => {
    const { socket } = renderApp();
    primeExposure(socket);
    expect(screen.queryByText("EXPOSURE · rw")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("switch", { name: "Debug info" }));
    expect(screen.getByText("EXPOSURE · rw")).toBeInTheDocument();
    expect(localStorage.getItem("indi-debug")).toBe("on");

    fireEvent.click(screen.getByRole("switch", { name: "Debug info" }));
    expect(screen.queryByText("EXPOSURE · rw")).not.toBeInTheDocument();
  });

  it("starts with debug info on when the last session enabled it", () => {
    localStorage.setItem("indi-debug", "on");
    const { socket } = renderApp();
    primeExposure(socket);
    expect(screen.getByText("EXPOSURE · rw")).toBeInTheDocument();
  });
});
