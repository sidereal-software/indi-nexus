/** Tests for the state indicators: which state they declare, and which ones pulse. */

import { IPState } from "@indi-nexus/client";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { StateBadge } from "./state-badge";

afterEach(cleanup);

describe("StateBadge", () => {
  // The colour itself lives in the theme, keyed off this attribute, so asserting
  // the attribute tests the contract rather than whichever class name is current.
  it.each([IPState.Idle, IPState.Ok, IPState.Busy, IPState.Alert])(
    "declares %s so the theme can colour it",
    (state) => {
      render(<StateBadge state={state} />);
      const badge = screen.getByText(state);
      expect(badge).toHaveAttribute("data-indi-state", state);
      expect(badge).toHaveClass("bg-[var(--indi-state)]");
    },
  );

  it("pulses only while Busy, and only when motion is welcome", () => {
    render(<StateBadge state="Busy" />);
    expect(screen.getByText("Busy")).toHaveClass("motion-safe:animate-pulse");

    for (const state of [IPState.Idle, IPState.Ok, IPState.Alert]) {
      cleanup();
      render(<StateBadge state={state} />);
      expect(screen.getByText(state).className).not.toContain("animate-pulse");
    }
  });

  it("merges a caller-supplied class name", () => {
    render(<StateBadge state="Ok" className="custom-class" />);
    expect(screen.getByText("Ok")).toHaveClass("custom-class");
  });
});
