/** Tests for the per-kind vector controls: rendering plus the frames they send. */

import type {
  BlobVector,
  LightVector,
  NewVector,
  NumberVector,
  SwitchVector,
  TextVector,
} from "@indi-nexus/client";
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { renderConnected } from "../testing/render";
import {
  BlobVectorControl,
  LightVectorControl,
  SwitchVectorControl,
  ValueVectorControl,
  VectorControl,
} from "./element-controls";

afterEach(cleanup);

/** Build a number vector; `perm` defaults to rw. */
function numberVec(overrides: Partial<NumberVector> = {}): NumberVector {
  return {
    kind: "number",
    device: "CCD",
    name: "EXPOSURE",
    state: "Idle",
    perm: "rw",
    elements: [{ kind: "number", name: "secs", format: "%.2f", value: 1.5 }],
    ...overrides,
  };
}

/** Build a switch vector with the given rule and On names. */
function switchVec(rule: SwitchVector["rule"], on: string[] = [], perm = "rw"): SwitchVector {
  return {
    kind: "switch",
    device: "Demo",
    name: "MODE",
    state: "Idle",
    perm: perm as SwitchVector["perm"],
    rule,
    elements: ["a", "b", "c"].map((name) => ({
      kind: "switch",
      name,
      value: on.includes(name) ? "On" : "Off",
    })),
  };
}

/** Submit the form containing `element`. */
function submitFormOf(element: HTMLElement) {
  const form = element.closest("form");
  if (!form) throw new Error("no form");
  fireEvent.submit(form);
}

describe("ValueVectorControl", () => {
  it("renders a read-only number honouring its printf precision", () => {
    renderConnected(<ValueVectorControl vector={numberVec({ perm: "ro" })} />);
    expect(screen.getByText("1.50")).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  it("applies min/max/step from the element to the input", () => {
    renderConnected(
      <ValueVectorControl
        vector={numberVec({
          elements: [{ kind: "number", name: "secs", value: 1, min: 0, max: 10, step: 0.5 }],
        })}
      />,
    );
    const input = screen.getByLabelText("secs");
    expect(input).toHaveAttribute("min", "0");
    expect(input).toHaveAttribute("max", "10");
    expect(input).toHaveAttribute("step", "0.5");
  });

  it("sends only the non-blank number inputs on Set", () => {
    const vector = numberVec({
      elements: [
        { kind: "number", name: "RA", value: 1 },
        { kind: "number", name: "DEC", value: 2 },
      ],
    });
    const { socket } = renderConnected(<ValueVectorControl vector={vector} />);

    fireEvent.change(screen.getByLabelText("RA"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("DEC"), { target: { value: "" } });
    submitFormOf(screen.getByLabelText("RA"));

    const frame = socket.lastSent<NewVector>();
    expect(frame.tag).toBe("new");
    expect(frame.vector.elements).toEqual([{ kind: "number", name: "RA", value: 5 }]);
  });

  it("sends every text value on Set", () => {
    const vector: TextVector = {
      kind: "text",
      device: "Scope",
      name: "INFO",
      state: "Idle",
      perm: "rw",
      elements: [{ kind: "text", name: "site", value: "old" }],
    };
    const { socket } = renderConnected(<ValueVectorControl vector={vector} />);

    fireEvent.change(screen.getByLabelText("site"), { target: { value: "MMT" } });
    submitFormOf(screen.getByLabelText("site"));

    const frame = socket.lastSent<NewVector>();
    expect(frame.vector).toMatchObject({
      kind: "text",
      device: "Scope",
      name: "INFO",
      elements: [{ kind: "text", name: "site", value: "MMT" }],
    });
  });
});

describe("SwitchVectorControl", () => {
  it("sends On for the newly selected switch under OneOfMany", () => {
    const { socket } = renderConnected(
      <SwitchVectorControl vector={switchVec("OneOfMany", ["a"])} />,
    );
    fireEvent.click(screen.getByText("b"));
    const frame = socket.lastSent<NewVector>();
    expect(frame.vector.elements).toEqual([{ kind: "switch", name: "b", value: "On" }]);
  });

  it("sends Off for the current switch when deselected under AtMostOne", () => {
    const { socket } = renderConnected(
      <SwitchVectorControl vector={switchVec("AtMostOne", ["a"])} />,
    );
    fireEvent.click(screen.getByText("a"));
    const frame = socket.lastSent<NewVector>();
    expect(frame.vector.elements).toEqual([{ kind: "switch", name: "a", value: "Off" }]);
  });

  it("sends only the toggled switch under AnyOfMany", () => {
    const { socket } = renderConnected(
      <SwitchVectorControl vector={switchVec("AnyOfMany", ["a"])} />,
    );
    fireEvent.click(screen.getByText("c"));
    const frame = socket.lastSent<NewVector>();
    expect(frame.vector.elements).toEqual([{ kind: "switch", name: "c", value: "On" }]);
  });

  it("disables the toggles and sends nothing when read-only", () => {
    const { socket } = renderConnected(
      <SwitchVectorControl vector={switchVec("AnyOfMany", ["a"], "ro")} />,
    );
    const toggle = screen.getByText("b").closest("button");
    expect(toggle).toBeDisabled();
    if (toggle) fireEvent.click(toggle);
    expect(socket.sent).toHaveLength(0);
  });
});

describe("LightVectorControl", () => {
  it("renders each light's state with its coloured dot", () => {
    const vector: LightVector = {
      kind: "light",
      device: "Dome",
      name: "STATUS",
      state: "Ok",
      elements: [
        { kind: "light", name: "shutter", value: "Ok" },
        { kind: "light", name: "rain", value: "Alert" },
      ],
    };
    renderConnected(<LightVectorControl vector={vector} />);
    expect(screen.getByText("Ok").querySelector(".bg-state-ok")).toBeInTheDocument();
    expect(screen.getByText("Alert").querySelector(".bg-state-alert")).toBeInTheDocument();
  });
});

describe("BlobVectorControl", () => {
  it("renders format, a human-readable size, and a download link when data is present", () => {
    const vector: BlobVector = {
      kind: "blob",
      device: "CCD",
      name: "IMAGE",
      state: "Ok",
      perm: "ro",
      elements: [
        { kind: "blob", name: "frame", format: ".fits", size: 2048, data: "aGVsbG8=" },
        { kind: "blob", name: "thumb", size: 512, data: null },
        { kind: "blob", name: "raw", size: 3 * 1024 * 1024, data: null },
        { kind: "blob", name: "empty" },
      ],
    };
    renderConnected(<BlobVectorControl vector={vector} />);

    expect(screen.getByText("2.0 KB")).toBeInTheDocument();
    expect(screen.getByText("512 B")).toBeInTheDocument();
    expect(screen.getByText("3.0 MB")).toBeInTheDocument();
    // Size and format placeholders for the metadata-less element.
    expect(screen.getAllByText("-").length).toBeGreaterThanOrEqual(2);

    const link = screen.getByRole("link", { name: "download" });
    expect(link).toHaveAttribute("download", "frame.fits");
    expect(link).toHaveAttribute("href", "data:application/octet-stream;base64,aGVsbG8=");
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });
});

describe("VectorControl", () => {
  it("dispatches to the control matching the vector kind", () => {
    const light: LightVector = {
      kind: "light",
      device: "Dome",
      name: "STATUS",
      state: "Idle",
      elements: [{ kind: "light", name: "ok", value: "Idle" }],
    };
    renderConnected(<VectorControl vector={light} />);
    expect(screen.getByText("Idle")).toBeInTheDocument();

    cleanup();
    renderConnected(<VectorControl vector={numberVec({ perm: "ro" })} />);
    expect(screen.getByText("1.50")).toBeInTheDocument();
  });
});
