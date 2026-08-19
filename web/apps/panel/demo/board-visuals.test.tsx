/**
 * The wind compass's geometry, measured off what it actually draws.
 *
 * The figure carries two variables in one mark - a bearing and a magnitude -
 * and it prints the magnitude in the middle of the same circle the mark points
 * into. That is only legible while the arrow stops short of the digits, and it
 * did not: at the arrow length this figure shipped with, any wind near east or
 * west above about 10 mph ran the shaft straight through the number. So the
 * clearance is the constraint the whole geometry rests on, and these tests
 * measure it from the rendered `d` rather than trusting the constants that
 * derive it.
 *
 * Everything here is read back out of the SVG - centre and radius off the rim
 * circle, the type size off the text element - so a test fails when the drawing
 * changes, not when a constant is renamed.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DaylightBar, WindCompass } from "./board-visuals";

afterEach(() => {
  cleanup();
  // One test pins the machine's timezone; nothing after it inherits that.
  vi.unstubAllEnvs();
});

/** The board's own full-scale wind, so these read as the board reads. */
const MAX_SPEED = 40;

/** A point in the figure's drawing units. */
interface Point {
  x: number;
  y: number;
}

/** The compass currently on screen. */
function figure(): HTMLElement {
  return screen.getByRole("img", { name: /^Wind/ });
}

/** Where the rim is, taken from the rim circle rather than assumed. */
function rim(): { centre: Point; radius: number } {
  const circle = figure().querySelector("circle");
  if (circle === null) throw new Error("the compass drew no rim");
  return {
    centre: { x: Number(circle.getAttribute("cx")), y: Number(circle.getAttribute("cy")) },
    radius: Number(circle.getAttribute("r")),
  };
}

/** The arrow's tip and the midpoint of its two wings, from the path it draws. */
function arrow(): { tip: Point; tail: Point } {
  const path = figure().querySelector("path[data-indi-state]");
  if (path === null) throw new Error("the compass drew no arrow");
  const n = (path.getAttribute("d") ?? "").match(/-?[\d.]+/g)?.map(Number) ?? [];
  const [tipX, tipY, aX, aY, bX, bY] = n;
  if (bY === undefined) throw new Error(`unreadable arrow path: ${path.getAttribute("d")}`);
  return {
    tip: { x: tipX as number, y: tipY as number },
    tail: { x: ((aX as number) + (bX as number)) / 2, y: ((aY as number) + (bY as number)) / 2 },
  };
}

/** Straight-line distance between two points. */
function distance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

/**
 * Half the width the printed speed occupies, in the figure's drawing units.
 *
 * The type size is read off the element; the rest is a property of the type,
 * not of this code. Every reading on the board is `tabular-nums`, so each glyph
 * advances the monospace 0.6 em, and the widest speed this prints is four
 * characters - "18.5" for a gust, "35.2" for the wind that closes the dome.
 */
function speedHalfWidth(printed: string): number {
  const text = within(figure()).getByText(printed);
  const fontSize = Number(text.getAttribute("font-size"));
  if (!Number.isFinite(fontSize) || fontSize === 0) {
    throw new Error(`the speed has no font size: ${text.outerHTML}`);
  }
  return (fontSize * 0.6 * 4) / 2;
}

/** How far the arrow reaches inward from the rim. */
function arrowLength(): number {
  const { centre, radius } = rim();
  return radius - distance(arrow().tip, centre);
}

describe("the wind compass's arrow", () => {
  it("sits on the rim, so its length is the whole of the speed encoding", () => {
    render(<WindCompass direction={90} speed={20} maxSpeed={MAX_SPEED} unit="mph" />);

    // The wings straddle the bearing at the rim; if the arrow floated inward
    // instead, its length would no longer be a distance anybody can read
    // against the circle it is drawn in.
    expect(distance(arrow().tail, rim().centre)).toBeCloseTo(rim().radius, 6);
  });

  it("grows with the wind", () => {
    render(<WindCompass direction={90} speed={0} maxSpeed={MAX_SPEED} unit="mph" />);
    const calm = arrowLength();
    cleanup();

    render(<WindCompass direction={90} speed={20} maxSpeed={MAX_SPEED} unit="mph" />);
    const middling = arrowLength();
    cleanup();

    render(<WindCompass direction={90} speed={MAX_SPEED} maxSpeed={MAX_SPEED} unit="mph" />);
    const full = arrowLength();

    expect(calm).toBeLessThan(middling);
    expect(middling).toBeLessThan(full);
  });

  it("still draws an arrow when the wind is calm, so the bearing stays readable", () => {
    render(<WindCompass direction={90} speed={0} maxSpeed={MAX_SPEED} unit="mph" />);

    expect(arrowLength()).toBeGreaterThan(0);
  });

  it("stops growing above the full-scale wind", () => {
    render(<WindCompass direction={90} speed={MAX_SPEED} maxSpeed={MAX_SPEED} unit="mph" />);
    const full = arrow().tip;
    cleanup();

    // A gust well past the scale, which is the case the board meets on a bad
    // night and the one an unclamped fraction sends through the digits.
    render(<WindCompass direction={90} speed={MAX_SPEED * 2} maxSpeed={MAX_SPEED} unit="mph" />);

    expect(arrow().tip.x).toBeCloseTo(full.x, 6);
    expect(arrow().tip.y).toBeCloseTo(full.y, 6);
  });
});

describe("the arrow's clearance from the printed speed", () => {
  // The failure this guards is not subtle and it shipped: an easterly or
  // westerly wind puts the shaft along the widest axis of the number, so the
  // digits are struck through at exactly the readings a dome is closed on.
  it.each([0, 45, 90, 135, 180, 225, 270, 315])(
    "keeps the tip clear of the digits at full scale, wind from %i degrees",
    (direction) => {
      render(
        <WindCompass direction={direction} speed={MAX_SPEED} maxSpeed={MAX_SPEED} unit="mph" />,
      );

      expect(distance(arrow().tip, rim().centre)).toBeGreaterThan(speedHalfWidth("40"));
    },
  );

  it("keeps the tip clear when a gust drives the speed past full scale", () => {
    render(<WindCompass direction={90} speed={82.5} maxSpeed={MAX_SPEED} unit="mph" />);

    expect(distance(arrow().tip, rim().centre)).toBeGreaterThan(speedHalfWidth("82.5"));
  });

  it("keeps the tip clear at a middling wind and when it is calm", () => {
    render(<WindCompass direction={270} speed={18.5} maxSpeed={MAX_SPEED} unit="mph" />);
    expect(distance(arrow().tip, rim().centre)).toBeGreaterThan(speedHalfWidth("18.5"));
    cleanup();

    render(<WindCompass direction={270} speed={0} maxSpeed={MAX_SPEED} unit="mph" />);
    expect(distance(arrow().tip, rim().centre)).toBeGreaterThan(speedHalfWidth("0"));
  });
});

describe("the wind compass with nothing to report", () => {
  it("prints dashes in the muted ink a blank is drawn in, never in reading ink", () => {
    render(<WindCompass maxSpeed={MAX_SPEED} unit="mph" />);

    const blank = within(figure()).getByText("--");
    expect(blank).toHaveClass("fill-muted-foreground");
    expect(blank).not.toHaveClass("fill-foreground");
  });

  it("prints a real speed in reading ink", () => {
    render(<WindCompass direction={304} speed={12.4} maxSpeed={MAX_SPEED} unit="mph" />);

    const reading = within(figure()).getByText("12.4");
    expect(reading).toHaveClass("fill-foreground");
    expect(reading).not.toHaveClass("fill-muted-foreground");
  });

  it("draws no arrow at all when the bearing is unknown", () => {
    render(<WindCompass speed={12.4} maxSpeed={MAX_SPEED} unit="mph" />);

    expect(screen.getByRole("img", { name: "Wind direction unknown" })).toBeInTheDocument();
    expect(figure().querySelector("path[data-indi-state]")).toBeNull();
  });
});

describe("the gust tick", () => {
  /** The gust mark, which is the one line drawn with a round cap. */
  function gustTick(): Element | null {
    return figure().querySelector('line[stroke-linecap="round"]');
  }

  it("marks a gust outside the rim, on the bearing the wind comes from", () => {
    render(<WindCompass direction={90} speed={12.4} gust={18.5} maxSpeed={MAX_SPEED} unit="mph" />);

    const tick = gustTick();
    if (tick === null) throw new Error("the compass drew no gust tick");
    const { centre, radius } = rim();
    const outer = { x: Number(tick.getAttribute("x2")), y: Number(tick.getAttribute("y2")) };
    // Outside the rim, so it reads as an overshoot of the arrow rather than as
    // a second arrow, and on the wind's own bearing (due east, so due right).
    expect(distance(outer, centre)).toBeGreaterThan(radius);
    expect(outer.y).toBeCloseTo(centre.y, 6);
    expect(outer.x).toBeGreaterThan(centre.x);
  });

  it("draws none when the gust is no stronger than the sustained wind", () => {
    render(<WindCompass direction={90} speed={12.4} gust={12.4} maxSpeed={MAX_SPEED} unit="mph" />);

    expect(gustTick()).toBeNull();
  });

  it("draws none when the driver has published no gust", () => {
    render(<WindCompass direction={90} speed={12.4} maxSpeed={MAX_SPEED} unit="mph" />);

    expect(gustTick()).toBeNull();
  });
});

describe("the daylight bar", () => {
  // The driver's own format, and a moment inside the window it describes. Both
  // are fixed: a bar that reads the wall clock is a test that fails at dawn.
  const SUNRISE = "2026-08-03 13:06";
  const SUNSET = "2026-08-04 02:52";
  const NOON = new Date("2026-08-03T18:00:00Z");

  it("labels the driver's times as the UTC they are, rather than localising them", () => {
    render(<DaylightBar sunrise={SUNRISE} sunset={SUNSET} now={NOON} />);

    expect(screen.getByText("↑ 13:06 UTC")).toBeInTheDocument();
    expect(screen.getByText("02:52 UTC ↓")).toBeInTheDocument();
  });

  it("places now against the driver's UTC times, not against the machine's zone", () => {
    // The driver publishes "2026-08-03 13:06", which every engine is entitled
    // to read as *local* time. The machine is pinned somewhere that is not UTC
    // on purpose: read the wrong way, both ends of the window shift four hours
    // and this moment falls off the bar entirely - but on a UTC box the two
    // readings agree and the mistake is invisible, which is how it would reach
    // an observatory that is not on UTC.
    vi.stubEnv("TZ", "America/New_York");
    const { container } = render(<DaylightBar sunrise={SUNRISE} sunset={SUNSET} now={NOON} />);

    const marker = container.querySelector("div[aria-hidden][style]");
    if (marker === null) throw new Error("no marker for now");
    const left = /left:\s*([\d.]+)%/.exec(marker.getAttribute("style") ?? "")?.[1];
    // 18:00 is 6h33m into a window that runs 11:27 to 04:31 the next day.
    expect(Number(left)).toBeCloseTo(38.4, 0);
  });

  it("marks nothing when now falls outside the window it is drawing", () => {
    const { container } = render(
      <DaylightBar sunrise={SUNRISE} sunset={SUNSET} now={new Date("2026-08-03T06:00:00Z")} />,
    );

    expect(screen.getByText("↑ 13:06 UTC")).toBeInTheDocument();
    expect(container.querySelector("div[aria-hidden][style]")).toBeNull();
  });

  it("draws a plain bar, with no times on it, before the almanac arrives", () => {
    render(<DaylightBar now={NOON} />);

    expect(screen.queryByText(/UTC/)).not.toBeInTheDocument();
  });

  it("draws a plain bar when the times do not make a window", () => {
    render(<DaylightBar sunrise={SUNSET} sunset={SUNRISE} now={NOON} />);

    expect(screen.queryByText(/UTC/)).not.toBeInTheDocument();
  });
});
