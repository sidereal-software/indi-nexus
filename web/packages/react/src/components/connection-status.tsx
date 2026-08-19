/** A compact indicator of the bridge and upstream connection state. */

import { CLIENT_PROTOCOL_VERSION } from "@indi-nexus/client";
import { cn } from "@/lib/utils";
import { useConnection } from "../hooks";

/**
 * A single labelled status dot.
 *
 * The two states differ by shape as well as by hue: connected is a filled disc,
 * disconnected is a hollow ring. Colour alone was the whole difference before,
 * and under simulated deuteranopia the green and the red measured 1.08:1 apart -
 * so a colour-blind operator could not tell a live panel from a dead one, which
 * is exactly the moment every reading on screen has stopped being true.
 *
 * The word is the other half, and it is the system's own rule rather than a
 * belt-and-braces addition: a state is written out in text, not left to a shape.
 * Only the failure is written, because "bridge online / indiserver online" is
 * two permanent extra lines in a 16rem sidebar for the state that is true almost
 * always; the affirmative stays visually hidden, so a screen reader still hears
 * it and only the alarm takes space.
 *
 * The fill is `--state-ok-ink`, not `--state-ok`: as a bare graphic with no
 * foreground of its own the Ok fill is 2.99:1 on the sidebar, under SC 1.4.11's
 * 3:1, and the fill is not ours to retune. The alert ring keeps `--state-alert`,
 * which already clears 3:1 on every surface this line can sit on.
 */
function StatusDot({ on, label }: { on: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className={cn(
          "size-2.5 shrink-0 rounded-full border-2",
          on ? "border-state-ok-ink bg-state-ok-ink" : "border-state-alert",
        )}
        aria-hidden
      />
      <span>{label}</span>
      {on ? <span className="sr-only">connected</span> : <span>offline</span>}
    </span>
  );
}

/** Props for {@link ConnectionStatus}. */
export interface ConnectionStatusProps {
  className?: string;
}

/**
 * Show two dots: the browser<->bridge socket and the bridge<->indiserver link.
 *
 * A third item appears only when the bridge announces a contract version this
 * build was not written against. It is deliberately quiet and never blocks
 * anything: version bumps are breaking-only, everything additive keeps working,
 * and the panel stays usable either way - but an operator chasing a control
 * that renders blank should not have to read the message log to find out that
 * the two halves are from different releases.
 *
 * @param props - Optional class name.
 * @returns The status element.
 */
export function ConnectionStatus({ className }: ConnectionStatusProps) {
  const { transport, upstream, protocol } = useConnection();
  // `null` means no frame has arrived yet, which is not a mismatch.
  const mismatched = protocol !== null && protocol !== CLIENT_PROTOCOL_VERSION;
  return (
    // Wrapping, because "offline" appears only when something is wrong and both
    // dots carrying it outgrow the sidebar's width. An outage is the right
    // moment for this line to take a second row.
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground",
        className,
      )}
    >
      <StatusDot on={transport} label="bridge" />
      <StatusDot on={upstream} label="indiserver" />
      {mismatched && (
        <span
          // `--state-alert` is a fill, tuned to be read behind its own foreground.
          // Set as 12px type on the sidebar - which is where this line lives - it
          // measures 3.42:1 in light mode, below AA. `-ink` is the same hue taken
          // down until it reads as text on every surface this line can sit on.
          className="text-state-alert-ink"
          title={`The bridge speaks protocol ${protocol}; this UI speaks ${CLIENT_PROTOCOL_VERSION}.`}
        >
          protocol {protocol}, UI {CLIENT_PROTOCOL_VERSION}
        </span>
      )}
    </div>
  );
}
