/** Tests for the grouped per-device property panel. */

import type { NumberVector, SwitchVector } from "@indi-nexus/client";
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { receive, renderConnected } from "../testing/render";
import { DevicePanel } from "./device-panel";

afterEach(cleanup);

/** Build a minimal ro number vector in the given group (or ungrouped). */
function numVec(name: string, group?: string): NumberVector {
  return {
    kind: "number",
    device: "CCD",
    name,
    group,
    state: "Idle",
    perm: "ro",
    elements: [{ kind: "number", name: "v", value: 0 }],
  };
}

/** A machinery switch, declared in whatever group the driver chose. */
function switchVec(name: string, group = "Options"): SwitchVector {
  return {
    kind: "switch",
    device: "CCD",
    name,
    group,
    state: "Idle",
    perm: "rw",
    rule: "AtMostOne",
    elements: [{ kind: "switch", name: `${name}_ENABLE`, value: "Off" }],
  };
}

/** libindi's CONFIG_PROCESS, which the panel pins as its own section. */
function configVec(): SwitchVector {
  return {
    ...switchVec("CONFIG_PROCESS"),
    label: "Configuration",
    elements: ["CONFIG_LOAD", "CONFIG_SAVE", "CONFIG_DEFAULT", "CONFIG_PURGE"].map((name) => ({
      kind: "switch" as const,
      name,
      value: "Off" as const,
    })),
  };
}

/** Open the "Driver internals" fold and return the property names inside it. */
function openFold(): string[] {
  const trigger = screen.queryByRole("button", { name: "Driver internals" });
  if (trigger === null) return [];
  // The fold is a collapsible accordion, so clicking an open one closes it.
  if (trigger.getAttribute("aria-expanded") !== "true") fireEvent.click(trigger);
  const content = document.querySelector('[data-slot="accordion-content"]');
  if (content === null) throw new Error("the fold did not open");
  return [...content.querySelectorAll('[data-slot="card-title"]')].map(
    (title) => title.textContent ?? "",
  );
}

describe("DevicePanel", () => {
  it("shows a placeholder while the device has no properties", () => {
    renderConnected(<DevicePanel device="CCD" />);
    expect(screen.getByText("No properties for CCD right now.")).toBeInTheDocument();
  });

  it("renders one card per property under sorted group headings", () => {
    const { socket } = renderConnected(<DevicePanel device="CCD" />);
    receive(socket, { tag: "def", vector: numVec("TEMP", "Options") });
    receive(socket, { tag: "def", vector: numVec("EXPOSURE", "Main") });
    receive(socket, { tag: "def", vector: numVec("GAIN", "Main") });

    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings.map((h) => h.textContent)).toEqual(["Main", "Options"]);

    // Cards are sorted by name within a group.
    const names = ["EXPOSURE", "GAIN", "TEMP"].map((name) => screen.getByText(name));
    expect(names[0]?.compareDocumentPosition(names[1] as Node)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("renders ungrouped properties without a group heading", () => {
    const { socket } = renderConnected(<DevicePanel device="CCD" />);
    receive(socket, { tag: "def", vector: numVec("EXPOSURE") });
    expect(screen.getByText("EXPOSURE")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 3 })).not.toBeInTheDocument();
  });

  it("pins Configuration first and does not also draw CONFIG_PROCESS as a card", () => {
    const { socket } = renderConnected(<DevicePanel device="CCD" />);
    receive(socket, { tag: "def", vector: numVec("EXPOSURE", "Main Control") });
    receive(socket, { tag: "def", vector: configVec() });

    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings.map((h) => h.textContent)).toEqual(["Configuration", "Main Control"]);
    // The card is the config card, not a generic switch vector: the generic one
    // would render the four members as toggles.
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "CONFIG_SAVE" })).not.toBeInTheDocument();
    expect(openFold()).toEqual([]);
  });

  it("orders groups deterministically: Main Control, then alphabetical", () => {
    const { socket } = renderConnected(<DevicePanel device="CCD" />);
    for (const group of ["Site", "Main Control", "Almanac", "Options"]) {
      receive(socket, { tag: "def", vector: numVec(`P_${group.replace(" ", "_")}`, group) });
    }

    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings.map((h) => h.textContent)).toEqual([
      "Main Control",
      "Almanac",
      "Options",
      "Site",
    ]);
  });

  it("folds exactly the driver's machinery, and leaves CONNECTION out of it", () => {
    const { socket } = renderConnected(<DevicePanel device="CCD" />);
    for (const name of [
      "CONNECTION",
      "DEBUG",
      "SIMULATION",
      "ACTIVE_DEVICES",
      "DEBUG_LEVEL",
      "LOGGING_LEVEL",
      "LOG_OUTPUT",
      "FILE_DEBUG",
    ]) {
      receive(socket, { tag: "def", vector: switchVec(name) });
    }
    receive(socket, { tag: "def", vector: configVec() });
    receive(socket, { tag: "def", vector: numVec("EXPOSURE", "Main Control") });

    // CONNECTION is on Ekos' skip list and deliberately not on ours: it is the
    // control an operator reaches for first, and the panel has no second home
    // for it the way Ekos' toolbar does.
    expect(openFold()).toEqual([
      "ACTIVE_DEVICES",
      "DEBUG",
      "DEBUG_LEVEL",
      "FILE_DEBUG",
      "LOG_OUTPUT",
      "LOGGING_LEVEL",
      "SIMULATION",
    ]);
    expect(screen.getByText("CONNECTION")).toBeInTheDocument();
  });

  it("follows a machinery property being defined and deleted mid-session", () => {
    const { socket } = renderConnected(<DevicePanel device="CCD" />);
    receive(socket, { tag: "def", vector: switchVec("DEBUG") });
    expect(openFold()).toEqual(["DEBUG"]);

    // libindi defines the level properties when DEBUG goes on and deletes them
    // again when it goes off, so the fold has to be computed per render.
    receive(socket, { tag: "def", vector: switchVec("DEBUG_LEVEL") });
    receive(socket, { tag: "def", vector: switchVec("LOGGING_LEVEL") });
    expect(openFold()).toEqual(["DEBUG", "DEBUG_LEVEL", "LOGGING_LEVEL"]);

    receive(socket, { tag: "delProperty", device: "CCD", name: "DEBUG_LEVEL" });
    receive(socket, { tag: "delProperty", device: "CCD", name: "LOGGING_LEVEL" });
    expect(openFold()).toEqual(["DEBUG"]);
  });
});
