/** Tests for the reconnecting WebSocket wrapper. */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReconnectingConnection } from "./connection";
import { asyncCloseFactory, FakeSocket, fakeFactory } from "./testing/fake-socket";

/** `WebSocket.OPEN`, which `connection.ts` keeps module-private. */
const OPEN = 1;

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

  it("does not open a second socket when start() lands inside the reconnect delay", () => {
    // `IndiProvider` calls `connect()` on mount, so a provider swap, a
    // StrictMode remount or a consumer's own "reconnect now" button can land
    // between an unexpected close and the deferred attempt it booked. The
    // deferred attempt then opens over the healthy socket, and the one that
    // stops being `this.socket` is orphaned: still OPEN, never closed, and
    // every frame it delivers dropped by the `current()` guard.
    const received: string[] = [];
    const conn = new ReconnectingConnection("ws://x/ws", {
      webSocketFactory: fakeFactory,
      reconnectDelay: 2000,
      handlers: { onMessage: (data) => received.push(data) },
    });
    conn.start();
    FakeSocket.latest().open();
    FakeSocket.latest().close(); // the bridge dropped us

    vi.advanceTimersByTime(500);
    conn.start(); // remounted, well inside the delay
    const healthy = FakeSocket.latest();
    healthy.open();

    vi.advanceTimersByTime(1500); // t = 2000, the deadline the close booked

    expect(FakeSocket.instances).toHaveLength(2);
    expect(conn.connected).toBe(true);
    // No socket is left alive but disowned: an orphan reports OPEN for ever,
    // which is the leak, and its frames are silently discarded, which is worse.
    expect(FakeSocket.instances.filter((s) => s.readyState === OPEN)).toEqual([healthy]);
    healthy.receive("telemetry");
    expect(received).toEqual(["telemetry"]);
  });

  it("does not open over a socket a consumer opened from inside onClose", () => {
    // The same orphan through a different door, and the one `start()` cannot
    // close on its own: a consumer that reconnects immediately on close runs
    // `start()` synchronously inside the `onClose` handler, which is *before*
    // the close handler books its own timer - so there is nothing to cancel,
    // and the timer is booked over a socket that is already live.

    // The handler needs the connection that does not exist yet, so it reads it
    // through a binding assigned the moment the constructor returns.
    let owner: ReconnectingConnection | null = null;
    const conn = new ReconnectingConnection("ws://x/ws", {
      webSocketFactory: fakeFactory,
      reconnectDelay: 1000,
      handlers: { onClose: () => owner?.start() },
    });
    owner = conn;

    conn.start();
    FakeSocket.latest().open();
    FakeSocket.latest().close(); // the bridge dropped us; onClose re-enters

    const healthy = FakeSocket.latest();
    healthy.open();

    vi.advanceTimersByTime(1000); // the deadline booked after the socket existed

    expect(FakeSocket.instances).toHaveLength(2);
    expect(FakeSocket.instances.filter((s) => s.readyState === OPEN)).toEqual([healthy]);
    expect(conn.connected).toBe(true);
  });

  it("measures the reconnect delay from the socket start() opened, not the one it replaced", () => {
    // The other half: a `start()` that leaves the booked timer running hands
    // the *next* close a timer that is already part-spent, so `scheduleReconnect`
    // early-returns on it and the backoff is silently short.
    const conn = new ReconnectingConnection("ws://x/ws", {
      webSocketFactory: fakeFactory,
      reconnectDelay: 1000,
    });
    conn.start();
    FakeSocket.latest().open();
    FakeSocket.latest().close(); // books a reconnect for t = 1000

    vi.advanceTimersByTime(500);
    conn.start(); // supersedes it
    FakeSocket.latest().open();
    FakeSocket.latest().close(); // t = 500, so the next attempt belongs at t = 1500

    vi.advanceTimersByTime(500); // t = 1000: the superseded deadline
    expect(FakeSocket.instances).toHaveLength(2);

    vi.advanceTimersByTime(500); // t = 1500: a full delay after the close that booked it
    expect(FakeSocket.instances).toHaveLength(3);
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
