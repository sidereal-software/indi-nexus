/**
 * Smoke tests for the assembled panel app.
 *
 * `App` hardwires its own `IndiProvider` (which derives the bridge URL from
 * `location` and uses the global `WebSocket`), so these tests stub the global
 * `WebSocket` with a controllable fake and drive the whole UI - sidebar, header,
 * and device panel - through real JSON frames.
 */

import { CLIENT_PROTOCOL_VERSION } from "@indikit/client";
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

/**
 * Render the app, open its socket, and return the socket for driving frames.
 *
 * The `hello` goes out first because the bridge sends it first; without it the
 * client logs a "no hello frame" entry and every message-count assertion below
 * is one out.
 */
function renderApp() {
  vi.stubGlobal("WebSocket", FakeWebSocket);
  const result = render(<App />);
  const socket = FakeWebSocket.instances[0];
  if (!socket) throw new Error("the app did not open a WebSocket");
  act(() => socket.open());
  act(() =>
    socket.receive(
      JSON.stringify({ event: "hello", protocol: CLIENT_PROTOCOL_VERSION, server: "test" }),
    ),
  );
  return { socket, ...result };
}

describe("App", () => {
  it("connects to the bridge /ws and shows the empty state", () => {
    const { socket } = renderApp();
    expect(socket.url).toMatch(/\/ws$/);
    expect(screen.getByText("No devices connected.")).toBeInTheDocument();
    expect(screen.getByText(/Waiting for devices/)).toBeInTheDocument();
  });

  it("puts the device list in a landmark and mounts the Alert live region", () => {
    renderApp();

    // The sidebar is all divs, so without the nav the only means of moving
    // between devices sat outside every landmark and a landmark walk reached
    // the main region and the messages strip and nothing else.
    expect(screen.getByRole("navigation", { name: "Devices" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Messages" })).toBeInTheDocument();

    // Page-level, not per-device: a fault on the device that is not on screen is
    // the one worth hearing about.
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByRole("log", { name: "INDI messages" })).toBeInTheDocument();
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

describe("the device menu's markup", () => {
  /** Define one property on a device, so the sidebar has an entry to draw. */
  function defineProperty(socket: FakeWebSocket, device: string, name: string) {
    act(() =>
      socket.receive(
        JSON.stringify({
          tag: "def",
          vector: {
            kind: "number",
            device,
            name,
            label: name,
            state: "Idle",
            perm: "rw",
            elements: [{ kind: "number", name: "secs", value: 1.5 }],
          },
        }),
      ),
    );
  }

  /** libindi's universal configuration property, which the menu grows an entry for. */
  function defineConfigProcess(socket: FakeWebSocket, device: string) {
    act(() =>
      socket.receive(
        JSON.stringify({
          tag: "def",
          vector: {
            kind: "switch",
            device,
            name: "CONFIG_PROCESS",
            label: "Configuration",
            group: "Options",
            state: "Idle",
            perm: "rw",
            rule: "AtMostOne",
            elements: [
              { kind: "switch", name: "CONFIG_LOAD", value: "Off" },
              { kind: "switch", name: "CONFIG_SAVE", value: "Off" },
            ],
          },
        }),
      ),
    );
  }

  /**
   * The children of every list under `root` that a list may not legally have.
   *
   * This is axe's `list` rule written out: the only element children of a `<ul>`
   * are `<li>`, `<script>` and `<template>`. Kept as a sweep rather than a count
   * so it covers whatever the menu grows next.
   */
  function illegalListChildren(root: HTMLElement): string[] {
    const offenders: string[] = [];
    for (const list of root.querySelectorAll("ul, ol")) {
      for (const child of list.children) {
        if (!["LI", "SCRIPT", "TEMPLATE"].includes(child.tagName)) {
          offenders.push(`${child.tagName} in ${list.tagName}`);
        }
      }
    }
    return offenders;
  }

  /** The device list's landmark. */
  function nav(): HTMLElement {
    return screen.getByRole("navigation", { name: "Devices" });
  }

  /** The text of every sidebar group heading currently on screen. */
  function groupLabels(): (string | null)[] {
    return [...document.querySelectorAll('[data-slot="sidebar-group-label"]')].map(
      (el) => el.textContent,
    );
  }

  it("keeps the empty state out of the list entirely", () => {
    // This was a real axe violation, serious: "No devices connected." was a `<p>`
    // sitting directly inside `SidebarMenu`'s `<ul>`, where the only legal child
    // is an `<li>`. It renders identically either way, so nothing but this notices.
    renderApp();
    const empty = screen.getByText("No devices connected.");

    expect(empty.tagName).toBe("P");
    expect(nav()).toContainElement(empty);
    expect(empty.closest("ul")).toBeNull();
    // Not merely "outside the list": there is no list at all until there is
    // something to put in it, so wrapping the sentence in an `<li>` is not a
    // passing answer either.
    expect(nav().querySelectorAll("ul")).toHaveLength(0);
    expect(illegalListChildren(nav())).toEqual([]);
  });

  it("renders the menu once a device arrives, with only list items in it", () => {
    const { socket } = renderApp();
    defineProperty(socket, "CCD Simulator", "EXPOSURE");

    expect(screen.queryByText("No devices connected.")).not.toBeInTheDocument();
    expect(nav().querySelectorAll("ul")).toHaveLength(1);
    expect(illegalListChildren(nav())).toEqual([]);
  });

  it("nests configuration under its device rather than beside it", () => {
    // Configuration acts *on* a device and is not one, and this menu has now
    // said that two wrong ways. As a sibling `<li>` of the device buttons it was
    // announced as a third device inside the landmark. Moved out to its own
    // `SidebarGroup` it left the landmark but kept the device's indent and grew
    // a heading repeating the device's name directly under the row that already
    // carried it. Nesting is the answer to both: inside the device's own item,
    // in a sub-list named for it.
    const { socket } = renderApp();
    defineProperty(socket, "CCD Simulator", "EXPOSURE");
    defineConfigProcess(socket, "CCD Simulator");

    const entry = screen.getByRole("button", { name: /Configuration/ });
    const device = screen.getByRole("button", { name: "CCD Simulator" });

    // Inside the landmark is right now, but only as a child of its device: the
    // assertion that matters is that it is not a sibling of the device buttons,
    // which is what "another device" looked like in the markup.
    expect(within(nav()).getByRole("button", { name: /Configuration/ })).toBe(entry);
    expect(device.closest("li")).toContainElement(entry);
    expect(entry.closest("ul")).not.toBe(device.closest("ul"));
    expect(illegalListChildren(nav())).toEqual([]);
    // And no heading anywhere is spending a row to repeat the device's name.
    expect(groupLabels()).toEqual(["Devices"]);
  });

  it("offers configuration only for the selected device", () => {
    // The panel shows one device at a time, so an entry under every device would
    // be a second row each for a dialog that can only ever act on the selection.
    const { socket } = renderApp();
    defineProperty(socket, "CCD Simulator", "EXPOSURE");
    defineProperty(socket, "Dome Simulator", "SHUTTER");
    defineConfigProcess(socket, "CCD Simulator");
    defineConfigProcess(socket, "Dome Simulator");

    // The first device to arrive is the one auto-selected.
    expect(screen.getAllByRole("button", { name: /Configuration/ })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "CCD Simulator" }).closest("li")).toContainElement(
      screen.getByRole("button", { name: /Configuration/ }),
    );
  });

  it("shows nothing at all for a device with no configuration", () => {
    // `DeviceConfigDialog` renders nothing without CONFIG_PROCESS, and nothing
    // now means nothing: it owns the sub-list as well as the item, so there is
    // no indented rule left hanging under the device's row. The demo's dome is
    // exactly that case, and every libindi driver is not.
    const { socket } = renderApp();
    defineProperty(socket, "CCD Simulator", "EXPOSURE");

    expect(screen.queryByRole("button", { name: /Configuration/ })).toBeNull();
    expect(within(nav()).queryAllByRole("list")).toHaveLength(1);
    expect(groupLabels()).toEqual(["Devices"]);
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
