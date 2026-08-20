/**
 * Per-kind controls for an INDI property vector.
 *
 * Each control renders one vector's elements and, for writable vectors, sends the
 * corresponding `new` frame through the client:
 *
 * - number/text: editable inputs plus a Set button (read-only vectors show values);
 * - switch: a group of toggle buttons honouring the vector's rule
 *   (OneOfMany/AtMostOne are single-select, AnyOfMany is multi-select), sending
 *   on each toggle - except the momentary-command shape, which is a push button;
 * - light: read-only coloured status dots;
 * - blob: read-only size/format with a download link when a payload is present.
 *
 * {@link VectorControl} dispatches to the right one. All are exported so callers
 * can compose their own layouts instead of using {@link PropertyVectorCard}.
 */

import {
  type BlobVector,
  displayLabel,
  formatNumber,
  isWritable,
  type LightVector,
  type NumberElement,
  type NumberVector,
  type SwitchVector,
  type TextElement,
  type TextVector,
  type Vector,
} from "@indikit/client";
import type { FormEvent } from "react";
import { Button } from "@/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/ui/field";
import { Input } from "@/ui/input";
import { Toggle } from "@/ui/toggle";
import { useIndiClient } from "../context";
import { StateDot } from "./state-badge";

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
            <FieldLabel className="text-muted-foreground">{displayLabel(element)}</FieldLabel>
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
                  {displayLabel(element)}
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
        {/* One writable vector per card means a device panel shows five buttons
            reading exactly "Set". The visible word stays - the card title is
            right above it - but the accessible name carries the vector, so a
            list of controls tells exposure from binning from gain. */}
        {/* The default variant, not `secondary`. This is the control that writes
            to the instrument, and with the brand's hue removed value is the only
            thing left to carry action hierarchy. Measured, `--secondary` sits
            1.22:1 against the card in light, 1.43 in dark, 1.21 in night - it is
            not a filled control at all, it is a label on the card, which is why
            it read as disabled beside an unselected switch segment. The default
            fill is 18.29 / 14.66 / 9.89:1 against the same cards, with its label
            at 18.29 / 15.31 / 10.24:1. */}
        <Button
          type="submit"
          size="sm"
          className="self-end"
          aria-label={`Set ${displayLabel(vector)}`}
        >
          Set
        </Button>
      </FieldGroup>
    </form>
  );
}

/**
 * The joined, segmented look these buttons used to inherit from `ToggleGroup`.
 *
 * `first:`/`last:` key off position within the group, exactly as the primitive's
 * own `data-[spacing=0]` rules did.
 *
 * A selected member *is* the instrument state, so mistaking it is a real error, not an
 * aesthetic one. It wears `secondary` - the same teal as the Set button - so "this is
 * the live state" looks like the rest of the action vocabulary, and it is never the
 * colour an unselected member can take: the stock outline toggle drew selection with
 * `accent` and hovered to `accent` too, which made a hovered unselected member identical
 * to the selected one.
 *
 * The bare `hover:` classes are what tailwind-merge needs to drop the variant's accent
 * hover (same modifier, same group); the `data-[state=on]:hover:` pair then holds the
 * selected look under the pointer, on specificity, since it carries the extra attribute
 * selector.
 */
/*
 * The ON member wears `--primary`, the same colour as the Set button.
 *
 * It used to wear `--secondary`, a raised neutral surface, and that was left
 * over from a palette where the brand had no hue at all: with only value to
 * work with, the selected member of a switch vector and an unselected one were
 * a shade apart, and "which one is the instrument actually on?" was a question
 * you had to lean in to answer. The theme's rule is now that hue is enumerated
 * rather than absent, and this is the same entry the Set button uses: the
 * colour of a control you act through.
 *
 * That does not make it a status colour. What the *instrument* is doing is the
 * badge at the top of the card, in one of the four state hues, and the selected
 * member stays clear of all of them - 18.18 CIEDE2000 in light and 18.75 in
 * dark, at the worst of normal, deuteranopic and protanopic vision. Under the
 * safelight it is 9.96, which is the ceiling that scheme is recorded as
 * accepting rather than a slack threshold.
 * Labels measure 8.64 / 7.70 / 10.58:1 on the fill.
 */
const SWITCH_MEMBER_CLASSES =
  "w-auto min-w-0 shrink-0 rounded-none border-l-0 px-3 shadow-none first:rounded-l-md " +
  "first:border-l last:rounded-r-md focus:z-10 focus-visible:z-10 " +
  "hover:bg-muted hover:text-foreground data-[state=on]:bg-primary " +
  "data-[state=on]:font-semibold data-[state=on]:text-primary-foreground " +
  "data-[state=on]:hover:bg-primary data-[state=on]:hover:text-primary-foreground";

/**
 * Whether a switch vector is a momentary command rather than a reported state.
 *
 * INDI has one switch type and uses it for two different objects: a selection
 * the driver reports back (`CONNECTION`, `DOME_PARK`) and a command that fires
 * once and leaves nothing on (`DOME_ABORT_MOTION`, `CONFIG_PROCESS`). Nothing on
 * the wire flags which, but the second has a shape the first cannot take: a
 * single member under `AtMostOne`. `AtMostOne` is the rule that permits *none*
 * on, and with one member there is no alternative to select, so "on" is not a
 * position the driver can leave it in. libindi's own drivers answer these by
 * putting the member straight back to Off, and so does this project's SDK
 * (`Device._handle_config`).
 *
 * A `OneOfMany` single member is on for ever by definition, and an `AnyOfMany`
 * one is a checkbox, so neither is caught here.
 *
 * @param vector - The switch vector to classify.
 * @returns Whether to draw it as a push button rather than as a toggle.
 */
function isCommand(vector: SwitchVector): boolean {
  return vector.rule === "AtMostOne" && vector.elements.length === 1;
}

/**
 * A momentary command: one push button, not a toggle stuck in its off position.
 *
 * Drawn as a toggle, `Abort` was transparent with a hairline border, which is
 * exactly the appearance an *unselected* member of a two-state control has. On
 * the dome's Main Control tab that put it beside `Connect` and `Park`, which
 * really are the unpressed halves of a pair, and made the one control that stops
 * the instrument the palest thing on the card. There is no other half here: the
 * member is not off, it has not been pressed.
 *
 * It wears `--primary`, the same fill every other control that writes to the
 * instrument wears, and there is deliberately no second variant here. `Abort`
 * was drawn `--destructive` for one release on the argument that stopping a
 * moving dome discards the instrument's position - true, and still not a reason
 * to spend a colour on it. Red on this panel is not "important", it is the
 * enumerated hue that belongs to a *destructive* button in a dialog; on a card
 * that can carry an Alert badge two inches away, a red control asks an operator
 * to tell "the instrument is in Alert" from "this button stops it" by hue at
 * 3am. The card's own title and the button's label already say which command
 * this is, and every command on the panel now looks like every other.
 *
 * Feedback is the vector's own state badge, as everywhere else in this package.
 * A push button has no on-state to show, and it needs none: the driver answering
 * Busy and then Ok is what says the command landed, and that is already at the
 * top of the card.
 *
 * @param props - The command vector, whose one member this draws.
 * @returns The button, inside the vector's own named group.
 */
function CommandSwitchControl({ vector }: { vector: SwitchVector }) {
  const client = useIndiClient();
  const writable = isWritable(vector.perm);
  const element = vector.elements[0];
  if (element === undefined) return null;

  return (
    // The same `fieldset` the toggle group uses, and for the same reason: the
    // button says "Abort" and the group says which "Abort", so two instruments
    // with a stop command do not offer a reader two identically named controls.
    <fieldset aria-label={displayLabel(vector)} className="flex w-fit min-w-0">
      <Button
        type="button"
        size="sm"
        disabled={!writable}
        onClick={() => client.setSwitch(vector.device, vector.name, { [element.name]: "On" })}
      >
        {displayLabel(element)}
      </Button>
    </fieldset>
  );
}

/**
 * Switch vector: a group of toggle buttons honouring the selection rule.
 *
 * Deliberately **not** a `ToggleGroup`, and the reason is a promise the group
 * could not keep. `type="single"` is a Radix radio group: `role="radiogroup"`
 * with `role="radio"` children, and the ARIA radio pattern is
 * selection-follows-focus, so arrowing from Disconnect to Connect tells a screen
 * reader the selection moved. It does not. Nothing goes on the wire until the
 * member is pressed, which is the right behaviour for a control that connects
 * hardware and the wrong thing to claim while doing it. A group of toggle
 * buttons says what actually happens: each member is pressed or not, focus
 * changes nothing, and pressing sends.
 *
 * A vector {@link isCommand} recognises is not a selection at all and is drawn
 * by {@link CommandSwitchControl} instead, where `aria-pressed` would be the
 * same kind of false claim the radio group made.
 *
 * @param props - The switch vector to render.
 * @returns The group element.
 */
export function SwitchVectorControl({ vector }: { vector: SwitchVector }) {
  const client = useIndiClient();
  const writable = isWritable(vector.perm);

  if (isCommand(vector)) return <CommandSwitchControl vector={vector} />;

  function onPressed(name: string, pressed: boolean) {
    if (!writable) return;
    if (pressed) {
      client.setSwitch(vector.device, vector.name, { [name]: "On" });
      return;
    }
    // Un-pressing means the member that was already on has been pressed again.
    // Under OneOfMany exactly one member is on by definition, so "none" is not a
    // state the instrument can be in - ignore it and make the operator press the
    // member they actually want, rather than silently turning the device off.
    // AtMostOne genuinely permits none, so there it stays a way to clear, and
    // AnyOfMany is just the member going Off.
    if (vector.rule === "OneOfMany") return;
    client.setSwitch(vector.device, vector.name, { [name]: "Off" });
  }

  return (
    // A fieldset rather than a div with role="group": it is a set of related
    // controls, which is the element's whole job, and `min-w-0` undoes the
    // `min-width: min-content` a fieldset carries by default and which would
    // otherwise stop the members wrapping.
    <fieldset
      aria-label={displayLabel(vector)}
      className="flex w-fit min-w-0 flex-wrap items-center justify-start rounded-md"
    >
      {vector.elements.map((element) => (
        <Toggle
          key={element.name}
          variant="outline"
          size="sm"
          pressed={element.value === "On"}
          disabled={!writable}
          onPressedChange={(pressed) => onPressed(element.name, pressed)}
          className={SWITCH_MEMBER_CLASSES}
        >
          {displayLabel(element)}
        </Toggle>
      ))}
    </fieldset>
  );
}

/** Light vector: read-only coloured status dots. */
export function LightVectorControl({ vector }: { vector: LightVector }) {
  return (
    <FieldGroup className="gap-2">
      {vector.elements.map((element) => (
        <Field key={element.name} orientation="horizontal">
          <FieldLabel className="text-muted-foreground">{displayLabel(element)}</FieldLabel>
          <span className="ml-auto flex items-center gap-2 text-sm">
            <StateDot state={element.value} />
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
          <FieldLabel className="text-muted-foreground">{displayLabel(element)}</FieldLabel>
          <span className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
            <span>{element.format ?? "-"}</span>
            <span className="tabular-nums">{formatBytes(element.size)}</span>
            {element.data ? (
              // A `data:` URL is decoded with forgiving-base64, which rejects the
              // URL-safe alphabet, so this link works only because the bridge pins
              // the standard one (see BLOB in protocol/models.py). Do not "fix" a
              // broken download by rewriting the payload here.
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
