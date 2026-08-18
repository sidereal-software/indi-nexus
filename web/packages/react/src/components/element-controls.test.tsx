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
import { useProperty } from "../hooks";
import { receive, renderConnected } from "../testing/render";
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

  it("uses step=any when the element declares no step", () => {
    // HTML number inputs default to step=1, which would make fractional values
    // (RA 5.5h) fail native validation and silently block the submit.
    renderConnected(
      <ValueVectorControl
        vector={numberVec({
          elements: [{ kind: "number", name: "RA", value: 0, min: 0, max: 24 }],
        })}
      />,
    );
    expect(screen.getByLabelText("RA")).toHaveAttribute("step", "any");
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

  it("names each Set button after the vector it submits", () => {
    // One writable vector per card, so a CCD panel offers five buttons all
    // reading "Set". The visible word stays; the accessible name carries the
    // vector, so a list of controls tells exposure from binning.
    renderConnected(
      <>
        <ValueVectorControl vector={numberVec({ name: "CCD_EXPOSURE", label: "Exposure" })} />
        <ValueVectorControl vector={numberVec({ name: "CCD_BINNING", label: "Binning" })} />
      </>,
    );
    expect(screen.getByRole("button", { name: "Set Exposure" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set Binning" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Set" })).not.toBeInTheDocument();
  });

  it("shows a live current-value readout beside a writable input", () => {
    // The readout is telemetry (where the device is now); the input is only the
    // requested new value, so a slewing dome must update the readout while
    // leaving whatever the operator typed in the input untouched.
    function Probe() {
      const vector = useProperty("Dome", "ABS_DOME_POSITION");
      return vector?.kind === "number" ? <ValueVectorControl vector={vector} /> : null;
    }
    const { socket } = renderConnected(<Probe />);
    const vector: NumberVector = {
      kind: "number",
      device: "Dome",
      name: "ABS_DOME_POSITION",
      state: "Busy",
      perm: "rw",
      elements: [{ kind: "number", name: "az", format: "%.2f", value: 10 }],
    };
    receive(socket, { tag: "def", vector });

    const input = screen.getByLabelText("az") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "120" } });

    receive(socket, {
      tag: "set",
      vector: { ...vector, elements: [{ kind: "number", name: "az", value: 15 }] },
    });
    expect(screen.getByTitle("Current value")).toHaveTextContent("15.00");
    expect(input.value).toBe("120"); // the operator's pending request survives

    receive(socket, {
      tag: "set",
      vector: { ...vector, elements: [{ kind: "number", name: "az", value: 20 }] },
    });
    expect(screen.getByTitle("Current value")).toHaveTextContent("20.00");
  });

  it("renders a sexagesimal readout for %m formats", () => {
    const vector = numberVec({
      perm: "ro",
      elements: [{ kind: "number", name: "RA", format: "%9.6m", value: 12.582777778 }],
    });
    renderConnected(<ValueVectorControl vector={vector} />);
    expect(screen.getByText("12:34:58")).toBeInTheDocument();
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

  it("draws the selected member differently from a hovered unselected one", () => {
    renderConnected(<SwitchVectorControl vector={switchVec("OneOfMany", ["a"])} />);
    const on = screen.getByText("a").closest("button");
    const off = screen.getByText("b").closest("button");

    expect(on).toHaveAttribute("data-state", "on");
    expect(off).toHaveAttribute("data-state", "off");
    // The regression: selection and hover both resolved to `accent`, so a hovered
    // unselected member looked exactly like the selected one. Selection now wears the
    // same `secondary` as the Set button, which hover can never reach.
    expect(on?.className).toContain("data-[state=on]:bg-secondary");
    expect(on?.className).toContain("data-[state=on]:hover:bg-secondary");
    expect(off?.className).toContain("hover:bg-muted");
    for (const button of [on, off]) {
      expect(button?.className).not.toContain("hover:bg-accent");
    }
  });

  it("ignores a click on the member already on under OneOfMany", () => {
    const { socket } = renderConnected(
      <SwitchVectorControl vector={switchVec("OneOfMany", ["a"])} />,
    );
    // Exactly one member is on by definition, so clicking it cannot mean "turn the
    // device off" - the operator has to press the member they want.
    fireEvent.click(screen.getByText("a"));
    expect(socket.sent).toHaveLength(0);
  });

  it("is a group of toggle buttons and never claims the radio pattern", () => {
    renderConnected(<SwitchVectorControl vector={switchVec("OneOfMany", ["a"], "rw")} />);

    // A Radix ToggleGroup type="single" is a radiogroup, and the ARIA radio
    // pattern is selection-follows-focus: arrowing from Disconnect to Connect
    // told a reader the connection had changed while nothing went on the wire.
    // The two-step behaviour is right for a control that connects hardware, so
    // the claim is what changed.
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("radio")).toHaveLength(0);

    const group = screen.getByRole("group", { name: "MODE" });
    const on = screen.getByRole("button", { name: "a", pressed: true });
    const off = screen.getByRole("button", { name: "b", pressed: false });
    expect(group).toContainElement(on);
    expect(group).toContainElement(off);
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
    expect(screen.getByText("Ok").querySelector("[data-indi-state='Ok']")).toBeInTheDocument();
    expect(
      screen.getByText("Alert").querySelector("[data-indi-state='Alert']"),
    ).toBeInTheDocument();
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

describe("empty labels", () => {
  it("falls back to the element name when the label is the empty string", () => {
    // libindi publishes DEVICE_BAUD_RATE with empty element labels, so a
    // `label ?? name` fallback renders a row of blank buttons.
    renderConnected(
      <SwitchVectorControl
        vector={{
          ...switchVec("OneOfMany", ["9600"]),
          name: "DEVICE_BAUD_RATE",
          elements: ["9600", "19200"].map((name) => ({
            kind: "switch" as const,
            name,
            label: "",
            value: name === "9600" ? ("On" as const) : ("Off" as const),
          })),
        }}
      />,
    );
    expect(screen.getByText("9600")).toBeInTheDocument();
    expect(screen.getByText("19200")).toBeInTheDocument();
  });

  it("falls back to the element name for a read-only value row", () => {
    renderConnected(
      <ValueVectorControl
        vector={numberVec({
          perm: "ro",
          elements: [{ kind: "number", name: "secs", label: "", value: 1.5 }],
        })}
      />,
    );
    expect(screen.getByText("secs")).toBeInTheDocument();
  });
});
