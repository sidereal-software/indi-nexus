/** Tests for the streaming message log. */

import { IndiClient } from "@indikit/client";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { IndiProvider } from "../context";
import { FakeSocket } from "../testing/fake-socket";
import { receive, renderConnected } from "../testing/render";
import { MessageLog } from "./message-log";

afterEach(cleanup);

describe("MessageLog", () => {
  it("shows a placeholder before any message arrives", () => {
    renderConnected(<MessageLog />);
    expect(screen.getByText("No messages yet.")).toBeInTheDocument();
  });

  it("stacks a time/device header above each message's text", () => {
    const { socket } = renderConnected(<MessageLog />);
    receive(socket, {
      tag: "message",
      device: "CCD",
      message: "exposure started",
      timestamp: "2026-07-30T12:34:56Z",
    });
    // The header line (time + device) sits directly above the message text, so
    // long messages wrap at the panel margin instead of mid-row.
    const header = screen.getByText("exposure started").previousElementSibling;
    expect(header).toHaveTextContent("CCD");
    // The exact rendering is locale-dependent; just require a non-empty time.
    expect(header?.querySelector(".tabular-nums")?.textContent).not.toBe("");
  });

  it("renders no time for a missing or unparseable timestamp", () => {
    const { socket } = renderConnected(<MessageLog />);
    receive(socket, { tag: "message", message: "no clock", timestamp: "not-a-date" });
    const line = screen.getByText("no clock").parentElement;
    expect(line?.querySelector(".tabular-nums")?.textContent).toBe("");
  });

  it("shows messages that arrived before the log mounted", () => {
    // The panel renders MessageLog inside a sheet that mounts on open, so the
    // buffer must live on the client, not in the component.
    const sockets: FakeSocket[] = [];
    const client = new IndiClient({
      url: "ws://x/ws",
      webSocketFactory: () => {
        const socket = new FakeSocket();
        sockets.push(socket);
        return socket;
      },
    });
    const { rerender } = render(<IndiProvider client={client}>{null}</IndiProvider>);
    const socket = sockets[0];
    if (!socket) throw new Error("client did not open a socket");
    act(() => socket.open());
    receive(socket, { tag: "message", message: "early bird" });

    rerender(
      <IndiProvider client={client}>
        <MessageLog />
      </IndiProvider>,
    );
    expect(screen.getByText("early bird")).toBeInTheDocument();
  });

  it("is a polite log region, and one a keyboard can scroll", () => {
    renderConnected(<MessageLog />);
    // The scrolling viewport carries both: `log` because everything arriving over
    // the socket has to reach a reader who cannot see the strip, and the tab stop
    // because the view follows the newest entry, so without it the history above
    // is reachable only with a wheel.
    const region = screen.getByRole("log", { name: "INDI messages" });
    expect(region).toHaveAttribute("data-slot", "scroll-area-viewport");
    expect(region).toHaveAttribute("tabindex", "0");
  });

  it("retains only the newest `limit` messages", () => {
    const { socket } = renderConnected(<MessageLog limit={2} />);
    receive(socket, { tag: "message", message: "one" });
    receive(socket, { tag: "message", message: "two" });
    receive(socket, { tag: "message", message: "three" });
    expect(screen.queryByText("one")).not.toBeInTheDocument();
    expect(screen.getByText("two")).toBeInTheDocument();
    expect(screen.getByText("three")).toBeInTheDocument();
  });
});
