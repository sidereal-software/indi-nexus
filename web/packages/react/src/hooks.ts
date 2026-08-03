/**
 * React hooks over an {@link IndiClient}.
 *
 * Each hook subscribes to the client and reads a *stable* snapshot from the store
 * through `useSyncExternalStore`. Because the store's merges are immutable (a
 * changed vector/device/list gets a new reference, everything else keeps its
 * reference), these hooks re-render precisely when the data they read changes.
 */

import {
  type ConnectionState,
  type DeviceSnapshot,
  elementByName,
  type IndiElement,
  type IPState,
  ISState,
  type Message,
  type Vector,
} from "@indi-nexus/client";
import { useCallback, useMemo, useSyncExternalStore } from "react";
import { useIndiClient } from "./context";

/** Subscribe to the bridge/upstream connection state. */
export function useConnection(): ConnectionState {
  const client = useIndiClient();
  const subscribe = useCallback(
    (onChange: () => void) => client.onConnection(() => onChange()),
    [client],
  );
  const getSnapshot = useCallback(() => client.connectionState, [client]);
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

/** Subscribe to the sorted list of known device names. */
export function useDevices(): readonly string[] {
  const client = useIndiClient();
  const subscribe = useCallback(
    (onChange: () => void) => client.subscribe(() => onChange()),
    [client],
  );
  const getSnapshot = useCallback(() => client.devices(), [client]);
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

/** Subscribe to one device's properties (keyed by property name). */
export function useDevice(device: string): DeviceSnapshot {
  const client = useIndiClient();
  const subscribe = useCallback(
    (onChange: () => void) => client.subscribe(() => onChange(), { device }),
    [client, device],
  );
  const getSnapshot = useCallback(() => client.device(device), [client, device]);
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

/** Subscribe to a single property vector (or `undefined` until it is defined). */
export function useProperty(device: string, name: string): Vector | undefined {
  const client = useIndiClient();
  const subscribe = useCallback(
    (onChange: () => void) => client.subscribe(() => onChange(), { device, name }),
    [client, device, name],
  );
  const getSnapshot = useCallback(() => client.get(device, name), [client, device, name]);
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

/**
 * Subscribe to a single element of a property vector.
 *
 * Sugar over {@link useProperty} for the common "I just want one value" case:
 *
 * ```tsx
 * const ra = useElement("Telescope Simulator", "EQUATORIAL_EOD_COORD", "RA");
 * return <span>{ra?.kind === "number" ? formatNumber(ra.value, ra.format) : "-"}</span>;
 * ```
 *
 * @returns The element, or `undefined` until the property is defined.
 */
export function useElement(device: string, name: string, element: string): IndiElement | undefined {
  const vector = useProperty(device, name);
  return vector === undefined ? undefined : elementByName(vector, element);
}

/**
 * Subscribe to one numeric value.
 *
 * {@link useElement} hands back the element union, so reading `.value` off it
 * does not narrow (a BLOB element has `data`, not `value`). These four hooks are
 * the "I know what kind this is" shortcut, and return the value itself:
 *
 * ```tsx
 * const azimuth = useNumber("Dome Simulator", "ABS_DOME_POSITION", "DOME_ABSOLUTE_POSITION");
 * return <h1>{azimuth ?? "--"}°</h1>;
 * ```
 *
 * @param device - The device name.
 * @param name - The property name.
 * @param element - The element name.
 * @returns The value, or `undefined` if the property is not defined yet or that
 *   element is of another kind.
 */
export function useNumber(device: string, name: string, element: string): number | undefined {
  const found = useElement(device, name, element);
  return found?.kind === "number" ? found.value : undefined;
}

/**
 * Subscribe to one text value. See {@link useNumber}.
 *
 * @param device - The device name.
 * @param name - The property name.
 * @param element - The element name.
 * @returns The value, or `undefined` when absent or of another kind.
 */
export function useText(device: string, name: string, element: string): string | undefined {
  const found = useElement(device, name, element);
  return found?.kind === "text" ? found.value : undefined;
}

/**
 * Subscribe to one switch, as a boolean. See {@link useNumber}.
 *
 * Boolean rather than the `"On"`/`"Off"` token because that is what a checkbox
 * or a toggle wants; `undefined` still distinguishes "not there" from "off".
 *
 * @param device - The device name.
 * @param name - The property name.
 * @param element - The element name.
 * @returns Whether the switch is On, or `undefined` when absent or of another kind.
 */
export function useSwitch(device: string, name: string, element: string): boolean | undefined {
  const found = useElement(device, name, element);
  return found?.kind === "switch" ? found.value === ISState.On : undefined;
}

/**
 * Subscribe to one status light. See {@link useNumber}.
 *
 * @param device - The device name.
 * @param name - The property name.
 * @param element - The element name.
 * @returns The light's state, or `undefined` when absent or of another kind.
 */
export function useLight(device: string, name: string, element: string): IPState | undefined {
  const found = useElement(device, name, element);
  return found?.kind === "light" ? found.value : undefined;
}

/**
 * Subscribe to the client's rolling log of INDI `message` notifications.
 *
 * The buffer lives on the client (see `IndiClient.messages`), not in this hook,
 * so a component that mounts late - a log panel opened on demand - still shows
 * everything received since the page connected.
 *
 * @param limit - Maximum messages to return (oldest dropped first).
 * @returns The most recent messages, oldest first.
 */
export function useMessages(limit = 200): readonly Message[] {
  const client = useIndiClient();
  const subscribe = useCallback(
    (onChange: () => void) => client.onMessage(() => onChange()),
    [client],
  );
  const getSnapshot = useCallback(() => client.messages(), [client]);
  const messages = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return useMemo(
    () => (messages.length > limit ? messages.slice(messages.length - limit) : messages),
    [messages, limit],
  );
}
