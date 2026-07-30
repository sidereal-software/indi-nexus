/**
 * A controllable in-memory `WebSocketLike` for component tests.
 *
 * Lets a test drive an {@link IndiClient} deterministically: open the socket,
 * feed it frames with `receive`, and read what the client sent from `sent`.
 */

import type { WebSocketLike } from "@indi-nexus/client";

/** A fake WebSocket whose lifecycle the test triggers by hand. */
export class FakeSocket implements WebSocketLike {
  readyState = 0;
  onopen: ((event: unknown) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  readonly sent: string[] = [];

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.({});
  }

  /** Transition to OPEN and fire `onopen`. */
  open(): void {
    this.readyState = 1;
    this.onopen?.({});
  }

  /** Deliver one inbound text frame. */
  receive(data: string): void {
    this.onmessage?.({ data });
  }

  /** The last frame the client sent, parsed. */
  lastSent<T = unknown>(): T {
    const frame = this.sent.at(-1);
    if (frame === undefined) throw new Error("nothing sent");
    return JSON.parse(frame) as T;
  }
}
