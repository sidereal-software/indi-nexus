/** Tests for the Alert live region: what it says, and everything it stays quiet for. */

import type { NumberVector } from "@indi-nexus/client";
import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { receive, renderConnected } from "../testing/render";
import { AlertAnnouncer } from "./alert-announcer";

afterEach(cleanup);

/** A number vector; `state` and `value` are what the tests vary. */
function vec(overrides: Partial<NumberVector> = {}): NumberVector {
  return {
    kind: "number",
    device: "CCD",
    name: "CCD_TEMPERATURE",
    label: "Temperature",
    state: "Idle",
    perm: "rw",
    elements: [{ kind: "number", name: "CCD_TEMPERATURE_VALUE", value: -10 }],
    ...overrides,
  };
}

/** The region's current text, or the empty string when it has said nothing. */
function announced(): string {
  return screen.getByRole("status").textContent ?? "";
}

describe("AlertAnnouncer", () => {
  it("renders a polite status region that starts empty", () => {
    renderConnected(<AlertAnnouncer />);
    const region = screen.getByRole("status");
    expect(region).toBeInTheDocument();
    expect(region).toHaveClass("sr-only");
    expect(announced()).toBe("");
  });

  it("announces a vector entering Alert, by label and device", () => {
    const { socket } = renderConnected(<AlertAnnouncer />);
    receive(socket, { tag: "def", vector: vec() });
    expect(announced()).toBe("");

    receive(socket, { tag: "set", vector: vec({ state: "Alert" }) });
    expect(announced()).toBe("Temperature on CCD is in Alert.");
  });

  it("says nothing for a value change or a state that is not Alert", () => {
    const { socket } = renderConnected(<AlertAnnouncer />);
    receive(socket, { tag: "def", vector: vec() });

    // Telemetry: on a CCD simulator this is continuous, and announcing it would
    // bury the one event worth hearing.
    for (const value of [-11, -12, -13]) {
      receive(socket, {
        tag: "set",
        vector: vec({ elements: [{ kind: "number", name: "CCD_TEMPERATURE_VALUE", value }] }),
      });
    }
    receive(socket, { tag: "set", vector: vec({ state: "Busy" }) });
    receive(socket, { tag: "set", vector: vec({ state: "Ok" }) });
    expect(announced()).toBe("");
  });

  it("does not repeat itself when a latched Alert re-emits", () => {
    const { socket } = renderConnected(<AlertAnnouncer />);
    receive(socket, { tag: "def", vector: vec() });
    receive(socket, { tag: "set", vector: vec({ state: "Alert" }) });
    expect(announced()).toBe("Temperature on CCD is in Alert.");

    // A second property enters Alert, so the region moves on to it.
    receive(socket, {
      tag: "def",
      vector: vec({ name: "CCD_COOLER", label: "Cooler", state: "Alert" }),
    });
    expect(announced()).toBe("Cooler on CCD is in Alert.");

    // The first property keeps re-emitting Alert - once with the state repeated,
    // once with no state on the wire at all (`state_present: false`), which
    // leaves the latched Alert in place. Neither is a transition, so neither may
    // steal the region back.
    receive(socket, { tag: "set", vector: vec({ state: "Alert" }) });
    receive(socket, {
      tag: "set",
      state_present: false,
      vector: vec({ elements: [{ kind: "number", name: "CCD_TEMPERATURE_VALUE", value: -14 }] }),
    });
    expect(announced()).toBe("Cooler on CCD is in Alert.");
  });

  it("announces again after the property recovers and fails a second time", () => {
    const { socket } = renderConnected(<AlertAnnouncer />);
    receive(socket, { tag: "def", vector: vec({ state: "Alert" }) });
    const first = screen.getByRole("status").firstElementChild;
    expect(announced()).toBe("Temperature on CCD is in Alert.");

    receive(socket, { tag: "set", vector: vec({ state: "Ok" }) });
    receive(socket, { tag: "set", vector: vec({ state: "Alert" }) });
    expect(announced()).toBe("Temperature on CCD is in Alert.");
    // Same sentence, different node: a live region whose text did not change may
    // not be re-read, so the announcement is keyed rather than assigned.
    expect(screen.getByRole("status").firstElementChild).not.toBe(first);
  });

  it("treats a property that comes back after deletion as news again", () => {
    const { socket } = renderConnected(<AlertAnnouncer />);
    receive(socket, { tag: "def", vector: vec({ state: "Alert" }) });
    const first = screen.getByRole("status").firstElementChild;

    receive(socket, { tag: "delProperty", device: "CCD", name: "CCD_TEMPERATURE" });
    receive(socket, { tag: "def", vector: vec({ state: "Alert" }) });
    expect(announced()).toBe("Temperature on CCD is in Alert.");
    expect(screen.getByRole("status").firstElementChild).not.toBe(first);
  });
});
