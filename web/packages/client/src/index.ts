/**
 * `@indi-nexus/client` - a framework-agnostic TypeScript client and typed property
 * store for the INDINexus web bridge.
 *
 * This is the transport + cache layer shared by any frontend: it speaks the JSON
 * wire contract, mirrors bridge state into a {@link PropertyStore}, and exposes a
 * small watch/send API ({@link IndiClient}). It has no framework or UI dependency;
 * `@indi-nexus/react` builds hooks and components on top of it.
 */

export type {
  ConnectionCallback,
  ConnectionState,
  IndiClientOptions,
  MessageCallback,
  Predicate,
  SwitchInput,
} from "./client";
// The client.
export { IndiClient } from "./client";
export type {
  ConnectionHandlers,
  ConnectionOptions,
  WebSocketFactory,
  WebSocketLike,
} from "./connection";
// Reconnecting connection.
export { ReconnectingConnection } from "./connection";
// Enums (values + their string-literal types) and helpers.
export { BLOBPolicy, IPerm, IPState, ISRule, ISState, isWritable } from "./enums";
export type {
  DeviceSnapshot,
  EventType,
  PropertyEvent,
  Subscriber,
  SubscriptionFilter,
} from "./store";
// Property store.
export { PropertyStore } from "./store";
export type {
  BlobElement,
  BlobVector,
  ConnectionFrame,
  DefVector,
  DelProperty,
  EnableBlob,
  GetProperties,
  IndiElement,
  IndiMessage,
  LightElement,
  LightVector,
  Message,
  NewVector,
  NumberElement,
  NumberVector,
  SetVector,
  SwitchElement,
  SwitchVector,
  TextElement,
  TextVector,
  Timestamp,
  Vector,
  VectorKind,
} from "./types";
// Wire types.
export { elementByName } from "./types";
