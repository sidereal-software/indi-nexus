/**
 * The card for `CONFIG_PROCESS`, the one property every libindi driver carries.
 *
 * Rendered as a generic switch vector it is four anonymous buttons, one of which
 * deletes a file with no undo. This card names what each one really does:
 *
 * - `CONFIG_DEFAULT` is **not** factory defaults. libindi reads a `.default`
 *   file, which is a copy of the first configuration ever saved for the device,
 *   so the honest label is "Restore first saved".
 * - `CONFIG_PURGE` is an unguarded `remove()` in libindi: no confirmation, no
 *   backup, no undo. It is behind an alert dialog here and sends nothing until
 *   the operator confirms.
 * - `CONFIG_LOAD` and `CONFIG_DEFAULT` replay every saved value through the
 *   driver's own handlers, so applying one to a connected instrument can move
 *   hardware. Both confirm while the device is connected, and neither does while
 *   it is not.
 * - `CONFIG_SAVE` writes whatever the driver's `saveConfigItems` chose, which is
 *   a subset a client cannot discover over the wire. The card says so rather than
 *   letting an operator assume the screen is what gets persisted.
 *
 * Feedback is the vector's own Idle/Ok/Busy/Alert state, as everywhere else in
 * this package: the driver answering is what says the action happened.
 */

import { displayLabel } from "@indi-nexus/client";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/ui/alert-dialog";
import { Button } from "@/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/ui/card";
import { useIndiClient } from "../context";
import { useProperty } from "../hooks";
import { StateBadge } from "./state-badge";

/** The INDI property this card presents. */
const CONFIG_PROCESS = "CONFIG_PROCESS";

/** What the card knows about one `CONFIG_PROCESS` member. */
interface ConfigAction {
  /** The INDI element name. */
  name: string;
  /** The button's text. Deliberately not the driver's own label. */
  label: string;
  /** The line under the button, saying what pressing it actually does. */
  description: string;
  /** Whether the button is the card's primary action. */
  primary?: boolean;
  /** Whether it replays saved values through the driver, so it can move hardware. */
  applies?: boolean;
  /** Whether pressing it destroys something. */
  destructive?: boolean;
}

/**
 * The four members libindi defines, in the order the card shows them.
 *
 * A driver exposing only some of them is normal, so this is a lookup rather than
 * an expectation: only the members the vector actually carries are rendered.
 */
const ACTIONS: readonly ConfigAction[] = [
  {
    name: "CONFIG_SAVE",
    label: "Save",
    description:
      "Writes this device's configuration on the observatory computer, so the driver starts " +
      "with it next time.",
    primary: true,
  },
  {
    name: "CONFIG_LOAD",
    label: "Load saved",
    description: "Applies the saved configuration to the driver now.",
    applies: true,
  },
  {
    name: "CONFIG_DEFAULT",
    label: "Restore first saved",
    description:
      "Loads the snapshot taken the first time this configuration was saved. These are not " +
      "factory settings.",
    applies: true,
  },
  {
    name: "CONFIG_PURGE",
    label: "Purge",
    description: "Deletes the saved configuration. There is no backup and nothing to undo it.",
    destructive: true,
  },
];

/** The wording of one confirmation, or `null` to act on the first press. */
interface Confirmation {
  title: string;
  body: string;
  /** The confirming button's text. Never "OK": it has to name the consequence. */
  confirm: string;
  destructive?: boolean;
}

/** A button that either acts immediately or opens an alert dialog first. */
function ActionButton({
  action,
  confirmation,
  onAct,
}: {
  action: ConfigAction;
  confirmation: Confirmation | null;
  onAct: () => void;
}): ReactNode {
  const button = (
    <Button
      type="button"
      size="sm"
      variant={action.destructive ? "destructive" : action.primary ? "default" : "outline"}
      className="self-start"
      {...(confirmation === null ? { onClick: onAct } : {})}
    >
      {action.label}
    </Button>
  );

  return (
    <div className="flex flex-col gap-1">
      {confirmation === null ? (
        button
      ) : (
        <AlertDialog>
          {/* The trigger only opens the dialog; nothing goes on the wire until
              the action below is pressed. */}
          <AlertDialogTrigger asChild>{button}</AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{confirmation.title}</AlertDialogTitle>
              <AlertDialogDescription>{confirmation.body}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                variant={confirmation.destructive ? "destructive" : "default"}
                onClick={onAct}
              >
                {confirmation.confirm}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
      <p className="text-xs text-muted-foreground">{action.description}</p>
    </div>
  );
}

/** Props for {@link DeviceConfigCard}. */
export interface DeviceConfigCardProps {
  /** The device whose `CONFIG_PROCESS` to render. */
  device: string;
  className?: string;
}

/**
 * Render one device's configuration actions, with the guards libindi lacks.
 *
 * Renders nothing at all when the device has no `CONFIG_PROCESS`, and only the
 * members the vector carries when it does.
 *
 * @param props - The device name and an optional class name.
 * @returns The card element, or `null` when the device has no `CONFIG_PROCESS`.
 */
export function DeviceConfigCard({ device, className }: DeviceConfigCardProps) {
  const client = useIndiClient();
  const vector = useProperty(device, CONFIG_PROCESS);
  const connection = useProperty(device, "CONNECTION");
  // A device with no CONNECTION vector at all cannot be said to be connected, so
  // an applying action gets no dialog: there is no instrument to move.
  const connected =
    connection?.kind === "switch" &&
    connection.elements.some((element) => element.name === "CONNECT" && element.value === "On");

  if (vector?.kind !== "switch") return null;

  const present = ACTIONS.filter((action) =>
    vector.elements.some((element) => element.name === action.name),
  );

  /** The dialog an action needs, or `null` when it may act on the first press. */
  function confirmationFor(action: ConfigAction): Confirmation | null {
    if (action.destructive) {
      return {
        title: `Delete the saved configuration for ${device}?`,
        body:
          `This removes ${device}'s configuration file from the observatory computer. There is ` +
          "no backup of it and nothing can undo this, so the driver will start from its own " +
          "defaults until a new configuration is saved.",
        confirm: "Delete saved config",
        destructive: true,
      };
    }
    if (!action.applies || !connected) return null;
    // CONFIG_LOAD and CONFIG_DEFAULT both replay every saved value through the
    // driver's handlers, so on a connected device they are hardware commands.
    return {
      title: `Apply the saved configuration to ${device}?`,
      body:
        `${device} is connected. The saved values are applied through the driver as though they ` +
        "had just been sent, so anything the configuration covers can move the instrument now.",
      confirm: "Apply to the instrument",
    };
  }

  return (
    <Card className={cn("gap-3 py-4", className)}>
      <CardHeader className="gap-0.5 px-4">
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="truncate text-sm">{displayLabel(vector)}</CardTitle>
          <StateBadge state={vector.state} />
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 px-4">
        {present.map((action) => (
          <ActionButton
            key={action.name}
            action={action}
            confirmation={confirmationFor(action)}
            onAct={() => client.setSwitch(vector.device, vector.name, { [action.name]: "On" })}
          />
        ))}
        {/* Always present, because a client cannot discover a driver's
            saveConfigItems over the wire: silence would read as "everything". */}
        <p className="border-t pt-3 text-xs text-muted-foreground">
          This driver does not report what Save writes. Most drivers save only part of what you see.
        </p>
      </CardContent>
    </Card>
  );
}
