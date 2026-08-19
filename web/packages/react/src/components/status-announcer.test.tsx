/** Tests for the spoken status region: what it says, and everything it stays quiet for. */

import {
  CLIENT_PROTOCOL_VERSION,
  IndiClient,
  type IPState,
  type NumberVector,
} from "@indikit/client";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IndiProvider } from "../context";
import { FakeSocket } from "../testing/fake-socket";
import { receive, renderConnected } from "../testing/render";
import { StatusAnnouncer } from "./status-announcer";

afterEach(() => {
  cleanup();
  // A test that installs fake timers and then fails would otherwise leave them
  // installed for whatever runs next, which is how a suite gains an order
  // dependence nobody can reproduce.
  vi.useRealTimers();
});

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

/** The dome shutter: the property an operator presses, on a second device. */
function shutter(overrides: Partial<NumberVector> = {}): NumberVector {
  return vec({ device: "Dome", name: "DOME_SHUTTER", label: "Shutter", ...overrides });
}

/**
 * The shutter partway through its travel.
 *
 * The position is what makes a run of Busy frames genuinely distinct: each one
 * merges a new value into the cache, so nothing upstream can collapse them and
 * the announcer's own guard is what has to hold.
 *
 * @param position - Percent open, as the driver reports it.
 * @param state - The state on that frame.
 * @returns The shutter vector at that position.
 */
function moving(position: number, state: IPState): NumberVector {
  return shutter({
    state,
    elements: [{ kind: "number", name: "SHUTTER_POSITION", value: position }],
  });
}

/** The region's current text, or the empty string when it has said nothing. */
function announced(): string {
  return screen.getByRole("status").textContent ?? "";
}

/**
 * The node carrying the current announcement.
 *
 * Compared by identity where a test needs "and said nothing further": the
 * announcement is keyed, so a repeat of the same sentence is a different node
 * and a silent region is the same one.
 */
function spoken(): Element | null {
  return screen.getByRole("status").firstElementChild;
}

/** How long the client waits before opening a replacement socket, in these tests. */
const RECONNECT_DELAY = 10;

/**
 * The nth socket the client has opened.
 *
 * @param sockets - Every socket the factory has produced, oldest first.
 * @param index - Which one.
 * @returns That socket.
 */
function socketAt(sockets: readonly FakeSocket[], index: number): FakeSocket {
  const socket = sockets[index];
  if (socket === undefined) throw new Error(`the client opened no socket ${index}`);
  return socket;
}

/**
 * Render the announcer over a client whose every socket the test can reach.
 *
 * `renderConnected` hands back the first socket only, and a transport recovery
 * needs the second: the client drops the dead one and builds a replacement from
 * the factory when its reconnect timer fires. Everything else here is what
 * `renderConnected` does, including the `hello` the bridge leads with.
 *
 * @returns The sockets the client has opened, oldest first.
 */
function renderAcrossReconnect(): { sockets: FakeSocket[] } {
  const sockets: FakeSocket[] = [];
  const client = new IndiClient({
    url: "ws://x/ws",
    reconnectDelay: RECONNECT_DELAY,
    webSocketFactory: () => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    },
  });
  render(
    <IndiProvider client={client}>
      <StatusAnnouncer />
    </IndiProvider>,
  );
  act(() => socketAt(sockets, 0).open());
  receive(socketAt(sockets, 0), {
    event: "hello",
    protocol: CLIENT_PROTOCOL_VERSION,
    server: "test",
  });
  return { sockets };
}

describe("StatusAnnouncer", () => {
  it("renders a polite status region that starts empty", () => {
    renderConnected(<StatusAnnouncer />);
    const region = screen.getByRole("status");
    expect(region).toBeInTheDocument();
    expect(region).toHaveClass("sr-only");
    expect(announced()).toBe("");
  });

  it("announces a vector entering Alert, by label and device", () => {
    const { socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: vec() });
    expect(announced()).toBe("");

    receive(socket, { tag: "set", vector: vec({ state: "Alert" }) });
    expect(announced()).toBe("Temperature on CCD is in Alert.");
  });

  it("says nothing for a value change or a state that is not Alert", () => {
    const { socket } = renderConnected(<StatusAnnouncer />);
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
    const { socket } = renderConnected(<StatusAnnouncer />);
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
    const { socket } = renderConnected(<StatusAnnouncer />);
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
    const { socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: vec({ state: "Alert" }) });
    const first = screen.getByRole("status").firstElementChild;

    receive(socket, { tag: "delProperty", device: "CCD", name: "CCD_TEMPERATURE" });
    receive(socket, { tag: "def", vector: vec({ state: "Alert" }) });
    expect(announced()).toBe("Temperature on CCD is in Alert.");
    expect(screen.getByRole("status").firstElementChild).not.toBe(first);
  });

  it("speaks for a device other than the first one it saw", () => {
    // The region is mounted page-level precisely so it covers the device that is
    // not on screen; a subscription narrowed to a selection would only ever
    // announce faults an operator was already looking at.
    const { socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: vec() });
    receive(socket, { tag: "def", vector: shutter() });

    receive(socket, { tag: "set", vector: shutter({ state: "Alert" }) });
    expect(announced()).toBe("Shutter on Dome is in Alert.");
  });
});

describe("StatusAnnouncer: a vector this browser wrote to", () => {
  it("announces the Busy and then the Ok that answer one press", () => {
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: shutter() });
    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });

    receive(socket, { tag: "set", vector: shutter({ state: "Busy" }) });
    expect(announced()).toBe("Shutter on Dome is Busy.");

    receive(socket, { tag: "set", vector: shutter({ state: "Ok" }) });
    expect(announced()).toBe("Shutter on Dome is Ok.");
  });

  it("says Busy once for a press, not once per progress frame", () => {
    // The dome reports its position for about thirteen seconds between the press
    // and the settle, and every one of those frames carries state="Busy" again.
    // Recording the state each press was announced at is the only thing between
    // that and a screen reader talking over the operator for the whole run.
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: moving(0, "Idle") });
    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });

    receive(socket, { tag: "set", vector: moving(0, "Busy") });
    expect(announced()).toBe("Shutter on Dome is Busy.");
    const busy = spoken();

    for (const position of [12, 25, 40, 63, 88]) {
      receive(socket, { tag: "set", vector: moving(position, "Busy") });
    }

    // One announcement for six frames. A second "…is Busy." reads identically, so
    // the node is the only thing that tells a repeat from silence - and the count
    // covers the other way a region could speak six times, by keeping the earlier
    // sentences beside the newest instead of replacing them.
    expect(spoken()).toBe(busy);
    expect(screen.getByRole("status").childElementCount).toBe(1);

    // The settle is the second and last sentence the press buys, and it disarms:
    // a driver still reporting afterwards is telemetry again.
    receive(socket, { tag: "set", vector: moving(100, "Ok") });
    expect(announced()).toBe("Shutter on Dome is Ok.");
    const settled = spoken();

    receive(socket, { tag: "set", vector: moving(100, "Busy") });
    expect(spoken()).toBe(settled);
  });

  it("acknowledges a press made while the property was already Busy", () => {
    // The gap the Busy-repeats-Busy guard left behind, and the second bug of the
    // shape "the answer to a press carried a state that did not change". The
    // dome is mid-travel on its own telemetry when the operator presses; the
    // frame answering the press carries Busy again, so a guard reading the
    // wire's previous state swallowed the acknowledgement and the press bought
    // nothing until the settle. Thirteen seconds of silence after pressing Open
    // is when an operator presses again.
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: moving(30, "Busy") });
    receive(socket, { tag: "set", vector: moving(45, "Busy") });
    expect(announced()).toBe("");

    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });
    receive(socket, { tag: "set", vector: moving(58, "Busy") });
    expect(announced()).toBe("Shutter on Dome is Busy.");
  });

  it("acknowledges a press once, even one made while already Busy", () => {
    // The acknowledgement above must not cost the volume guard: the frames after
    // it are the same position telemetry as ever, and the press has been
    // answered. Once per press, not once per frame, whatever the property was
    // doing when it was pressed.
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: moving(30, "Busy") });
    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });
    receive(socket, { tag: "set", vector: moving(45, "Busy") });
    const acknowledged = spoken();

    for (const position of [58, 71, 84]) {
      receive(socket, { tag: "set", vector: moving(position, "Busy") });
    }
    expect(spoken()).toBe(acknowledged);
    expect(screen.getByRole("status").childElementCount).toBe(1);

    receive(socket, { tag: "set", vector: moving(100, "Ok") });
    expect(announced()).toBe("Shutter on Dome is Ok.");
  });

  it("acknowledges a second press on a property still working on the first", () => {
    // Two presses are two things the operator is owed an answer to, and the
    // second lands while the property is Busy from the first - so the same
    // "nothing changed" reading that swallowed the case above would swallow this
    // one. Re-arming on every `onWrite` is what answers it.
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: moving(0, "Idle") });
    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });
    receive(socket, { tag: "set", vector: moving(10, "Busy") });
    const first = spoken();

    client.setSwitch("Dome", "DOME_SHUTTER", { CLOSE: true });
    receive(socket, { tag: "set", vector: moving(20, "Busy") });

    expect(announced()).toBe("Shutter on Dome is Busy.");
    expect(spoken()).not.toBe(first);
  });

  it("goes quiet once the write settles, however long the driver reports", () => {
    // One press buys at most two sentences. A dome that keeps moving its
    // position for another hour is telemetry again the moment it stops saying
    // Busy, and this is the assertion that stops the region turning into the log.
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: shutter() });
    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });
    receive(socket, { tag: "set", vector: shutter({ state: "Busy" }) });
    receive(socket, { tag: "set", vector: shutter({ state: "Ok" }) });
    const settled = spoken();

    receive(socket, { tag: "set", vector: shutter({ state: "Busy" }) });
    receive(socket, { tag: "set", vector: shutter({ state: "Idle" }) });
    receive(socket, { tag: "set", vector: shutter({ state: "Ok" }) });

    expect(announced()).toBe("Shutter on Dome is Ok.");
    // Same node, so nothing was re-announced - a fresh "…is Ok." would read
    // identically and only the node identity tells them apart.
    expect(spoken()).toBe(settled);
  });

  it("disarms on the first state that is not Busy, even when Busy never came", () => {
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: shutter() });
    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });

    receive(socket, { tag: "set", vector: shutter({ state: "Ok" }) });
    expect(announced()).toBe("Shutter on Dome is Ok.");
    const settled = spoken();

    receive(socket, { tag: "set", vector: shutter({ state: "Busy" }) });
    expect(spoken()).toBe(settled);
  });

  it("answers a write whose state never changed", () => {
    // The regression. Most libindi writes go straight to Ok or Idle with no
    // intermediate Busy, onto a property already sitting at that state, so this
    // is the ordinary case and not an edge: the answer to the press carries the
    // state the property already held. A single `previous === state` guard above
    // the arming read it as telemetry and the press produced silence.
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: shutter({ state: "Ok" }) });
    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });

    receive(socket, { tag: "set", vector: shutter({ state: "Ok" }) });
    expect(announced()).toBe("Shutter on Dome is Ok.");
  });

  it("does not hand a later transition to a write that was already answered", () => {
    // The second half of the same defect, and the worse half: the unchanged
    // state left the property armed as well as silent, so the next transition -
    // telemetry, minutes later, nothing to do with the press - was announced as
    // the answer. Here the settle disarms, so what follows is telemetry again.
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: shutter({ state: "Ok" }) });
    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });
    receive(socket, { tag: "set", vector: shutter({ state: "Ok" }) });
    const settled = spoken();

    receive(socket, { tag: "set", vector: shutter({ state: "Busy" }) });
    receive(socket, { tag: "set", vector: shutter({ state: "Idle" }) });

    expect(announced()).toBe("Shutter on Dome is Ok.");
    expect(spoken()).toBe(settled);
  });

  it("says nothing for a property this browser never wrote to", () => {
    // The arming is per property, not "somebody wrote something recently": the
    // CCD going Busy on its own poll is telemetry even in the second after a
    // dome command.
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: shutter() });
    receive(socket, { tag: "def", vector: vec() });
    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });

    receive(socket, { tag: "set", vector: vec({ state: "Busy" }) });
    expect(announced()).toBe("");
  });

  it("still calls an Alert an Alert, and stops there", () => {
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: shutter() });
    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });

    receive(socket, { tag: "set", vector: shutter({ state: "Alert" }) });
    expect(announced()).toBe("Shutter on Dome is in Alert.");
    const failed = spoken();

    // Alert is not Busy, so it also ends the write: what the driver does next is
    // telemetry, and only a fresh Alert would be news again.
    receive(socket, { tag: "set", vector: shutter({ state: "Ok" }) });
    expect(spoken()).toBe(failed);
  });

  it("answers a press that a latched Alert replies to", () => {
    // A property already sitting in Alert answers the press by saying Alert
    // again. Nothing changed, so rule 1 has nothing to report - and silence here
    // loses the press outright, which is why arming is the second way into the
    // Alert branch.
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: shutter({ state: "Alert" }) });
    expect(announced()).toBe("Shutter on Dome is in Alert.");
    const entered = spoken();

    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });
    receive(socket, { tag: "set", vector: shutter({ state: "Alert" }) });
    // Same sentence as the entry, so only a fresh node says it was spoken again.
    expect(announced()).toBe("Shutter on Dome is in Alert.");
    expect(spoken()).not.toBe(entered);
  });

  it("disarms on the latched Alert that answered the press", () => {
    // The other half: Alert is not Busy, so answering with it ends the write. A
    // recovery minutes later is telemetry, and collecting it as the answer is
    // the failure the unchanged-state defect used to produce.
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: shutter({ state: "Alert" }) });
    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });
    receive(socket, { tag: "set", vector: shutter({ state: "Alert" }) });
    const answered = spoken();

    receive(socket, { tag: "set", vector: shutter({ state: "Ok" }) });
    expect(announced()).toBe("Shutter on Dome is in Alert.");
    expect(spoken()).toBe(answered);
  });

  it("forgets a pending write when the property is deleted", () => {
    // A `del` retracts the property, so the write it was going to answer is gone
    // with it. A driver redefining on reconnect is not the answer to a press
    // made before the property existed in this incarnation.
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: shutter() });
    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });

    receive(socket, { tag: "delProperty", device: "Dome", name: "DOME_SHUTTER" });
    receive(socket, { tag: "def", vector: shutter({ state: "Busy" }) });

    expect(announced()).toBe("");
  });

  it("forgets every pending write on the device when the device goes away", () => {
    const { client, socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { tag: "def", vector: shutter() });
    receive(socket, { tag: "def", vector: shutter({ name: "DOME_PARK", label: "Park" }) });
    client.setSwitch("Dome", "DOME_SHUTTER", { OPEN: true });
    client.setSwitch("Dome", "DOME_PARK", { PARK: true });

    // No name: the whole device is retracted, not one of its properties.
    receive(socket, { tag: "delProperty", device: "Dome" });
    receive(socket, { tag: "def", vector: shutter({ state: "Busy" }) });
    receive(socket, {
      tag: "def",
      vector: shutter({ name: "DOME_PARK", label: "Park", state: "Busy" }),
    });

    expect(announced()).toBe("");
  });
});

describe("StatusAnnouncer: the connection", () => {
  it("says nothing when a session comes up connected", () => {
    // The first `connection` frame arrives while `upstream` is still false from
    // the socket opening. Without the "only if we announced the loss" guard this
    // is a recovery announcement for a fault that never happened.
    const { socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { event: "connection", connected: true });
    expect(announced()).toBe("");
  });

  it("announces an upstream loss and the recovery that follows it", () => {
    const { socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { event: "connection", connected: true });

    receive(socket, { event: "connection", connected: false });
    expect(announced()).toBe("The bridge lost its connection to indiserver.");

    receive(socket, { event: "connection", connected: true });
    expect(announced()).toBe("The bridge is connected to indiserver again.");
  });

  it("announces a dropped socket once, not once per link", () => {
    // A closed socket takes `upstream` down with it. Two sentences for one event
    // would leave the second - the narrower one - as what an operator hears.
    const { socket } = renderConnected(<StatusAnnouncer />);
    receive(socket, { event: "connection", connected: true });

    act(() => socket.close());
    expect(announced()).toBe("Disconnected from the bridge. Readings are no longer live.");
  });

  it("announces the reconnect, and arms the upstream side with it", () => {
    const { sockets } = renderAcrossReconnect();
    receive(socketAt(sockets, 0), { event: "connection", connected: true });

    vi.useFakeTimers();
    act(() => socketAt(sockets, 0).close());
    expect(announced()).toBe("Disconnected from the bridge. Readings are no longer live.");
    act(() => vi.advanceTimersByTime(RECONNECT_DELAY));
    vi.useRealTimers();

    act(() => socketAt(sockets, 1).open());
    expect(announced()).toBe("Reconnected to the bridge.");

    // The reopened socket reports `upstream` down until the bridge says
    // otherwise, so the upstream side is armed rather than claimed either way -
    // and unlike a fresh session, this one has a loss to recover from.
    receive(socketAt(sockets, 1), { event: "connection", connected: true });
    expect(announced()).toBe("The bridge is connected to indiserver again.");
  });
});
