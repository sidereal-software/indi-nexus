/**
 * Number formatting per INDI printf-style `format` strings.
 *
 * A hand-authored mirror of `indi_nexus.protocol.xml.format_number`: it handles
 * the INDI `%m` sexagesimal form (e.g. `%9.6m`, field-width padded like
 * libindi's `fs_sexa`) plus the common printf conversions elements actually use
 * (`%f`, `%d`/`%i`); anything else falls back to the plain decimal value. Keep
 * the two implementations in sync - the Python side's test table is mirrored in
 * `format.test.ts`.
 */

/** Fraction denominators per `%m` precision digit (libindi's fs_sexa bases). */
const FRACBASES: Record<number, number> = { 9: 360000, 8: 36000, 6: 3600, 5: 600 };

/** Left-pad a nonnegative integer to two digits. */
function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** Format `value` as sexagesimal for a `%<width>.<frac>m` INDI format. */
function formatSexagesimal(value: number, width: number, frac: number): string {
  const fracbase = FRACBASES[frac] ?? 60;
  const negative = value < 0;
  const n = Math.round(Math.abs(value) * fracbase);
  const d = Math.floor(n / fracbase);
  const f = n % fracbase;
  const field = Math.max(width - frac, 1);
  const dd = `${negative ? "-" : ""}${d}`.padStart(field);
  switch (fracbase) {
    case 60: // dd:mm
      return `${dd}:${pad2(f)}`;
    case 600: // dd:mm.m
      return `${dd}:${pad2(Math.floor(f / 10))}.${f % 10}`;
    case 3600: // dd:mm:ss
      return `${dd}:${pad2(Math.floor(f / 60))}:${pad2(f % 60)}`;
    case 36000: // dd:mm:ss.s
      return `${dd}:${pad2(Math.floor(f / 600))}:${pad2(Math.floor((f % 600) / 10))}.${f % 10}`;
    default: // dd:mm:ss.ss
      return (
        `${dd}:${pad2(Math.floor(f / 6000))}:${pad2(Math.floor((f % 6000) / 100))}` +
        `.${String(f % 100).padStart(2, "0")}`
      );
  }
}

/**
 * Format a number per an INDI printf-style format string.
 *
 * Mirrors the Python codec's `format_number` (including libindi-faithful field
 * padding for `%m`); trim the result for display when alignment padding is not
 * wanted.
 */
export function formatNumber(value: number, format?: string | null): string {
  if (!format) return String(value);
  const sexa = /^%(\d+)\.(\d+)m$/.exec(format.trim());
  if (sexa) return formatSexagesimal(value, Number(sexa[1]), Number(sexa[2]));
  const printf = /^%[-+ 0#]*\d*(?:\.(\d+))?([dif])$/.exec(format.trim());
  if (printf) {
    if (printf[2] === "d" || printf[2] === "i") return String(Math.round(value));
    return value.toFixed(printf[1] === undefined ? 6 : Number(printf[1]));
  }
  return String(value);
}
