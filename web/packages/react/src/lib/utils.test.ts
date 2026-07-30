/** Tests for the `cn` class-merging helper. */

import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("joins classes and drops falsy values", () => {
    expect(cn("a", undefined, false, "b")).toBe("a b");
  });

  it("resolves Tailwind conflicts with the later class winning", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("supports conditional objects", () => {
    expect(cn({ hidden: false, flex: true })).toBe("flex");
  });
});
