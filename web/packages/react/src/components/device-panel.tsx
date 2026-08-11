/** All of one device's properties, grouped by INDI group, as a grid of cards. */

import type { DeviceSnapshot, Vector } from "@indi-nexus/client";
import { cn } from "@/lib/utils";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/ui/empty";
import { useDevice } from "../hooks";
import { PropertyVectorCard } from "./property-vector-card";

/** Group a device's vectors by their `group`, sorted by group then name. */
function groupVectors(properties: DeviceSnapshot): [string, Vector[]][] {
  const groups = new Map<string, Vector[]>();
  for (const vector of Object.values(properties)) {
    const key = vector.group ?? "";
    const bucket = groups.get(key);
    if (bucket) bucket.push(vector);
    else groups.set(key, [vector]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([group, vectors]) => [group, vectors.sort((a, b) => a.name.localeCompare(b.name))]);
}

/** Props for {@link DevicePanel}. */
export interface DevicePanelProps {
  /** The device whose properties to render. */
  device: string;
  className?: string;
}

/**
 * Render every property of one device, grouped and laid out as responsive cards.
 *
 * @param props - The device name and an optional class name.
 * @returns The panel element.
 */
export function DevicePanel({ device, className }: DevicePanelProps) {
  const properties = useDevice(device);
  const groups = groupVectors(properties);

  if (groups.length === 0) {
    return (
      <Empty className={cn("border-none", className)}>
        <EmptyHeader>
          <EmptyTitle className="text-sm">No properties for {device} yet.</EmptyTitle>
          <EmptyDescription>
            A device publishes what it has when it starts up. If this stays empty, the driver is
            connected but has not defined anything.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    // Column count follows the panel's own width (container queries), not the
    // viewport - docked siblings (e.g. a messages panel) shrink the container.
    <div className={cn("@container flex flex-col gap-6", className)}>
      {groups.map(([group, vectors]) => (
        <section key={group} className="flex flex-col gap-3">
          {group ? (
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {group}
            </h3>
          ) : null}
          <div className="grid gap-3 @xl:grid-cols-2 @4xl:grid-cols-3">
            {vectors.map((vector) => (
              <PropertyVectorCard key={vector.name} vector={vector} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
