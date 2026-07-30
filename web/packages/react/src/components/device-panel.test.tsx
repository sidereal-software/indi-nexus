/** Tests for the grouped per-device property panel. */

import type { NumberVector } from "@indi-nexus/client";
import { cleanup, screen } from "@testing-library/react";
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

describe("DevicePanel", () => {
  it("shows a placeholder while the device has no properties", () => {
    renderConnected(<DevicePanel device="CCD" />);
    expect(screen.getByText("No properties for CCD yet.")).toBeInTheDocument();
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
});
