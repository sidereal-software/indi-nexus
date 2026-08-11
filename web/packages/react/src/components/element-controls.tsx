/**
 * Per-kind controls for an INDI property vector.
 *
 * Each control renders one vector's elements and, for writable vectors, sends the
 * corresponding `new` frame through the client:
 *
 * - number/text: editable inputs plus a Set button (read-only vectors show values);
 * - switch: a `ToggleGroup` honouring the vector's rule (OneOfMany/AtMostOne are
 *   single-select, AnyOfMany is multi-select), sending on each toggle;
 * - light: read-only coloured status dots;
 * - blob: read-only size/format with a download link when a payload is present.
 *
 * {@link VectorControl} dispatches to the right one. All are exported so callers
 * can compose their own layouts instead of using {@link PropertyVectorCard}.
 */

import {
  type BlobVector,
  formatNumber,
  type IPState,
  isWritable,
  type LightVector,
  type NumberElement,
  type NumberVector,
  type SwitchVector,
  type TextElement,
  type TextVector,
  type Vector,
} from "@indi-nexus/client";
import type { FormEvent } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/ui/field";
import { Input } from "@/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/ui/toggle-group";
import { useIndiClient } from "../context";

/** Tailwind background classes per light/vector state. */
const STATE_DOT: Record<IPState, string> = {
  Idle: "bg-state-idle",
  Ok: "bg-state-ok",
  Busy: "bg-state-busy",
  Alert: "bg-state-alert",
};

/** The display text for an element's current value (numbers per their format). */
function currentValue(element: NumberElement | TextElement): string {
  if (element.kind === "number") return formatNumber(element.value, element.format).trim();
  return element.value;
}

/** Extract `min`/`max`/`step` HTML attributes from a number element. */
function numberInputProps(element: NumberElement): {
  min?: number;
  max?: number;
  step: number | "any";
} {
  // Without an explicit step, HTML number inputs default to step=1, which makes
  // fractional values (e.g. RA 5.5h) fail native validation and silently block
  // the form submit. INDI's "no step" (absent or 0) must mean "any".
  const props: { min?: number; max?: number; step: number | "any" } = {
    step: element.step ? element.step : "any",
  };
  if (element.min != null) props.min = element.min;
  if (element.max != null) props.max = element.max;
  return props;
}

/** Human-readable byte size for a BLOB element. */
function formatBytes(size: number | null | undefined): string {
  if (size == null) return "-";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

/** Number/text vector: editable inputs + Set when writable, values when not. */
export function ValueVectorControl({ vector }: { vector: NumberVector | TextVector }) {
  const client = useIndiClient();
  const writable = isWritable(vector.perm);
  const elements = vector.elements as (NumberElement | TextElement)[];

  if (!writable) {
    return (
      <FieldGroup className="gap-2">
        {elements.map((element) => (
          <Field key={element.name} orientation="horizontal">
            <FieldLabel className="text-muted-foreground">
              {element.label ?? element.name}
            </FieldLabel>
            <span className="ml-auto truncate font-mono text-sm tabular-nums">
              {currentValue(element)}
            </span>
          </Field>
        ))}
      </FieldGroup>
    );
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    if (vector.kind === "number") {
      const values: Record<string, number> = {};
      for (const element of vector.elements) {
        const raw = data.get(element.name);
        if (typeof raw === "string" && raw.trim() !== "") values[element.name] = Number(raw);
      }
      client.setNumber(vector.device, vector.name, values);
    } else {
      const values: Record<string, string> = {};
      for (const element of vector.elements) {
        const raw = data.get(element.name);
        if (typeof raw === "string") values[element.name] = raw;
      }
      client.setText(vector.device, vector.name, values);
    }
  }

  return (
    <form onSubmit={onSubmit}>
      <FieldGroup className="gap-3">
        {elements.map((element) => {
          const id = `${vector.device}.${vector.name}.${element.name}`;
          return (
            // Two deterministic lines per element: a header pairing the label
            // with the live readout (telemetry: where the device is now), and a
            // full-width input below (the *requested* new value). Nothing
            // competes for one row, so long labels and sexagesimal values -
            // "RA (hh:mm:ss)" / "12:34:56" - always fit.
            <Field key={element.name} className="gap-1.5">
              <div className="flex items-baseline justify-between gap-3">
                <FieldLabel htmlFor={id} className="shrink-0 text-muted-foreground">
                  {element.label ?? element.name}
                </FieldLabel>
                <span
                  title="Current value"
                  className="min-w-0 truncate font-mono text-sm tabular-nums"
                >
                  {currentValue(element)}
                </span>
              </div>
              <Input
                id={id}
                name={element.name}
                type={element.kind === "number" ? "number" : "text"}
                defaultValue={String(element.value)}
                className="w-full font-mono tabular-nums"
                {...(element.kind === "number" ? numberInputProps(element) : {})}
              />
            </Field>
          );
        })}
        <Button type="submit" variant="secondary" size="sm" className="self-end">
          Set
        </Button>
      </FieldGroup>
    </form>
  );
}

/** Switch vector: a ToggleGroup honouring the selection rule. */
export function SwitchVectorControl({ vector }: { vector: SwitchVector }) {
  const client = useIndiClient();
  const writable = isWritable(vector.perm);
  const single = vector.rule === "OneOfMany" || vector.rule === "AtMostOne";
  const onNames = vector.elements.filter((element) => element.value === "On").map((e) => e.name);

  // A selected member *is* the instrument state, so it has to read at a glance. The stock
  // outline toggle draws selection with `accent` and hovers to `accent` as well, which
  // leaves the two indistinguishable while the pointer is anywhere in the group, on top of
  // being a near-invisible fill (#eee on white, #333 on #121212). Selection is inverted
  // instead. The bare `hover:` classes are what tailwind-merge needs to drop the variant's
  // accent hover (same modifier, same group); the `data-[state=on]:hover:` pair then holds
  // the selected look under the pointer, on specificity, since it carries the extra
  // attribute selector.
  const items = vector.elements.map((element) => (
    <ToggleGroupItem
      key={element.name}
      value={element.name}
      className="px-3 hover:bg-muted hover:text-foreground data-[state=on]:bg-foreground data-[state=on]:text-background data-[state=on]:hover:bg-foreground data-[state=on]:hover:text-background"
    >
      {element.label ?? element.name}
    </ToggleGroupItem>
  ));

  if (single) {
    const current = onNames[0] ?? "";
    return (
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        value={current}
        disabled={!writable}
        className="flex-wrap justify-start"
        onValueChange={(next) => {
          if (!writable) return;
          if (next) client.setSwitch(vector.device, vector.name, { [next]: "On" });
          else if (current) client.setSwitch(vector.device, vector.name, { [current]: "Off" });
        }}
      >
        {items}
      </ToggleGroup>
    );
  }

  return (
    <ToggleGroup
      type="multiple"
      variant="outline"
      size="sm"
      value={onNames}
      disabled={!writable}
      className="flex-wrap justify-start"
      onValueChange={(next) => {
        if (!writable) return;
        const nextOn = new Set(next);
        const changes: Record<string, "On" | "Off"> = {};
        for (const element of vector.elements) {
          const wasOn = element.value === "On";
          const nowOn = nextOn.has(element.name);
          if (wasOn !== nowOn) changes[element.name] = nowOn ? "On" : "Off";
        }
        if (Object.keys(changes).length > 0) {
          client.setSwitch(vector.device, vector.name, changes);
        }
      }}
    >
      {items}
    </ToggleGroup>
  );
}

/** Light vector: read-only coloured status dots. */
export function LightVectorControl({ vector }: { vector: LightVector }) {
  return (
    <FieldGroup className="gap-2">
      {vector.elements.map((element) => (
        <Field key={element.name} orientation="horizontal">
          <FieldLabel className="text-muted-foreground">{element.label ?? element.name}</FieldLabel>
          <span className="ml-auto flex items-center gap-2 text-sm">
            <span className={cn("size-2.5 rounded-full", STATE_DOT[element.value])} aria-hidden />
            {element.value}
          </span>
        </Field>
      ))}
    </FieldGroup>
  );
}

/** BLOB vector: read-only size/format with a download link when present. */
export function BlobVectorControl({ vector }: { vector: BlobVector }) {
  return (
    <FieldGroup className="gap-2">
      {vector.elements.map((element) => (
        <Field key={element.name} orientation="horizontal">
          <FieldLabel className="text-muted-foreground">{element.label ?? element.name}</FieldLabel>
          <span className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
            <span>{element.format ?? "-"}</span>
            <span className="tabular-nums">{formatBytes(element.size)}</span>
            {element.data ? (
              <a
                className="text-primary underline underline-offset-2"
                download={`${element.name}${element.format ?? ""}`}
                href={`data:application/octet-stream;base64,${element.data}`}
              >
                download
              </a>
            ) : null}
          </span>
        </Field>
      ))}
    </FieldGroup>
  );
}

/** Render the control appropriate to a vector's kind. */
export function VectorControl({ vector }: { vector: Vector }) {
  switch (vector.kind) {
    case "number":
    case "text":
      return <ValueVectorControl vector={vector} />;
    case "switch":
      return <SwitchVectorControl vector={vector} />;
    case "light":
      return <LightVectorControl vector={vector} />;
    case "blob":
      return <BlobVectorControl vector={vector} />;
  }
}
