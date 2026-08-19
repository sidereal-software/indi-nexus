/** Tests for the grouped per-device property panel. */

import type { NumberVector, SwitchVector, TextVector } from "@indikit/client";
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

/** libindi's CONFIG_PROCESS, which the panel leaves to the sidebar entry. */
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

/** An INDIkit driver's list of what Save writes, which the dialog renders. */
function persistedVec(): TextVector {
  return {
    kind: "text",
    device: "CCD",
    name: "INDIKIT_CONFIG_PERSISTED",
    label: "Saved properties",
    group: "Options",
    state: "Ok",
    perm: "ro",
    elements: [{ kind: "text", name: "PROPERTIES", value: "GEOGRAPHIC_COORD" }],
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

    const headings = screen.getAllByRole("heading", { level: 2 });
    expect(headings.map((h) => h.textContent)).toEqual(["Main", "Options"]);

    // Cards are sorted by name within a group.
    const names = ["EXPOSURE", "GAIN", "TEMP"].map((name) => screen.getByText(name));
    expect(names[0]?.compareDocumentPosition(names[1] as Node)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("keeps the heading level for ungrouped properties but hides the name", () => {
    const { socket } = renderConnected(<DevicePanel device="CCD" />);
    receive(socket, { tag: "def", vector: numVec("EXPOSURE") });
    expect(screen.getByText("EXPOSURE")).toBeInTheDocument();

    // Nothing is drawn for a bucket with no group name, but the level has to
    // stay: the card titles below are h3, so dropping the h2 would step the
    // shell's h1 straight to h3 and break the outline.
    const heading = screen.getByRole("heading", { level: 2 });
    expect(heading).toHaveClass("sr-only");
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
      "EXPOSURE",
    ]);
  });

  it("leaves CONFIG_PROCESS out of the panel entirely", () => {
    const { socket } = renderConnected(<DevicePanel device="CCD" />);
    receive(socket, { tag: "def", vector: numVec("EXPOSURE", "Main Control") });
    receive(socket, { tag: "def", vector: configVec() });

    // Configuration is a per-device action surface offered from the sidebar by
    // DeviceConfigDialog, so the panel neither pins it nor draws it generically
    // - the generic card would render the four members as toggles, one of which
    // deletes a file with no undo.
    const headings = screen.getAllByRole("heading", { level: 2 });
    expect(headings.map((h) => h.textContent)).toEqual(["Main Control"]);
    expect(screen.queryByText("Configuration")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "CONFIG_SAVE" })).not.toBeInTheDocument();
    expect(openFold()).toEqual([]);
  });

  it("leaves INDIKIT_CONFIG_PERSISTED out of the panel entirely", () => {
    const { socket } = renderConnected(<DevicePanel device="CCD" />);
    receive(socket, { tag: "def", vector: numVec("EXPOSURE", "Main Control") });
    receive(socket, { tag: "def", vector: persistedVec() });

    // The dialog turns this into a sentence about what Save writes. Drawn as a
    // card it is a read-only field of wire names, which tells an operator less
    // than the sentence does and takes a slot in the grid to do it.
    expect(screen.queryByText("Saved properties")).not.toBeInTheDocument();
    expect(screen.queryByText("GEOGRAPHIC_COORD")).not.toBeInTheDocument();
    expect(openFold()).toEqual([]);
  });

  it("orders groups deterministically: Main Control, then alphabetical", () => {
    const { socket } = renderConnected(<DevicePanel device="CCD" />);
    for (const group of ["Site", "Main Control", "Almanac", "Options"]) {
      receive(socket, { tag: "def", vector: numVec(`P_${group.replace(" ", "_")}`, group) });
    }

    const headings = screen.getAllByRole("heading", { level: 2 });
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
