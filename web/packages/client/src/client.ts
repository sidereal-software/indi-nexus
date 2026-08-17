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
 * control frame). {@link IndiClient.onConnection} reports both, alongside the
 * bridge's announced contract version from its `hello` frame.
 */

import {
  type ConnectionOptions,
  ReconnectingConnection,
  type WebSocketFactory,
} from "./connection";
import { type BLOBPolicy, ISState } from "./enums";
import { acceptFrame } from "./frames";
import {
  type PropertyEvent,
  PropertyStore,
  type Subscriber,
  type SubscriptionFilter,
} from "./store";
import {
  type BridgeFrame,
  CLIENT_PROTOCOL_VERSION,
  type EnableBlob,
  type GetProperties,
  type HelloFrame,
  type IndiMessage,
  type Message,
  type NewVector,
  type Vector,
} from "./types";

/** Combined connection state: browser<->bridge and bridge<->indiserver. */
export interface ConnectionState {
  /** Whether the browser<->bridge WebSocket is open. */
  transport: boolean;
  /** Whether the bridge reports a live `indiserver` connection. */
  upstream: boolean;
  /**
   * The bridge's contract version, from its `hello` frame.
   *
   * `null` before any frame has arrived on the current socket, and `0` once a
   * frame that was not a `hello` has arrived first - which means a bridge older
   * than the frame, not an unknown one. Compare with
   * {@link CLIENT_PROTOCOL_VERSION}; a mismatch is never fatal.
   */
  protocol: number | null;
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
  /**
   * Maximum inbound `message` notifications retained in {@link IndiClient.messages}
   * (oldest dropped first).
   */
  messageLogLimit?: number;
}

/**
 * Derive the bridge WebSocket URL from the current page location.
 *
 * The page's own `?token=` is carried across to `/ws`. A bridge started with a
 * token requires it there, and a browser cannot put one in a header on a
 * WebSocket handshake, so the query parameter is the only form available - and
 * the panel is served by that same bridge from a URL that already carries it.
 */
function defaultWsUrl(): string {
  if (typeof location === "undefined") {
    throw new Error("No global location; pass `url` to IndiClient.");
  }
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const token = new URLSearchParams(location.search).get("token");
  const query = token === null ? "" : `?token=${encodeURIComponent(token)}`;
  return `${protocol}://${location.host}/ws${query}`;
}

/** Coerce a {@link SwitchInput} to an `ISState`. */
function coerceSwitch(value: SwitchInput): ISState {
  return value === true || value === "On" ? ISState.On : ISState.Off;
}

/**
 * The map key for one remembered BLOB policy.
 *
 * The Python client keys these on the `(device, name)` tuple; a JS `Map` has no
 * tuple key, and joining the pair with a separator is not injective - "A" and
 * "B C" would collide with "A B" and "C" - so encode the pair instead.
 */
function blobPolicyKey(device: string, name: string | undefined): string {
  return JSON.stringify([device, name ?? null]);
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
  private readonly messageLogLimit: number;
  private _state: ConnectionState = { transport: false, upstream: false, protocol: null };

  /**
   * Whether any frame has arrived on the current socket.
   *
   * The version latch: the first frame decides whether this bridge speaks the
   * `hello`. Reset on every close alongside `protocol`, or a reconnect onto an
   * older bridge would leave `protocol` at `null` for ever instead of settling
   * on `0`.
   */
  private sawFrame = false;

  /**
   * Rolling log of inbound `message` notifications, oldest first. Kept on the
   * client (immutably, a new array per append) so UI that mounts late - a log
   * panel opened on demand - can still show everything since the page loaded.
   */
  private _messages: readonly Message[] = [];

  constructor(options: IndiClientOptions = {}) {
    this.autoGetProperties = options.autoGetProperties ?? false;
    this.messageLogLimit = options.messageLogLimit ?? 200;
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

  /**
   * The retained inbound `message` notifications, oldest first.
   *
   * The returned array is a stable snapshot (a new reference only when a
   * message arrives), so it is safe to feed to `useSyncExternalStore`.
   */
  messages(): readonly Message[] {
    return this._messages;
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
    this.blobPolicies.set(blobPolicyKey(device, name), message);
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
    this.setState({
      transport: true,
      upstream: this._state.upstream,
      protocol: this._state.protocol,
    });
  }

  private handleClose(): void {
    // With the socket down we cannot know the upstream state; report both down.
    // The version goes with them: the next socket may reach a different bridge,
    // and a stale version number is worse than no number at all.
    this.sawFrame = false;
    this.setState({ transport: false, upstream: false, protocol: null });
  }

  private handleMessage(data: string): void {
    let parsed: unknown;
    try {
      parsed = JSON.parse(data);
    } catch {
      return; // drop malformed frames, matching the bridge's leniency
    }
    // Valid JSON need not be an object: `null`, a bare number and a bare string
    // all parse, and none of them is a frame (`"event" in null` would throw).
    if (typeof parsed !== "object" || parsed === null) return;
    const frame = parsed as IndiMessage | BridgeFrame;
    // The version latch is evaluated here: ahead of the control-frame branch,
    // and ahead of `acceptFrame` below. A first frame the frame guard rejects
    // is still a frame that was not a `hello`, so a bridge that sends no hello
    // and whose first `def` happens to be malformed must not leave `protocol`
    // stuck at `null` for the life of the socket.
    if (!this.sawFrame) {
      this.sawFrame = true;
      if (!("event" in frame) || frame.event !== "hello") this.assumeLegacyBridge();
    }
    // A bridge control frame is not an INDI message and never reaches the store.
    // An `event` this version does not know is dropped, as it always was.
    if ("event" in frame) {
      if (frame.event === "hello") {
        this.acceptHello(frame);
      } else if (frame.event === "connection") {
        this.setState({
          transport: this._state.transport,
          upstream: frame.connected,
          protocol: this._state.protocol,
        });
      } else if (frame.event === "error") {
        this.recordMessage({
          tag: "message",
          message: frame.tag ? `${frame.tag} was not sent: ${frame.message}` : frame.message,
        });
      }
      return;
    }
    const message = frame as IndiMessage;
    // A frame the wire contract cannot represent is dropped whole, exactly like
    // the non-object JSON above: a `def` with no device would otherwise cache a
    // phantom device, and a NaN would reach a control. See `frames.ts`.
    if (!acceptFrame(message)) return;
    const event = this._store.apply(message);
    if (event !== null) this.dispatch(event);
    if (message.tag === "message") this.recordMessage(message);
  }

  /**
   * Record the bridge's announced contract version, warning on a skew.
   *
   * Never fatal, in either direction. Version bumps are breaking-only and every
   * additive change leaves both sides working - the client already drops an
   * `event` and an object key it does not know - so refusing the socket would
   * turn a cosmetic skew into a dark panel mid-session.
   */
  private acceptHello(frame: HelloFrame): void {
    this.setState({
      transport: this._state.transport,
      upstream: this._state.upstream,
      protocol: frame.protocol,
    });
    if (frame.protocol !== CLIENT_PROTOCOL_VERSION) {
      this.recordMessage({
        tag: "message",
        message:
          `bridge protocol ${frame.protocol} (server ${frame.server}) does not match this ` +
          `client's ${CLIENT_PROTOCOL_VERSION}; continuing, but some frames may not be understood`,
      });
    }
  }

  /**
   * Record that this bridge predates the `hello` frame.
   *
   * `0` rather than `null`: the question has been answered, and the answer is
   * "older than the version announcement". Leaving it `null` would be
   * indistinguishable from a socket that has not received anything yet.
   */
  private assumeLegacyBridge(): void {
    this.setState({
      transport: this._state.transport,
      upstream: this._state.upstream,
      protocol: 0,
    });
    this.recordMessage({
      tag: "message",
      message: "the bridge sent no hello frame; assuming a version older than protocol 1",
    });
  }

  /** Append to the rolling log and notify `onMessage` subscribers. */
  private recordMessage(message: Message): void {
    const next = [...this._messages, message];
    if (next.length > this.messageLogLimit) next.splice(0, next.length - this.messageLogLimit);
    this._messages = next;
    for (const callback of this.messageSubs.values()) callback(message);
  }

  private dispatch(event: PropertyEvent): void {
    for (const callback of this._store.matching(event)) callback(event);
  }

  private setState(next: ConnectionState): void {
    // Every field of the state, not only the two links: a comparison that
    // missed one would assign the field and never notify a subscriber, and no
    // typecheck catches that.
    if (
      next.transport === this._state.transport &&
      next.upstream === this._state.upstream &&
      next.protocol === this._state.protocol
    ) {
      return;
    }
    this._state = next;
    for (const callback of this.connSubs.values()) callback(next);
  }
}
