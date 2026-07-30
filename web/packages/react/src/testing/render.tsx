/**
 * Shared component-test harness.
 *
 * `renderConnected` renders UI under an `IndiProvider` whose client is wired to
 * an already-open {@link FakeSocket}, so a test can feed the client inbound JSON
 * frames with `receive` and read what it sent from `socket.sent`.
 */

import { IndiClient } from "@indi-nexus/client";
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
  return { client, socket, ...result };
}

/** Deliver one inbound frame (serialized to JSON) inside React's `act`. */
export function receive(socket: FakeSocket, frame: unknown): void {
  act(() => socket.receive(JSON.stringify(frame)));
}
