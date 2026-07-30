/** Tests for the {@link IndiClient} watch/send surface over a fake socket. */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { IndiClient } from "./client";
import { FakeSocket, fakeFactory } from "./testing/fake-socket";
import type { DefVector, NumberVector, SetVector } from "./types";

function numVec(value = 1.0, state: NumberVector["state"] = "Idle"): NumberVector {
  return {
    kind: "number",
    device: "CCD",
    name: "EXPOSURE",
    state,
    perm: "rw",
    elements: [{ kind: "number", name: "secs", value }],
  };
}

/** Build a started client wired to a fresh open FakeSocket. */
function connectedClient() {
  FakeSocket.reset();
  const client = new IndiClient({ url: "ws://x/ws", webSocketFactory: fakeFactory });
  client.connect();
  const socket = FakeSocket.latest();
  socket.open();
  return { client, socket };
}

describe("IndiClient inbound", () => {
  it("folds def/set frames into the store and dispatches to subscribers", () => {
    const { client, socket } = connectedClient();
    const events: string[] = [];
    client.subscribe((event) => events.push(event.type), { device: "CCD" });

    socket.receive(JSON.stringify({ tag: "def", vector: numVec(1.0) } satisfies DefVector));
    socket.receive(JSON.stringify({ tag: "set", vector: numVec(2.5, "Ok") } satisfies SetVector));

    expect(events).toEqual(["def", "set"]);
    expect(client.get("CCD", "EXPOSURE")?.state).toBe("Ok");
    expect(client.devices()).toEqual(["CCD"]);
  });

  it("routes message frames to message subscribers", () => {
    const { client, socket } = connectedClient();
    const messages: string[] = [];
    client.onMessage((message) => messages.push(message.message));

    socket.receive(JSON.stringify({ tag: "message", device: "CCD", message: "ready" }));
    expect(messages).toEqual(["ready"]);
  });

  it("tracks transport and upstream connection state separately", () => {
    const states: string[] = [];
    FakeSocket.reset();
    const client = new IndiClient({ url: "ws://x/ws", webSocketFactory: fakeFactory });
    client.onConnection((state) => states.push(`${state.transport}/${state.upstream}`));
    client.connect();

    FakeSocket.latest().open();
    expect(client.connected).toBe(true);
    expect(client.upstreamConnected).toBe(false);

    FakeSocket.latest().receive(JSON.stringify({ event: "connection", connected: true }));
    expect(client.upstreamConnected).toBe(true);

    FakeSocket.latest().close();
    expect(client.connected).toBe(false);
    expect(client.upstreamConnected).toBe(false);

    expect(states).toEqual(["true/false", "true/true", "false/false"]);
  });

  it("ignores malformed frames without throwing", () => {
    const { client, socket } = connectedClient();
    expect(() => socket.receive("not json")).not.toThrow();
    expect(client.devices()).toEqual([]);
  });
});

describe("IndiClient sends", () => {
  it("emits a typed new frame from setSwitch, coercing the value", () => {
    const { client, socket } = connectedClient();
    client.setSwitch("Demo", "power", { on: true, off: false });

    const frame = JSON.parse(socket.sent.at(-1) as string);
    expect(frame.tag).toBe("new");
    expect(frame.vector.kind).toBe("switch");
    expect(frame.vector.elements).toEqual([
      { kind: "switch", name: "on", value: "On" },
      { kind: "switch", name: "off", value: "Off" },
    ]);
  });

  it("remembers enableBlob policies and replays them on reconnect", () => {
    const { client, socket } = connectedClient();
    client.enableBlob("CCD");
    expect(JSON.parse(socket.sent.at(-1) as string)).toMatchObject({
      tag: "enableBLOB",
      device: "CCD",
      policy: "Also",
    });

    // Drop and reconnect: the policy is re-sent on the fresh socket.
    vi.useFakeTimers();
    socket.close();
    vi.advanceTimersByTime(2000);
    const reconnected = FakeSocket.latest();
    reconnected.open();
    vi.useRealTimers();

    expect(reconnected.sent.some((f) => f.includes("enableBLOB"))).toBe(true);
  });
});

describe("IndiClient.waitFor", () => {
  beforeEach(() => {
    FakeSocket.reset();
  });

  it("resolves immediately when the cached property already matches", async () => {
    const { client, socket } = connectedClient();
    socket.receive(JSON.stringify({ tag: "def", vector: numVec(1.0, "Ok") }));

    const vector = await client.waitFor("CCD", "EXPOSURE", (v) => v.state === "Ok");
    expect(vector.name).toBe("EXPOSURE");
  });

  it("resolves when a later frame satisfies the predicate", async () => {
    const { client, socket } = connectedClient();
    socket.receive(JSON.stringify({ tag: "def", vector: numVec(1.0, "Idle") }));

    const pending = client.waitFor("CCD", "EXPOSURE", (v) => v.state === "Ok", { timeout: 1000 });
    socket.receive(JSON.stringify({ tag: "set", vector: numVec(2.5, "Ok") }));

    const vector = await pending;
    expect(vector.state).toBe("Ok");
  });

  it("rejects on timeout", async () => {
    const { client } = connectedClient();
    await expect(client.waitFor("CCD", "EXPOSURE", undefined, { timeout: 10 })).rejects.toThrow(
      /timed out/,
    );
  });
});
