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

  it("merges a caller-supplied class name", () => {
    render(<StateBadge state="Ok" className="custom-class" />);
    expect(screen.getByText("Ok")).toHaveClass("custom-class");
  });
});
