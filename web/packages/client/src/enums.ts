/**
 * INDI protocol enumerations.
 *
 * These mirror `indi_nexus.protocol.enums` on the Python side. Each is a frozen
 * object whose members equal their exact INDI wire token (so `IPState.Ok === "Ok"`),
 * paired with a string-literal type of the same name - the TypeScript equivalent of
 * Python's `StrEnum`. Because the protocol is INDI 1.7 (frozen), these are hand
 * maintained rather than generated.
 */

/** State of a vector property (the coloured status light in a GUI). */
export const IPState = {
  Idle: "Idle",
  Ok: "Ok",
  Busy: "Busy",
  Alert: "Alert",
} as const;
export type IPState = (typeof IPState)[keyof typeof IPState];

/** Client access permission for a vector property. */
export const IPerm = {
  ro: "ro",
  wo: "wo",
  rw: "rw",
} as const;
export type IPerm = (typeof IPerm)[keyof typeof IPerm];

/** Constraint on how many switches in a switch vector may be On. */
export const ISRule = {
  OneOfMany: "OneOfMany",
  AtMostOne: "AtMostOne",
  AnyOfMany: "AnyOfMany",
} as const;
export type ISRule = (typeof ISRule)[keyof typeof ISRule];

/** On/Off state of a single switch. */
export const ISState = {
  Off: "Off",
  On: "On",
} as const;
export type ISState = (typeof ISState)[keyof typeof ISState];

/** How `indiserver` should deliver BLOBs to a client. */
export const BLOBPolicy = {
  Never: "Never",
  Also: "Also",
  Only: "Only",
} as const;
export type BLOBPolicy = (typeof BLOBPolicy)[keyof typeof BLOBPolicy];

/** Whether a permission string grants write access (`rw`/`wo`). */
export function isWritable(perm: IPerm | undefined): boolean {
  return perm === IPerm.rw || perm === IPerm.wo;
}
