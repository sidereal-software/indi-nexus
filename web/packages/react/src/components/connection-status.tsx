/** A compact indicator of the bridge and upstream connection state. */

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
 * @param props - Optional class name.
 * @returns The status element.
 */
export function ConnectionStatus({ className }: ConnectionStatusProps) {
  const { transport, upstream } = useConnection();
  return (
    <div className={cn("flex items-center gap-4 text-xs text-muted-foreground", className)}>
      <StatusDot on={transport} label="bridge" />
      <StatusDot on={upstream} label="indiserver" />
    </div>
  );
}
