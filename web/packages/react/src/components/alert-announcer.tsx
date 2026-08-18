/**
 * The live region that speaks a property going into Alert.
 *
 * Nothing else on the page can do this job. {@link MessageLog} is a `log` region
 * and announces the driver's own text; a property's *state* never appears there,
 * so a vector going Idle to Alert reached a sighted operator (the badge changes
 * colour and word) and nobody else.
 *
 * The reason it is a second region rather than more of the log is volume. INDI
 * `set` frames are telemetry: a CCD simulator emits them continuously, and a
 * five-minute poll updating a temperature is not a status message. Announcing
 * every `set` would make the page unusable and would bury the one event that
 * matters. So this region fires on exactly one thing - a vector *entering* Alert
 * - and stays silent for value changes, for a `set` that repeats a state, and
 * for every other state.
 *
 * "Entering" is the whole point. A latched Alert re-emits with every subsequent
 * `set` (a `set` carrying no `state` deliberately leaves the cached one alone,
 * so the vector stays Alert until the driver says otherwise), and announcing
 * each of those would be the same fault as announcing the poll. The last state
 * seen per property is therefore kept here, and the announcement happens only on
 * the transition.
 */

import { displayLabel, type IPState } from "@indi-nexus/client";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useIndiClient } from "../context";

/** One announcement, keyed so an identical repeat still replaces the node. */
interface Announcement {
  /** Monotonic, so React swaps the node even when the text is unchanged. */
  id: number;
  /** The sentence read out. */
  text: string;
}

/** Props for {@link AlertAnnouncer}. */
export interface AlertAnnouncerProps {
  /**
   * Extra classes. The region is visually hidden by default; a caller wanting a
   * visible banner can override that.
   */
  className?: string;
}

/**
 * Announce, politely and once, each property vector that enters the Alert state.
 *
 * Renders a visually hidden `status` region. Mount it once, high in the tree: it
 * watches every device, because a fault on the device an operator is *not*
 * looking at is the one they most need to be told about.
 *
 * @param props - An optional class name.
 * @returns The live region element.
 */
export function AlertAnnouncer({ className }: AlertAnnouncerProps) {
  const client = useIndiClient();
  const [announcement, setAnnouncement] = useState<Announcement | null>(null);

  useEffect(() => {
    // The last state seen per property, so a re-emitted Alert is recognised as
    // the same latched one. Nested by device rather than a joined key: no
    // separator is illegal in a device name, so a flat map would let "Dome" and
    // "Dome 2" collide on a whole-device deletion.
    const seen = new Map<string, Map<string, IPState>>();
    return client.subscribe((event) => {
      if (event.type === "del") {
        // A deleted property is gone, not resting: if it comes back in Alert that
        // is news. An unnamed `del` retracts the whole device, so forget all of it.
        if (event.name === null) seen.delete(event.device);
        else seen.get(event.device)?.delete(event.name);
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
      if (vector.state !== "Alert" || previous === "Alert") return;
      // Counted off the previous announcement rather than a closure variable, so
      // the id keeps rising across a client swap that re-runs this effect.
      setAnnouncement((last) => ({
        id: (last?.id ?? 0) + 1,
        text: `${displayLabel(vector)} on ${vector.device} is in Alert.`,
      }));
    });
  }, [client]);

  return (
    <div role="status" className={cn("sr-only", className)}>
      {/* Keyed: two runs of the same fault produce the same sentence, and a live
          region whose text is byte-identical may not be re-read. Replacing the
          node makes it a mutation either way. */}
      {announcement === null ? null : <span key={announcement.id}>{announcement.text}</span>}
    </div>
  );
}
