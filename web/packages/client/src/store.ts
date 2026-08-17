/**
 * `PropertyStore`: the client's typed cache of INDI properties.
 *
 * A faithful port of `indi_nexus.client.store.PropertyStore`. It folds inbound
 * messages into a `device -> name -> vector` cache following standard INDI
 * semantics (`def` defines, `set` merges values onto the definition keeping
 * def-only metadata, `del` removes a property or a whole device) and holds the
 * subscription registry. Like the Python store it is behaviour-free with respect
 * to any socket - `apply` returns a {@link PropertyEvent} and `matching` returns
 * the interested callbacks; the client performs the actual dispatch.
 *
 * Divergence from Python: merges are **immutable**. A `set` replaces the cached
 * vector (and its element array) with new objects rather than mutating in place,
 * so React's `useSyncExternalStore` can detect changes by reference. Per-device
 * snapshots are likewise cached and only rebuilt when that device changes, giving
 * the hooks stable references between unrelated updates.
 */

import type { DelProperty, IndiElement, IndiMessage, Timestamp, Vector } from "./types";

/** The kind of change {@link PropertyStore.apply} recorded. */
export type EventType = "def" | "set" | "del";

/** A change the store applied to its cache. */
export interface PropertyEvent {
  /** `"def"`, `"set"`, or `"del"`. */
  type: EventType;
  /** The device the change applies to. */
  device: string;
  /** The property name, or `null` for a whole-device `del`. */
  name: string | null;
  /** The affected (post-merge) vector, or `null` for a `del`. */
  vector: Vector | null;
  /**
   * The explanation a `delProperty` carried, if any.
   *
   * Only a `del` sets this: a `def` or `set` keeps its message on the vector,
   * whereas a deletion has no vector to keep anything on, and the text is often
   * the only account of *why* the property went away.
   */
  message?: string | null;
  /**
   * When a `delProperty` said the retraction happened, if it said. Carried for
   * the same reason as `message`; `null` for a `def` or `set`, whose vector is
   * already stamped.
   */
  timestamp?: Timestamp | null;
}

/** A subscription callback invoked with each matching event. */
export type Subscriber = (event: PropertyEvent) => void;

/** A filter narrowing a subscription to a device and/or property. */
export interface SubscriptionFilter {
  device?: string;
  name?: string;
}

/** A read-only snapshot of one device's properties, keyed by property name. */
export type DeviceSnapshot = Readonly<Record<string, Vector>>;

const EMPTY_DEVICE: DeviceSnapshot = Object.freeze({});

/**
 * Merge a `set` element's value onto a cached element, returning a new element.
 *
 * Only the value (and, for BLOBs, the payload/size/format) is copied; metadata
 * such as a number's `min`/`max`/`format` stays as defined, per INDI semantics.
 */
function mergeElement(current: IndiElement, incoming: IndiElement): IndiElement {
  if (current.kind === "blob") {
    if (incoming.kind !== "blob") return current;
    return {
      ...current,
      data: incoming.data ?? null,
      size: incoming.size ?? null,
      format: incoming.format ?? current.format,
    };
  }
  if (incoming.kind === "blob" || incoming.kind !== current.kind) return current;
  // Same value-bearing kind: copy just the value. The cast is safe because the
  // discriminants match; TypeScript cannot narrow both sides of a union at once.
  return { ...current, value: incoming.value } as IndiElement;
}

/**
 * Merge a `set` vector's values and status onto a cached definition.
 *
 * Returns a new vector (immutable) so reference equality changes exactly when the
 * data changes.
 *
 * `statePresent` is whether the wire message carried a `state`. It is `#IMPLIED`
 * on every `set*Vector` and means "no change if absent", so a stateless `set`
 * leaves the cached state alone rather than resetting it to the parsed default -
 * a property latched into Alert stays there until the device says otherwise.
 */
function mergeVector(destination: Vector, source: Vector, statePresent: boolean): Vector {
  const incomingByName = new Map(source.elements.map((el) => [el.name, el]));
  const elements = destination.elements.map((current) => {
    const incoming = incomingByName.get(current.name);
    return incoming ? mergeElement(current, incoming) : current;
  });
  const merged = {
    ...destination,
    elements,
  } as Vector;
  if (statePresent) merged.state = source.state;
  if (source.timeout != null) merged.timeout = source.timeout;
  if (source.timestamp != null) merged.timestamp = source.timestamp;
  if (source.message != null) merged.message = source.message;
  return merged as Vector;
}

/** A cache of INDI property vectors plus a subscription registry. */
export class PropertyStore {
  private readonly byDevice = new Map<string, Map<string, Vector>>();
  private readonly deviceSnapshots = new Map<string, DeviceSnapshot>();
  private deviceListSnapshot: readonly string[] = [];
  private readonly subs = new Map<
    number,
    { callback: Subscriber; device?: string; name?: string }
  >();
  private nextSubId = 0;

  // -- reads ------------------------------------------------------------- //
  /** Return a cached vector, or `undefined` if it is not present. */
  get(device: string, name: string): Vector | undefined {
    return this.byDevice.get(device)?.get(name);
  }

  /**
   * Return a stable read-only snapshot of one device's properties.
   *
   * The returned object identity only changes when that device changes, so it is
   * safe to use directly as a `useSyncExternalStore` snapshot.
   */
  device(name: string): DeviceSnapshot {
    return this.deviceSnapshots.get(name) ?? EMPTY_DEVICE;
  }

  /** Return a stable, sorted list of all known device names. */
  devices(): readonly string[] {
    return this.deviceListSnapshot;
  }

  // -- writes ------------------------------------------------------------ //
  /**
   * Fold one inbound message into the cache.
   *
   * Returns the change applied, or `null` if the message did not change the cache
   * (an unknown `set`, or a non-property message).
   */
  apply(message: IndiMessage): PropertyEvent | null {
    switch (message.tag) {
      case "def": {
        const vector = message.vector;
        this.put(vector);
        return { type: "def", device: vector.device, name: vector.name, vector };
      }
      case "set": {
        const current = this.get(message.vector.device, message.vector.name);
        if (current === undefined) return null;
        // A frame that omits the flag entirely carried its state, which is both
        // the Python model's default and what a pre-flag bridge sends.
        const merged = mergeVector(current, message.vector, message.state_present ?? true);
        this.put(merged);
        return { type: "set", device: merged.device, name: merged.name, vector: merged };
      }
      case "delProperty":
        return this.remove(message);
      default:
        return null;
    }
  }

  /** Insert or replace a vector and refresh the affected snapshots. */
  private put(vector: Vector): void {
    let props = this.byDevice.get(vector.device);
    const isNewDevice = props === undefined;
    if (props === undefined) {
      props = new Map();
      this.byDevice.set(vector.device, props);
    }
    props.set(vector.name, vector);
    this.refreshDeviceSnapshot(vector.device);
    if (isNewDevice) this.refreshDeviceList();
  }

  /**
   * Remove a property or a whole device from the cache.
   *
   * A named deletion removes only that property. The device stays, even when it
   * was the last one: "this device is here and currently publishes nothing" is
   * an ordinary state - it is what a driver that defines its properties on
   * connect looks like while disconnected - and it is not the same thing as the
   * device being gone, which is what an unnamed `delProperty` means. The Python
   * store and `web/static/debug.html` draw the line in the same place, as does
   * libindi's own `AbstractBaseClient`.
   */
  private remove(message: DelProperty): PropertyEvent | null {
    const props = this.byDevice.get(message.device);
    if (props === undefined) return null;
    const { message: why, timestamp } = message;
    if (message.name == null) {
      this.byDevice.delete(message.device);
      this.deviceSnapshots.delete(message.device);
      this.refreshDeviceList();
      return {
        type: "del",
        device: message.device,
        name: null,
        vector: null,
        message: why,
        timestamp,
      };
    }
    if (!props.has(message.name)) return null;
    props.delete(message.name);
    this.refreshDeviceSnapshot(message.device);
    return {
      type: "del",
      device: message.device,
      name: message.name,
      vector: null,
      message: why,
      timestamp,
    };
  }

  /** Rebuild the cached immutable snapshot for one device. */
  private refreshDeviceSnapshot(device: string): void {
    const props = this.byDevice.get(device);
    if (props === undefined) return;
    const snapshot: Record<string, Vector> = {};
    for (const [name, vector] of props) snapshot[name] = vector;
    this.deviceSnapshots.set(device, Object.freeze(snapshot));
  }

  /** Rebuild the cached, sorted device-name list. */
  private refreshDeviceList(): void {
    this.deviceListSnapshot = Object.freeze([...this.byDevice.keys()].sort());
  }

  // -- subscriptions ----------------------------------------------------- //
  /** Register a callback for matching property events; returns an unsubscribe fn. */
  subscribe(callback: Subscriber, filter: SubscriptionFilter = {}): () => void {
    const token = this.nextSubId++;
    this.subs.set(token, { callback, device: filter.device, name: filter.name });
    return () => {
      this.subs.delete(token);
    };
  }

  /**
   * Return the callbacks whose device/name filters match an event.
   *
   * A whole-device `del` reaches **every** subscriber for that device,
   * including the name-filtered ones. Its event carries no name because the
   * deletion names no property - it takes all of them - so matching the filter
   * against it literally would silence exactly the subscribers with the most to
   * lose: `subscribe(cb, {device: "CCD", name: "EXPOSURE"})` heard nothing when
   * the CCD's driver died and the whole device went away. Same rule in
   * `client/store.py`.
   */
  matching(event: PropertyEvent): Subscriber[] {
    const out: Subscriber[] = [];
    for (const { callback, device, name } of this.subs.values()) {
      if (device !== undefined && device !== event.device) continue;
      if (name !== undefined && event.name !== null && name !== event.name) continue;
      out.push(callback);
    }
    return out;
  }
}
