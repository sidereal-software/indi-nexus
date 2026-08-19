/**
 * Hand-authored TypeScript mirror of `indikit.protocol.models`.
 *
 * This is the browser side of the wire contract. The bridge serialises the same
 * Pydantic models to JSON, so these interfaces must stay structurally identical to
 * the Python models. The INDI 1.7 protocol is frozen, so the surface here is small
 * and stable; there is deliberately no codegen step.
 *
 * Notes
 * -----
 * - A *vector* is the canonical in-memory shape of a property, discriminated on
 *   `kind`. Messages (`def`/`set`/`new`/...) are thin wrappers discriminated on
 *   `tag`, exactly as on the Python side.
 * - Element metadata (a number's `min`/`max`/`format`, a switch vector's `rule`)
 *   is only present on a `def`; a `set`/`new` carries just `name` + value. That is
 *   why those fields are optional here.
 * - BLOB payloads travel as a base64 `string` in the **standard** alphabet
 *   (RFC 4648 section 4, `+` and `/`), which the Python `BLOB` model pins with a
 *   field serializer. That is the alphabet `atob` and a `data:...;base64,` URL
 *   accept; the URL-safe one they reject outright, which is what a download link
 *   built from `data` depends on.
 */

import type { BLOBPolicy, IPerm, IPState, ISRule, ISState } from "./enums";

/** An ISO-8601 timestamp string, as emitted by Pydantic's JSON serialiser. */
export type Timestamp = string;

// --------------------------------------------------------------------------- //
// Elements                                                                     //
// --------------------------------------------------------------------------- //
/** A single numeric element (`defNumber` / `oneNumber`). */
export interface NumberElement {
  kind: "number";
  name: string;
  label?: string | null;
  format?: string;
  min?: number | null;
  max?: number | null;
  step?: number | null;
  value: number;
}

/** A single text element (`defText` / `oneText`). */
export interface TextElement {
  kind: "text";
  name: string;
  label?: string | null;
  value: string;
}

/** A single switch element (`defSwitch` / `oneSwitch`). */
export interface SwitchElement {
  kind: "switch";
  name: string;
  label?: string | null;
  value: ISState;
}

/** A single light element (`defLight` / `oneLight`); read-only status. */
export interface LightElement {
  kind: "light";
  name: string;
  label?: string | null;
  value: IPState;
}

/** A single BLOB element (`defBLOB` / `oneBLOB`); `data` is standard base64. */
export interface BlobElement {
  kind: "blob";
  name: string;
  label?: string | null;
  format?: string | null;
  size?: number | null;
  data?: string | null;
}

/** Any property element, discriminated on `kind`. */
export type IndiElement = NumberElement | TextElement | SwitchElement | LightElement | BlobElement;

// --------------------------------------------------------------------------- //
// Vectors                                                                      //
// --------------------------------------------------------------------------- //
/** Fields shared by every property vector. */
interface VectorBase {
  device: string;
  name: string;
  label?: string | null;
  group?: string | null;
  state: IPState;
  timeout?: number | null;
  timestamp?: Timestamp | null;
  message?: string | null;
}

/** A vector of numeric elements. */
export interface NumberVector extends VectorBase {
  kind: "number";
  perm: IPerm;
  elements: NumberElement[];
}

/** A vector of text elements. */
export interface TextVector extends VectorBase {
  kind: "text";
  perm: IPerm;
  elements: TextElement[];
}

/** A vector of switch elements with a selection `rule`. */
export interface SwitchVector extends VectorBase {
  kind: "switch";
  perm: IPerm;
  rule: ISRule;
  elements: SwitchElement[];
}

/** A vector of read-only light elements (lights carry no `perm`). */
export interface LightVector extends VectorBase {
  kind: "light";
  elements: LightElement[];
}

/** A vector of BLOB elements (binary payloads). */
export interface BlobVector extends VectorBase {
  kind: "blob";
  perm: IPerm;
  elements: BlobElement[];
}

/** Any property vector, discriminated on `kind`. */
export type Vector = NumberVector | TextVector | SwitchVector | LightVector | BlobVector;

/** The `kind` discriminator shared by a vector and its elements. */
export type VectorKind = Vector["kind"];

// --------------------------------------------------------------------------- //
// Messages                                                                     //
// --------------------------------------------------------------------------- //
/** A property definition (device -> client). */
export interface DefVector {
  tag: "def";
  vector: Vector;
}

/** A value update to an already-defined property (device -> client). */
export interface SetVector {
  tag: "set";
  vector: Vector;
  /**
   * Whether the wire message actually carried a `state`.
   *
   * `state` is `#IMPLIED` on every `set*Vector` (white paper p.7) and means "no
   * change if absent", so a `set` without one must leave the cached state
   * alone. The vector's own `state` is never absent - the parser fills it with
   * the model default - which is why the fact rides on the message instead, as
   * `SetVector.state_present` does on the Python side. Absent here (an older
   * bridge, or a frame built by hand) means the state was carried.
   */
  state_present?: boolean;
}

/** A client's request to change a property's value (client -> device). */
export interface NewVector {
  tag: "new";
  vector: Vector;
}

/** Client -> device/server request to enumerate properties. */
export interface GetProperties {
  tag: "getProperties";
  version?: string;
  device?: string | null;
  name?: string | null;
}

/** Notification that a property (or a whole device) has gone away. */
export interface DelProperty {
  tag: "delProperty";
  device: string;
  name?: string | null;
  timestamp?: Timestamp | null;
  message?: string | null;
}

/** A free-form log/notification message. */
export interface Message {
  tag: "message";
  device?: string | null;
  timestamp?: Timestamp | null;
  message: string;
}

/** Client -> server request controlling BLOB delivery. */
export interface EnableBlob {
  tag: "enableBLOB";
  device: string;
  name?: string | null;
  policy: BLOBPolicy;
}

/** Any INDI wire message, discriminated on `tag`. */
export type IndiMessage =
  | DefVector
  | SetVector
  | NewVector
  | GetProperties
  | DelProperty
  | Message
  | EnableBlob;

/**
 * The version of the browser JSON contract this build is written against.
 *
 * Compared with the `protocol` a {@link HelloFrame} announces. It versions the
 * bridge<->browser contract only, and has nothing to do with INDI's own frozen
 * 1.7 `version` attribute. Bumped **only** on a breaking change - a field
 * removed, renamed, or given a new meaning - because a client that ignores an
 * unknown key is already handling an additive change correctly. Mirrors
 * `BRIDGE_PROTOCOL_VERSION` in `indikit/web/control_frames.py`.
 */
export const CLIENT_PROTOCOL_VERSION = 1;

/**
 * The first frame on every bridge socket: what this browser is talking to.
 *
 * Sent ahead of the seeded property definitions, so the contract version is
 * known before anything written in that contract has to be interpreted. A
 * client that never sees one is talking to a bridge older than the frame, which
 * is not an error: see `ConnectionState.protocol`.
 */
export interface HelloFrame {
  event: "hello";
  /** The bridge's contract version; compare with {@link CLIENT_PROTOCOL_VERSION}. */
  protocol: number;
  /** The INDIkit version serving this socket, for display and bug reports. */
  server: string;
}

/**
 * The non-INDI frame the bridge emits for upstream connection state.
 *
 * The INDI protocol has no message for "the hub connected/disconnected", but the
 * UI needs it, so the bridge sends this small control frame (see
 * `indikit.web.bridge.Bridge.connection_frame`).
 */
export interface ConnectionFrame {
  event: "connection";
  connected: boolean;
}

/**
 * The bridge's report that a frame this browser sent did not go upstream.
 *
 * Sent only to the browser that sent the frame, and never for something the
 * bridge accepted. The socket stays open. Silence would be worse than the
 * frame: a write that is refused (no upstream connection, a full outbox, a
 * message kind a client may not send) is not retried anywhere, so a browser
 * that hears nothing has no reason not to believe it landed.
 */
export interface ErrorFrame {
  event: "error";
  /** A stable machine-readable reason, e.g. `not_connected`. */
  code: string;
  /** Human-readable detail, suitable for a UI log. */
  message: string;
  /** The rejected message's INDI tag, or `null` if it did not parse. */
  tag?: string | null;
}

/**
 * Any bridge control frame, discriminated on `event`.
 *
 * The mirror of `BridgeFrame` in `indikit/web/control_frames.py`. An `event`
 * this build does not know is dropped rather than coerced, which is what makes
 * the bridge free to add one without breaking an older browser.
 */
export type BridgeFrame = HelloFrame | ConnectionFrame | ErrorFrame;

/** Return the element with a given name, or `undefined`. */
export function elementByName(vector: Vector, name: string): IndiElement | undefined {
  return vector.elements.find((element) => element.name === name);
}
