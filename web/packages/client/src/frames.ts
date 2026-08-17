/**
 * The guard between a decoded wire frame and the property store.
 *
 * The Python side refuses two things at the point a message is built, and the
 * browser has to refuse them at the point one is decoded, because a frame can
 * reach a browser without ever having passed through the Python parser - a
 * bridge in front of another server, a hand-built frame in a test, a driver
 * emitting JSON directly.
 *
 * - **A missing `device` (or `name` where the model requires one) drops the
 *   frame.** `_required` in `protocol/xml.py` puts it this way: `""` is not a
 *   degraded device, it is an invented one, and it used to land in the cache as
 *   a phantom device called `""` holding properties nothing would ever update.
 * - **A non-finite number drops the frame.** `Number.value` is
 *   `allow_inf_nan=False`, so `from_json` rejects a message carrying one, and
 *   this is the same codec boundary. JSON has no literal for NaN or the
 *   infinities (`JSON.parse("NaN")` throws), so on the wire they arrive as
 *   `null` or as the strings `"NaN"`/`"Infinity"` depending on the producer;
 *   any of those in a `value` would end up rendered as `NaN` in a control, or
 *   sent straight back to an instrument.
 *
 * The optional numeric metadata - a number's `min`/`max`/`step`, a vector's
 * `timeout` - *can* say "absent", so a non-finite one degrades to `null` rather
 * than costing the frame, exactly as `_optfloat` does. Dropping a `def` over a
 * junk `min` would leave the client permanently blind to that property, which
 * is the failure that rule exists to avoid.
 */

import type { IndiMessage, Vector } from "./types";

/** Whether a `#REQUIRED` identifier is really there. */
function isNamed(value: unknown): value is string {
  return typeof value === "string" && value !== "";
}

/** Whether a value is a real, finite number (not `null`, `"NaN"` or `Infinity`). */
function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * Whether a vector may enter the cache, degrading its optional numbers.
 *
 * Mutates only to degrade, and only what the model can express as absent. The
 * caller owns the frame outright - it is the result of its own `JSON.parse` and
 * has not been handed to the store yet - so there is nothing else holding a
 * reference to observe the change.
 */
function acceptVector(vector: Vector | undefined): boolean {
  // The parameter is typed, but the frame is not: it came from `JSON.parse` and
  // was cast. A vector-less `def` reaching the store crashes the merge - or the
  // renderer, one frame later - so it is dropped here with the rest.
  if (vector == null || !Array.isArray(vector.elements)) return false;
  if (!isNamed(vector.device) || !isNamed(vector.name)) return false;
  if (vector.timeout != null && !isFiniteNumber(vector.timeout)) vector.timeout = null;
  if (vector.kind !== "number") return true;
  for (const element of vector.elements) {
    if (!isFiniteNumber(element.value)) return false;
    for (const key of ["min", "max", "step"] as const) {
      if (element[key] != null && !isFiniteNumber(element[key])) element[key] = null;
    }
  }
  return true;
}

/**
 * Whether a decoded frame may be folded into the store.
 *
 * A frame this rejects is dropped whole, the way `from_json` rejects a message
 * it cannot represent and the way the client already drops JSON that is not an
 * object at all.
 *
 * @param message - A frame decoded from the bridge, not yet applied.
 * @returns `false` if the frame must be dropped.
 */
export function acceptFrame(message: IndiMessage): boolean {
  switch (message.tag) {
    case "def":
    case "set":
    case "new":
      return acceptVector(message.vector);
    case "delProperty":
    case "enableBLOB":
      // `device` is required on both models; `name` is the optional half of a
      // delProperty (absent means the whole device) and of an enableBLOB.
      return isNamed(message.device);
    default:
      // getProperties and message carry no required identifier: an absent
      // device on either means "all devices", which is a real value.
      return true;
  }
}
