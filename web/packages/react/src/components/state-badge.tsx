/** A small badge whose colour tracks an INDI vector/light state. */

import type { IPState } from "@indi-nexus/client";
import { cn } from "../lib/utils";
import { Badge } from "../ui/badge";

/** Tailwind classes per state, using the theme's `--color-state-*` tokens. */
const STATE_CLASSES: Record<IPState, string> = {
  Idle: "bg-state-idle text-state-idle-foreground",
  Ok: "bg-state-ok text-state-ok-foreground",
  Busy: "bg-state-busy text-state-busy-foreground",
  Alert: "bg-state-alert text-state-alert-foreground",
};

/** Props for {@link StateBadge}. */
export interface StateBadgeProps {
  /** The INDI property state to display. */
  state: IPState;
  className?: string;
}

/**
 * Render an INDI state as a coloured badge (Idle/Ok/Busy/Alert).
 *
 * @param props - The state and optional class name.
 * @returns The badge element.
 */
export function StateBadge({ state, className }: StateBadgeProps) {
  return (
    <Badge className={cn("border-transparent tabular-nums", STATE_CLASSES[state], className)}>
      {state}
    </Badge>
  );
}
