/** All of one device's properties, grouped by INDI group, as a grid of cards. */

import type { DeviceSnapshot, Vector } from "@indi-nexus/client";
import { useDevice } from "../hooks";
import { cn } from "../lib/utils";
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
      <p className={cn("py-8 text-center text-sm text-muted-foreground", className)}>
        No properties for {device} yet.
      </p>
    );
  }

  return (
    <div className={cn("flex flex-col gap-6", className)}>
      {groups.map(([group, vectors]) => (
        <section key={group} className="flex flex-col gap-3">
          {group ? (
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {group}
            </h3>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {vectors.map((vector) => (
              <PropertyVectorCard key={vector.name} vector={vector} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
