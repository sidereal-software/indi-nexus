/**
 * `ReconnectingConnection`: a small reconnecting WebSocket wrapper.
 *
 * This plays the role the Python client's connection loop plays against
 * `indiserver`, but here the peer is the FastAPI bridge's `WS /ws`. It reconnects
 * with a fixed delay, encodes/decodes text frames, and buffers outbound frames
 * while the socket is not open (flushing them on connect, like the Python outbox).
 *
 * The `WebSocket` implementation is injectable so tests can drive it with an
 * in-memory fake; the default uses the global browser `WebSocket`.
 */

/** The minimal surface of a WebSocket this module relies on. */
export interface WebSocketLike {
  send(data: string): void;
  close(): void;
  readyState: number;
  onopen: ((event: unknown) => void) | null;
  onclose: ((event: unknown) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
}

/** Builds a socket for a URL; injectable for tests. */
export type WebSocketFactory = (url: string) => WebSocketLike;

/** Lifecycle callbacks the owning client wires up. */
export interface ConnectionHandlers {
  /** Called when the socket opens (after the outbox is flushed). */
  onOpen?: () => void;
  /** Called when the socket closes. */
  onClose?: () => void;
  /** Called with each inbound text frame. */
  onMessage?: (data: string) => void;
}

/** Options for {@link ReconnectingConnection}. */
export interface ConnectionOptions {
  /** Milliseconds between a lost connection and the next attempt. */
  reconnectDelay?: number;
  /** Socket factory; defaults to the global `WebSocket`. */
  webSocketFactory?: WebSocketFactory;
  handlers?: ConnectionHandlers;
}

const OPEN = 1;

/** The default factory: the browser's global `WebSocket`. */
function defaultFactory(url: string): WebSocketLike {
  if (typeof WebSocket === "undefined") {
    throw new Error("No global WebSocket; pass a webSocketFactory (e.g. in Node).");
  }
  // The browser WebSocket satisfies WebSocketLike structurally; the DOM event
  // types are narrower, so a single cast at the boundary keeps callers clean.
  return new WebSocket(url) as unknown as WebSocketLike;
}

/** A WebSocket that transparently reconnects and buffers sends while offline. */
export class ReconnectingConnection {
  private readonly url: string;
  private readonly reconnectDelay: number;
  private readonly factory: WebSocketFactory;
  private readonly handlers: ConnectionHandlers;

  private socket: WebSocketLike | null = null;
  private outbox: string[] = [];
  private closing = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(url: string, options: ConnectionOptions = {}) {
    this.url = url;
    this.reconnectDelay = options.reconnectDelay ?? 2000;
    this.factory = options.webSocketFactory ?? defaultFactory;
    this.handlers = options.handlers ?? {};
  }

  /** Whether the socket is currently open. */
  get connected(): boolean {
    return this.socket !== null && this.socket.readyState === OPEN;
  }

  /** Open the connection (idempotent while already connecting/connected). */
  start(): void {
    this.closing = false;
    if (this.socket !== null) return;
    this.open();
  }

  /** Close the connection and stop reconnecting. */
  close(): void {
    this.closing = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket !== null) {
      const socket = this.socket;
      this.socket = null;
      socket.close();
      // Report the close from here rather than from `onclose`: the socket is no
      // longer ours the moment we drop it, and a real one takes a round trip to
      // finish closing, by which time a `start()` may already have replaced it.
      this.handlers.onClose?.();
    }
  }

  /** Send a text frame, buffering it if the socket is not open yet. */
  send(data: string): void {
    if (this.socket !== null && this.socket.readyState === OPEN) {
      this.socket.send(data);
    } else {
      this.outbox.push(data);
    }
  }

  private open(): void {
    const socket = this.factory(this.url);
    this.socket = socket;
    // A socket we have already dropped must do nothing at all. Closing is
    // asynchronous, so under React StrictMode's mount/cleanup/mount the first
    // socket is still alive when the second is open, and it can still deliver
    // events: reporting its close would call a live connection down, and
    // reconnecting from it would open a third socket that orphans the healthy
    // one. Every handler checks it is still the current socket first.
    const current = () => this.socket === socket;
    socket.onopen = () => {
      if (!current()) return;
      const pending = this.outbox;
      this.outbox = [];
      for (const frame of pending) socket.send(frame);
      this.handlers.onOpen?.();
    };
    socket.onmessage = (event) => {
      if (!current()) return;
      if (typeof event.data === "string") this.handlers.onMessage?.(event.data);
    };
    socket.onerror = () => {
      // Let the subsequent close event drive the reconnect.
      socket.close();
    };
    socket.onclose = () => {
      if (!current()) return;
      this.socket = null;
      this.handlers.onClose?.();
      if (!this.closing) this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.closing) this.open();
    }, this.reconnectDelay);
  }
}
