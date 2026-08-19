/** Tests for the two-dot bridge/indiserver connection indicator. */

import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { receive, renderConnected } from "../testing/render";
import { ConnectionStatus } from "./connection-status";

afterEach(cleanup);

/**
 * The state word next to the given dot label.
 *
 * It is the last child of the row either way, but not in the same channel: the
 * healthy state stays visually hidden while the failure is written out on
 * screen, because colour alone could not tell them apart.
 */
function statusOf(label: string): string | null {
  return wordFor(label).textContent;
}

/**
 * The element carrying the state word for the given dot label.
 *
 * Returned rather than just its text because *which channel it is in* is the
 * fix: the failure is on screen and the healthy state is `sr-only`.
 */
function wordFor(label: string): HTMLElement {
  const row = screen.getByText(label).parentElement;
  const word = row?.lastElementChild;
  if (!(word instanceof HTMLElement)) throw new Error(`no state word for ${label}`);
  return word;
}

/** The dot graphic for the given label: the first child of its row. */
function dotFor(label: string): HTMLElement {
  const row = screen.getByText(label).parentElement;
  const dot = row?.firstElementChild;
  if (!(dot instanceof HTMLElement)) throw new Error(`no dot for ${label}`);
  return dot;
}

describe("ConnectionStatus", () => {
  it("shows the bridge connected and indiserver down after the socket opens", () => {
    renderConnected(<ConnectionStatus />);
    expect(statusOf("bridge")).toBe("connected");
    expect(statusOf("indiserver")).toBe("offline");
  });

  it("marks indiserver connected when the bridge reports upstream up", () => {
    const { socket } = renderConnected(<ConnectionStatus />);
    receive(socket, { event: "connection", connected: true });
    expect(statusOf("bridge")).toBe("connected");
    expect(statusOf("indiserver")).toBe("connected");
  });

  it("writes the failure on screen and leaves only the healthy state sr-only", () => {
    // The whole point of the fix: a sighted colour-blind operator reads the
    // failure as a word. Putting "offline" in the same visually hidden span as
    // "connected" would keep every assertion above green and take the alarm off
    // the screen, which is the state it exists for.
    renderConnected(<ConnectionStatus />);
    expect(wordFor("bridge")).toHaveTextContent("connected");
    expect(wordFor("bridge")).toHaveClass("sr-only");
    expect(wordFor("indiserver")).toHaveTextContent("offline");
    expect(wordFor("indiserver")).not.toHaveClass("sr-only");
  });

  it("takes the word back off the screen when the link recovers", () => {
    // The affirmative stays hidden on purpose: two permanent extra lines in a
    // 16rem sidebar, for the state that is true almost always.
    const { socket } = renderConnected(<ConnectionStatus />);
    receive(socket, { event: "connection", connected: true });
    expect(wordFor("indiserver")).toHaveTextContent("connected");
    expect(wordFor("indiserver")).toHaveClass("sr-only");
  });

  it("draws connected as a filled disc and offline as a hollow ring", () => {
    // Shape, not hue. Colour was the whole difference before, and under
    // simulated deuteranopia the two fills measured 1.08:1 apart - so this dot
    // said nothing at all to the operator it most needed to reach. The absence
    // of any fill utility on the offline dot is the assertion that matters:
    // re-tinting the palette leaves it passing, filling the ring back in does not.
    const { socket } = renderConnected(<ConnectionStatus />);
    expect(dotFor("bridge")).toHaveClass("bg-state-ok-ink", "border-state-ok-ink");
    expect(dotFor("indiserver")).toHaveClass("border-state-alert");
    expect(dotFor("indiserver").className).not.toMatch(/\bbg-\S/);

    receive(socket, { event: "connection", connected: true });
    expect(dotFor("indiserver")).toHaveClass("bg-state-ok-ink");
  });

  it("keeps the dot out of the accessibility tree, since the word carries it", () => {
    renderConnected(<ConnectionStatus />);
    expect(dotFor("bridge")).toHaveAttribute("aria-hidden");
    expect(dotFor("indiserver")).toHaveAttribute("aria-hidden");
  });
});
