/** Tests for the streaming message log. */

import { IndiClient } from "@indi-nexus/client";
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

  it("renders device, text, and a local time for each message", () => {
    const { socket } = renderConnected(<MessageLog />);
    receive(socket, {
      tag: "message",
      device: "CCD",
      message: "exposure started",
      timestamp: "2026-07-30T12:34:56Z",
    });
    expect(screen.getByText("CCD")).toBeInTheDocument();
    const line = screen.getByText("exposure started").parentElement;
    // The exact rendering is locale-dependent; just require a non-empty time.
    expect(line?.querySelector(".tabular-nums")?.textContent).not.toBe("");
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
