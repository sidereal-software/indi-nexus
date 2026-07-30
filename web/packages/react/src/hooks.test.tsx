/** Tests for the store-backed hooks: each re-renders on the events it watches. */

import type { NumberVector } from "@indi-nexus/client";
import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  useConnection,
  useDevice,
  useDevices,
  useElement,
  useMessages,
  useProperty,
} from "./hooks";
import { receive, renderConnected } from "./testing/render";

afterEach(cleanup);

/** Build a minimal rw number vector for `device`/`name`. */
function numVec(device: string, name: string, value = 1): NumberVector {
  return {
    kind: "number",
    device,
    name,
    state: "Idle",
    perm: "rw",
    elements: [{ kind: "number", name: "v", value }],
  };
}

describe("useConnection", () => {
  function Probe() {
    const { transport, upstream } = useConnection();
    return (
      <span>
        transport:{String(transport)} upstream:{String(upstream)}
      </span>
    );
  }

  it("tracks the transport and upstream states separately", () => {
    const { socket } = renderConnected(<Probe />);
    expect(screen.getByText("transport:true upstream:false")).toBeInTheDocument();

    receive(socket, { event: "connection", connected: true });
    expect(screen.getByText("transport:true upstream:true")).toBeInTheDocument();
  });
});

describe("useDevices", () => {
  function Probe() {
    return <span>{useDevices().join(",") || "(none)"}</span>;
  }

  it("lists device names sorted as defs arrive", () => {
    const { socket } = renderConnected(<Probe />);
    expect(screen.getByText("(none)")).toBeInTheDocument();

    receive(socket, { tag: "def", vector: numVec("Mount", "COORDS") });
    receive(socket, { tag: "def", vector: numVec("CCD", "EXPOSURE") });
    expect(screen.getByText("CCD,Mount")).toBeInTheDocument();
  });
});

describe("useDevice", () => {
  function Probe({ device }: { device: string }) {
    return <span>{Object.keys(useDevice(device)).join(",") || "(none)"}</span>;
  }

  it("exposes only the watched device's properties", () => {
    const { socket } = renderConnected(<Probe device="CCD" />);
    receive(socket, { tag: "def", vector: numVec("CCD", "EXPOSURE") });
    receive(socket, { tag: "def", vector: numVec("CCD", "TEMP") });
    receive(socket, { tag: "def", vector: numVec("Mount", "COORDS") });
    expect(screen.getByText("EXPOSURE,TEMP")).toBeInTheDocument();
  });

  it("drops a property on delProperty", () => {
    const { socket } = renderConnected(<Probe device="CCD" />);
    receive(socket, { tag: "def", vector: numVec("CCD", "EXPOSURE") });
    receive(socket, { tag: "delProperty", device: "CCD", name: "EXPOSURE" });
    expect(screen.getByText("(none)")).toBeInTheDocument();
  });
});

describe("useProperty", () => {
  function Probe() {
    const vector = useProperty("CCD", "EXPOSURE");
    if (vector === undefined) return <span>(undefined)</span>;
    const element = vector.elements[0];
    return <span>{element?.kind === "number" ? `value:${element.value}` : "?"}</span>;
  }

  it("is undefined until defined, then follows set merges", () => {
    const { socket } = renderConnected(<Probe />);
    expect(screen.getByText("(undefined)")).toBeInTheDocument();

    receive(socket, { tag: "def", vector: numVec("CCD", "EXPOSURE", 1.5) });
    expect(screen.getByText("value:1.5")).toBeInTheDocument();

    receive(socket, { tag: "set", vector: numVec("CCD", "EXPOSURE", 2.5) });
    expect(screen.getByText("value:2.5")).toBeInTheDocument();
  });
});

describe("useElement", () => {
  function Probe() {
    const element = useElement("CCD", "EXPOSURE", "v");
    if (element === undefined) return <span>(undefined)</span>;
    return <span>{element.kind === "number" ? `value:${element.value}` : "?"}</span>;
  }

  it("is undefined until defined, then follows the one element", () => {
    const { socket } = renderConnected(<Probe />);
    expect(screen.getByText("(undefined)")).toBeInTheDocument();

    receive(socket, { tag: "def", vector: numVec("CCD", "EXPOSURE", 1.5) });
    expect(screen.getByText("value:1.5")).toBeInTheDocument();

    receive(socket, { tag: "set", vector: numVec("CCD", "EXPOSURE", 2.5) });
    expect(screen.getByText("value:2.5")).toBeInTheDocument();
  });
});

describe("useMessages", () => {
  function Probe({ limit }: { limit?: number }) {
    const messages = useMessages(limit);
    return <span>{messages.map((m) => m.message).join("|") || "(none)"}</span>;
  }

  it("accumulates message notifications oldest first", () => {
    const { socket } = renderConnected(<Probe />);
    expect(screen.getByText("(none)")).toBeInTheDocument();

    receive(socket, { tag: "message", device: "CCD", message: "one" });
    receive(socket, { tag: "message", device: "CCD", message: "two" });
    expect(screen.getByText("one|two")).toBeInTheDocument();
  });

  it("drops the oldest messages beyond the limit", () => {
    const { socket } = renderConnected(<Probe limit={2} />);
    receive(socket, { tag: "message", message: "one" });
    receive(socket, { tag: "message", message: "two" });
    receive(socket, { tag: "message", message: "three" });
    expect(screen.getByText("two|three")).toBeInTheDocument();
  });
});
