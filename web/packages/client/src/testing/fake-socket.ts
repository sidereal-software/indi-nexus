/**
 * A controllable in-memory `WebSocketLike` for tests.
 *
 * Nothing here is part of the public package; it lets the connection and client
 * tests drive open/message/close transitions deterministically without a real
 * WebSocket, the same way the Python tests drive an in-memory byte stream.
 */

import type { WebSocketLike } from "../connection";

/** A fake WebSocket whose lifecycle the test triggers by hand. */
export class FakeSocket implements WebSocketLike {
  /** Every socket the shared factory has created, newest last. */
  static instances: FakeSocket[] = [];

  readyState = 0; // CONNECTING
  onopen: ((event: unknown) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;

  /** Frames the client sent through this socket. */
  readonly sent: string[] = [];
  readonly url: string;

  constructor(url: string) {
    this.url = url;
    FakeSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    if (this.readyState === 3) return;
    this.readyState = 3; // CLOSED
    this.onclose?.({});
  }

  // -- test helpers ------------------------------------------------------ //
  /** Transition to OPEN and fire `onopen`. */
  open(): void {
    this.readyState = 1; // OPEN
    this.onopen?.({});
  }

  /** Deliver one inbound text frame. */
  receive(data: string): void {
    this.onmessage?.({ data });
  }

  /** The most recently created socket. */
  static latest(): FakeSocket {
    const socket = FakeSocket.instances.at(-1);
    if (socket === undefined) throw new Error("no FakeSocket created yet");
    return socket;
  }

  /** Reset the shared registry between tests. */
  static reset(): void {
    FakeSocket.instances = [];
  }
}

/** A `WebSocketFactory` that produces {@link FakeSocket}s. */
export function fakeFactory(url: string): FakeSocket {
  return new FakeSocket(url);
}
