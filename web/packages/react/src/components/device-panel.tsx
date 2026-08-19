/** All of one device's properties, grouped by INDI group, as a grid of cards. */

import type { Vector } from "@indi-nexus/client";
import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/ui/accordion";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/ui/empty";
import { useDevice } from "../hooks";
import { DRIVER_MACHINERY } from "./machinery";
import { PropertyVectorCard } from "./property-vector-card";

/**
 * The properties {@link DeviceConfigDialog} owns, kept out of the groups.
 *
 * `NEXUS_CONFIG_PERSISTED` is there for the dialog to read, not for an operator:
 * drawn as a card it is a read-only text field holding a list of property names,
 * which says nothing the dialog does not say in words.
 */
const CONFIG_PROPERTIES: ReadonlySet<string> = new Set([
  "CONFIG_PROCESS",
  "NEXUS_CONFIG_PERSISTED",
]);

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
 * Three things sit outside the alphabetical groups. The configuration
 * properties are not here at all: `CONFIG_PROCESS` is a per-device action
 * surface rather than a property group, so {@link DeviceConfigDialog} offers it
 * from the sidebar and the panel excludes it so it is not also drawn as four
 * anonymous buttons, and `NEXUS_CONFIG_PERSISTED` is the answer that dialog
 * renders in words rather than as a text field full of property names. `Main
 * Control` leads, because it is where a driver puts the controls an operator
 * actually came for. The rest of {@link DRIVER_MACHINERY} - the driver's debug
 * plumbing and its snooping - folds into a collapsed "Driver internals" section
 * at the end, out of whichever group it was declared in.
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
  // Above the early return, or the hook order changes between the empty and the
  // populated render. Both lists derive from the same `Object.values` pass and
  // both re-sort, so they are memoised together: splitting them would leave
  // `machinery` rebuilding on every `set` frame anyway.
  const { machinery, groups } = useMemo(() => {
    const all = Object.values(properties);
    return {
      machinery: byName(
        all.filter(
          (vector) => !CONFIG_PROPERTIES.has(vector.name) && DRIVER_MACHINERY.has(vector.name),
        ),
      ),
      groups: groupVectors(
        all.filter(
          (vector) => !CONFIG_PROPERTIES.has(vector.name) && !DRIVER_MACHINERY.has(vector.name),
        ),
      ),
    };
  }, [properties]);

  if (Object.keys(properties).length === 0) {
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
      {groups.map(([group, vectors]) => (
        <section key={group} className="flex flex-col gap-3">
          {/* The panel sits under the shell's h1 and each card title is an h3, so
              the group name is the h2 between them. A vector may carry no group
              at all, and dropping the heading there would step h1 to h3 and break
              the outline, so the unnamed bucket keeps its level and loses only
              its pixels. */}
          {group ? (
            <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {group}
            </h2>
          ) : (
            <h2 className="sr-only">Ungrouped properties</h2>
          )}
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
