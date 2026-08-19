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

  it("marks only Busy as pulsing", () => {
    // The animation itself lives on `[data-indi-pulse]::after` in the theme, held
    // behind a `prefers-reduced-motion: no-preference` query, so this attribute is
    // the whole of the component's half of the contract. What the theme then does
    // with it - that the keyframes move nothing but transform and opacity, and
    // that they apply to a pseudo-element - is asserted in `theme-contract.test.tsx`,
    // which can read the stylesheet that jsdom cannot.
    render(<StateBadge state="Busy" />);
    expect(screen.getByText("Busy")).toHaveAttribute("data-indi-pulse", "");

    for (const state of [IPState.Idle, IPState.Ok, IPState.Alert]) {
      cleanup();
      render(<StateBadge state={state} />);
      expect(screen.getByText(state)).not.toHaveAttribute("data-indi-pulse");
    }
  });

  it("merges a caller-supplied class name", () => {
    render(<StateBadge state="Ok" className="custom-class" />);
    expect(screen.getByText("Ok")).toHaveClass("custom-class");
  });
});
