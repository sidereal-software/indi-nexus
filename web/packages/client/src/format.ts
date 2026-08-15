/**
 * Number formatting per INDI printf-style `format` strings.
 *
 * A hand-authored mirror of `indi_nexus.protocol.xml.format_number`: it handles
 * the INDI `%m` sexagesimal form (e.g. `%9.6m`, field-width padded like
 * libindi's `fs_sexa`) plus the printf conversions elements actually use
 * (`%g` - the default for a Number element - along with `%f`, `%e` and
 * `%d`/`%i`, with flags, width and precision); anything else falls back to the
 * plain decimal value. Keep the two implementations in sync - the Python side's
 * test table is mirrored in `format.test.ts`.
 *
 * The printf conversions round from a double's *exact* decimal expansion rather
 * than through `toFixed`, because C and Python round half-to-even on the exact
 * value while `toFixed` rounds half-up: `"%.0f" % 2.5` is `'2'` on both sides
 * only if the rounding agrees.
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

// --------------------------------------------------------------------------- //
// Exact decimal arithmetic                                                     //
// --------------------------------------------------------------------------- //

/**
 * A finite double's exact decimal expansion.
 *
 * `digits` holds every digit of the magnitude with the decimal point after
 * `point` of them, so 0.1 is `"0"` followed by its true 55 fractional digits
 * rather than the one digit it prints as. Rounding from the exact value is what
 * makes ties (`2.5` at zero decimals) resolve the way C and Python resolve
 * them, and what keeps `%.20g` honest.
 */
interface Decimal {
  /** Whether the value carries a minus sign (true for -0 as well). */
  negative: boolean;
  /** Every digit of the magnitude, most significant first. */
  digits: string;
  /** How many of `digits` sit before the decimal point; always at least 1. */
  point: number;
}

/** Scratch view for reading a double's bits; module-level to avoid re-allocating. */
const BITS = new DataView(new ArrayBuffer(8));

/** Expand a finite number into its exact decimal digits. */
function toDecimal(value: number): Decimal {
  BITS.setFloat64(0, value);
  const high = BITS.getUint32(0);
  const low = BITS.getUint32(4);
  const negative = (high & 0x8000_0000) !== 0;
  const biased = (high >>> 20) & 0x7ff;
  const fraction = ((BigInt(high) & 0xf_ffffn) << 32n) | BigInt(low);
  // Subnormals drop the implicit leading 1 and share the smallest exponent.
  const mantissa = biased === 0 ? fraction : fraction | (1n << 52n);
  const exponent = (biased === 0 ? 1 : biased) - 1075;
  if (mantissa === 0n) return { negative, digits: "0", point: 1 };
  if (exponent >= 0) {
    const digits = (mantissa << BigInt(exponent)).toString();
    return { negative, digits, point: digits.length };
  }
  // m / 2**k is exactly m * 5**k / 10**k, so the expansion terminates at k
  // fractional digits and the padding leaves exactly one leading zero when the
  // magnitude is below 1.
  const k = -exponent;
  const digits = (mantissa * 5n ** BigInt(k)).toString().padStart(k + 1, "0");
  return { negative, digits, point: digits.length - k };
}

/**
 * Round to `places` digits after the decimal point, half-to-even.
 *
 * C and Python round a tie to the even digit (`"%.0f" % 2.5` is `'2'`), unlike
 * `Number.toFixed`, which rounds it up. `places` may be negative, rounding to
 * tens, hundreds and so on; callers keep `point + places` at 1 or more, which
 * every conversion below does.
 */
function roundDecimal(value: Decimal, places: number): Decimal {
  const fraction = value.digits.length - value.point;
  if (places >= fraction) {
    return { ...value, digits: value.digits + "0".repeat(places - fraction) };
  }
  const keep = value.point + places;
  const head = value.digits.slice(0, keep);
  const dropped = value.digits.slice(keep);
  const first = dropped.charAt(0);
  const above = first > "5" || (first === "5" && /[1-9]/.test(dropped.slice(1)));
  const halfway = first === "5" && !above;
  const odd = (head.charCodeAt(head.length - 1) - 48) % 2 === 1;
  // Negative places dropped digits that still count toward the value's size, so
  // put them back as zeros to keep `point` meaning what it says.
  const zeros = "0".repeat(Math.max(0, -places));
  if (!above && !(halfway && odd)) return { ...value, digits: head + zeros };
  const bumped = (BigInt(head) + 1n).toString();
  return bumped.length > head.length
    ? // A carry out of the leading digit (9.99 to 10.0) shifts the point right.
      { ...value, digits: bumped + zeros, point: value.point + 1 }
    : { ...value, digits: bumped.padStart(head.length, "0") + zeros };
}

/** The decimal exponent X with 10**X <= |value| < 10**(X+1); 0 for zero. */
function exponentOf(value: Decimal): number {
  const first = value.digits.search(/[1-9]/);
  return first < 0 ? 0 : value.point - 1 - first;
}

/** Drop a fraction's trailing zeros, and the point if nothing survives it. */
function trimTrailingZeros(text: string): string {
  const marker = text.search(/[eE]/);
  const head = marker < 0 ? text : text.slice(0, marker);
  if (!head.includes(".")) return text;
  return head.replace(/\.?0+$/, "") + (marker < 0 ? "" : text.slice(marker));
}

// --------------------------------------------------------------------------- //
// printf conversions                                                           //
// --------------------------------------------------------------------------- //

/** The magnitude's integer part, truncated toward zero as Python's `%d` is. */
function integerBody(value: Decimal): string {
  return value.digits.slice(0, value.point);
}

/** The magnitude with exactly `precision` digits after the point (`%f`). */
function fixedBody(value: Decimal, precision: number): string {
  const rounded = roundDecimal(value, precision);
  const whole = rounded.digits.slice(0, rounded.point);
  return precision > 0 ? `${whole}.${rounded.digits.slice(rounded.point)}` : whole;
}

/** The magnitude as `d.ddd<marker>[+-]dd` with `precision` fraction digits (`%e`). */
function scientificBody(value: Decimal, precision: number, marker: string): string {
  let exponent = exponentOf(value);
  const rounded = roundDecimal(value, precision - exponent);
  const carried = exponentOf(rounded) !== exponent;
  const first = rounded.digits.search(/[1-9]/);
  let significant: string;
  if (carried) {
    // Carrying out of the leading digit can only land on a power of ten
    // (9.99 at two digits is 1.0e+01), so the digits need no second rounding.
    exponent += 1;
    significant = "1".padEnd(precision + 1, "0");
  } else if (first < 0) {
    significant = "0".repeat(precision + 1); // the value is zero
  } else {
    significant = rounded.digits.slice(first, first + precision + 1);
  }
  const mantissa =
    precision > 0 ? `${significant.slice(0, 1)}.${significant.slice(1)}` : significant;
  const sign = exponent < 0 ? "-" : "+";
  return `${mantissa}${marker}${sign}${String(Math.abs(exponent)).padStart(2, "0")}`;
}

/** The magnitude per `%g`: `%e` or `%f` by exponent, trailing zeros dropped. */
function generalBody(value: Decimal, precision: number, trim: boolean, marker: string): string {
  // C reads a precision of 0 as 1, and picks the style from the exponent the
  // value has *after* rounding to that many significant digits: 999999.5 to six
  // digits is 1000000, so it prints as 1e+06 rather than 1000000.
  const significant = precision === 0 ? 1 : precision;
  const exponent = exponentOf(roundDecimal(value, significant - 1 - exponentOf(value)));
  const body =
    exponent < -4 || exponent >= significant
      ? scientificBody(value, significant - 1, marker)
      : fixedBody(value, significant - 1 - exponent);
  return trim ? trimTrailingZeros(body) : body;
}

/** Insert the decimal point the `#` flag keeps even when no fraction follows it. */
function withPoint(body: string): string {
  if (body.includes(".")) return body;
  const marker = body.search(/[eE]/);
  return marker < 0 ? `${body}.` : `${body.slice(0, marker)}.${body.slice(marker)}`;
}

/** Apply a field width: `-` left-justifies, `0` fills after the sign. */
function padTo(sign: string, body: string, flags: string, width: number): string {
  const text = sign + body;
  if (text.length >= width) return text;
  if (flags.includes("-")) return text.padEnd(width);
  if (flags.includes("0")) return sign + body.padStart(width - sign.length, "0");
  return text.padStart(width);
}

/** Flags, width, precision and conversion of a printf spec this mirror handles. */
const PRINTF = /^%([-+ 0#]*)(\d+)?(?:\.(\d+))?([dieEfFgG])$/;

/**
 * Format a number per an INDI printf-style format string.
 *
 * Mirrors the Python codec's `format_number` (including libindi-faithful field
 * padding for `%m`, and that function's strip of the printf result, which is
 * why a space-padded width never shows); trim the result for display when the
 * `%m` alignment padding is not wanted.
 */
export function formatNumber(value: number, format?: string | null): string {
  if (!format) return String(value);
  const trimmed = format.trim();
  const sexa = /^%(\d+)\.(\d+)m$/.exec(trimmed);
  if (sexa) return formatSexagesimal(value, Number(sexa[1]), Number(sexa[2]));
  const printf = PRINTF.exec(trimmed);
  // Infinities and NaN cannot arrive over JSON, so rather than mirror Python's
  // spellings for them the plain fallback keeps the conversions total.
  if (printf === null || !Number.isFinite(value)) return String(value);

  const flags = printf[1] ?? "";
  const width = printf[2] === undefined ? 0 : Number(printf[2]);
  const precision = printf[3] === undefined ? undefined : Number(printf[3]);
  const conversion = printf[4];
  const alt = flags.includes("#");
  const decimal = toDecimal(value);

  const integral = conversion === "d" || conversion === "i";
  let body: string;
  switch (conversion) {
    case "d":
    case "i":
      body = integerBody(decimal);
      break;
    case "e":
    case "E":
      body = scientificBody(decimal, precision ?? 6, conversion);
      break;
    case "g":
    case "G":
      body = generalBody(decimal, precision ?? 6, !alt, conversion === "g" ? "e" : "E");
      break;
    default: // "f"/"F": the only conversions the pattern still allows.
      body = fixedBody(decimal, precision ?? 6);
  }
  // A precision means digits after the point everywhere except %d/%i, where it
  // is the minimum number of digits; `#` keeps a point no fraction follows.
  if (integral) body = body.padStart(precision ?? 0, "0");
  else if (alt) body = withPoint(body);

  // A truncated %d loses the sign along with the fraction (-0.4 is '0'), while
  // %f, %e and %g keep it (-0.0 is '-0.00'), matching C and Python.
  const negative = decimal.negative && !(integral && !/[1-9]/.test(body));
  const sign = negative ? "-" : flags.includes("+") ? "+" : flags.includes(" ") ? " " : "";
  // `format_number` strips its printf result, so a space-padded width never
  // reaches the wire and a zero-padded one does. Strip here too or they differ.
  return padTo(sign, body, flags, width).trim();
}
