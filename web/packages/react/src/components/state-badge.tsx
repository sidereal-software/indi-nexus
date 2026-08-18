/** The two ways an INDI state is shown: a labelled badge, and a bare status dot. */

import type { IPState } from "@indi-nexus/client";
import { cn } from "@/lib/utils";
import { Badge } from "@/ui/badge";

/**
 * Whether the state is one that should pulse.
 *
 * Busy is the only state that means "still happening", and a still indicator cannot
 * tell an instrument mid-move from one that stopped there. The other three are
 * resting states: animating them would spend the reader's attention on nothing.
 * `motion-safe` holds it still for anyone whose system asks for reduced motion.
 *
 * The animation rings the element rather than fading it (see `--animate-state-pulse`
 * in `theme.css`): Tailwind's `animate-pulse` drops the opacity to 0.5, which takes
 * the badge's text down with its fill and put a passing badge at 1.75:1 for half of
 * every cycle.
 */
function pulseClass(state: IPState): string {
  return state === "Busy" ? "motion-safe:animate-state-pulse" : "";
}

/** Props for {@link StateBadge}. */
export interface StateBadgeProps {
  /** The INDI property state to display. */
  state: IPState;
  /**
   * DOM id for the badge, so a surrounding region can name itself with the state
   * as well as the label (`aria-labelledby="title badge"`).
   */
  id?: string;
  className?: string;
}

/**
 * Render an INDI state as a coloured badge (Idle/Ok/Busy/Alert).
 *
 * The colour comes from `data-indi-state`, which the theme maps to
 * `--indi-state`, so this file holds no copy of the state-to-colour table.
 *
 * @param props - The state and optional class name.
 * @returns The badge element.
 */
export function StateBadge({ state, id, className }: StateBadgeProps) {
  return (
    <Badge
      id={id}
      data-indi-state={state}
      className={cn(
        "border-transparent bg-[var(--indi-state)] text-[var(--indi-state-foreground)] tabular-nums",
        pulseClass(state),
        className,
      )}
    >
      {state}
    </Badge>
  );
}

/** Props for {@link StateDot}. */
export interface StateDotProps {
  /** The INDI state to display. */
  state: IPState;
  className?: string;
}

/**
 * Render an INDI state as a bare coloured dot, for use beside its own label.
 *
 * Decorative: the state is named in text next to it, because colour alone would
 * be unreadable to anyone who cannot separate the Busy and Alert hues.
 *
 * @param props - The state and an optional class name.
 * @returns The dot element.
 */
export function StateDot({ state, className }: StateDotProps) {
  return (
    <span
      data-indi-state={state}
      className={cn("size-2.5 rounded-full bg-[var(--indi-state)]", pulseClass(state), className)}
      aria-hidden
    />
  );
}
