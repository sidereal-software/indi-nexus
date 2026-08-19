/**
 * The page's spoken status region: what an operator who is not looking is told.
 *
 * Nothing else on the page can do this job. {@link MessageLog} is a `log` region
 * and announces the driver's own text; a property's *state* never appears there,
 * and neither does the socket, so a vector going Idle to Alert - or the bridge
 * dying outright - reached a sighted operator and nobody else.
 *
 * The reason it is a second region rather than more of the log is volume. INDI
 * `set` frames are telemetry: a CCD simulator emits them continuously, and a
 * five-minute poll updating a temperature is not a status message. Announcing
 * every `set` would make the page unusable and would bury the one event that
 * matters. So this region speaks for exactly three things, and the rule for each
 * is what keeps it from becoming the log again:
 *
 * 1. **A vector entering Alert.** "Entering" is the whole point: a latched Alert
 *    re-emits with every subsequent `set` (a `set` carrying no `state`
 *    deliberately leaves the cached one alone, so the vector stays Alert until
 *    the driver says otherwise), and announcing each of those would be the same
 *    fault as announcing the poll. The last state seen per property is therefore
 *    kept here, and the announcement happens only on the transition.
 * 2. **A vector this browser wrote to, until it settles.** A state change is
 *    telemetry only when nobody asked for it. When the operator presses Open,
 *    the shutter going Busy and then Ok is the answer to that press, and a
 *    sighted operator gets it from the badge. `IndiClient.onWrite` is what tells
 *    the two apart - only the sender can. The property is disarmed by the first
 *    state that is not Busy, so one press buys at most two sentences and a
 *    driver that keeps emitting afterwards is back to being telemetry.
 * 3. **The connection.** A lost socket is not telemetry under any reading: every
 *    number on screen stops being true and nothing else says so out loud. A
 *    recovery is announced only when this region announced the loss before it,
 *    which is also what keeps a freshly opened session silent.
 *
 * **The last state seen is rule 1's, and no other rule may read it.** That is
 * the invariant, and it is written as one because the region has now had two
 * separate bugs of one shape: "the answer to a press carried a state that did
 * not change". First a `previous === state` guard above everything, which left a
 * same-state answer silent *and* still armed, so an unrelated transition minutes
 * later was collected as the answer. Then, after that was split out, a
 * `state === "Busy" && previous === "Busy"` guard on the write side, which
 * swallowed the acknowledgement whenever the property was already Busy from
 * telemetry when the operator pressed - thirteen seconds of silence after
 * pressing Open, which is precisely when an operator presses again. Neither is
 * an edge case: most libindi writes go straight to Ok or Idle with no
 * intermediate Busy, onto a property frequently already at that state.
 *
 * So the two rules ask two different questions, and neither borrows the other's
 * state:
 *
 * - **Telemetry** asks "has it changed", against the last state seen on the
 *   wire. Entering Alert is news; a latched Alert re-emitting is not.
 * - **A press** asks "what have I already said about this write", against the
 *   state that write was last announced at (null until it is acknowledged).
 *   Never the wire's previous state, which has nothing to do with what the
 *   operator has been told.
 *
 * The second rule is one line - `announcedFor !== state` - and it does the work
 * three guards were doing. Every press is acknowledged exactly once, whatever
 * the driver answers with and whatever the property was doing beforehand; a
 * driver repeating itself says nothing, which is what keeps the dome's thirteen
 * seconds of Busy position telemetry down to one sentence.
 *
 * That bounds it in both directions. It cannot become a firehose: one sentence
 * per entry into Alert, and per press at most one acknowledgement plus the
 * settle that disarms. It cannot go silent: an armed property announces its very
 * next frame unconditionally. The one thing it cannot recover from is a write
 * the bridge refuses outright, which arms a property that will never answer -
 * see `CONCERNS.md`, which also says why the `error` control frame cannot fix it.
 */

import { displayLabel, type IPState } from "@indikit/client";
import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useIndiClient } from "../context";

/** One announcement, keyed so an identical repeat still replaces the node. */
interface Announcement {
  /** Monotonic, so React swaps the node even when the text is unchanged. */
  id: number;
  /** The sentence read out. */
  text: string;
}

/** Props for {@link StatusAnnouncer}. */
export interface StatusAnnouncerProps {
  /**
   * Extra classes. The region is visually hidden by default; a caller wanting a
   * visible banner can override that.
   */
  className?: string;
}

/**
 * Announce, politely and once, each thing an operator cannot afford to miss.
 *
 * Renders a visually hidden `status` region. Mount it once, high in the tree: it
 * watches every device, because a fault on the device an operator is *not*
 * looking at is the one they most need to be told about.
 *
 * @param props - An optional class name.
 * @returns The live region element.
 */
export function StatusAnnouncer({ className }: StatusAnnouncerProps) {
  const client = useIndiClient();
  const [announcement, setAnnouncement] = useState<Announcement | null>(null);

  const announce = useCallback((text: string) => {
    // Counted off the previous announcement rather than a closure variable, so
    // the id keeps rising across a client swap that re-runs the effects.
    setAnnouncement((last) => ({ id: (last?.id ?? 0) + 1, text }));
  }, []);

  useEffect(() => {
    // The last state seen per property, so a re-emitted Alert is recognised as
    // the same latched one. Nested by device rather than a joined key: no
    // separator is illegal in a device name, so a flat map would let "Dome" and
    // "Dome 2" collide on a whole-device deletion.
    const seen = new Map<string, Map<string, IPState>>();
    // The properties this browser has written to and that have not answered yet,
    // nested the same way and for the same reason. The value is the state that
    // write has already been *announced* at, or null while the press is still
    // unacknowledged - which is what turns the rule below into "never say the
    // same thing twice about one press" rather than a case analysis.
    const awaiting = new Map<string, Map<string, IPState | null>>();

    const unwatch = client.onWrite((device, name) => {
      let pending = awaiting.get(device);
      if (pending === undefined) {
        pending = new Map<string, IPState | null>();
        awaiting.set(device, pending);
      }
      // Back to null even for a property already pending: a second press is a
      // second thing the operator is owed an answer to, and hearing the same
      // sentence again is how they learn it registered.
      pending.set(name, null);
    });

    const unsubscribe = client.subscribe((event) => {
      if (event.type === "del") {
        // A deleted property is gone, not resting: if it comes back in Alert that
        // is news. An unnamed `del` retracts the whole device, so forget all of it.
        if (event.name === null) {
          seen.delete(event.device);
          awaiting.delete(event.device);
          return;
        }
        seen.get(event.device)?.delete(event.name);
        awaiting.get(event.device)?.delete(event.name);
        return;
      }
      const vector = event.vector;
      if (vector === null) return;
      let states = seen.get(vector.device);
      if (states === undefined) {
        states = new Map<string, IPState>();
        seen.set(vector.device, states);
      }
      const previous = states.get(vector.name);
      states.set(vector.name, vector.state);

      const pending = awaiting.get(vector.device);
      const armed = pending?.has(vector.name) === true;
      // What this pending write has already been announced at. Only meaningful
      // while `armed`, and null there until the press has been acknowledged.
      const announcedFor = pending?.get(vector.name) ?? null;

      // The one decision, and the two rules side by side. `previous` appears on
      // the telemetry side and NOWHERE ELSE, which is the invariant: both bugs
      // this component has had were the write side reading it, because "the
      // answer to a press carried a state that did not change" is the ordinary
      // case and not an edge one. What the write side asks is what it has
      // already said, so a press is acknowledged exactly once however the
      // driver answers, and a driver repeating itself is silent.
      const news = armed
        ? announcedFor !== vector.state
        : vector.state === "Alert" && previous !== "Alert";

      if (armed) {
        // Busy is the only state that means "still happening", so anything else
        // ends the write. Until it does, recording what was said is what keeps
        // the dome's thirteen seconds of position telemetry to one sentence.
        if (vector.state === "Busy") pending.set(vector.name, vector.state);
        else {
          pending.delete(vector.name);
          if (pending.size === 0) awaiting.delete(vector.device);
        }
      }

      if (!news) return;
      // Alert keeps its own wording on both sides. It names a fault rather than
      // a state, and an armed property in Alert is both at once.
      announce(
        vector.state === "Alert"
          ? `${displayLabel(vector)} on ${vector.device} is in Alert.`
          : `${displayLabel(vector)} on ${vector.device} is ${vector.state}.`,
      );
    });

    return () => {
      unwatch();
      unsubscribe();
    };
  }, [client, announce]);

  useEffect(() => {
    // Seeded from the live state, so mounting into a session that is already up
    // announces nothing: only a change from what was true when this region
    // started listening is news. `protocol` also moves this state, and a version
    // arriving is not a connection event, so each link is compared by name.
    let previous = client.connectionState;
    // A recovery is only news to someone who heard the loss. Without this, the
    // first `connection` frame of a session - sent while `upstream` is still
    // false from the socket opening - would announce a fault that never
    // happened.
    let transportLost = false;
    let upstreamLost = false;

    return client.onConnection((state) => {
      const was = previous;
      previous = state;
      if (state.transport !== was.transport) {
        if (!state.transport) {
          transportLost = true;
          announce("Disconnected from the bridge. Readings are no longer live.");
        } else if (transportLost) {
          transportLost = false;
          // A reopened socket reports `upstream` down until the bridge's next
          // `connection` frame says otherwise, so this arms the upstream side
          // rather than claiming either way for it here.
          upstreamLost = true;
          announce("Reconnected to the bridge.");
        }
        // A dropped socket takes `upstream` with it. One sentence, not two.
        return;
      }
      if (state.upstream === was.upstream) return;
      if (!state.upstream) {
        upstreamLost = true;
        announce("The bridge lost its connection to indiserver.");
      } else if (upstreamLost) {
        upstreamLost = false;
        announce("The bridge is connected to indiserver again.");
      }
    });
  }, [client, announce]);

  return (
    // `status` and not `alert`, for the connection sentences as much as for the
    // rest: assertive would interrupt whatever the operator is having read to
    // them, and a region that talks over a screen reader is one they turn off.
    // Losing the socket is the strongest case against that - every reading on
    // screen has stopped being true - and it is still not a frequent event, so
    // the sentence can wait its turn. Decided, not defaulted.
    <div role="status" className={cn("sr-only", className)}>
      {/* Keyed: two runs of the same fault produce the same sentence, and a live
          region whose text is byte-identical may not be re-read. Replacing the
          node makes it a mutation either way. */}
      {announcement === null ? null : <span key={announcement.id}>{announcement.text}</span>}
    </div>
  );
}
