/** Component tests: rendering vectors and sending writes through a fake client. */

import type { NumberVector, SwitchVector } from "@indi-nexus/client";
import { act, cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DisplaySettingsProvider } from "../display-settings";
import { useProperty } from "../hooks";
import { renderConnected } from "../testing/render";
import { PropertyVectorCard } from "./property-vector-card";

afterEach(cleanup);

/** A tiny harness that renders one property's card once it is defined. */
function CardFor({ device, name }: { device: string; name: string }) {
  const vector = useProperty(device, name);
  return vector ? <PropertyVectorCard vector={vector} /> : null;
}

const numberVec: NumberVector = {
  kind: "number",
  device: "CCD",
  name: "EXPOSURE",
  label: "Exposure",
  group: "Main",
  state: "Idle",
  perm: "rw",
  elements: [{ kind: "number", name: "secs", format: "%.2f", value: 1.5 }],
};

const switchVec: SwitchVector = {
  kind: "switch",
  device: "Demo",
  name: "power",
  state: "Idle",
  perm: "rw",
  rule: "OneOfMany",
  elements: [
    { kind: "switch", name: "on", value: "Off" },
    { kind: "switch", name: "off", value: "On" },
  ],
};

describe("PropertyVectorCard", () => {
  it("renders a writable number vector and sends a new frame on Set", () => {
    const { socket } = renderConnected(<CardFor device="CCD" name="EXPOSURE" />);
    act(() => socket.receive(JSON.stringify({ tag: "def", vector: numberVec })));

    const input = screen.getByLabelText("secs") as HTMLInputElement;
    expect(input.value).toBe("1.5");

    fireEvent.change(input, { target: { value: "3" } });
    const form = input.closest("form");
    if (!form) throw new Error("no form");
    fireEvent.submit(form);

    const frame = socket.lastSent<{ tag: string; vector: NumberVector }>();
    expect(frame.tag).toBe("new");
    expect(frame.vector.elements[0]).toMatchObject({ name: "secs", value: 3 });
  });

  it("re-renders when a later set changes the property state", () => {
    const { socket } = renderConnected(<CardFor device="CCD" name="EXPOSURE" />);
    act(() => socket.receive(JSON.stringify({ tag: "def", vector: numberVec })));
    expect(screen.getByText("Idle")).toBeInTheDocument();

    act(() =>
      socket.receive(JSON.stringify({ tag: "set", vector: { ...numberVec, state: "Ok" } })),
    );
    expect(screen.getByText("Ok")).toBeInTheDocument();
  });

  it("hides the raw property name and permission by default", () => {
    renderConnected(<PropertyVectorCard vector={numberVec} />);
    expect(screen.getByText("Exposure")).toBeInTheDocument();
    expect(screen.queryByText("EXPOSURE · rw")).not.toBeInTheDocument();
  });

  it("shows the raw name and permission when debug info is enabled", () => {
    renderConnected(
      <DisplaySettingsProvider showDebug>
        <PropertyVectorCard vector={numberVec} />
      </DisplaySettingsProvider>,
    );
    expect(screen.getByText("EXPOSURE · rw")).toBeInTheDocument();
  });

  it("renders switch elements and sends a new switch frame when toggled", () => {
    const { socket } = renderConnected(<CardFor device="Demo" name="power" />);
    act(() => socket.receive(JSON.stringify({ tag: "def", vector: switchVec })));

    // Both switch options are shown as toggles.
    expect(screen.getByText("on")).toBeInTheDocument();
    expect(screen.getByText("off")).toBeInTheDocument();

    fireEvent.click(screen.getByText("on"));

    const frame = socket.lastSent<{ tag: string; vector: SwitchVector }>();
    expect(frame.tag).toBe("new");
    expect(frame.vector.elements).toContainEqual({ kind: "switch", name: "on", value: "On" });
  });
});
