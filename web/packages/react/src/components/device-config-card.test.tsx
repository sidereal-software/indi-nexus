/**
 * Tests for the configuration card.
 *
 * Most of these are about copy and about what does *not* go on the wire, because
 * that is the whole reason the card exists: `CONFIG_PURGE` deletes a file with no
 * backup, and `CONFIG_DEFAULT` is not what its name says.
 */

import type { NewVector, SwitchVector } from "@indi-nexus/client";
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { FakeSocket } from "../testing/fake-socket";
import { receive, renderConnected } from "../testing/render";
import { DeviceConfigCard } from "./device-config-card";

afterEach(cleanup);

/** libindi's own CONFIG_PROCESS, with the given members. */
function configVec(
  members: string[] = ["CONFIG_LOAD", "CONFIG_SAVE", "CONFIG_DEFAULT", "CONFIG_PURGE"],
): SwitchVector {
  return {
    kind: "switch",
    device: "CCD",
    name: "CONFIG_PROCESS",
    label: "Configuration",
    group: "Options",
    state: "Idle",
    perm: "rw",
    rule: "AtMostOne",
    elements: members.map((name) => ({ kind: "switch" as const, name, value: "Off" as const })),
  };
}

/** The CONNECTION switch in one of its two positions. */
function connectionVec(connected: boolean): SwitchVector {
  return {
    kind: "switch",
    device: "CCD",
    name: "CONNECTION",
    state: "Ok",
    perm: "rw",
    rule: "OneOfMany",
    elements: [
      { kind: "switch", name: "CONNECT", value: connected ? "On" : "Off" },
      { kind: "switch", name: "DISCONNECT", value: connected ? "Off" : "On" },
    ],
  };
}

/** The vectors of every `new` frame the client has sent so far. */
function sentFrames(socket: FakeSocket): NewVector["vector"][] {
  return socket.sent
    .map((raw) => JSON.parse(raw) as NewVector)
    .filter((frame) => frame.tag === "new")
    .map((frame) => frame.vector);
}

/** Every switch member the card has asked for, as `device.property.element=value`. */
function requested(socket: FakeSocket): string[] {
  return sentFrames(socket).flatMap((vector) =>
    vector.kind === "switch"
      ? vector.elements.map(
          (element) => `${vector.device}.${vector.name}.${element.name}=${element.value}`,
        )
      : [],
  );
}

describe("DeviceConfigCard", () => {
  it("renders nothing when the device has no CONFIG_PROCESS", () => {
    const { container } = renderConnected(<DeviceConfigCard device="CCD" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders only the members the vector carries", () => {
    const { socket } = renderConnected(<DeviceConfigCard device="CCD" />);
    receive(socket, { tag: "def", vector: configVec(["CONFIG_LOAD", "CONFIG_SAVE"]) });

    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load saved" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Purge" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restore first saved" })).not.toBeInTheDocument();
  });

  it("calls CONFIG_DEFAULT what it is, not 'Default'", () => {
    const { socket } = renderConnected(<DeviceConfigCard device="CCD" />);
    receive(socket, { tag: "def", vector: configVec() });

    // Asserted by string on purpose: renaming this back to "Default" is the
    // regression, because libindi's `.default` file is a copy of the first
    // configuration ever saved and not the factory settings.
    expect(screen.getByRole("button", { name: "Restore first saved" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Default" })).not.toBeInTheDocument();
    expect(
      screen.getByText(/snapshot taken the first time this configuration was saved/),
    ).toBeInTheDocument();
    expect(screen.getByText(/not factory settings/)).toBeInTheDocument();
  });

  it("says that Save does not necessarily save what is on screen", () => {
    const { socket } = renderConnected(<DeviceConfigCard device="CCD" />);
    receive(socket, { tag: "def", vector: configVec() });

    expect(
      screen.getByText(
        "This driver does not report what Save writes. Most drivers save only part of what you see.",
      ),
    ).toBeInTheDocument();
  });

  it("sends Save on the first press, with no dialog", () => {
    const { socket } = renderConnected(<DeviceConfigCard device="CCD" />);
    receive(socket, { tag: "def", vector: configVec() });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(requested(socket)).toEqual(["CCD.CONFIG_PROCESS.CONFIG_SAVE=On"]);
  });

  it("sends nothing when Purge is pressed and the dialog is cancelled", () => {
    const { socket } = renderConnected(<DeviceConfigCard device="CCD" />);
    receive(socket, { tag: "def", vector: configVec() });

    fireEvent.click(screen.getByRole("button", { name: "Purge" }));
    expect(requested(socket)).toEqual([]);

    expect(screen.getByRole("alertdialog")).toHaveTextContent("CCD");
    expect(screen.getByRole("alertdialog")).toHaveTextContent(/no backup/);
    expect(screen.getByRole("alertdialog")).toHaveTextContent(/nothing can undo this/);
    expect(screen.getByRole("alertdialog")).toHaveTextContent(/observatory computer/);

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(requested(socket)).toEqual([]);
  });

  it("sends CONFIG_PURGE only once the deletion is confirmed", () => {
    const { socket } = renderConnected(<DeviceConfigCard device="CCD" />);
    receive(socket, { tag: "def", vector: configVec() });

    fireEvent.click(screen.getByRole("button", { name: "Purge" }));
    // Never "OK": the confirming button has to name the consequence.
    fireEvent.click(screen.getByRole("button", { name: "Delete saved config" }));

    expect(requested(socket)).toEqual(["CCD.CONFIG_PROCESS.CONFIG_PURGE=On"]);
  });

  it("confirms a load while the device is connected", () => {
    const { socket } = renderConnected(<DeviceConfigCard device="CCD" />);
    receive(socket, { tag: "def", vector: configVec() });
    receive(socket, { tag: "def", vector: connectionVec(true) });

    fireEvent.click(screen.getByRole("button", { name: "Load saved" }));
    expect(requested(socket)).toEqual([]);
    expect(screen.getByRole("alertdialog")).toHaveTextContent(/move the instrument/);

    fireEvent.click(screen.getByRole("button", { name: "Apply to the instrument" }));
    expect(requested(socket)).toEqual(["CCD.CONFIG_PROCESS.CONFIG_LOAD=On"]);
  });

  it("confirms 'Restore first saved' too, since it also replays through the driver", () => {
    const { socket } = renderConnected(<DeviceConfigCard device="CCD" />);
    receive(socket, { tag: "def", vector: configVec() });
    receive(socket, { tag: "def", vector: connectionVec(true) });

    fireEvent.click(screen.getByRole("button", { name: "Restore first saved" }));
    expect(requested(socket)).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Apply to the instrument" }));
    expect(requested(socket)).toEqual(["CCD.CONFIG_PROCESS.CONFIG_DEFAULT=On"]);
  });

  it("loads straight away while the device is disconnected", () => {
    const { socket } = renderConnected(<DeviceConfigCard device="CCD" />);
    receive(socket, { tag: "def", vector: configVec() });
    receive(socket, { tag: "def", vector: connectionVec(false) });

    fireEvent.click(screen.getByRole("button", { name: "Load saved" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(requested(socket)).toEqual(["CCD.CONFIG_PROCESS.CONFIG_LOAD=On"]);
  });

  it("loads straight away when the device has no CONNECTION vector", () => {
    const { socket } = renderConnected(<DeviceConfigCard device="CCD" />);
    receive(socket, { tag: "def", vector: configVec() });

    fireEvent.click(screen.getByRole("button", { name: "Load saved" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(requested(socket)).toEqual(["CCD.CONFIG_PROCESS.CONFIG_LOAD=On"]);
  });

  it("follows the vector's own state for feedback", () => {
    const { socket } = renderConnected(<DeviceConfigCard device="CCD" />);
    receive(socket, { tag: "def", vector: configVec() });
    expect(screen.getByText("Idle")).toBeInTheDocument();

    receive(socket, { tag: "set", vector: { ...configVec(), state: "Busy" } });
    expect(screen.getByText("Busy")).toBeInTheDocument();

    receive(socket, { tag: "set", vector: { ...configVec(), state: "Alert" } });
    expect(screen.getByText("Alert")).toBeInTheDocument();
  });
});
