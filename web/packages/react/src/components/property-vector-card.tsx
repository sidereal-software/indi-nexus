/** A card presenting one INDI property vector: header + kind-specific control. */

import type { Vector } from "@indi-nexus/client";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/ui/card";
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
 * @param props - The vector and an optional class name.
 * @returns The card element.
 */
export function PropertyVectorCard({ vector, className }: PropertyVectorCardProps) {
  const perm = "perm" in vector ? vector.perm : undefined;
  return (
    <Card className={cn("gap-3 py-4", className)}>
      <CardHeader className="gap-0.5 px-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="truncate text-sm">{vector.label ?? vector.name}</CardTitle>
            <CardDescription className="truncate font-mono text-xs">
              {vector.name}
              {perm ? ` · ${perm}` : ""}
            </CardDescription>
          </div>
          <StateBadge state={vector.state} />
        </div>
      </CardHeader>
      <CardContent className="px-4">
        <VectorControl vector={vector} />
      </CardContent>
    </Card>
  );
}
