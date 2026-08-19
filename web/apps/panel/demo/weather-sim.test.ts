/**
 * Drives the Open-Meteo simulator without a network, over an injected payload.
 *
 * The disconnect path is the one that had drifted: `on_disconnect` in
 * `examples/openmeteo_device.py` idles all three published properties, and a
 * simulator that leaves one of them Ok keeps showing a reading it no longer has.
 */

import type { Vector } from "@indikit/client";
import { describe, expect, it } from "vitest";
import { WeatherSimSocket } from "./weather-sim";

const DEVICE = "Open-Meteo";

/** A reply in the shape the simulator reads, standing in for the API. */
const PAYLOAD = {
  current_units: { temperature_2m: "°F" },
  current: {
    temperature_2m: 66.9,
    relative_humidity_2m: 95,
    cloud_cover: 12,
    wind_speed_10m: 2.4,
    wind_gusts_10m: 2.5,
    pressure_msl: 1008.2,
    wind_direction_10m: 304,
    apparent_temperature: 71.6,
    is_day: 1,
    weather_code: 1,
  },
  daily: { sunrise: ["2026-08-03T13:06"], sunset: ["2026-08-04T02:52"], moon_phase: [0.659] },
};

/** One frame the simulator delivered to the client. */
interface Frame {
  tag?: string;
  vector?: Vector;
}

/** Let the simulator's timers and awaited fetches run. */
function flush(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

/** The partial CONNECTION write a client sends. */
function connection(member: string): Vector {
  return {
    kind: "switch",
    device: DEVICE,
    name: "CONNECTION",
    state: "Idle",
    perm: "rw",
    rule: "OneOfMany",
    elements: [{ kind: "switch", name: member, value: "On" }],
  } as Vector;
}

/** The partial CONFIG_PROCESS write a client sends. */
function config(member: string): Vector {
  return {
    kind: "switch",
    device: DEVICE,
    name: "CONFIG_PROCESS",
    state: "Idle",
    perm: "rw",
    rule: "AtMostOne",
    elements: [{ kind: "switch", name: member, value: "On" }],
  } as Vector;
}

/** The most recent `set` for one property, if the simulator sent one. */
function latest(frames: Frame[], name: string): Vector | undefined {
  return frames.filter((f) => f.tag === "set" && f.vector?.name === name).at(-1)?.vector;
}

describe("WeatherSimSocket", () => {
  it("idles every published property when the client disconnects", async () => {
    const frames: Frame[] = [];
    const socket = new WeatherSimSocket(async () => PAYLOAD);
    socket.onmessage = (event) => frames.push(JSON.parse(String(event.data)) as Frame);
    await flush();

    socket.send(JSON.stringify({ tag: "new", vector: connection("CONNECT") }));
    await flush();
    expect(latest(frames, "WEATHER_PARAMETERS")?.state).toBe("Ok");
    expect(latest(frames, "SKY")?.state).toBe("Ok");
    frames.length = 0;

    socket.send(JSON.stringify({ tag: "new", vector: connection("DISCONNECT") }));
    await flush();
    expect(latest(frames, "WEATHER_PARAMETERS")?.state).toBe("Idle");
    expect(latest(frames, "WEATHER_STATUS")?.state).toBe("Idle");
    expect(latest(frames, "SKY")?.state).toBe("Idle");
    socket.close();
  });

  it("runs a configuration action and leaves every member Off", async () => {
    const frames: Frame[] = [];
    const socket = new WeatherSimSocket(async () => PAYLOAD);
    socket.onmessage = (event) => frames.push(JSON.parse(String(event.data)) as Frame);
    await flush();

    // Nothing has been saved yet, which is exactly libindi's error case.
    socket.send(JSON.stringify({ tag: "new", vector: config("CONFIG_LOAD") }));
    expect(latest(frames, "CONFIG_PROCESS")?.state).toBe("Alert");

    socket.send(JSON.stringify({ tag: "new", vector: config("CONFIG_SAVE") }));
    const saved = latest(frames, "CONFIG_PROCESS");
    expect(saved?.state).toBe("Ok");
    // A member left On would render as a button stuck in its pressed position.
    expect(saved?.kind === "switch" && saved.elements.every((el) => el.value === "Off")).toBe(true);

    socket.send(JSON.stringify({ tag: "new", vector: config("CONFIG_LOAD") }));
    expect(latest(frames, "CONFIG_PROCESS")?.state).toBe("Ok");

    socket.send(JSON.stringify({ tag: "new", vector: config("CONFIG_PURGE") }));
    expect(latest(frames, "CONFIG_PROCESS")?.state).toBe("Ok");
    socket.send(JSON.stringify({ tag: "new", vector: config("CONFIG_LOAD") }));
    expect(latest(frames, "CONFIG_PROCESS")?.state).toBe("Alert");
  });
});
