/** A compact indicator of the bridge and upstream connection state. */

import { CLIENT_PROTOCOL_VERSION } from "@indi-nexus/client";
import { cn } from "@/lib/utils";
import { useConnection } from "../hooks";

/** A single labelled status dot. */
function StatusDot({ on, label }: { on: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className={cn("size-2 rounded-full", on ? "bg-state-ok" : "bg-state-alert")}
        aria-hidden
      />
      <span>{label}</span>
      <span className="sr-only">{on ? "connected" : "disconnected"}</span>
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
    <div className={cn("flex items-center gap-4 text-xs text-muted-foreground", className)}>
      <StatusDot on={transport} label="bridge" />
      <StatusDot on={upstream} label="indiserver" />
      {mismatched && (
        <span
          className="text-state-alert"
          title={`The bridge speaks protocol ${protocol}; this UI speaks ${CLIENT_PROTOCOL_VERSION}.`}
        >
          protocol {protocol}, UI {CLIENT_PROTOCOL_VERSION}
        </span>
      )}
    </div>
  );
}
