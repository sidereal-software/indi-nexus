/** A card presenting one INDI property vector: header + kind-specific control. */

import { displayLabel, type Vector } from "@indi-nexus/client";
import { memo, useId } from "react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/ui/card";
import { useDisplaySettings } from "../display-settings";
import { VectorControl } from "./element-controls";
import { StateBadge } from "./state-badge";

/** Props for {@link PropertyVectorCard}. */
export interface PropertyVectorCardProps {
  /** The property vector to render. */
  vector: Vector;
  className?: string;
}

/**
 * Render a property vector as a titled card with its state badge and control.
 *
 * The technical detail line (raw INDI property name and permission) only shows
 * when the surrounding `DisplaySettingsProvider` enables debug info; operators
 * see just the human label by default.
 *
 * The card is a labelled group and its title is a level-3 heading, which is what
 * makes a panel of thirty cards navigable without a mouse: the heading list is
 * the property list. The group's name is the title *and* the state badge, so
 * "Exposure, Alert" arrives as one thing rather than as a title with a coloured
 * shape floating near it. `CardTitle` renders a plain `div`, so the heading role
 * is declared on it rather than by swapping the vendored primitive's element.
 *
 * Memoised, because a device publishes thirty of these and a `set` frame changes
 * one. `PropertyStore` merges immutably - a `set` replaces only the vector it
 * touched and leaves every other reference alone - so the default shallow compare
 * is exactly the right test and re-rendering is confined to the card that moved.
 *
 * @param props - The vector and an optional class name.
 * @returns The card element.
 */
export const PropertyVectorCard = memo(function PropertyVectorCard({
  vector,
  className,
}: PropertyVectorCardProps) {
  const { showDebug } = useDisplaySettings();
  const perm = "perm" in vector ? vector.perm : undefined;
  const id = useId();
  const titleId = `${id}-title`;
  const stateId = `${id}-state`;
  return (
    <Card
      role="group"
      aria-labelledby={`${titleId} ${stateId}`}
      className={cn("gap-3 py-4", className)}
    >
      <CardHeader className="gap-0.5 px-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle id={titleId} role="heading" aria-level={3} className="truncate text-sm">
              {displayLabel(vector)}
            </CardTitle>
            {showDebug ? (
              <CardDescription className="truncate font-mono text-xs">
                {vector.name}
                {perm ? ` · ${perm}` : ""}
              </CardDescription>
            ) : null}
          </div>
          <StateBadge id={stateId} state={vector.state} />
        </div>
      </CardHeader>
      <CardContent className="px-4">
        <VectorControl vector={vector} />
      </CardContent>
    </Card>
  );
});
