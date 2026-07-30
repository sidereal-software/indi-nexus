/**
 * `IndiClient`: a reconnecting browser client for the INDINexus web bridge.
 *
 * This mirrors the public surface of `indi_nexus.client.client.IndiClient`, but its
 * peer is the FastAPI bridge's `WS /ws` (which relays a shared upstream
 * `indiserver` connection), and it speaks the JSON contract rather than XML. It
 * keeps a typed {@link PropertyStore} up to date from inbound frames, lets code
 * watch it and wait on conditions, and sends updates as typed models.
 *
 * Two connection states are tracked, because the browser sits one hop further out
 * than the Python client: `transport` (this browser <-> the bridge WebSocket) and
 * `upstream` (the bridge <-> `indiserver`, learned from the bridge's `connection`
 * control frame). {@link IndiClient.onConnection} reports both.
 */

import {
  type ConnectionOptions,
  ReconnectingConnection,
  type WebSocketFactory,
} from "./connection";
import { type BLOBPolicy, ISState } from "./enums";
import {
  type PropertyEvent,
  PropertyStore,
  type Subscriber,
  type SubscriptionFilter,
} from "./store";
import type {
  ConnectionFrame,
  EnableBlob,
  GetProperties,
  IndiMessage,
  Message,
  NewVector,
  Vector,
} from "./types";

/** Combined connection state: browser<->bridge and bridge<->indiserver. */
export interface ConnectionState {
  /** Whether the browser<->bridge WebSocket is open. */
  transport: boolean;
  /** Whether the bridge reports a live `indiserver` connection. */
  upstream: boolean;
}

/** A callback for inbound `message` notifications. */
export type MessageCallback = (message: Message) => void;

/** A callback for connection-state transitions. */
export type ConnectionCallback = (state: ConnectionState) => void;

/** A predicate over a vector, used by {@link IndiClient.waitFor}. */
export type Predicate = (vector: Vector) => boolean;

/** A switch value in the forms the send helpers accept. */
export type SwitchInput = ISState | boolean | "On" | "Off";

/** Options for {@link IndiClient}. */
export interface IndiClientOptions {
  /** The bridge WebSocket URL; defaults to `ws(s)://<host>/ws` from `location`. */
  url?: string;
  /** Milliseconds between a lost connection and the next attempt. */
  reconnectDelay?: number;
  /** Socket factory; defaults to the global `WebSocket` (injectable for tests). */
  webSocketFactory?: WebSocketFactory;
  /**
   * Whether to send `getProperties` on every (re)connect. Off by default: the
   * bridge primes each new socket with a full snapshot, so this is redundant
   * unless talking to a server that does not.
   */
  autoGetProperties?: boolean;
}

/** Derive the bridge WebSocket URL from the current page location. */
function defaultWsUrl(): string {
  if (typeof location === "undefined") {
    throw new Error("No global location; pass `url` to IndiClient.");
  }
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${location.host}/ws`;
}

/** Coerce a {@link SwitchInput} to an `ISState`. */
function coerceSwitch(value: SwitchInput): ISState {
  return value === true || value === "On" ? ISState.On : ISState.Off;
}

/** Number of bytes a base64 string decodes to (for BLOB `size`). */
function base64ByteLength(base64: string): number {
  const padding = base64.endsWith("==") ? 2 : base64.endsWith("=") ? 1 : 0;
  return Math.floor((base64.length * 3) / 4) - padding;
}

/** A reconnecting client that mirrors bridge state into a typed cache. */
export class IndiClient {
  private readonly _store = new PropertyStore();
  private readonly connection: ReconnectingConnection;
  private readonly messageSubs = new Map<number, MessageCallback>();
  private readonly connSubs = new Map<number, ConnectionCallback>();
  private nextSubId = 0;

  /** Remembered BLOB policies, replayed on every (re)connect. */
  private readonly blobPolicies = new Map<string, EnableBlob>();

  private readonly autoGetProperties: boolean;
  private _state: ConnectionState = { transport: false, upstream: false };

  constructor(options: IndiClientOptions = {}) {
    this.autoGetProperties = options.autoGetProperties ?? false;
    const connectionOptions: ConnectionOptions = {
      reconnectDelay: options.reconnectDelay,
      webSocketFactory: options.webSocketFactory,
      handlers: {
        onOpen: () => this.handleOpen(),
        onClose: () => this.handleClose(),
        onMessage: (data) => this.handleMessage(data),
      },
    };
    this.connection = new ReconnectingConnection(options.url ?? defaultWsUrl(), connectionOptions);
  }

  // -- lifecycle --------------------------------------------------------- //
  /** Open the connection to the bridge and begin mirroring state. */
  connect(): void {
    this.connection.start();
  }

  /** Close the connection and stop reconnecting. */
  close(): void {
    this.connection.close();
  }

  /** The current combined connection state. */
  get connectionState(): ConnectionState {
    return this._state;
  }

  /** Whether the browser<->bridge WebSocket is open. */
  get connected(): boolean {
    return this._state.transport;
  }

  /** Whether the bridge reports a live upstream `indiserver` connection. */
  get upstreamConnected(): boolean {
    return this._state.upstream;
  }

  // -- reads (delegate to the store) ------------------------------------- //
  /** Return a cached vector, or `undefined` if it is not present. */
  get(device: string, name: string): Vector | undefined {
    return this._store.get(device, name);
  }

  /** The underlying property cache. */
  get store(): PropertyStore {
    return this._store;
  }

  /** A stable read-only snapshot of one device's properties. */
  device(name: string) {
    return this._store.device(name);
  }

  /** A stable, sorted list of all known device names. */
  devices(): readonly string[] {
    return this._store.devices();
  }

  // -- subscriptions ----------------------------------------------------- //
  /** Register a property-event callback; returns an unsubscribe function. */
  subscribe(callback: Subscriber, filter: SubscriptionFilter = {}): () => void {
    return this._store.subscribe(callback, filter);
  }

  /** Register a callback for inbound `message` notifications. */
  onMessage(callback: MessageCallback): () => void {
    const token = this.nextSubId++;
    this.messageSubs.set(token, callback);
    return () => {
      this.messageSubs.delete(token);
    };
  }

  /** Register a callback for connection-state transitions. */
  onConnection(callback: ConnectionCallback): () => void {
    const token = this.nextSubId++;
    this.connSubs.set(token, callback);
    return () => {
      this.connSubs.delete(token);
    };
  }

  /**
   * Resolve once a property exists (and satisfies `predicate`).
   *
   * Resolves immediately if the cached property already matches; rejects with a
   * `TimeoutError`-like `Error` if `timeout` (ms) elapses first.
   */
  waitFor(
    device: string,
    name: string,
    predicate?: Predicate,
    options: { timeout?: number } = {},
  ): Promise<Vector> {
    const current = this._store.get(device, name);
    if (current !== undefined && (predicate === undefined || predicate(current))) {
      return Promise.resolve(current);
    }
    return new Promise<Vector>((resolve, reject) => {
      let timer: ReturnType<typeof setTimeout> | undefined;
      const unsubscribe = this._store.subscribe(
        (event) => {
          const vector = event.vector;
          if (vector !== null && (predicate === undefined || predicate(vector))) {
            cleanup();
            resolve(vector);
          }
        },
        { device, name },
      );
      const cleanup = () => {
        unsubscribe();
        if (timer !== undefined) clearTimeout(timer);
      };
      if (options.timeout !== undefined) {
        timer = setTimeout(() => {
          cleanup();
          reject(new Error(`waitFor timed out after ${options.timeout}ms: ${device}.${name}`));
        }, options.timeout);
      }
    });
  }

  // -- sends ------------------------------------------------------------- //
  /** Queue an arbitrary message to send upstream. */
  send(message: IndiMessage): void {
    this.connection.send(JSON.stringify(message));
  }

  /** Ask the server to (re-)send property definitions. */
  getProperties(device?: string, name?: string): void {
    const message: GetProperties = { tag: "getProperties", device, name };
    this.send(message);
  }

  /**
   * Set the BLOB delivery policy for a device (or one property).
   *
   * The request is remembered and replayed on every reconnect, matching the
   * Python client.
   */
  enableBlob(device: string, name?: string, policy: BLOBPolicy = "Also"): void {
    const message: EnableBlob = { tag: "enableBLOB", device, name, policy };
    this.blobPolicies.set(`${device} ${name ?? ""}`, message);
    this.send(message);
  }

  /** Send new number values for a property. */
  setNumber(device: string, name: string, values: Record<string, number>): void {
    const vector: NewVector["vector"] = {
      kind: "number",
      device,
      name,
      state: "Idle",
      perm: "rw",
      elements: Object.entries(values).map(([elementName, value]) => ({
        kind: "number",
        name: elementName,
        value,
      })),
    };
    this.send({ tag: "new", vector });
  }

  /** Send new text values for a property. */
  setText(device: string, name: string, values: Record<string, string>): void {
    const vector: NewVector["vector"] = {
      kind: "text",
      device,
      name,
      state: "Idle",
      perm: "rw",
      elements: Object.entries(values).map(([elementName, value]) => ({
        kind: "text",
        name: elementName,
        value,
      })),
    };
    this.send({ tag: "new", vector });
  }

  /** Send new switch states for a property. */
  setSwitch(device: string, name: string, values: Record<string, SwitchInput>): void {
    const vector: NewVector["vector"] = {
      kind: "switch",
      device,
      name,
      state: "Idle",
      perm: "rw",
      rule: "AnyOfMany",
      elements: Object.entries(values).map(([elementName, value]) => ({
        kind: "switch",
        name: elementName,
        value: coerceSwitch(value),
      })),
    };
    this.send({ tag: "new", vector });
  }

  /** Send new BLOB payloads (base64 strings) for a property. */
  setBlob(device: string, name: string, values: Record<string, string>): void {
    const vector: NewVector["vector"] = {
      kind: "blob",
      device,
      name,
      state: "Idle",
      perm: "rw",
      elements: Object.entries(values).map(([elementName, data]) => ({
        kind: "blob",
        name: elementName,
        data,
        size: base64ByteLength(data),
      })),
    };
    this.send({ tag: "new", vector });
  }

  // -- inbound handling -------------------------------------------------- //
  private handleOpen(): void {
    if (this.autoGetProperties) this.getProperties();
    for (const policy of this.blobPolicies.values()) this.send(policy);
    this.setState({ transport: true, upstream: this._state.upstream });
  }

  private handleClose(): void {
    // With the socket down we cannot know the upstream state; report both down.
    this.setState({ transport: false, upstream: false });
  }

  private handleMessage(data: string): void {
    let parsed: IndiMessage | ConnectionFrame;
    try {
      parsed = JSON.parse(data) as IndiMessage | ConnectionFrame;
    } catch {
      return; // drop malformed frames, matching the bridge's leniency
    }
    if ("event" in parsed && parsed.event === "connection") {
      this.setState({ transport: this._state.transport, upstream: parsed.connected });
      return;
    }
    const message = parsed as IndiMessage;
    const event = this._store.apply(message);
    if (event !== null) this.dispatch(event);
    if (message.tag === "message") {
      for (const callback of this.messageSubs.values()) callback(message);
    }
  }

  private dispatch(event: PropertyEvent): void {
    for (const callback of this._store.matching(event)) callback(event);
  }

  private setState(next: ConnectionState): void {
    if (next.transport === this._state.transport && next.upstream === this._state.upstream) {
      return;
    }
    this._state = next;
    for (const callback of this.connSubs.values()) callback(next);
  }
}
