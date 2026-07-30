/** Tests for the wire-type helpers. */

import { describe, expect, it } from "vitest";
import type { TextVector } from "./types";
import { elementByName } from "./types";

const vector: TextVector = {
  kind: "text",
  device: "Scope",
  name: "INFO",
  state: "Idle",
  perm: "ro",
  elements: [
    { kind: "text", name: "site", value: "MMT" },
    { kind: "text", name: "operator", value: "dan" },
  ],
};

describe("elementByName", () => {
  it("finds an element by name", () => {
    expect(elementByName(vector, "operator")).toMatchObject({ value: "dan" });
  });

  it("returns undefined for an unknown name", () => {
    expect(elementByName(vector, "missing")).toBeUndefined();
  });
});
