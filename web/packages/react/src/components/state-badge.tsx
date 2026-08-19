/** The two ways an INDI state is shown: a labelled badge, and a bare status dot. */

import type { IPState } from "@indikit/client";
import { cn } from "@/lib/utils";
import { Badge } from "@/ui/badge";

/**
 * Whether this state should pulse, as the attribute `theme.css` hooks.
 *
 * Busy is the only state that means "still happening", and a still indicator
 * cannot tell an instrument mid-move from one that stopped there. The other
 * three are resting states: animating them would spend the reader's attention
 * on nothing. `undefined` leaves the attribute off the element entirely.
 *
 * The animation is a ring on an `::after`, not a fade of the element (see
 * `[data-indi-pulse]` in `theme.css`): Tailwind's `animate-pulse` drops the
 * opacity to 0.5, which takes the badge's text down with its fill and put a
 * passing badge at 1.75:1 for half of every cycle. `prefers-reduced-motion` is
 * honoured by the media query around that rule rather than by a `motion-safe:`
 * class here, so the whole mechanism lives in one place.
 *
 * @param state - The INDI property state being shown.
 * @returns The empty string when the state pulses, `undefined` otherwise.
 */
function pulseAttribute(state: IPState): "" | undefined {
  return state === "Busy" ? "" : undefined;
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
 * `relative` is the containing block the pulse ring is positioned against, and
 * `overflow-visible` is what lets the ring leave the badge: twMerge drops the
 * primitive's own `overflow-hidden`, which would otherwise clip it back to the
 * badge's edge at every frame. Both are unconditional, so nothing about the box
 * changes when the instrument goes Busy.
 *
 * @param props - The state and optional class name.
 * @returns The badge element.
 */
export function StateBadge({ state, id, className }: StateBadgeProps) {
  return (
    <Badge
      id={id}
      data-indi-state={state}
      data-indi-pulse={pulseAttribute(state)}
      className={cn(
        "relative overflow-visible border-transparent bg-[var(--indi-state)] text-[var(--indi-state-foreground)] tabular-nums",
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
      data-indi-pulse={pulseAttribute(state)}
      className={cn("relative size-2.5 rounded-full bg-[var(--indi-state)]", className)}
      aria-hidden
    />
  );
}
