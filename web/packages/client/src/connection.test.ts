/** Tests for the reconnecting WebSocket wrapper. */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReconnectingConnection } from "./connection";
import { asyncCloseFactory, FakeSocket, fakeFactory } from "./testing/fake-socket";

describe("ReconnectingConnection", () => {
  beforeEach(() => {
    FakeSocket.reset();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("reports open state and forwards messages", () => {
    const received: string[] = [];
    const conn = new ReconnectingConnection("ws://x/ws", {
      webSocketFactory: fakeFactory,
      handlers: { onMessage: (data) => received.push(data) },
    });
    conn.start();
    expect(conn.connected).toBe(false);

    FakeSocket.latest().open();
    expect(conn.connected).toBe(true);

    FakeSocket.latest().receive("hello");
    expect(received).toEqual(["hello"]);
  });

  it("buffers sends until open, then flushes in order", () => {
    const conn = new ReconnectingConnection("ws://x/ws", { webSocketFactory: fakeFactory });
    conn.start();
    conn.send("a");
    conn.send("b");
    const socket = FakeSocket.latest();
    expect(socket.sent).toEqual([]);

    socket.open();
    expect(socket.sent).toEqual(["a", "b"]);

    conn.send("c");
    expect(socket.sent).toEqual(["a", "b", "c"]);
  });

  it("reconnects with a fixed delay after an unexpected close", () => {
    const conn = new ReconnectingConnection("ws://x/ws", {
      webSocketFactory: fakeFactory,
      reconnectDelay: 1000,
    });
    conn.start();
    FakeSocket.latest().open();
    expect(FakeSocket.instances).toHaveLength(1);

    FakeSocket.latest().close(); // server dropped us
    expect(conn.connected).toBe(false);

    vi.advanceTimersByTime(1000);
    expect(FakeSocket.instances).toHaveLength(2); // a fresh socket was opened
  });

  it("ignores a close from a socket it has already replaced", () => {
    // React StrictMode mounts, cleans up and mounts again, so the first socket
    // is still closing when the second is open. A real WebSocket fires the old
    // socket's onclose at that point; nothing about it may reach the owner.
    let reopened = false;
    let lateCloses = 0;
    const conn = new ReconnectingConnection("ws://x/ws", {
      webSocketFactory: asyncCloseFactory,
      reconnectDelay: 1000,
      handlers: {
        onClose: () => {
          if (reopened) lateCloses++;
        },
      },
    });

    conn.start();
    FakeSocket.latest().open();
    conn.close();
    conn.start(); // remounted before the first socket finished closing
    FakeSocket.latest().open();
    reopened = true;

    vi.runAllTimers(); // deliver the stale onclose, and any reconnect it booked

    expect(FakeSocket.instances).toHaveLength(2);
    expect(lateCloses).toBe(0);
    expect(conn.connected).toBe(true); // the healthy second socket is still ours
  });

  it("ignores a frame from a socket it has already replaced", () => {
    const received: string[] = [];
    const conn = new ReconnectingConnection("ws://x/ws", {
      webSocketFactory: asyncCloseFactory,
      handlers: { onMessage: (data) => received.push(data) },
    });

    conn.start();
    const first = FakeSocket.latest();
    first.open();
    conn.close();
    conn.start();
    FakeSocket.latest().open();

    first.receive("stale"); // still closing, and still delivering
    FakeSocket.latest().receive("fresh");

    expect(received).toEqual(["fresh"]);
  });

  it("does not reconnect after an explicit close", () => {
    const conn = new ReconnectingConnection("ws://x/ws", {
      webSocketFactory: fakeFactory,
      reconnectDelay: 1000,
    });
    conn.start();
    FakeSocket.latest().open();

    conn.close();
    vi.advanceTimersByTime(5000);
    expect(FakeSocket.instances).toHaveLength(1);
  });
});
