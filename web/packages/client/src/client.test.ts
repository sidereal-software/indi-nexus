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

/**
 * A frame built from a plain object, so a test can put on the wire what a
 * mistaken producer would: a missing attribute, or a value JSON can carry but
 * the model cannot.
 */
function rawFrame(frame: unknown): string {
  return JSON.stringify(frame);
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

  it("surfaces a bridge error frame in the message log without touching the store", () => {
    const { client, socket } = connectedClient();
    const messages: string[] = [];
    client.onMessage((message) => messages.push(message.message));

    socket.receive(
      JSON.stringify({
        event: "error",
        code: "not_connected",
        message: "not connected to indiserver; the write was not sent",
        tag: "new",
      }),
    );

    // The bridge only sends this when a write did *not* go upstream, and
    // nothing retries it, so dropping it silently would leave the operator
    // believing the slew was accepted.
    expect(messages).toEqual([
      "new was not sent: not connected to indiserver; the write was not sent",
    ]);
    expect(client.messages()).toHaveLength(1);
    expect(client.devices()).toEqual([]);
  });

  it("ignores a control frame it does not know", () => {
    const { client, socket } = connectedClient();
    expect(() => socket.receive(JSON.stringify({ event: "from-the-future" }))).not.toThrow();
    expect(client.devices()).toEqual([]);
    expect(client.messages()).toEqual([]);
  });

  it("ignores malformed frames without throwing", () => {
    const { client, socket } = connectedClient();
    expect(() => socket.receive("not json")).not.toThrow();
    expect(client.devices()).toEqual([]);
  });

  it("ignores valid JSON that is not a frame object", () => {
    const { client, socket } = connectedClient();
    for (const frame of ["null", "42", '"a string"', "true", "[]"]) {
      expect(() => socket.receive(frame)).not.toThrow();
    }
    expect(client.devices()).toEqual([]);
    expect(client.connectionState).toEqual({ transport: true, upstream: false });
  });
});

// The Python parser drops a frame whose #REQUIRED device or name is missing
// rather than defaulting it to "" (`_required` in protocol/xml.py): "" is not a
// degraded device, it is an invented one, and it landed in the cache as a
// phantom device nothing would ever update. A frame can reach a browser without
// having passed through that parser, so the rule is enforced here too.
describe("IndiClient frame validation: identity", () => {
  it("drops a def whose device is empty, leaving the cache untouched", () => {
    const { client, socket } = connectedClient();
    const events: string[] = [];
    client.subscribe((event) => events.push(event.type));

    socket.receive(rawFrame({ tag: "def", vector: { ...numVec(), device: "" } }));

    expect(client.devices()).toEqual([]);
    expect(client.device("")).toEqual({});
    expect(events).toEqual([]);
  });

  it("drops a def with no device attribute at all", () => {
    const { client, socket } = connectedClient();
    const { device: _device, ...vector } = numVec();

    socket.receive(rawFrame({ tag: "def", vector }));

    expect(client.devices()).toEqual([]);
    expect(client.device("undefined")).toEqual({});
  });

  it("drops a def with no property name", () => {
    const { client, socket } = connectedClient();
    const { name: _name, ...vector } = numVec();

    socket.receive(rawFrame({ tag: "def", vector }));

    expect(client.devices()).toEqual([]);
  });

  it("drops a def with no vector rather than throwing", () => {
    const { client, socket } = connectedClient();
    expect(() => socket.receive(rawFrame({ tag: "def" }))).not.toThrow();
    expect(client.devices()).toEqual([]);
  });

  it("drops a delProperty with no device, keeping the cached property", () => {
    const { client, socket } = connectedClient();
    socket.receive(JSON.stringify({ tag: "def", vector: numVec() }));

    socket.receive(rawFrame({ tag: "delProperty" }));

    expect(client.get("CCD", "EXPOSURE")).toBeDefined();
    expect(client.devices()).toEqual(["CCD"]);
  });
});

// `Number.value` is `allow_inf_nan=False`, so `from_json` rejects a message
// carrying one and the XML parser drops the element. JSON has no NaN or
// Infinity literal - `JSON.parse("NaN")` throws - so a producer sends `null` or
// the string, and either would render as NaN in a control or go back to an
// instrument as one.
describe("IndiClient frame validation: non-finite numbers", () => {
  const nonFinite = [null, "NaN", "Infinity", "-Infinity"];

  it("leaves the cached vector untouched when a set carries one", () => {
    const { client, socket } = connectedClient();
    socket.receive(JSON.stringify({ tag: "def", vector: numVec(1.5, "Ok") }));
    const cached = client.get("CCD", "EXPOSURE");
    const events: string[] = [];
    client.subscribe((event) => events.push(event.type));

    for (const value of nonFinite) {
      socket.receive(
        rawFrame({
          tag: "set",
          vector: {
            ...numVec(),
            state: "Alert",
            elements: [{ kind: "number", name: "secs", value }],
          },
        }),
      );
    }

    // Not merged, not replaced, and no subscriber told otherwise.
    expect(client.get("CCD", "EXPOSURE")).toBe(cached);
    expect((client.get("CCD", "EXPOSURE") as NumberVector).elements[0]?.value).toBe(1.5);
    expect(client.get("CCD", "EXPOSURE")?.state).toBe("Ok");
    expect(events).toEqual([]);
  });

  it("drops a def carrying one instead of caching a NaN", () => {
    const { client, socket } = connectedClient();

    for (const value of nonFinite) {
      socket.receive(
        rawFrame({
          tag: "def",
          vector: { ...numVec(), elements: [{ kind: "number", name: "secs", value }] },
        }),
      );
    }

    expect(client.devices()).toEqual([]);
  });

  // The optional metadata *can* say absent, so it degrades instead of costing
  // the frame - dropping the def would leave the client permanently blind to
  // the property, which is what `_optfloat` exists to avoid.
  it("degrades a non-finite min/max/step to absent and keeps the property", () => {
    const { client, socket } = connectedClient();

    socket.receive(
      rawFrame({
        tag: "def",
        vector: {
          ...numVec(),
          timeout: "Infinity",
          elements: [
            { kind: "number", name: "secs", value: 1.5, min: "NaN", max: 3600, step: null },
          ],
        },
      }),
    );

    const cached = client.get("CCD", "EXPOSURE") as NumberVector;
    expect(cached.elements[0]?.value).toBe(1.5);
    expect(cached.elements[0]?.min).toBeNull();
    expect(cached.elements[0]?.max).toBe(3600);
    expect(cached.timeout).toBeNull();
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

  it("keeps both policies of a pair a joined key would confuse", () => {
    const { client, socket } = connectedClient();
    // Joined with a space these two are the same string, "A B C", so one policy
    // would overwrite the other and never be replayed.
    client.enableBlob("A", "B C", "Also");
    client.enableBlob("A B", "C", "Only");

    vi.useFakeTimers();
    socket.close();
    vi.advanceTimersByTime(2000);
    const reconnected = FakeSocket.latest();
    reconnected.open();
    vi.useRealTimers();

    const replayed = reconnected.sent
      .map((frame) => JSON.parse(frame))
      .filter((frame) => frame.tag === "enableBLOB");
    expect(replayed).toEqual([
      { tag: "enableBLOB", device: "A", name: "B C", policy: "Also" },
      { tag: "enableBLOB", device: "A B", name: "C", policy: "Only" },
    ]);
  });
});

describe("IndiClient send helpers", () => {
  it("emits a typed new frame from setNumber", () => {
    const { client, socket } = connectedClient();
    client.setNumber("CCD", "EXPOSURE", { secs: 2.5 });

    const frame = JSON.parse(socket.sent.at(-1) as string);
    expect(frame.tag).toBe("new");
    expect(frame.vector).toMatchObject({
      kind: "number",
      device: "CCD",
      name: "EXPOSURE",
      elements: [{ kind: "number", name: "secs", value: 2.5 }],
    });
  });

  it("emits a typed new frame from setText", () => {
    const { client, socket } = connectedClient();
    client.setText("Scope", "SITE", { name: "MMT" });

    const frame = JSON.parse(socket.sent.at(-1) as string);
    expect(frame.vector).toMatchObject({
      kind: "text",
      elements: [{ kind: "text", name: "name", value: "MMT" }],
    });
  });

  it("emits base64 payloads with decoded byte sizes from setBlob", () => {
    const { client, socket } = connectedClient();
    // "aGVsbG8=" decodes to 5 bytes ("hello"); "aGk=" to 2 ("hi").
    client.setBlob("CCD", "IMAGE", { frame: "aGVsbG8=", thumb: "aGk=" });

    const frame = JSON.parse(socket.sent.at(-1) as string);
    expect(frame.vector.kind).toBe("blob");
    expect(frame.vector.elements).toEqual([
      { kind: "blob", name: "frame", data: "aGVsbG8=", size: 5 },
      { kind: "blob", name: "thumb", data: "aGk=", size: 2 },
    ]);
  });

  it("emits getProperties with the optional device/name filter", () => {
    const { client, socket } = connectedClient();
    client.getProperties("CCD", "EXPOSURE");
    expect(JSON.parse(socket.sent.at(-1) as string)).toMatchObject({
      tag: "getProperties",
      device: "CCD",
      name: "EXPOSURE",
    });
  });

  it("sends getProperties on open only when autoGetProperties is set", () => {
    FakeSocket.reset();
    const client = new IndiClient({
      url: "ws://x/ws",
      webSocketFactory: fakeFactory,
      autoGetProperties: true,
    });
    client.connect();
    const socket = FakeSocket.latest();
    socket.open();
    expect(socket.sent.some((f) => f.includes("getProperties"))).toBe(true);
  });
});

describe("IndiClient reads and lifecycle", () => {
  it("exposes the cache through get/device/devices", () => {
    const { client, socket } = connectedClient();
    socket.receive(JSON.stringify({ tag: "def", vector: numVec() }));

    expect(client.get("CCD", "EXPOSURE")?.name).toBe("EXPOSURE");
    expect(Object.keys(client.device("CCD"))).toEqual(["EXPOSURE"]);
    expect(client.devices()).toEqual(["CCD"]);
    expect(client.store.get("CCD", "EXPOSURE")).toBe(client.get("CCD", "EXPOSURE"));
  });

  it("requires a url when there is no global location (Node)", () => {
    expect(() => new IndiClient({ webSocketFactory: fakeFactory })).toThrow(/pass `url`/);
  });

  it("stops delivering to unsubscribed message and connection callbacks", () => {
    const { client, socket } = connectedClient();
    const onMessage = vi.fn();
    const onConnection = vi.fn();
    client.onMessage(onMessage)();
    client.onConnection(onConnection)();

    socket.receive(JSON.stringify({ tag: "message", device: "CCD", message: "hi" }));
    socket.receive(JSON.stringify({ event: "connection", connected: true }));
    expect(onMessage).not.toHaveBeenCalled();
    expect(onConnection).not.toHaveBeenCalled();
  });

  it("close() stops the connection and reports both links down", () => {
    const { client, socket } = connectedClient();
    expect(client.connected).toBe(true);
    client.close();
    expect(socket.readyState).toBe(3);
    expect(client.connected).toBe(false);
    expect(client.upstreamConnected).toBe(false);
    expect(client.connectionState).toEqual({ transport: false, upstream: false });
  });
});

describe("IndiClient message log", () => {
  it("retains inbound messages oldest first, capped at messageLogLimit", () => {
    FakeSocket.reset();
    const client = new IndiClient({
      url: "ws://x/ws",
      webSocketFactory: fakeFactory,
      messageLogLimit: 2,
    });
    client.connect();
    const socket = FakeSocket.latest();
    socket.open();

    for (const text of ["one", "two", "three"]) {
      socket.receive(JSON.stringify({ tag: "message", device: "CCD", message: text }));
    }
    expect(client.messages().map((m) => m.message)).toEqual(["two", "three"]);
  });

  it("returns a stable snapshot that changes reference only on arrival", () => {
    const { client, socket } = connectedClient();
    const before = client.messages();
    expect(client.messages()).toBe(before);

    socket.receive(JSON.stringify({ tag: "message", message: "hi" }));
    const after = client.messages();
    expect(after).not.toBe(before);
    expect(client.messages()).toBe(after);
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
