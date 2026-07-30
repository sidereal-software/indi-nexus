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

/** Format a number for display, honouring a simple printf `%.Nf` precision. */
function formatNumber(element: NumberElement): string {
  const match = element.format?.match(/\.(\d+)f/);
  if (match) return element.value.toFixed(Number(match[1]));
  return String(element.value);
}

/** Extract `min`/`max`/`step` HTML attributes from a number element. */
function numberInputProps(element: NumberElement): {
  min?: number;
  max?: number;
  step?: number;
} {
  const props: { min?: number; max?: number; step?: number } = {};
  if (element.min != null) props.min = element.min;
  if (element.max != null) props.max = element.max;
  if (element.step != null) props.step = element.step;
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
              {element.kind === "number" ? formatNumber(element) : element.value}
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
            <Field key={element.name} orientation="horizontal">
              <FieldLabel htmlFor={id} className="text-muted-foreground">
                {element.label ?? element.name}
              </FieldLabel>
              <Input
                id={id}
                name={element.name}
                type={element.kind === "number" ? "number" : "text"}
                defaultValue={String(element.value)}
                className="ml-auto w-44 font-mono tabular-nums"
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

  const items = vector.elements.map((element) => (
    <ToggleGroupItem key={element.name} value={element.name} className="px-3">
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
