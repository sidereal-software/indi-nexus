/**
 * Drives the flat-panel simulator the way the documentation demo's panel does.
 *
 * These are the behaviours it has to share with `examples/flat_panel.py`: the
 * standard CONNECTION switch, commands refused while the link is down, the
 * clamped brightness range, and a lamp that goes dark when the client leaves.
 */

import type { SwitchVector, Vector } from "@indi-nexus/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FlatPanelSimSocket } from "./flat-panel-sim";

const DEVICE = "Flat Panel";

/** One frame the simulator delivered to the client. */
interface Frame {
  tag?: string;
  vector?: Vector;
  message?: string;
}

/** A simulator with its frames collected, opened and (optionally) connected. */
function start(connect = true) {
  const frames: Frame[] = [];
  const socket = new FlatPanelSimSocket();
  socket.onmessage = (event) => frames.push(JSON.parse(String(event.data)) as Frame);
  vi.advanceTimersByTime(0); // the constructor opens and primes on a timer
  if (connect) {
    send(socket, switchVector("CONNECTION", "CONNECT"));
    frames.length = 0; // from here on the test only cares about what it caused
  }
  return { socket, frames };
}

/** Send a client write, as `IndiClient` would. */
function send(socket: FlatPanelSimSocket, vector: Vector): void {
  socket.send(JSON.stringify({ tag: "new", vector }));
}

/** The partial switch vector a client sends when a member is clicked. */
function switchVector(name: string, member: string): Vector {
  return {
    kind: "switch",
    device: DEVICE,
    name,
    state: "Idle",
    perm: "rw",
    rule: "OneOfMany",
    elements: [{ kind: "switch", name: member, value: "On" }],
  } as Vector;
}

/** A brightness write for one value. */
function brightness(value: number): Vector {
  return {
    kind: "number",
    device: DEVICE,
    name: "LIGHT_BRIGHTNESS",
    state: "Idle",
    perm: "rw",
    elements: [{ kind: "number", name: "BRIGHTNESS", value }],
  } as Vector;
}

/** The most recent frame of one tag for one property, if the simulator sent one. */
function latest(frames: Frame[], tag: string, name: string): Vector | undefined {
  return frames.filter((f) => f.tag === tag && f.vector?.name === name).at(-1)?.vector;
}

/** The member a switch vector has On. */
function selected(vector: Vector | undefined): string | undefined {
  if (vector === undefined || vector.kind !== "switch") return undefined;
  return (vector as SwitchVector).elements.find((el) => el.value === "On")?.name;
}

/** The value of a number vector's only element. */
function value(vector: Vector | undefined): number | undefined {
  return vector?.kind === "number" ? vector.elements[0]?.value : undefined;
}

describe("FlatPanelSimSocket", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("defines the standard CONNECTION switch, disconnected", () => {
    const { frames } = start(false);
    const connection = latest(frames, "def", "CONNECTION");
    expect(connection?.group).toBe("Main Control");
    expect(selected(connection)).toBe("DISCONNECT");
  });

  it("refuses lamp and brightness writes while disconnected", () => {
    const { socket, frames } = start(false);
    send(socket, switchVector("LIGHT_CONTROL", "ON"));
    send(socket, brightness(200));

    expect(latest(frames, "set", "LIGHT_CONTROL")).toBeUndefined();
    expect(latest(frames, "set", "LIGHT_BRIGHTNESS")).toBeUndefined();
    expect(frames.map((f) => f.message)).toContain("[ERROR] Flat Panel is not connected.");
  });

  it("applies lamp and brightness writes once connected", () => {
    const { socket, frames } = start();
    send(socket, switchVector("LIGHT_CONTROL", "ON"));
    send(socket, brightness(64));

    expect(selected(latest(frames, "set", "LIGHT_CONTROL"))).toBe("ON");
    expect(value(latest(frames, "set", "LIGHT_BRIGHTNESS"))).toBe(64);
  });

  it("clamps a brightness request to the advertised range", () => {
    const { socket, frames } = start();
    send(socket, brightness(1000));
    expect(value(latest(frames, "set", "LIGHT_BRIGHTNESS"))).toBe(255);

    send(socket, brightness(-5));
    expect(value(latest(frames, "set", "LIGHT_BRIGHTNESS"))).toBe(0);
  });

  it("turns the lamp off when the client disconnects", () => {
    const { socket, frames } = start();
    send(socket, switchVector("LIGHT_CONTROL", "ON"));
    frames.length = 0;

    send(socket, switchVector("CONNECTION", "DISCONNECT"));

    // A panel left lit fogs the next exposure, so the lamp cannot outlive the link.
    const lamp = latest(frames, "set", "LIGHT_CONTROL");
    expect(selected(lamp)).toBe("OFF");
    expect(lamp?.state).toBe("Idle");
    expect(frames.map((f) => f.message)).toContain("[INFO] Lamp turned off on disconnect.");
    expect(selected(latest(frames, "set", "CONNECTION"))).toBe("DISCONNECT");
  });
});
