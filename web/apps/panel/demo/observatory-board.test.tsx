/**
 * The observatory wallboard, driven by the frames its two drivers really send.
 *
 * The vectors here are the ones `dome-sim.ts` and `weather-sim.ts` emit (and
 * therefore the ones `examples/dome_device.py` and `examples/openmeteo_device.py`
 * emit), so this checks the board against its instruments rather than against
 * its own source.
 *
 * Three things get most of the attention, because they are where a wallboard
 * fails quietly rather than loudly:
 *
 * - **the bearing across the 0/360 seam**, where the only visible symptom of a
 *   regression is a dome that spins the long way round on screen;
 * - **the liveness gate**, where the symptom is a number that is merely old;
 * - **`UNKNOWN`**, which has to stay a neutral third reading and not decay into
 *   either of the two it is not.
 */

import type { IPState } from "@indikit/react";
import { cleanup, receive, renderConnected, screen, within } from "@indikit/react/testing";
import { type ReactElement, StrictMode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { ObservatoryBoard } from "./observatory-board";

const DOME = "Dome Simulator";
const WEATHER = "Open-Meteo";

afterEach(cleanup);

/** The harness socket, named the way the helpers below take it. */
type Socket = Parameters<typeof receive>[0];

// -- the frames the two drivers send ---------------------------------------- //

/** The dome's `CONNECTION`, whose CONNECT member gates every dome reading. */
function domeConnection(connected: boolean) {
  return {
    kind: "switch",
    device: DOME,
    name: "CONNECTION",
    label: "Connection",
    state: "Ok",
    perm: "rw",
    rule: "OneOfMany",
    elements: [
      { kind: "switch", name: "CONNECT", label: "Connect", value: connected ? "On" : "Off" },
      { kind: "switch", name: "DISCONNECT", label: "Disconnect", value: connected ? "Off" : "On" },
    ],
  };
}

/** `ABS_DOME_POSITION`, which wraps at 360 and is the whole reason for the hook. */
function domePosition(azimuth: number, state: IPState = "Ok") {
  return {
    kind: "number",
    device: DOME,
    name: "ABS_DOME_POSITION",
    label: "Absolute Position",
    state,
    perm: "rw",
    elements: [
      {
        kind: "number",
        name: "DOME_ABSOLUTE_POSITION",
        label: "Degrees",
        min: 0,
        max: 360,
        value: azimuth,
      },
    ],
  };
}

/** `DOME_SHUTTER`; `null` is the driver's own "neither member is On" case. */
function domeShutter(on: "SHUTTER_OPEN" | "SHUTTER_CLOSE" | null, state: IPState = "Ok") {
  return {
    kind: "switch",
    device: DOME,
    name: "DOME_SHUTTER",
    label: "Shutter",
    state,
    perm: "rw",
    rule: "OneOfMany",
    elements: [
      {
        kind: "switch",
        name: "SHUTTER_OPEN",
        label: "Open",
        value: on === "SHUTTER_OPEN" ? "On" : "Off",
      },
      {
        kind: "switch",
        name: "SHUTTER_CLOSE",
        label: "Close",
        value: on === "SHUTTER_CLOSE" ? "On" : "Off",
      },
    ],
  };
}

/** `DOME_PARK`; which member is On follows the *request*, and the state says whether it finished. */
function domePark(on: "PARK" | "UNPARK" | null, state: IPState = "Ok") {
  return {
    kind: "switch",
    device: DOME,
    name: "DOME_PARK",
    label: "Parking",
    state,
    perm: "rw",
    rule: "OneOfMany",
    elements: [
      { kind: "switch", name: "PARK", label: "Park", value: on === "PARK" ? "On" : "Off" },
      { kind: "switch", name: "UNPARK", label: "Unpark", value: on === "UNPARK" ? "On" : "Off" },
    ],
  };
}

/** The readings the Open-Meteo driver publishes, from a recorded response. */
const READINGS: Record<string, number> = {
  TEMPERATURE: 66.9,
  HUMIDITY: 95,
  CLOUD_COVER: 31,
  WIND_SPEED: 12.4,
  WIND_GUST: 18.5,
  PRESSURE: 1008.2,
  WIND_DIRECTION: 304,
};

/** `WEATHER_PARAMETERS`; the driver parks it at `Idle` when the source stops answering. */
function weatherParameters(overrides: Record<string, number> = {}, state: IPState = "Ok") {
  const values = { ...READINGS, ...overrides };
  return {
    kind: "number",
    device: WEATHER,
    name: "WEATHER_PARAMETERS",
    label: "Weather",
    state,
    perm: "ro",
    elements: Object.entries(values).map(([name, value]) => ({ kind: "number", name, value })),
  };
}

/** `WEATHER_STATUS`, one light per reading. `labels` overrides a label, empty string included. */
function weatherStatus(alerting: string[] = [], labels: Record<string, string> = {}) {
  const names = ["TEMPERATURE", "HUMIDITY", "CLOUD_COVER", "WIND_SPEED", "WIND_GUST", "PRESSURE"];
  return {
    kind: "light",
    device: WEATHER,
    name: "WEATHER_STATUS",
    label: "Status",
    state: alerting.length > 0 ? "Alert" : "Ok",
    elements: names.map((name) => ({
      kind: "light",
      name,
      label: labels[name] ?? name.charAt(0) + name.slice(1).toLowerCase().replace("_", " "),
      value: alerting.includes(name) ? "Alert" : "Ok",
    })),
  };
}

// -- publishing ------------------------------------------------------------- //

/** Define the dome's four properties, connected and pointing at `azimuth`. */
function publishDome(
  socket: Socket,
  options: { connected?: boolean; azimuth?: number } = {},
): void {
  const { connected = true, azimuth = 137 } = options;
  for (const vector of [
    domeConnection(connected),
    domePosition(azimuth),
    domeShutter("SHUTTER_OPEN"),
    domePark("UNPARK"),
  ]) {
    receive(socket, { tag: "def", vector });
  }
}

/** Define everything the weather driver publishes, with live readings. */
function publishWeather(socket: Socket, alerting: string[] = []): void {
  for (const vector of [
    weatherParameters(),
    weatherStatus(alerting),
    {
      kind: "text",
      device: WEATHER,
      name: "SKY",
      state: "Ok",
      perm: "ro",
      elements: [
        { kind: "text", name: "CONDITIONS", label: "Conditions", value: "Mainly clear" },
        { kind: "text", name: "DAYLIGHT", label: "Daylight", value: "Night" },
      ],
    },
    {
      kind: "text",
      device: WEATHER,
      name: "ALMANAC",
      state: "Ok",
      perm: "ro",
      elements: [
        { kind: "text", name: "SUNRISE", label: "Sunrise (UTC)", value: "2026-08-03 13:06" },
        { kind: "text", name: "SUNSET", label: "Sunset (UTC)", value: "2026-08-04 02:52" },
        { kind: "text", name: "MOON_PHASE", label: "Moon phase", value: "Waning gibbous (0.66)" },
      ],
    },
  ]) {
    receive(socket, { tag: "def", vector });
  }
}

// -- reading the board ------------------------------------------------------ //

/**
 * The rotation the dome figure is actually drawing, in degrees.
 *
 * This is the one place the continuously tracked total is observable, and the
 * only reason a test here looks at a `transform` at all: the whole point of the
 * hook is that the number handed to CSS is deliberately not the bearing.
 */
function domeRotation(): number {
  const group = domeFigure().querySelector("g");
  if (group === null) throw new Error("the dome figure is drawing no aperture");
  const rotation = /rotate\((-?[\d.]+)deg\)/.exec(group.getAttribute("style") ?? "");
  if (rotation === null) throw new Error(`no rotation: ${group.getAttribute("style")}`);
  return Number(rotation[1]);
}

/** The dome plan currently on screen. */
function domeFigure(): HTMLElement {
  return screen.getByRole("img", { name: /^Dome/ });
}

/**
 * The band drawn across the wall where the slit is - the shutter reading itself.
 *
 * The stroked path, as against the filled corridor an open shutter also draws:
 * this is the mark whose shape has to differ between the three readings.
 */
function slitBand(): Element {
  const band = domeFigure().querySelector("g path[stroke-width]");
  if (band === null) throw new Error("the dome figure drew no slit band");
  return band;
}

/** The shutter word, which is the largest thing on the board. */
function shutterWord(): string {
  const word = screen.getByRole("heading", { level: 1 }).lastElementChild;
  if (word === null) throw new Error("the board drew no shutter word");
  return word.textContent ?? "";
}

/** The figure printed under one of the dome's two captions. */
function underCaption(caption: string): string {
  const value = screen.getByText(caption).nextElementSibling;
  if (value === null) throw new Error(`nothing printed under ${caption}`);
  return (value.textContent ?? "").replace(/\s+/g, " ").trim();
}

/** One weather tile: the number under its caption and the state word under that. */
function tile(caption: string): { value: string; state: string } {
  const value = screen.getByText(caption).nextElementSibling;
  const state = value?.nextElementSibling?.nextElementSibling;
  if (value == null || state == null) throw new Error(`no tile under ${caption}`);
  return { value: value.textContent ?? "", state: state.textContent ?? "" };
}

/** The derived slit-to-wind line: the angle it prints and the word under it. */
function slit(): { angle: string; qualifier: string } {
  const line = screen.getByText(/^Slit\s+off the wind$/);
  const qualifier = line.nextElementSibling;
  if (qualifier === null) throw new Error("the slit line has no qualifier under it");
  return {
    angle: (line.textContent ?? "")
      .replace(/\s+/g, " ")
      .replace("Slit ", "")
      .replace(" off the wind", ""),
    qualifier: qualifier.textContent ?? "",
  };
}

/** The tile grid, found through the first caption it draws. */
function tileGrid(): Element {
  const grid = screen.getByText("Wind").closest("div")?.parentElement;
  if (grid == null) throw new Error("no tile grid");
  return grid;
}

// -- the bearing across the seam -------------------------------------------- //

/**
 * Every seam case, run plainly and then again under `StrictMode`.
 *
 * `useContinuousBearing` writes a ref *during render*, which is safe only
 * because the write is idempotent: a second pass over the same bearing takes a
 * zero step and returns the total it already has. `StrictMode` renders
 * everything twice, so the same sequence has to land on the same number - and
 * if it does not, the figure silently double-counts every move the dome makes
 * while a single-pass test stays green. That is what stops the ref write being
 * "fixed" into an effect, or into an accumulation that runs once per render.
 */
describe.each([
  ["", (board: ReactElement) => board],
  [", under StrictMode", (board: ReactElement) => <StrictMode>{board}</StrictMode>],
])("the dome's rotation across the 0/360 seam%s", (_mode, wrap) => {
  /** The board, rendered the way this pass renders it. */
  function renderBoard() {
    return renderConnected(wrap(<ObservatoryBoard />));
  }

  it("turns two degrees, not 358 backwards, when the dome crosses north", () => {
    const { socket } = renderBoard();
    publishDome(socket, { azimuth: 359 });
    expect(domeRotation()).toBe(359);

    receive(socket, { tag: "set", vector: domePosition(1) });

    // 361: the figure keeps turning the way the dome turned. 1 is the naive
    // binding sweeping backwards; 363 is a second render pass counting again.
    expect(domeRotation()).toBe(361);
  });

  it("turns two degrees backwards, not 358 forwards, when it crosses the other way", () => {
    const { socket } = renderBoard();
    publishDome(socket, { azimuth: 1 });
    expect(domeRotation()).toBe(1);

    receive(socket, { tag: "set", vector: domePosition(359) });

    expect(domeRotation()).toBe(-1);
  });

  it("keeps counting past a full lap rather than snapping back to zero", () => {
    const { socket } = renderBoard();
    publishDome(socket, { azimuth: 0 });
    for (const azimuth of [90, 180, 270, 0]) {
      receive(socket, { tag: "set", vector: domePosition(azimuth) });
    }

    // A whole lap forwards is 360, which is legitimately outside [0, 360).
    expect(domeRotation()).toBe(360);
  });

  it("adds up a run of small moves either side of north", () => {
    const { socket } = renderBoard();
    publishDome(socket, { azimuth: 350 });
    for (const azimuth of [10, 350, 30]) {
      receive(socket, { tag: "set", vector: domePosition(azimuth) });
    }

    // +20, -20, +40.
    expect(domeRotation()).toBe(390);
  });

  it("still reports the wrapped bearing to a reader who cannot see the figure", () => {
    const { socket } = renderBoard();
    publishDome(socket, { azimuth: 359 });
    receive(socket, { tag: "set", vector: domePosition(1) });

    // The running total is for CSS only. The azimuth is a compass bearing and
    // there is no such bearing as 361.
    expect(underCaption("Azimuth")).toContain("1°");
    expect(screen.getByRole("img", { name: /^Dome at 1 degrees, N/ })).toBeInTheDocument();
  });

  it("prints a bearing a compass has, whatever the driver puts on the wire", () => {
    // `ABS_DOME_POSITION` declares 0..360 and a driver is free to ignore it -
    // an encoder count past a lap, or a negative relative move applied without
    // wrapping. The reader gets a bearing either way.
    const { socket } = renderBoard();
    publishDome(socket, { azimuth: 400 });

    expect(underCaption("Azimuth")).toContain("40°");
    expect(screen.getByRole("img", { name: /^Dome at 40 degrees, NE/ })).toBeInTheDocument();
    // And the figure still gets the un-normalised number, which is the whole
    // point of the split: 400 is where the dome has turned to.
    expect(domeRotation()).toBe(400);
  });

  it("forgets the total when the dome stops reporting, and restarts from the new bearing", () => {
    const { socket } = renderBoard();
    publishDome(socket, { azimuth: 350 });
    receive(socket, { tag: "set", vector: domePosition(10) });
    expect(domeRotation()).toBe(370);

    receive(socket, { tag: "set", vector: domeConnection(false) });
    expect(domeFigure().querySelector("g")).toBeNull();

    receive(socket, { tag: "set", vector: domeConnection(true) });
    // 10, not 370: a total carried across a gap in the reporting would make the
    // figure spin a lap it has no evidence for.
    expect(domeRotation()).toBe(10);
  });

  it("dashes the wall when there is no bearing, and draws it solid when there is", () => {
    const { socket } = renderBoard();
    const wall = () => domeFigure().querySelectorAll("circle")[1];

    // Solid against dashed is the only thing separating "facing north" from
    // "position unknown", so the wall carries it and not a colour.
    expect(wall()).toHaveAttribute("stroke-dasharray");
    publishDome(socket, { azimuth: 137 });
    expect(wall()).not.toHaveAttribute("stroke-dasharray");
  });
});

// -- the shutter ------------------------------------------------------------ //

describe("the shutter's three readings", () => {
  it("reads OPEN when the driver reports the open member on", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishDome(socket);

    expect(shutterWord()).toBe("OPEN");
  });

  it("reads CLOSED when the driver reports the close member on", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishDome(socket);
    receive(socket, { tag: "set", vector: domeShutter("SHUTTER_CLOSE") });

    expect(shutterWord()).toBe("CLOSED");
  });

  it("reads UNKNOWN when the dome has published no shutter vector at all", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    receive(socket, { tag: "def", vector: domeConnection(true) });
    receive(socket, { tag: "def", vector: domePosition(137) });

    expect(shutterWord()).toBe("UNKNOWN");
  });

  it("reads UNKNOWN when neither member is on", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishDome(socket);
    receive(socket, { tag: "set", vector: domeShutter(null) });

    expect(shutterWord()).toBe("UNKNOWN");
  });

  it("reads UNKNOWN after an aborted move, keeping the azimuth it still knows", () => {
    // Connect, Open, Abort: `dome-sim.ts` puts DOME_SHUTTER into Alert with
    // "Shutter operation aborted. Status: unknown." while the switch still
    // reports the position that was *commanded*. Repeating that would be the
    // board making something up; the azimuth is unaffected and stays.
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishDome(socket, { azimuth: 137 });
    expect(shutterWord()).toBe("OPEN");

    receive(socket, { tag: "set", vector: domeShutter("SHUTTER_OPEN", "Alert") });

    expect(shutterWord()).toBe("UNKNOWN");
    expect(underCaption("Azimuth")).toContain("137°");
  });

  it("reads UNKNOWN when the dome driver is disconnected", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishDome(socket);
    expect(shutterWord()).toBe("OPEN");

    receive(socket, { tag: "set", vector: domeConnection(false) });

    expect(shutterWord()).toBe("UNKNOWN");
  });

  it("draws UNKNOWN as a neutral break in the wall, never as an alarm", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishDome(socket, { azimuth: 137 });
    receive(socket, { tag: "set", vector: domeShutter("SHUTTER_OPEN", "Alert") });

    // Neutral ink, not the state hue - the vector is in Alert and the board
    // still refuses to paint the aperture as an alarm.
    expect(slitBand()).toHaveClass("stroke-muted-foreground");
    expect(slitBand().getAttribute("class")).not.toContain("var(--indi-state)");
    // And there is no corridor: a lit corridor says the instrument is looking
    // out through the gap, which is exactly what nobody knows.
    expect(domeFigure().querySelectorAll("g path")).toHaveLength(1);
  });

  it("separates its three readings by shape before it separates them by hue", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishDome(socket, { azimuth: 137 });

    // Open: an unbroken band in the state hue, over the corridor it looks down.
    expect(domeFigure().querySelectorAll("g path")).toHaveLength(2);
    expect(slitBand()).not.toHaveAttribute("stroke-dasharray");
    const open = Number(slitBand().getAttribute("stroke-width"));

    // Closed: a solid shutter panel in foreground ink, and no corridor.
    receive(socket, { tag: "set", vector: domeShutter("SHUTTER_CLOSE") });
    expect(domeFigure().querySelectorAll("g path")).toHaveLength(1);
    expect(slitBand()).toHaveClass("stroke-foreground");
    expect(slitBand()).not.toHaveAttribute("stroke-dasharray");
    expect(Number(slitBand().getAttribute("stroke-width"))).toBeLessThan(open);

    // Unknown: the same span, dashed.
    receive(socket, { tag: "set", vector: domeShutter(null) });
    expect(slitBand()).toHaveAttribute("stroke-dasharray");
  });
});

// -- the park state machine -------------------------------------------------- //

describe("the park readout", () => {
  it.each([
    ["PARK", "Ok", "PARKED"],
    ["PARK", "Busy", "PARKING"],
    ["UNPARK", "Ok", "UNPARKED"],
    ["UNPARK", "Busy", "UNPARKING"],
    ["PARK", "Alert", "UNKNOWN"],
    ["UNPARK", "Alert", "UNKNOWN"],
  ] as const)("reads %s at %s as %s", (member, state, expected) => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishDome(socket);
    receive(socket, { tag: "set", vector: domePark(member, state) });

    expect(underCaption("Park")).toBe(expected);
  });

  it("reads UNKNOWN when neither member is on", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishDome(socket);
    receive(socket, { tag: "set", vector: domePark(null) });

    expect(underCaption("Park")).toBe("UNKNOWN");
  });

  it("reads UNKNOWN when the dome has published no park vector at all", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    receive(socket, { tag: "def", vector: domeConnection(true) });
    receive(socket, { tag: "def", vector: domePosition(137) });

    expect(underCaption("Park")).toBe("UNKNOWN");
  });

  it("reads UNKNOWN once the driver disconnects, not the last state it was in", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishDome(socket);
    receive(socket, { tag: "set", vector: domePark("PARK") });
    expect(underCaption("Park")).toBe("PARKED");

    receive(socket, { tag: "set", vector: domeConnection(false) });

    expect(underCaption("Park")).toBe("UNKNOWN");
  });
});

// -- the liveness gate ------------------------------------------------------- //

describe("the liveness gate", () => {
  it("blanks the dome's azimuth rather than repeating it when the driver disconnects", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishDome(socket, { azimuth: 137 });
    expect(underCaption("Azimuth")).toContain("137°");

    receive(socket, { tag: "set", vector: domeConnection(false) });

    expect(underCaption("Azimuth")).toBe("--");
    // Not merely "shows a dash somewhere": the last reading is gone from the
    // figure's label too, where a stale number reads as fact.
    expect(screen.queryByText(/137/)).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Dome position unknown" })).toBeInTheDocument();
  });

  it("blanks every weather reading when the source stops answering", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishWeather(socket);
    expect(tile("Temperature").value).toBe("66.9");
    expect(tile("Wind").value).toBe("12.4");

    // The driver parks its readings at Idle when Open-Meteo stops answering.
    receive(socket, { tag: "set", vector: weatherParameters({}, "Idle") });

    for (const caption of ["Wind", "Gust", "Cloud", "Humidity", "Temperature", "Pressure"]) {
      expect(tile(caption).value).toBe("--");
      expect(tile(caption).state).toBe("no data");
    }
    expect(screen.queryByText("66.9")).not.toBeInTheDocument();
    expect(screen.queryByText("12.4")).not.toBeInTheDocument();
  });

  it("drops the alert line when the driver parks its lights with the readings", () => {
    // Both real drivers park the two vectors in one go - `WEATHER_PARAMETERS`
    // at Idle and every light in `WEATHER_STATUS` at Idle (`_go_offline` in
    // `examples/openmeteo_device.py`, `parkReadings` in `weather-sim.ts`) - and
    // the header line has to go with them, or the board is naming a fault it
    // can no longer see. This is that path, and the board no longer depends on
    // it: the line is gated on `live` the way every other reading is.
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishWeather(socket, ["HUMIDITY"]);
    expect(screen.getByText("Alert: Humidity")).toBeInTheDocument();

    receive(socket, { tag: "set", vector: weatherParameters({}, "Idle") });
    receive(socket, {
      tag: "set",
      vector: {
        kind: "light",
        device: WEATHER,
        name: "WEATHER_STATUS",
        state: "Idle",
        elements: [{ kind: "light", name: "HUMIDITY", label: "Humidity", value: "Idle" }],
      },
    });

    expect(screen.queryByText(/^Alert:/)).not.toBeInTheDocument();
    expect(tile("Humidity").state).toBe("no data");
  });

  it("blanks the wind compass and the derived slit angle with them", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishDome(socket, { azimuth: 137 });
    publishWeather(socket);
    expect(slit().angle).not.toBe("--");

    receive(socket, { tag: "set", vector: weatherParameters({}, "Idle") });

    expect(screen.getByRole("img", { name: "Wind direction unknown" })).toBeInTheDocument();
    expect(slit()).toEqual({ angle: "--", qualifier: "unknown" });
  });

  it("prints the compass speed in muted ink once the source is dead", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishWeather(socket);
    const compass = () => screen.getByRole("img", { name: /^Wind/ });
    expect(within(compass()).getByText("12.4")).toHaveClass("fill-foreground");

    receive(socket, { tag: "set", vector: weatherParameters({}, "Idle") });

    expect(within(compass()).getByText("--")).toHaveClass("fill-muted-foreground");
  });

  it("keeps the weather readings when it is the dome that has gone", () => {
    // Two instruments, two gates. A single liveness flag would blank both.
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishDome(socket, { azimuth: 137 });
    publishWeather(socket);

    receive(socket, { tag: "set", vector: domeConnection(false) });

    expect(tile("Temperature").value).toBe("66.9");
    expect(underCaption("Azimuth")).toBe("--");
  });

  it("keeps the dome's readings when it is the weather that has gone", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishDome(socket, { azimuth: 137 });
    publishWeather(socket);

    receive(socket, { tag: "set", vector: weatherParameters({}, "Idle") });

    expect(underCaption("Azimuth")).toContain("137°");
    expect(shutterWord()).toBe("OPEN");
  });
});

describe("the missing-feed line", () => {
  it("keeps its dashes out of the sentence a screen reader hears", () => {
    renderConnected(<ObservatoryBoard />);

    // The `--` is the mark this board already uses for a reading it does not
    // have, and it is decoration beside a sentence that says the same thing.
    // Folding it into the sentence would change the accessible name; that is
    // the whole reason it lives in a span of its own.
    const sentence = screen.getByText("Weather source is not answering");
    expect(sentence).not.toHaveAttribute("aria-hidden");

    const dashes = sentence.previousElementSibling;
    expect(dashes).toHaveTextContent("--");
    expect(dashes).toHaveAttribute("aria-hidden");
  });

  it("gives way to the conditions once the source answers", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishWeather(socket);

    expect(screen.queryByText("Weather source is not answering")).not.toBeInTheDocument();
    expect(screen.getByText("Mainly clear")).toBeInTheDocument();
    expect(screen.getByText(/Night/)).toBeInTheDocument();
  });
});

// -- the slit-to-wind readout ------------------------------------------------ //

describe("the slit-to-wind angle", () => {
  it.each([
    // Straddling north, where a subtraction gives the reflex angle instead.
    [350, 10, "20°", "head on"],
    [10, 350, "20°", "head on"],
    [355, 25, "30°", "quartering"],
    [350, 50, "60°", "crosswind"],
    [340, 100, "120°", "crosswind"],
    [350, 111, "121°", "quartering"],
    [350, 141, "151°", "downwind"],
    // Nowhere near the seam, for the plain reading of each band.
    [0, 20, "20°", "head on"],
    [0, 90, "90°", "crosswind"],
    [0, 180, "180°", "downwind"],
    [180, 0, "180°", "downwind"],
  ] as const)(
    "reads a dome at %i with the wind from %i as %s, %s",
    (azimuth, windFrom, angle, qualifier) => {
      const { socket } = renderConnected(<ObservatoryBoard />);
      publishDome(socket, { azimuth });
      publishWeather(socket);
      receive(socket, {
        tag: "set",
        vector: weatherParameters({ WIND_DIRECTION: windFrom }),
      });

      expect(slit()).toEqual({ angle, qualifier });
    },
  );

  it("says nothing about the wind while the dome position is unknown", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishWeather(socket);

    // The weather is live; the angle is a two-instrument quantity and one of
    // the instruments is not reporting.
    expect(tile("Wind").value).toBe("12.4");
    expect(slit()).toEqual({ angle: "--", qualifier: "unknown" });
  });
});

// -- the tiles ---------------------------------------------------------------- //

describe("the weather tiles", () => {
  it("leads with wind and rules off the two readings that only explain", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishWeather(socket);

    const order = Array.from(tileGrid().children).map((child) =>
      child.getAttribute("data-slot") === "separator"
        ? null
        : (child.querySelector("p")?.firstChild?.textContent ?? "?"),
    );

    // Wind and gust first because they are what closes a dome; the rule falls
    // between the four readings that can stop the night and the two that only
    // put them in context.
    expect(order).toEqual(["Wind", "Gust", "Cloud", "Humidity", null, "Temperature", "Pressure"]);
  });

  it("captions each reading with the unit the driver's request asked for", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishWeather(socket);

    const unit = (caption: string) => screen.getByText(caption).querySelector("span")?.textContent;
    expect(unit("Wind")).toBe("mph");
    expect(unit("Gust")).toBe("mph");
    expect(unit("Cloud")).toBe("%");
    expect(unit("Humidity")).toBe("%");
    expect(unit("Temperature")).toBe("°F");
    expect(unit("Pressure")).toBe("hPa");
  });

  it("prints each reading's condition as a word, not as a colour alone", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishWeather(socket, ["HUMIDITY", "CLOUD_COVER"]);

    expect(tile("Humidity").state).toBe("Alert");
    expect(tile("Cloud").state).toBe("Alert");
    expect(tile("Temperature").state).toBe("Ok");
  });

  it("claims no verdict on a reading the driver has not lit yet", () => {
    // The numbers and the lights are two vectors, so there is a moment with a
    // reading and no judgement on it. "Ok" is a judgement, and on a board a
    // dome is closed from it has to have been made by the instrument.
    const { socket } = renderConnected(<ObservatoryBoard />);
    receive(socket, { tag: "def", vector: weatherParameters() });

    expect(tile("Humidity").value).toBe("95");
    expect(tile("Humidity").state).toBe("Idle");
  });

  it("names the readings holding the dome shut", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishWeather(socket, ["HUMIDITY", "CLOUD_COVER"]);

    expect(screen.getByText("Alert: Humidity · Cloud cover")).toBeInTheDocument();
  });

  it("says nothing about alerts when every reading is inside its limits", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishWeather(socket);

    expect(screen.queryByText(/^Alert:/)).not.toBeInTheDocument();
  });

  it("falls back to the INDI name when a driver ships an empty label", () => {
    // libindi does ship elements whose label is the empty string, and `??`
    // treats that as present - so the line would name the fault with nothing.
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishWeather(socket);
    receive(socket, {
      tag: "def",
      vector: weatherStatus(["HUMIDITY"], { HUMIDITY: "" }),
    });

    expect(screen.getByText("Alert: HUMIDITY")).toBeInTheDocument();
  });

  it("updates one reading in place and leaves the others alone", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishWeather(socket);

    receive(socket, {
      tag: "set",
      vector: {
        kind: "number",
        device: WEATHER,
        name: "WEATHER_PARAMETERS",
        state: "Ok",
        perm: "ro",
        elements: [{ kind: "number", name: "CLOUD_COVER", value: 4 }],
      },
    });

    expect(tile("Cloud").value).toBe("4");
    expect(tile("Temperature").value).toBe("66.9");
  });
});

// -- the almanac -------------------------------------------------------------- //

describe("the moon", () => {
  /** The moon figure, and the phase named beside it. */
  function moon(): { figure: HTMLElement; named: string } {
    const figure = screen.getByRole("img", { name: /^Moon/ });
    return { figure, named: figure.nextElementSibling?.textContent ?? "" };
  }

  it("draws the disc at the fraction the almanac reports, and names it without the number", () => {
    const { socket } = renderConnected(<ObservatoryBoard />);
    publishWeather(socket);

    // "Waning gibbous (0.66)": the fraction drives the drawing, the words go
    // beside it, and the number is in neither of them twice.
    expect(moon().figure).toHaveAccessibleName("Moon 77% illuminated");
    expect(moon().named).toBe("Waning gibbous");
  });

  it("shows a placeholder while the driver has defined the phase but not filled it", () => {
    // `openmeteo_device.py` defines ALMANAC empty and fills it on its first
    // fetch, so an empty string is "not yet" exactly as `undefined` is.
    const { socket } = renderConnected(<ObservatoryBoard />);
    receive(socket, {
      tag: "def",
      vector: {
        kind: "text",
        device: WEATHER,
        name: "ALMANAC",
        state: "Idle",
        perm: "ro",
        elements: [
          { kind: "text", name: "SUNRISE", label: "Sunrise (UTC)", value: "" },
          { kind: "text", name: "SUNSET", label: "Sunset (UTC)", value: "" },
          { kind: "text", name: "MOON_PHASE", label: "Moon phase", value: "" },
        ],
      },
    });

    expect(moon().figure).toHaveAccessibleName("Moon phase unknown");
    expect(moon().named).toBe("--");
  });
});

// -- what the board shows before anything arrives ----------------------------- //

describe("the board before any frame arrives", () => {
  it("draws every figure and blanks every reading, alarming about nothing", () => {
    renderConnected(<ObservatoryBoard />);

    expect(shutterWord()).toBe("UNKNOWN");
    expect(underCaption("Azimuth")).toBe("--");
    expect(underCaption("Park")).toBe("UNKNOWN");
    expect(screen.getByRole("img", { name: "Dome position unknown" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Wind direction unknown" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Moon phase unknown" })).toBeInTheDocument();
    expect(screen.queryByText(/^Alert:/)).not.toBeInTheDocument();
  });
});
