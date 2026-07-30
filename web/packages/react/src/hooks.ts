/**
 * React hooks over an {@link IndiClient}.
 *
 * Each hook subscribes to the client and reads a *stable* snapshot from the store
 * through `useSyncExternalStore`. Because the store's merges are immutable (a
 * changed vector/device/list gets a new reference, everything else keeps its
 * reference), these hooks re-render precisely when the data they read changes.
 */

import type { ConnectionState, DeviceSnapshot, Message, Vector } from "@indi-nexus/client";
import { useCallback, useRef, useSyncExternalStore } from "react";
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
 * Accumulate the most recent INDI `message` notifications into a rolling buffer.
 *
 * Messages are not part of the property cache, so this keeps its own bounded log.
 *
 * @param limit - Maximum messages to retain (oldest dropped first).
 * @returns The buffered messages, oldest first.
 */
export function useMessages(limit = 200): readonly Message[] {
  const client = useIndiClient();
  const bufferRef = useRef<Message[]>([]);
  const subscribe = useCallback(
    (onChange: () => void) =>
      client.onMessage((message) => {
        const next = [...bufferRef.current, message];
        if (next.length > limit) next.splice(0, next.length - limit);
        bufferRef.current = next;
        onChange();
      }),
    [client, limit],
  );
  const getSnapshot = useCallback(() => bufferRef.current, []);
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
