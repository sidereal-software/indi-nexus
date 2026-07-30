/** Tests for `IndiProvider` / `useIndiClient` lifecycle and wiring. */

import { IndiClient } from "@indi-nexus/client";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IndiProvider, useIndiClient } from "./context";
import { FakeSocket } from "./testing/fake-socket";

afterEach(cleanup);

/** Build a client plus the list of sockets its factory creates. */
function clientWithSockets() {
  const sockets: FakeSocket[] = [];
  const client = new IndiClient({
    url: "ws://x/ws",
    webSocketFactory: () => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    },
  });
  return { client, sockets };
}

/** Render the provided client's identity so a test can assert on it. */
function ShowClient() {
  const client = useIndiClient();
  return <span data-testid="client">{client.constructor.name}</span>;
}

describe("IndiProvider", () => {
  it("provides the given client and connects it on mount", () => {
    const { client, sockets } = clientWithSockets();
    render(
      <IndiProvider client={client}>
        <ShowClient />
      </IndiProvider>,
    );
    expect(screen.getByTestId("client")).toHaveTextContent("IndiClient");
    expect(sockets).toHaveLength(1);
  });

  it("closes the client on unmount", () => {
    const { client, sockets } = clientWithSockets();
    const { unmount } = render(<IndiProvider client={client}>x</IndiProvider>);
    sockets[0]?.open();
    unmount();
    expect(sockets[0]?.readyState).toBe(3);
  });

  it("constructs its own client from inline options when none is given", () => {
    const sockets: FakeSocket[] = [];
    render(
      <IndiProvider
        url="ws://x/ws"
        webSocketFactory={() => {
          const socket = new FakeSocket();
          sockets.push(socket);
          return socket;
        }}
      >
        <ShowClient />
      </IndiProvider>,
    );
    expect(screen.getByTestId("client")).toHaveTextContent("IndiClient");
    expect(sockets).toHaveLength(1);
  });
});

describe("useIndiClient", () => {
  it("throws outside an IndiProvider", () => {
    // React logs render-phase errors to console.error; keep the test output clean.
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<ShowClient />)).toThrow(/within an <IndiProvider>/);
    errorSpy.mockRestore();
  });
});
