/**
 * The multiplexed demo bridge's frame-ordering contract.
 *
 * This is wire behaviour rather than rendering: the real bridge sends exactly
 * one `hello` per socket and sends it first, and every device on the connection
 * defines itself behind it. Two simulators pushed down one socket each want to
 * introduce the bridge themselves, and a duplicated or missing `hello` shows a
 * visitor a fault on the page most of them meet first.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ObservatorySimSocket } from "./observatory-sim";
import type { Payload } from "./weather-sim";

/** A reply in the shape the weather simulator reads, standing in for the API. */
const PAYLOAD: Payload = {
  current_units: { temperature_2m: "°F" },
  current: { temperature_2m: 66.9, is_day: 1, weather_code: 1 },
  daily: { sunrise: ["2026-08-03T13:06"], sunset: ["2026-08-04T02:52"], moon_phase: [0.659] },
};

/** One frame the bridge delivered to the client. */
interface Frame {
  event?: string;
  tag?: string;
  vector?: { device?: string };
}

/** Open the bridge and collect its opening burst. */
function open(): Frame[] {
  const frames: Frame[] = [];
  const socket = new ObservatorySimSocket(async () => PAYLOAD);
  socket.onmessage = (event) => frames.push(JSON.parse(String(event.data)) as Frame);
  // Two turns: the bridge opens on the first and its devices, constructed there,
  // book their own opening burst and deliver it on the second. Well short of the
  // dome's one-second tick, so nothing here is simulation output.
  vi.advanceTimersByTime(1);
  vi.advanceTimersByTime(1);
  return frames;
}

describe("ObservatorySimSocket", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("introduces the bridge exactly once, ahead of everything else", () => {
    const frames = open();

    expect(frames.filter((frame) => frame.event === "hello")).toHaveLength(1);
    expect(frames[0]?.event).toBe("hello");
    // The upstream link is the bridge's to report too, and there is one of it.
    expect(frames.filter((frame) => frame.event === "connection")).toHaveLength(1);
  });

  it("defines both devices behind that one hello", () => {
    const frames = open();

    const defining = frames.filter((frame) => frame.tag === "def");
    expect(new Set(defining.map((frame) => frame.vector?.device))).toEqual(
      new Set(["Dome Simulator", "Open-Meteo"]),
    );
    expect(frames.findIndex((frame) => frame.tag === "def")).toBeGreaterThan(0);
  });
});
