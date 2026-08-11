/** Tests for the state badge's per-state colour classes. */

import { IPState } from "@indi-nexus/client";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { StateBadge } from "./state-badge";

afterEach(cleanup);

describe("StateBadge", () => {
  it.each([
    [IPState.Idle, "bg-state-idle"],
    [IPState.Ok, "bg-state-ok"],
    [IPState.Busy, "bg-state-busy"],
    [IPState.Alert, "bg-state-alert"],
  ])("renders %s with its state colour", (state, className) => {
    render(<StateBadge state={state} />);
    expect(screen.getByText(state)).toHaveClass(className);
  });

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
