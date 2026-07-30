/** Tests for the two-dot bridge/indiserver connection indicator. */

import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { receive, renderConnected } from "../testing/render";
import { ConnectionStatus } from "./connection-status";

afterEach(cleanup);

/** The screen-reader status text next to the given dot label. */
function statusOf(label: string): string | null {
  const dot = screen.getByText(label).parentElement;
  if (!dot) throw new Error(`no dot for ${label}`);
  return dot.querySelector(".sr-only")?.textContent ?? null;
}

describe("ConnectionStatus", () => {
  it("shows the bridge connected and indiserver down after the socket opens", () => {
    renderConnected(<ConnectionStatus />);
    expect(statusOf("bridge")).toBe("connected");
    expect(statusOf("indiserver")).toBe("disconnected");
  });

  it("marks indiserver connected when the bridge reports upstream up", () => {
    const { socket } = renderConnected(<ConnectionStatus />);
    receive(socket, { event: "connection", connected: true });
    expect(statusOf("bridge")).toBe("connected");
    expect(statusOf("indiserver")).toBe("connected");
  });
});
