/** Tests for the client-side {@link PropertyStore} cache and subscriptions. */

import { describe, expect, it } from "vitest";
import { type PropertyEvent, PropertyStore } from "./store";
import type { DefVector, DelProperty, NumberVector, SetVector } from "./types";

function numVec(value = 1.0, state: NumberVector["state"] = "Idle"): NumberVector {
  return {
    kind: "number",
    device: "CCD",
    name: "EXPOSURE",
    state,
    perm: "rw",
    elements: [{ kind: "number", name: "secs", format: "%.2f", min: 0, max: 3600, value }],
  };
}

const def = (vector: NumberVector): DefVector => ({ tag: "def", vector });
const set = (vector: NumberVector): SetVector => ({ tag: "set", vector });
/** A `set` whose wire message carried no `state`, as the XML parser reports it. */
const statelessSet = (vector: NumberVector): SetVector => ({
  tag: "set",
  vector,
  state_present: false,
});

describe("PropertyStore.apply", () => {
  it("caches the full vector on def", () => {
    const store = new PropertyStore();
    const event = store.apply(def(numVec()));

    expect(event?.type).toBe("def");
    expect(store.get("CCD", "EXPOSURE")).toBeDefined();
    expect(store.devices()).toEqual(["CCD"]);
  });

  it("merges value and state onto the def, preserving metadata", () => {
    const store = new PropertyStore();
    store.apply(def(numVec(1.0)));
    const event = store.apply(set(numVec(2.5, "Ok")));

    expect(event?.type).toBe("set");
    const cached = store.get("CCD", "EXPOSURE") as NumberVector;
    expect(cached.elements[0]?.value).toBe(2.5);
    expect(cached.state).toBe("Ok");
    // Metadata from the def is preserved (a set does not carry it).
    expect(cached.elements[0]?.max).toBe(3600);
  });

  it("keeps a cached Busy when the set carried no state", () => {
    const store = new PropertyStore();
    store.apply(def(numVec(1.0, "Busy")));

    // The parser fills the absent attribute with the model default, so the
    // vector says Idle; `state_present` is what says not to believe it.
    store.apply(statelessSet(numVec(7.0, "Idle")));

    const cached = store.get("CCD", "EXPOSURE") as NumberVector;
    expect(cached.state).toBe("Busy");
    expect(cached.elements[0]?.value).toBe(7.0);
  });

  it("keeps a latched Alert when the set carried no state", () => {
    const store = new PropertyStore();
    store.apply(def(numVec(1.0, "Alert")));

    store.apply(statelessSet(numVec(7.0, "Idle")));

    const cached = store.get("CCD", "EXPOSURE") as NumberVector;
    expect(cached.state).toBe("Alert");
    expect(cached.elements[0]?.value).toBe(7.0);
  });

  it("still applies a state the set did carry", () => {
    const store = new PropertyStore();
    store.apply(def(numVec(1.0, "Alert")));

    store.apply({ tag: "set", vector: numVec(7.0, "Ok"), state_present: true });

    const cached = store.get("CCD", "EXPOSURE") as NumberVector;
    expect(cached.state).toBe("Ok");
    expect(cached.elements[0]?.value).toBe(7.0);
  });

  it("treats a set with no state_present flag as carrying its state", () => {
    // A bridge older than the flag omits it and always sends its merged state.
    const store = new PropertyStore();
    store.apply(def(numVec(1.0, "Alert")));

    store.apply(set(numVec(7.0, "Ok")));

    const cached = store.get("CCD", "EXPOSURE") as NumberVector;
    expect(cached.state).toBe("Ok");
    expect(cached.elements[0]?.value).toBe(7.0);
  });

  it("ignores a set before its def", () => {
    const store = new PropertyStore();
    expect(store.apply(set(numVec()))).toBeNull();
    expect(store.get("CCD", "EXPOSURE")).toBeUndefined();
  });

  it("removes one named property (and the now-empty device)", () => {
    const store = new PropertyStore();
    store.apply(def(numVec()));
    const del: DelProperty = { tag: "delProperty", device: "CCD", name: "EXPOSURE" };
    const event = store.apply(del);

    expect(event?.type).toBe("del");
    expect(store.get("CCD", "EXPOSURE")).toBeUndefined();
    expect(store.devices()).toEqual([]);
  });

  it("removes a whole device when no name is given", () => {
    const store = new PropertyStore();
    store.apply(def(numVec()));
    const event = store.apply({ tag: "delProperty", device: "CCD" });

    expect(event?.type).toBe("del");
    expect(event?.name).toBeNull();
    expect(store.devices()).toEqual([]);
  });

  it("returns null deleting something not cached", () => {
    const store = new PropertyStore();
    expect(store.apply({ tag: "delProperty", device: "CCD", name: "EXPOSURE" })).toBeNull();
  });

  it("ignores a non-property message", () => {
    const store = new PropertyStore();
    expect(store.apply({ tag: "message", device: "CCD", message: "hi" })).toBeNull();
  });
});

describe("PropertyStore immutability (for React referential stability)", () => {
  it("replaces the vector object on a merge and keeps unrelated snapshots stable", () => {
    const store = new PropertyStore();
    store.apply(def(numVec(1.0)));
    const before = store.get("CCD", "EXPOSURE");
    const deviceBefore = store.device("CCD");

    store.apply(set(numVec(2.5, "Ok")));
    const after = store.get("CCD", "EXPOSURE");

    // The merged vector (and its device snapshot) are new references...
    expect(after).not.toBe(before);
    expect(store.device("CCD")).not.toBe(deviceBefore);
    // ...but reading the same state twice yields the same reference.
    expect(store.device("CCD")).toBe(store.device("CCD"));
  });

  it("replaces the vector object even when the set carried no state", () => {
    const store = new PropertyStore();
    store.apply(def(numVec(1.0, "Busy")));
    const before = store.get("CCD", "EXPOSURE");

    store.apply(statelessSet(numVec(7.0, "Idle")));

    // Carrying the state over must not turn the merge into a mutation, or React
    // would never see the new value.
    expect(store.get("CCD", "EXPOSURE")).not.toBe(before);
    expect((before as NumberVector).elements[0]?.value).toBe(1.0);
  });

  it("returns a stable empty snapshot for unknown devices", () => {
    const store = new PropertyStore();
    expect(store.device("nope")).toBe(store.device("nope"));
    expect(store.device("nope")).toEqual({});
  });
});

describe("PropertyStore subscriptions", () => {
  it("matches by device and name", () => {
    const store = new PropertyStore();
    store.subscribe(() => {}, { device: "CCD", name: "EXPOSURE" });
    store.subscribe(() => {}, { device: "Mount" });
    store.subscribe(() => {}); // wildcard

    const event: PropertyEvent = { type: "set", device: "CCD", name: "EXPOSURE", vector: null };
    expect(store.matching(event)).toHaveLength(2); // exact + wildcard, not Mount
  });

  it("stops delivery after unsubscribe", () => {
    const store = new PropertyStore();
    const unsubscribe = store.subscribe(() => {});
    const event: PropertyEvent = { type: "def", device: "CCD", name: "EXPOSURE", vector: null };
    expect(store.matching(event)).toHaveLength(1);
    unsubscribe();
    expect(store.matching(event)).toEqual([]);
  });
});
