/**
 * Tests for the configuration entry and its modal.
 *
 * Most of these are about copy and about what does *not* go on the wire, because
 * that is the whole reason the component exists: `CONFIG_PURGE` deletes a file
 * with no backup, and `CONFIG_DEFAULT` is not what its name says. The rest are
 * about the two dialogs stacking, since the confirmation now opens on top of a
 * modal rather than on the page.
 */

import type { NewVector, NumberVector, SwitchVector, TextVector } from "@indikit/client";
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SidebarProvider } from "@/ui/sidebar";
import { TooltipProvider } from "@/ui/tooltip";
import type { FakeSocket } from "../testing/fake-socket";
import { type ConnectedRender, receive, renderConnected } from "../testing/render";
import { DeviceConfigDialog } from "./device-config-dialog";

afterEach(cleanup);

/**
 * Render the entry inside the shell it is built for.
 *
 * The default trigger is a sidebar menu button, so it needs the sidebar's own
 * providers exactly as the reference panel supplies them.
 *
 * @param device - The selected device, or null for none.
 * @returns The connected render result.
 */
function renderEntry(device: string | null = "CCD"): ConnectedRender {
  return renderConnected(
    <TooltipProvider>
      <SidebarProvider>
        <DeviceConfigDialog device={device} />
      </SidebarProvider>
    </TooltipProvider>,
  );
}

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

/** An INDIkit driver's answer to "what does Save write?". */
function persistedVec(names: string): TextVector {
  return {
    kind: "text",
    device: "CCD",
    name: "INDIKIT_CONFIG_PERSISTED",
    label: "Saved properties",
    group: "Options",
    state: "Ok",
    perm: "ro",
    elements: [{ kind: "text", name: "PROPERTIES", label: "Properties", value: names }],
  };
}

/** A persisted property, so the dialog has a label to render instead of a name. */
function siteVec(): NumberVector {
  return {
    kind: "number",
    device: "CCD",
    name: "GEOGRAPHIC_COORD",
    label: "Site",
    group: "Options",
    state: "Ok",
    perm: "rw",
    elements: [{ kind: "number", name: "LAT", value: 47.6 }],
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

/** The sidebar entry that opens the dialog. */
function trigger(): HTMLElement {
  return screen.getByRole("button", { name: "Configuration" });
}

/** Open the configuration dialog from the sidebar entry. */
function open(): void {
  fireEvent.click(trigger());
}

/** The vectors of every `new` frame the client has sent so far. */
function sentFrames(socket: FakeSocket): NewVector["vector"][] {
  return socket.sent
    .map((raw) => JSON.parse(raw) as NewVector)
    .filter((frame) => frame.tag === "new")
    .map((frame) => frame.vector);
}

/** Every switch member the dialog has asked for, as `device.property.element=value`. */
function requested(socket: FakeSocket): string[] {
  return sentFrames(socket).flatMap((vector) =>
    vector.kind === "switch"
      ? vector.elements.map(
          (element) => `${vector.device}.${vector.name}.${element.name}=${element.value}`,
        )
      : [],
  );
}

describe("DeviceConfigDialog", () => {
  it("offers nothing when the device has no CONFIG_PROCESS", () => {
    renderEntry();
    // A device that cannot be configured must not offer a button that opens an
    // empty dialog.
    expect(screen.queryByRole("button", { name: "Configuration" })).not.toBeInTheDocument();
  });

  it("offers nothing when no device is selected", () => {
    const { socket } = renderEntry(null);
    receive(socket, { tag: "def", vector: configVec() });

    expect(screen.queryByRole("button", { name: "Configuration" })).not.toBeInTheDocument();
  });

  it("offers the entry once the selected device has CONFIG_PROCESS", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });

    expect(trigger()).toBeInTheDocument();
    // The entry alone is not the dialog: nothing is on screen until it is used.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("nests the default entry in a sub-list named for its device", () => {
    // There is no server-wide configuration in INDI, so this entry always
    // belongs to exactly one device and the markup has to say so. Drawn flat it
    // was read as another device, twice over: first as a sibling `<li>` of the
    // device buttons, then as its own group under a heading repeating the
    // device's name. The nesting is what carries ownership now, and the list's
    // name is what a reader hears in place of that heading.
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });

    const sub = screen.getByRole("list", { name: "CCD" });
    expect(sub).toContainElement(trigger());
    expect(sub.tagName).toBe("UL");
    // Every child of a list is a list item, which is the rule the flat version
    // broke when the entry was a bare button in a `SidebarMenu`.
    expect([...sub.children].every((child) => child.tagName === "LI")).toBe(true);
  });

  it("makes the default entry a real button rather than the primitive's anchor", () => {
    // `SidebarMenuSubButton` renders an `<a>`, and this trigger carries no href,
    // so taking the primitive as it comes would leave the only way into a
    // device's configuration out of the tab order entirely.
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });

    expect(trigger().tagName).toBe("BUTTON");
  });

  it("takes the whole sub-list with it when there is nothing to configure", () => {
    // Absent, not empty. The component owns the `<ul>` as well as the `<li>`, so
    // a device with no CONFIG_PROCESS leaves no indented rule hanging under its
    // row. The demo's dome is exactly that case; every libindi driver is not.
    renderEntry();

    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("sends nothing when the dialog is opened and closed again", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });

    open();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(requested(socket)).toEqual([]);
  });

  it("renders only the members the vector carries", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec(["CONFIG_LOAD", "CONFIG_SAVE"]) });
    open();

    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load saved" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Purge" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restore first saved" })).not.toBeInTheDocument();
  });

  it("calls CONFIG_DEFAULT what it is, not 'Default'", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    open();

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
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    open();

    // The fallback, and what every libindi driver gets: its persisted subset is
    // chosen in `saveConfigItems`, which no client can read.
    expect(
      screen.getByText(
        "This driver does not report what Save writes. Most drivers save only part of what you see.",
      ),
    ).toBeInTheDocument();
  });

  it("names what Save writes when the driver reports it", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    receive(socket, { tag: "def", vector: siteVec() });
    receive(socket, { tag: "def", vector: persistedVec("GEOGRAPHIC_COORD") });
    open();

    // The property's own label, not the wire name: "Site" is the word the rest
    // of the panel uses for it.
    expect(
      screen.getByText("Save writes Site. Nothing else on this screen is saved."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/does not report what Save writes/)).not.toBeInTheDocument();
  });

  it("falls back to the wire name for a property the device is not publishing", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    receive(socket, { tag: "def", vector: persistedVec("GEOGRAPHIC_COORD BACKLASH") });
    open();

    expect(
      screen.getByText(
        "Save writes GEOGRAPHIC_COORD, BACKLASH. Nothing else on this screen is saved.",
      ),
    ).toBeInTheDocument();
  });

  it("says plainly when the driver reports that Save writes nothing", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    receive(socket, { tag: "def", vector: persistedVec("") });
    open();

    // An empty list is an answer, and a different one from "cannot say": an
    // empty list rendered as a list would be a blank line saying neither.
    expect(
      screen.getByText("This driver reports that Save writes none of its properties."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/does not report what Save writes/)).not.toBeInTheDocument();
  });

  it("attaches each button's consequence to the button", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    open();

    // The copy *is* the component: "Purge" alone does not say that it deletes a
    // file with no backup. As a sibling paragraph that reached sighted readers
    // only, so the accessible description carries it too.
    expect(screen.getByRole("button", { name: "Purge" })).toHaveAccessibleDescription(
      "Deletes the saved configuration. There is no backup and nothing to undo it.",
    );
    expect(screen.getByRole("button", { name: "Save" })).toHaveAccessibleDescription(
      /Writes this device's configuration on the observatory computer/,
    );
  });

  it("sends Save on the first press, with no confirmation", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    open();

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(requested(socket)).toEqual(["CCD.CONFIG_PROCESS.CONFIG_SAVE=On"]);
  });

  it("sends nothing when Purge is pressed and the confirmation is cancelled", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    open();

    fireEvent.click(screen.getByRole("button", { name: "Purge" }));
    expect(requested(socket)).toEqual([]);

    expect(screen.getByRole("alertdialog")).toHaveTextContent("CCD");
    expect(screen.getByRole("alertdialog")).toHaveTextContent(/no backup/);
    expect(screen.getByRole("alertdialog")).toHaveTextContent(/nothing can undo this/);
    expect(screen.getByRole("alertdialog")).toHaveTextContent(/observatory computer/);

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(requested(socket)).toEqual([]);
    // Cancelling the confirmation leaves the configuration dialog behind it
    // standing: the operator changed their mind about purging, not about
    // configuring.
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("dismisses only the confirmation on Escape, and sends nothing", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    open();

    fireEvent.click(screen.getByRole("button", { name: "Purge" }));
    fireEvent.keyDown(screen.getByRole("alertdialog"), { key: "Escape" });

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(requested(socket)).toEqual([]);
  });

  it("sends CONFIG_PURGE only once the deletion is confirmed", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    open();

    fireEvent.click(screen.getByRole("button", { name: "Purge" }));
    // Never "OK": the confirming button has to name the consequence.
    fireEvent.click(screen.getByRole("button", { name: "Delete saved config" }));

    expect(requested(socket)).toEqual(["CCD.CONFIG_PROCESS.CONFIG_PURGE=On"]);
  });

  it("confirms a load while the device is connected", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    receive(socket, { tag: "def", vector: connectionVec(true) });
    open();

    fireEvent.click(screen.getByRole("button", { name: "Load saved" }));
    expect(requested(socket)).toEqual([]);
    expect(screen.getByRole("alertdialog")).toHaveTextContent(/move the instrument/);

    fireEvent.click(screen.getByRole("button", { name: "Apply to the instrument" }));
    expect(requested(socket)).toEqual(["CCD.CONFIG_PROCESS.CONFIG_LOAD=On"]);
  });

  it("confirms 'Restore first saved' too, since it also replays through the driver", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    receive(socket, { tag: "def", vector: connectionVec(true) });
    open();

    fireEvent.click(screen.getByRole("button", { name: "Restore first saved" }));
    expect(requested(socket)).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Apply to the instrument" }));
    expect(requested(socket)).toEqual(["CCD.CONFIG_PROCESS.CONFIG_DEFAULT=On"]);
  });

  it("loads straight away while the device is disconnected", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    receive(socket, { tag: "def", vector: connectionVec(false) });
    open();

    fireEvent.click(screen.getByRole("button", { name: "Load saved" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(requested(socket)).toEqual(["CCD.CONFIG_PROCESS.CONFIG_LOAD=On"]);
  });

  it("loads straight away when the device has no CONNECTION vector", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    open();

    fireEvent.click(screen.getByRole("button", { name: "Load saved" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(requested(socket)).toEqual(["CCD.CONFIG_PROCESS.CONFIG_LOAD=On"]);
  });

  it("follows the vector's own state for feedback", () => {
    const { socket } = renderEntry();
    receive(socket, { tag: "def", vector: configVec() });
    open();
    expect(screen.getByText("Idle")).toBeInTheDocument();

    receive(socket, { tag: "set", vector: { ...configVec(), state: "Busy" } });
    expect(screen.getByText("Busy")).toBeInTheDocument();

    receive(socket, { tag: "set", vector: { ...configVec(), state: "Alert" } });
    expect(screen.getByText("Alert")).toBeInTheDocument();
  });

  it("opens from a caller's own trigger instead of the sidebar entry", () => {
    const { socket } = renderConnected(
      <DeviceConfigDialog device="CCD">
        <button type="button">Configure the camera</button>
      </DeviceConfigDialog>,
    );
    receive(socket, { tag: "def", vector: configVec() });

    // No sidebar providers here: a consumer's own shell owes this component
    // nothing but a trigger.
    fireEvent.click(screen.getByRole("button", { name: "Configure the camera" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });
});
