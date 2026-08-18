/**
 * Tests for the display helpers: the label fallback and the number formatter.
 *
 * Every expectation here is what Python prints for the same value and format:
 * the sexagesimal cases mirror `tests/test_protocol.py::test_format_number`, and
 * the printf cases were taken from `indi_nexus.protocol.xml.format_number` itself
 * (which strips its result, so a space-padded width never survives). The two
 * implementations must produce identical output.
 */

import { describe, expect, it } from "vitest";
import { displayLabel, formatNumber } from "./format";

describe("formatNumber sexagesimal", () => {
  it.each([
    [10.5, "%5.3m", "10:30"],
    [10.5, "%8.5m", " 10:30.0"],
    [10.5, "%8.6m", "10:30:00"],
    [-10.5, "%8.6m", "-10:30:00"],
    [10.5, "%11.8m", " 10:30:00.0"],
    [10.5, "%12.9m", " 10:30:00.00"],
    [12.582777778, "%9.6m", " 12:34:58"], // width-9 field pads the degrees
  ])("formats %f with %s as %j (matching the Python codec)", (value, format, expected) => {
    expect(formatNumber(value, format)).toBe(expected);
  });
});

describe("formatNumber %g", () => {
  // %g is the default format for a Number element (models.py), so this is the
  // common case rather than an exotic one.
  it.each([
    [0.1 + 0.2, "%g", "0.3"], // not 0.30000000000000004
    [1 / 3, "%g", "0.333333"], // six significant digits by default
    [1234567, "%g", "1.23457e+06"], // exponent >= precision: scientific
    [0.000012345, "%g", "1.2345e-05"], // exponent < -4: scientific
    [0.0001, "%g", "0.0001"], // exponent -4 is the last fixed one
    [0.00001, "%g", "1e-05"],
    [100000, "%g", "100000"], // exponent 5 is the last fixed one
    [1000000, "%g", "1e+06"],
    [999999.5, "%g", "1e+06"], // the style follows the *rounded* exponent
    [1200, "%g", "1200"], // trailing zeros before the point are kept
    [1.5, "%g", "1.5"],
    [12.582777778, "%g", "12.5828"],
    [66.9, "%g", "66.9"],
    [-1234.5678, "%g", "-1234.57"],
    [0, "%g", "0"],
    [-0, "%g", "-0"],
    [1234567, "%G", "1.23457E+06"],
    [123.456, "%.3g", "123"],
    [0.0001234, "%.3g", "0.000123"],
    [123.456, "%.0g", "1e+02"], // a precision of 0 counts as 1
    [1.5, "%.1g", "2"],
    [2.5, "%.1g", "2"], // and ties still go to even
    [0.1, "%.20g", "0.10000000000000000555"], // the double's exact value
    [1, "%#g", "1.00000"], // '#' keeps the trailing zeros
    [100, "%#.3g", "100."], // ... and the point
  ])("formats %f with %s as %j", (value, format, expected) => {
    expect(formatNumber(value, format)).toBe(expected);
  });
});

describe("formatNumber rounding", () => {
  it.each([
    [2.5, "%.0f", "2"], // half-to-even, not toFixed's half-up
    [3.5, "%.0f", "4"],
    [-2.5, "%.0f", "-2"],
    [0.5, "%.0f", "0"],
    [9.99, "%.1e", "1.0e+01"], // a carry into the next decade
    [1.005, "%.2f", "1.00"], // the double is just below the tie
    [1.015, "%.2f", "1.01"],
    [2.675, "%.2f", "2.67"],
    [-0, "%.2f", "-0.00"], // the sign of negative zero survives
    [-0.001, "%.2f", "-0.00"],
    [1, "%.2f", "1.00"],
    [1234567, "%e", "1.234567e+06"],
    [0, "%.2e", "0.00e+00"],
  ])("formats %f with %s as %j", (value, format, expected) => {
    expect(formatNumber(value, format)).toBe(expected);
  });
});

describe("formatNumber integers", () => {
  it.each([
    [41.7, "%d", "41"], // Python's %d truncates toward zero; it does not round
    [-41.7, "%d", "-41"],
    [41.2, "%3i", "41"],
    [-0.4, "%d", "0"], // truncating to zero drops the sign too
  ])("formats %f with %s as %j", (value, format, expected) => {
    expect(formatNumber(value, format)).toBe(expected);
  });
});

describe("formatNumber field width", () => {
  it.each([
    [7, "%04d", "0007"], // a zero-padded width survives
    [-7, "%04d", "-007"], // ... and fills after the sign
    [0.05, "%05.2f", "00.05"],
    [-0.05, "%05.2f", "-0.05"],
    [1, "%8.2f", "1.00"], // a space-padded one does not: format_number strips it
    [1, "%-8.2f", "1.00"],
    [1.5, "%+.2f", "+1.50"],
    [1.5, "% .2f", "1.50"], // the space flag is stripped along with the padding
  ])("formats %f with %s as %j", (value, format, expected) => {
    expect(formatNumber(value, format)).toBe(expected);
  });
});

describe("formatNumber fallbacks", () => {
  it("falls back to the plain value for missing or unknown formats", () => {
    expect(formatNumber(1.5)).toBe("1.5");
    expect(formatNumber(1.5, "%x")).toBe("1.5");
    expect(formatNumber(1.5, "no-placeholder")).toBe("1.5");
  });

  it("falls back for values JSON cannot carry", () => {
    expect(formatNumber(Number.NaN, "%g")).toBe("NaN");
    expect(formatNumber(Number.POSITIVE_INFINITY, "%.2f")).toBe("Infinity");
  });
});

describe("displayLabel", () => {
  it("prefers the label when it carries something", () => {
    expect(displayLabel({ name: "CONNECT", label: "Connect" })).toBe("Connect");
  });

  it.each([
    ["absent", undefined],
    ["null", null],
    ["empty", ""],
    ["blank", "   "],
  ])("falls back to the name when the label is %s", (_case, label) => {
    // libindi ships DEVICE_BAUD_RATE with empty element labels, so this is the
    // real driver behaviour rather than a defensive branch.
    expect(displayLabel({ name: "9600", label })).toBe("9600");
  });
});
