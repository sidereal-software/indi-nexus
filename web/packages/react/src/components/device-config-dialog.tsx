/**
 * The sidebar entry and modal for `CONFIG_PROCESS`, the one property every
 * libindi driver carries.
 *
 * Configuration is not a property group. It is a per-device action surface an
 * operator visits deliberately and rarely, and one of its members deletes a file
 * with no undo, so it does not belong on screen beside live instrument readings.
 * It lives in the sidebar next to the device list - the same place that owns
 * which device is selected - and opens in a dialog.
 *
 * Rendered as a generic switch vector the property is four anonymous buttons.
 * This names what each one really does:
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
 * - `CONFIG_SAVE` writes a subset of the device's properties. A libindi driver
 *   picks it in `saveConfigItems`, a C++ virtual no client can read, so for one
 *   of those the dialog says outright that it cannot tell you - silence would
 *   read as "everything you see". An INDINexus driver declares persistence at
 *   define time and publishes the answer as `NEXUS_CONFIG_PERSISTED`, and then
 *   the dialog names the properties instead of apologising.
 *
 * Feedback is the vector's own Idle/Ok/Busy/Alert state, as everywhere else in
 * this package: the driver answering is what says the action happened.
 */

import { displayLabel, type Vector } from "@indi-nexus/client";
import { Settings2 } from "lucide-react";
import { type ReactNode, useId } from "react";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/ui/dialog";
import { SidebarMenuButton, SidebarMenuItem } from "@/ui/sidebar";
import { useIndiClient } from "../context";
import { useDevice, useProperty } from "../hooks";
import { StateBadge } from "./state-badge";

/** The INDI property this dialog presents. */
const CONFIG_PROCESS = "CONFIG_PROCESS";

/**
 * The property an INDINexus driver publishes to say what Save writes, and the
 * element holding the persisted property names separated by spaces.
 *
 * No libindi driver has it, which is the point: its absence is what the fallback
 * copy below is for, and an empty value is a different answer again - a driver
 * saying that Save writes nothing.
 */
const CONFIG_PERSISTED = "NEXUS_CONFIG_PERSISTED";
const CONFIG_PERSISTED_NAMES = "PROPERTIES";

/** What this component knows about one `CONFIG_PROCESS` member. */
interface ConfigAction {
  /** The INDI element name. */
  name: string;
  /** The button's text. Deliberately not the driver's own label. */
  label: string;
  /** The line under the button, saying what pressing it actually does. */
  description: string;
  /** Whether the button is the dialog's primary action. */
  primary?: boolean;
  /** Whether it replays saved values through the driver, so it can move hardware. */
  applies?: boolean;
  /** Whether pressing it destroys something. */
  destructive?: boolean;
}

/**
 * The four members libindi defines, in the order they are shown.
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

/**
 * The dialog an action needs, or `null` when it may act on the first press.
 *
 * @param action - The member being offered.
 * @param device - The device the action would run against.
 * @param connected - Whether that device's `CONNECTION` says `CONNECT` is On.
 * @returns The confirmation wording, or null.
 */
function confirmationFor(
  action: ConfigAction,
  device: string,
  connected: boolean,
): Confirmation | null {
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

/**
 * A button that either acts immediately or opens an alert dialog first.
 *
 * The line under the button is wired to it with `aria-describedby`. That copy is
 * the reason this component exists - "Purge" alone does not say that it deletes a
 * file with no backup - and as a plain sibling paragraph it reached sighted
 * readers only.
 */
function ActionButton({
  action,
  confirmation,
  onAct,
}: {
  action: ConfigAction;
  confirmation: Confirmation | null;
  onAct: () => void;
}): ReactNode {
  const descriptionId = useId();
  const button = (
    <Button
      type="button"
      size="sm"
      variant={action.destructive ? "destructive" : action.primary ? "default" : "outline"}
      className="self-start"
      aria-describedby={descriptionId}
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
        // Nested inside the configuration dialog: Radix stacks dismissable
        // layers, so Escape closes this one and leaves the dialog behind it
        // open, which is what an operator who changed their mind expects.
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
      <p id={descriptionId} className="text-xs text-muted-foreground">
        {action.description}
      </p>
    </div>
  );
}

/**
 * The property names a driver says Save writes, or `null` when it does not say.
 *
 * @param vector - The device's `NEXUS_CONFIG_PERSISTED`, if it has one.
 * @returns The names, empty when the driver persists nothing, or null when there
 *   is no answer to be had - which is every libindi driver.
 */
function persistedNames(vector: Vector | undefined): string[] | null {
  if (vector?.kind !== "text") return null;
  const element = vector.elements.find((candidate) => candidate.name === CONFIG_PERSISTED_NAMES);
  if (element === undefined) return null;
  // The driver refuses to persist a property whose name holds whitespace, which
  // is what makes splitting on it safe. An empty value is an empty list, not a
  // list of one empty name.
  return element.value.split(/\s+/).filter((name) => name !== "");
}

/**
 * The line under the buttons saying what pressing Save actually writes.
 *
 * Three different statements, and the difference between them matters to an
 * operator deciding whether to trust the screen: the driver named the
 * properties, the driver said there are none, or the driver cannot say. Only the
 * third is an apology, and it is the one every libindi driver gets.
 *
 * Names are rendered as the properties' own labels where the device still
 * publishes them, since `GEOGRAPHIC_COORD` is the wire's word for "Site" and the
 * operator is reading the panel's.
 *
 * @param props - The device whose configuration is on screen.
 * @returns The paragraph.
 */
function SaveScope({ device }: { device: string }): ReactNode {
  const properties = useDevice(device);
  const names = persistedNames(properties[CONFIG_PERSISTED]);

  let text: string;
  if (names === null) {
    text =
      "This driver does not report what Save writes. Most drivers save only part of what you " +
      "see.";
  } else if (names.length === 0) {
    text = "This driver reports that Save writes none of its properties.";
  } else {
    const labels = names.map((name) => {
      const vector = properties[name];
      return vector === undefined ? name : displayLabel(vector);
    });
    text = `Save writes ${labels.join(", ")}. Nothing else on this screen is saved.`;
  }

  return <p className="border-t pt-3 text-xs text-muted-foreground">{text}</p>;
}

/** Props for {@link DeviceConfigDialog}. */
export interface DeviceConfigDialogProps {
  /**
   * The device whose `CONFIG_PROCESS` to offer, or `null` when nothing is
   * selected. `CONFIG_PROCESS` is per-device, so this follows the selection.
   */
  device: string | null;
  /**
   * An element to open the dialog with, replacing the default sidebar entry.
   * It is rendered as the trigger itself (`asChild`), so it has to forward its
   * props and accept a ref - any of this package's primitives will.
   */
  children?: ReactNode;
}

/**
 * Offer one device's configuration actions, with the guards libindi lacks.
 *
 * Renders a sidebar entry that opens the actions in a modal. Renders nothing at
 * all when no device is selected or the selected device has no
 * `CONFIG_PROCESS`, since a device that cannot be configured must not offer a
 * button that opens an empty dialog, and only the members the vector carries
 * when it does.
 *
 * With no `children` the trigger is a `SidebarMenuButton` wrapped in its own
 * `SidebarMenuItem`, so it drops straight into a `SidebarMenu` and disappears
 * with its list item rather than leaving an empty row behind. Pass `children`
 * to open the same dialog from your own shell.
 *
 * @param props - The selected device, and an optional trigger element.
 * @returns The trigger and its dialog, or `null` when there is nothing to configure.
 */
export function DeviceConfigDialog({ device, children }: DeviceConfigDialogProps) {
  const client = useIndiClient();
  // Hooks run before the guard below, so an unselected device subscribes to "",
  // which the frame guard refuses to cache and no device can therefore be named.
  const vector = useProperty(device ?? "", CONFIG_PROCESS);
  const connection = useProperty(device ?? "", "CONNECTION");
  // A device with no CONNECTION vector at all cannot be said to be connected, so
  // an applying action gets no dialog: there is no instrument to move.
  const connected =
    connection?.kind === "switch" &&
    connection.elements.some((element) => element.name === "CONNECT" && element.value === "On");

  if (device === null || vector?.kind !== "switch") return null;

  const present = ACTIONS.filter((action) =>
    vector.elements.some((element) => element.name === action.name),
  );

  const dialog = (
    <Dialog>
      {/* Opening and closing the dialog sends nothing: every frame comes from a
          button inside it. */}
      <DialogTrigger asChild>
        {children ?? (
          <SidebarMenuButton tooltip="Configuration">
            <Settings2 />
            <span>Configuration</span>
          </SidebarMenuButton>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          {/* The padding clears the dialog's own close button. */}
          <div className="flex items-start justify-between gap-3 pr-6">
            <DialogTitle className="text-base">{displayLabel(vector)}</DialogTitle>
            <StateBadge state={vector.state} />
          </div>
          <DialogDescription>{device}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          {present.map((action) => (
            <ActionButton
              key={action.name}
              action={action}
              confirmation={confirmationFor(action, vector.device, connected)}
              onAct={() => client.setSwitch(vector.device, vector.name, { [action.name]: "On" })}
            />
          ))}
          {/* Always present: what Save writes is never the whole screen, and
              silence would read as "everything". Mounted with the dialog's
              content, so the whole-device subscription it needs to name the
              properties is only live while the dialog is open. */}
          <SaveScope device={vector.device} />
        </div>
      </DialogContent>
    </Dialog>
  );

  // The default trigger is a sidebar entry, so it brings its own list item; a
  // caller-supplied one is placed wherever the caller already is.
  return children ? dialog : <SidebarMenuItem>{dialog}</SidebarMenuItem>;
}
