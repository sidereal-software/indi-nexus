/**
 * Shared component-test harness.
 *
 * `renderConnected` renders UI under an `IndiProvider` whose client is wired to
 * an already-open {@link FakeSocket} that has already sent its `hello`, exactly
 * as the bridge does, so a test can feed the client inbound JSON frames with
 * `receive` and read what it sent from `socket.sent`.
 */

import { CLIENT_PROTOCOL_VERSION, IndiClient } from "@indikit/client";
import { act, type RenderResult, render } from "@testing-library/react";
import type { ReactNode } from "react";
import { IndiProvider } from "../context";
import { FakeSocket } from "./fake-socket";

/** What {@link renderConnected} returns: the render result plus the wiring. */
export interface ConnectedRender extends RenderResult {
  client: IndiClient;
  socket: FakeSocket;
}

/** Render `ui` under a provider whose client is wired to an open fake socket. */
export function renderConnected(ui: ReactNode): ConnectedRender {
  const sockets: FakeSocket[] = [];
  const client = new IndiClient({
    url: "ws://x/ws",
    webSocketFactory: () => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    },
  });
  const result = render(<IndiProvider client={client}>{ui}</IndiProvider>);
  const socket = sockets[0];
  if (!socket) throw new Error("client did not open a socket");
  act(() => socket.open());
  // The bridge leads every socket with its `hello`, and a harness that skipped
  // it would put a "no hello frame" entry at the head of every message log a
  // consumer asserts on.
  receive(socket, { event: "hello", protocol: CLIENT_PROTOCOL_VERSION, server: "test" });
  return { client, socket, ...result };
}

/** Deliver one inbound frame (serialized to JSON) inside React's `act`. */
export function receive(socket: FakeSocket, frame: unknown): void {
  act(() => socket.receive(JSON.stringify(frame)));
}
