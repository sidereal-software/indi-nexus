/** Tests for the {@link IndiClient} watch/send surface over a fake socket. */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { IndiClient } from "./client";
import { FakeSocket, fakeFactory } from "./testing/fake-socket";
import {
  CLIENT_PROTOCOL_VERSION,
  type DefVector,
  type NewVector,
  type NumberVector,
  type SetVector,
} from "./types";

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

/** The client's whole message log as one string, for a substring assertion. */
function logged(client: IndiClient): string {
  return client
    .messages()
    .map((message) => message.message)
    .join("\n");
}

/**
 * Build a started client wired to a fresh open FakeSocket.
 *
 * The `hello` is delivered because a real bridge always sends it first, and a
 * socket that skips it puts every later test one message-log entry off. The
 * tests for the version handshake itself use {@link openedClient}, which stops
 * at the open.
 */
function connectedClient() {
  const { client, socket } = openedClient();
  socket.receive(
    JSON.stringify({ event: "hello", protocol: CLIENT_PROTOCOL_VERSION, server: "0" }),
  );
  return { client, socket };
}

/** Build a started client on an open socket that has received nothing yet. */
function openedClient() {
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

    FakeSocket.latest().receive(
      JSON.stringify({ event: "hello", protocol: CLIENT_PROTOCOL_VERSION, server: "0.2.0" }),
    );
    FakeSocket.latest().receive(JSON.stringify({ event: "connection", connected: true }));
    expect(client.upstreamConnected).toBe(true);

    FakeSocket.latest().close();
    expect(client.connected).toBe(false);
    expect(client.upstreamConnected).toBe(false);

    // The hello does not move either link, so it adds no entry here: the
    // notification it does cause carries the same two booleans as the one
    // before it, and `setState` compares the whole state.
    expect(states).toEqual(["true/false", "true/false", "true/true", "false/false"]);
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

  it("records the bridge's protocol version and notifies a connection subscriber", () => {
    const { client, socket } = openedClient();
    const states: (number | null)[] = [];
    client.onConnection((state) => states.push(state.protocol));

    socket.receive(
      JSON.stringify({ event: "hello", protocol: CLIENT_PROTOCOL_VERSION, server: "9.9.9" }),
    );

    expect(client.connectionState.protocol).toBe(CLIENT_PROTOCOL_VERSION);
    // Notified, not merely assigned. `setState` returns early on an unchanged
    // state, so a comparison that looked only at the two links would have set
    // the field and told nobody - which no typecheck can see.
    expect(states).toEqual([CLIENT_PROTOCOL_VERSION]);
    expect(client.messages()).toEqual([]);
  });

  it("keeps running when the bridge announces a newer protocol, and says so", () => {
    const { client, socket } = openedClient();
    socket.receive(
      JSON.stringify({ event: "hello", protocol: CLIENT_PROTOCOL_VERSION + 1, server: "9.9.9" }),
    );

    expect(client.connectionState.protocol).toBe(CLIENT_PROTOCOL_VERSION + 1);
    expect(client.messages()).toHaveLength(1);
    expect(logged(client)).toContain(`${CLIENT_PROTOCOL_VERSION + 1}`);

    // Non-fatal in the loud direction too: the socket still carries traffic.
    socket.receive(JSON.stringify({ tag: "def", vector: numVec() }));
    expect(client.devices()).toEqual(["CCD"]);
  });

  it("keeps running when the bridge announces an older protocol, naming both", () => {
    const { client, socket } = openedClient();
    socket.receive(JSON.stringify({ event: "hello", protocol: 0, server: "0.0.1" }));

    expect(client.connectionState.protocol).toBe(0);
    expect(logged(client)).toContain("0");
    expect(logged(client)).toContain(`${CLIENT_PROTOCOL_VERSION}`);
  });

  it("settles on protocol 0 when the first frame is not a hello", () => {
    const { client, socket } = openedClient();
    socket.receive(JSON.stringify({ event: "connection", connected: true }));

    // The case that made the latch "first frame" rather than "no hello before
    // the first def": with the upstream down and the cache empty, a bridge's
    // first frame is the connection frame and no def ever arrives.
    expect(client.connectionState.protocol).toBe(0);
    expect(client.upstreamConnected).toBe(true);
    expect(client.messages()).toHaveLength(1);
  });

  it("trips the version latch on a first frame the frame guard rejects", () => {
    const { client, socket } = openedClient();
    // A def with no device never reaches the store. It is still a frame, and it
    // is still not a hello, so leaving `protocol` at null here would strand a
    // legacy bridge as "unknown" for the life of the socket.
    socket.receive(rawFrame({ tag: "def", vector: { ...numVec(), device: "" } }));

    expect(client.connectionState.protocol).toBe(0);
    expect(client.devices()).toEqual([]);
  });

  it("forgets the protocol version on close, latch included", () => {
    vi.useFakeTimers();
    try {
      FakeSocket.reset();
      const client = new IndiClient({
        url: "ws://x/ws",
        webSocketFactory: fakeFactory,
        reconnectDelay: 1000,
      });
      client.connect();
      const socket = FakeSocket.latest();
      socket.open();
      socket.receive(
        JSON.stringify({ event: "hello", protocol: CLIENT_PROTOCOL_VERSION, server: "0.2.0" }),
      );
      expect(client.connectionState.protocol).toBe(CLIENT_PROTOCOL_VERSION);

      socket.close();
      expect(client.connectionState.protocol).toBeNull();

      // The next socket may reach an entirely different bridge. Without
      // resetting the latch alongside the version, a reconnect onto one older
      // than the hello would sit at null for ever instead of settling on 0.
      vi.advanceTimersByTime(1000);
      const next = FakeSocket.latest();
      next.open();
      next.receive(JSON.stringify({ event: "connection", connected: false }));
      expect(client.connectionState.protocol).toBe(0);
    } finally {
      vi.useRealTimers();
    }
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
    expect(client.connectionState).toEqual({
      transport: true,
      upstream: false,
      protocol: CLIENT_PROTOCOL_VERSION,
    });
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

describe("IndiClient.onWrite", () => {
  /**
   * Subscribe a recorder and hand back the list it fills.
   *
   * @param client - The client to watch.
   * @returns The `(device, name)` pairs seen so far, in the order they fired.
   */
  function writesOf(client: IndiClient): [string, string][] {
    const writes: [string, string][] = [];
    client.onWrite((device, name) => writes.push([device, name]));
    return writes;
  }

  it("reports a new frame a caller assembled itself", () => {
    // Reported from `send`, not from the four helpers, so a consumer building
    // its own frame - which the type allows - is covered by the same rule.
    const { client } = connectedClient();
    const writes = writesOf(client);

    client.send({ tag: "new", vector: numVec(3.0) } satisfies NewVector);

    expect(writes).toEqual([["CCD", "EXPOSURE"]]);
  });

  it.each([
    ["setNumber", (client: IndiClient) => client.setNumber("Dome", "SHUTTER", { secs: 1 })],
    ["setText", (client: IndiClient) => client.setText("Dome", "SHUTTER", { note: "open" })],
    ["setSwitch", (client: IndiClient) => client.setSwitch("Dome", "SHUTTER", { OPEN: true })],
    ["setBlob", (client: IndiClient) => client.setBlob("Dome", "SHUTTER", { frame: "AAAA" })],
  ])("reports the write %s puts on the wire", (_name, write) => {
    const { client } = connectedClient();
    const writes = writesOf(client);

    write(client);

    expect(writes).toEqual([["Dome", "SHUTTER"]]);
  });

  it("reports one write per frame, not one per element", () => {
    // The unit of a write is the vector: INDI applies a `new` atomically and the
    // operator pressed one button, so three elements are still one action.
    const { client } = connectedClient();
    const writes = writesOf(client);

    client.setSwitch("Dome", "SHUTTER", { OPEN: true, CLOSE: false, ABORT: false });

    expect(writes).toEqual([["Dome", "SHUTTER"]]);
  });

  it("stays silent for the outbound frames that are not writes", () => {
    // These three go out over the same socket and none of them asks the
    // instrument to change: a consumer told about them would arm on a page load.
    const { client, socket } = connectedClient();
    const writes = writesOf(client);

    client.getProperties("CCD", "EXPOSURE");
    client.enableBlob("CCD", "CCD1", "Only");

    // Including the enableBLOB replay a reconnect sends by itself, which no
    // operator asked for at all.
    vi.useFakeTimers();
    socket.close();
    vi.advanceTimersByTime(2000);
    FakeSocket.latest().open();
    vi.useRealTimers();

    expect(writes).toEqual([]);
  });

  it("stays silent for inbound frames, including one tagged new", () => {
    // The point of the callback is telling apart what this browser asked for
    // from what arrived on its own, so a frame coming *in* can never fire it -
    // not even the one carrying the same tag a write does.
    const { client, socket } = connectedClient();
    const writes = writesOf(client);

    socket.receive(JSON.stringify({ tag: "def", vector: numVec(1.0) }));
    socket.receive(JSON.stringify({ tag: "set", vector: numVec(2.0, "Busy") }));
    socket.receive(JSON.stringify({ tag: "new", vector: numVec(3.0) }));

    expect(writes).toEqual([]);
  });

  it("fires while the socket is down, because the frame is only buffered", () => {
    // Documented contract: the callback fires on the send rather than on any
    // acknowledgement. The connection buffers while offline and the operator
    // pressed the button regardless, so a consumer waiting for the socket would
    // silently lose the write that most needs reporting.
    FakeSocket.reset();
    const client = new IndiClient({ url: "ws://x/ws", webSocketFactory: fakeFactory });
    const writes = writesOf(client);

    client.setSwitch("Dome", "SHUTTER", { OPEN: true });

    expect(writes).toEqual([["Dome", "SHUTTER"]]);
    expect(FakeSocket.instances).toEqual([]);

    // And the frame really was buffered rather than dropped.
    client.connect();
    const socket = FakeSocket.latest();
    socket.open();
    expect(socket.sent.some((frame) => frame.includes('"tag":"new"'))).toBe(true);
  });

  it("delivers to every subscriber", () => {
    const { client } = connectedClient();
    const first = writesOf(client);
    const second = writesOf(client);

    client.setNumber("CCD", "EXPOSURE", { secs: 1 });

    expect(first).toEqual([["CCD", "EXPOSURE"]]);
    expect(second).toEqual([["CCD", "EXPOSURE"]]);
  });

  it("stops delivering to an unsubscribed callback and leaves the others", () => {
    const { client } = connectedClient();
    const dropped: string[] = [];
    const kept: string[] = [];
    const unsubscribe = client.onWrite((_device, name) => dropped.push(name));
    client.onWrite((_device, name) => kept.push(name));

    client.setNumber("CCD", "EXPOSURE", { secs: 1 });
    unsubscribe();
    client.setNumber("CCD", "COOLER", { on: 1 });

    expect(dropped).toEqual(["EXPOSURE"]);
    expect(kept).toEqual(["EXPOSURE", "COOLER"]);
  });

  it("is idempotent on repeated unsubscribe, leaving other callbacks alone", () => {
    const { client } = connectedClient();
    const kept: string[] = [];
    const unsubscribe = client.onWrite(() => {});
    client.onWrite((_device, name) => kept.push(name));

    unsubscribe();
    unsubscribe();
    client.setNumber("CCD", "EXPOSURE", { secs: 1 });

    expect(kept).toEqual(["EXPOSURE"]);
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
    expect(client.connectionState).toEqual({ transport: false, upstream: false, protocol: null });
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
