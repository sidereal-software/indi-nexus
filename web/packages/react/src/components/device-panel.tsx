/** All of one device's properties, grouped by INDI group, as a grid of cards. */

import type { Vector } from "@indi-nexus/client";
import { cn } from "@/lib/utils";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/ui/accordion";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/ui/empty";
import { useDevice } from "../hooks";
import { DeviceConfigCard } from "./device-config-card";
import { DRIVER_MACHINERY } from "./machinery";
import { PropertyVectorCard } from "./property-vector-card";

/** The property {@link DeviceConfigCard} renders, pinned out of the groups. */
const CONFIG_PROCESS = "CONFIG_PROCESS";

/** Where a group sorts: Main Control leads, everything else is alphabetical. */
function groupRank(group: string): number {
  return group === "Main Control" ? 0 : 1;
}

/** Group vectors by their `group`, Main Control first then alphabetical. */
function groupVectors(vectors: Vector[]): [string, Vector[]][] {
  const groups = new Map<string, Vector[]>();
  for (const vector of vectors) {
    const key = vector.group ?? "";
    const bucket = groups.get(key);
    if (bucket) bucket.push(vector);
    else groups.set(key, [vector]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => groupRank(a) - groupRank(b) || a.localeCompare(b))
    .map(([group, vectors]) => [group, vectors.sort((a, b) => a.name.localeCompare(b.name))]);
}

/** Sort a flat list of vectors by name. */
function byName(vectors: Vector[]): Vector[] {
  return [...vectors].sort((a, b) => a.name.localeCompare(b.name));
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
 * Three things sit outside the alphabetical groups. `CONFIG_PROCESS` is pinned
 * first as a Configuration section, drawn by {@link DeviceConfigCard} rather than
 * as four anonymous buttons, and excluded from its own group so it is not drawn
 * twice. `Main Control` follows, because it is where a driver puts the controls
 * an operator actually came for. The rest of {@link DRIVER_MACHINERY} - the
 * driver's debug plumbing and its snooping - folds into a collapsed "Driver
 * internals" section at the end, out of whichever group it was declared in.
 *
 * The fold is computed from what the device has right now, so a driver that
 * defines `DEBUG_LEVEL` when debugging is switched on, and deletes it again
 * afterwards (which libindi does), moves it in and out of the fold on its own.
 *
 * @param props - The device name and an optional class name.
 * @returns The panel element.
 */
export function DevicePanel({ device, className }: DevicePanelProps) {
  const properties = useDevice(device);
  const all = Object.values(properties);
  const configured = properties[CONFIG_PROCESS] !== undefined;
  const machinery = byName(
    all.filter((vector) => vector.name !== CONFIG_PROCESS && DRIVER_MACHINERY.has(vector.name)),
  );
  const groups = groupVectors(
    all.filter((vector) => vector.name !== CONFIG_PROCESS && !DRIVER_MACHINERY.has(vector.name)),
  );

  if (all.length === 0) {
    return (
      <Empty className={cn("border-none", className)}>
        <EmptyHeader>
          <EmptyTitle className="text-sm">No properties for {device} right now.</EmptyTitle>
          <EmptyDescription>
            A device publishes what it has when it starts up, and a driver may withdraw properties
            that only exist while its instrument is connected. The device is still here; it is just
            not offering anything at the moment.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    // Column count follows the panel's own width (container queries), not the
    // viewport - docked siblings (e.g. a messages panel) shrink the container.
    <div className={cn("@container flex flex-col gap-6", className)}>
      {configured ? (
        <section className="flex flex-col gap-3">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Configuration
          </h3>
          <div className="grid gap-3 @xl:grid-cols-2 @4xl:grid-cols-3">
            <DeviceConfigCard device={device} />
          </div>
        </section>
      ) : null}
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
      {machinery.length > 0 ? (
        <Accordion type="single" collapsible>
          <AccordionItem value="driver-internals" className="border-t border-b-0">
            <AccordionTrigger className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Driver internals
            </AccordionTrigger>
            <AccordionContent className="grid gap-3 @xl:grid-cols-2 @4xl:grid-cols-3">
              {machinery.map((vector) => (
                <PropertyVectorCard key={vector.name} vector={vector} />
              ))}
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      ) : null}
    </div>
  );
}
