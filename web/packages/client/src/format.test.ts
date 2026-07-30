/**
 * Tests for the INDI number formatter.
 *
 * The sexagesimal cases mirror `tests/test_protocol.py::test_format_number` on
 * the Python side - the two implementations must produce identical output.
 */

import { describe, expect, it } from "vitest";
import { formatNumber } from "./format";

describe("formatNumber", () => {
  it.each([
    [10.5, "%5.3m", "10:30"],
    [10.5, "%8.5m", " 10:30.0"],
    [10.5, "%8.6m", "10:30:00"],
    [-10.5, "%8.6m", "-10:30:00"],
    [10.5, "%11.8m", " 10:30:00.0"],
    [10.5, "%12.9m", " 10:30:00.00"],
    [12.582777778, "%9.6m", " 12:34:58"], // width-9 field pads the degrees
    [1.0, "%.2f", "1.00"],
  ])("formats %f with %s as %j (matching the Python codec)", (value, format, expected) => {
    expect(formatNumber(value, format)).toBe(expected);
  });

  it("rounds %d and %i formats to integers", () => {
    expect(formatNumber(41.7, "%d")).toBe("42");
    expect(formatNumber(41.2, "%3i")).toBe("41");
  });

  it("falls back to the plain value for missing or unknown formats", () => {
    expect(formatNumber(1.5)).toBe("1.5");
    expect(formatNumber(1.5, "%x")).toBe("1.5");
    expect(formatNumber(1.5, "no-placeholder")).toBe("1.5");
  });
});
