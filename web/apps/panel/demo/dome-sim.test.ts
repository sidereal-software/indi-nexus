/**
 * Drives the dome simulator the way the documentation demo's panel does.
 *
 * These are the behaviours the simulator shares with `examples/dome_device.py`
 * and had drifted from: which park button is lit while parking runs, parking
 * with no rotation left to do, and what a disconnect leaves behind.
 */

import type { SwitchVector, Vector } from "@indikit/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DomeSimSocket } from "./dome-sim";

const DEVICE = "Dome Simulator";

/** One frame the simulator delivered to the client. */
interface Frame {
  tag?: string;
  vector?: Vector;
  message?: string;
}

/** A simulator with its frames collected, opened and (optionally) connected. */
function start(connect = true) {
  const frames: Frame[] = [];
  const socket = new DomeSimSocket();
  socket.onmessage = (event) => frames.push(JSON.parse(String(event.data)) as Frame);
  vi.advanceTimersByTime(0); // the constructor opens and primes on a timer
  if (connect) {
    send(socket, switchVector("CONNECTION", "CONNECT"));
    frames.length = 0; // from here on the test only cares about what it caused
  }
  return { socket, frames };
}

/** Send a client write, as `IndiClient` would. */
function send(socket: DomeSimSocket, vector: Vector): void {
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

/** A number write for one element. */
function numberVector(name: string, element: string, value: number): Vector {
  return {
    kind: "number",
    device: DEVICE,
    name,
    state: "Idle",
    perm: "rw",
    elements: [{ kind: "number", name: element, value }],
  } as Vector;
}

/** The most recent `set` for one property, if the simulator sent one. */
function latest(frames: Frame[], name: string): Vector | undefined {
  return frames.filter((f) => f.tag === "set" && f.vector?.name === name).at(-1)?.vector;
}

/** The member a switch vector has On. */
function selected(vector: Vector | undefined): string | undefined {
  if (vector === undefined || vector.kind !== "switch") return undefined;
  return (vector as SwitchVector).elements.find((el) => el.value === "On")?.name;
}

describe("DomeSimSocket", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("keeps PARK selected for the whole busy period", () => {
    const { socket, frames } = start();
    send(socket, switchVector("DOME_PARK", "PARK"));

    // The dome starts at 0 and parks at 90, so this park takes many ticks.
    const busy = latest(frames, "DOME_PARK");
    expect(busy?.state).toBe("Busy");
    expect(selected(busy)).toBe("PARK");

    vi.advanceTimersByTime(20_000);
    const parked = latest(frames, "DOME_PARK");
    expect(parked?.state).toBe("Ok");
    expect(selected(parked)).toBe("PARK");
  });

  it("selects UNPARK when the client unparks", () => {
    const { socket, frames } = start();
    send(socket, switchVector("DOME_PARK", "UNPARK"));
    expect(selected(latest(frames, "DOME_PARK"))).toBe("UNPARK");

    vi.advanceTimersByTime(20_000);
    const unparked = latest(frames, "DOME_PARK");
    expect(unparked?.state).toBe("Ok");
    expect(selected(unparked)).toBe("UNPARK");
  });

  it("parks at once when the dome is already at the park azimuth", () => {
    const { socket, frames } = start();
    send(socket, numberVector("ABS_DOME_POSITION", "DOME_ABSOLUTE_POSITION", 90));
    vi.advanceTimersByTime(20_000);
    frames.length = 0;

    send(socket, switchVector("DOME_PARK", "PARK")); // no tick in between
    const parked = latest(frames, "DOME_PARK");
    expect(parked?.state).toBe("Ok");
    expect(selected(parked)).toBe("PARK");
    expect(frames.map((f) => f.message)).toContain("[INFO] Dome parked.");
  });

  it("arrives immediately when the move is within one step", () => {
    const { socket, frames } = start();
    send(socket, numberVector("REL_DOME_POSITION", "DOME_RELATIVE_POSITION", 4));

    const position = latest(frames, "ABS_DOME_POSITION");
    expect(position?.state).toBe("Ok"); // not Busy waiting for the next tick
    expect(position?.kind === "number" && position.elements[0]?.value).toBe(4);
  });

  it("idles everything it was driving when the client disconnects", () => {
    const { socket, frames } = start();
    send(socket, switchVector("DOME_PARK", "PARK"));
    vi.advanceTimersByTime(2000); // mid-rotation, mid-shutter
    expect(latest(frames, "ABS_DOME_POSITION")?.state).toBe("Busy");
    frames.length = 0;

    send(socket, switchVector("CONNECTION", "DISCONNECT"));
    // The tick stops with the link, so nothing else can clear a Busy badge.
    expect(latest(frames, "ABS_DOME_POSITION")?.state).toBe("Idle");
    expect(latest(frames, "DOME_SHUTTER")?.state).toBe("Idle");
    expect(latest(frames, "DOME_PARK")?.state).toBe("Idle");

    vi.advanceTimersByTime(20_000);
    expect(latest(frames, "ABS_DOME_POSITION")?.state).toBe("Idle");
  });

  it("reports new speeds back on the SPEEDS vector", () => {
    const { socket, frames } = start();
    send(socket, numberVector("SPEEDS", "DOME", 7.5));

    const speeds = latest(frames, "SPEEDS");
    expect(speeds?.name).toBe("SPEEDS");
    expect(speeds?.state).toBe("Ok");
    expect(speeds?.kind === "number" && speeds.elements.map((el) => el.value)).toEqual([7.5, 0.1]);
  });
});
