/**
 * Tests for the hand-authored enum tokens and the `isWritable` helper.
 *
 * The enums are a hand-maintained mirror of `indi_nexus.protocol.enums`; these
 * assertions pin each member to its exact INDI wire token so a drift from the
 * Python side fails loudly.
 */

import { describe, expect, it } from "vitest";
import { BLOBPolicy, IPerm, IPState, ISRule, ISState, isWritable } from "./enums";

describe("enum wire tokens", () => {
  it("match the INDI 1.7 tokens exactly", () => {
    expect(Object.values(IPState)).toEqual(["Idle", "Ok", "Busy", "Alert"]);
    expect(Object.values(IPerm)).toEqual(["ro", "wo", "rw"]);
    expect(Object.values(ISRule)).toEqual(["OneOfMany", "AtMostOne", "AnyOfMany"]);
    expect(Object.values(ISState)).toEqual(["Off", "On"]);
    expect(Object.values(BLOBPolicy)).toEqual(["Never", "Also", "Only"]);
  });
});

describe("isWritable", () => {
  it("grants write access for rw and wo only", () => {
    expect(isWritable("rw")).toBe(true);
    expect(isWritable("wo")).toBe(true);
    expect(isWritable("ro")).toBe(false);
    expect(isWritable(undefined)).toBe(false);
  });
});
