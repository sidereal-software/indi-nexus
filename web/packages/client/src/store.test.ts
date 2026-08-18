/** Tests for the client-side {@link PropertyStore} cache and subscriptions. */

import { describe, expect, it } from "vitest";
import { type PropertyEvent, PropertyStore } from "./store";
import type {
  BlobVector,
  DefVector,
  DelProperty,
  IndiElement,
  NumberVector,
  SetVector,
} from "./types";

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

  // Deleting the last property leaves the device present and empty. That is
  // where a driver defining its properties on connect sits while disconnected,
  // and it is not the same as the device being gone - which is what an unnamed
  // delProperty means, and the only thing that drops a device. The panel has to
  // be able to tell them apart. Same rule in client/store.py and debug.html.
  it("removes one named property and keeps the now-empty device", () => {
    const store = new PropertyStore();
    store.apply(def(numVec()));
    const del: DelProperty = { tag: "delProperty", device: "CCD", name: "EXPOSURE" };
    const event = store.apply(del);

    expect(event?.type).toBe("del");
    expect(store.get("CCD", "EXPOSURE")).toBeUndefined();
    expect(store.devices()).toEqual(["CCD"]);
    expect(store.device("CCD")).toEqual({});
  });

  it("carries a deletion's message and timestamp onto the event", () => {
    const store = new PropertyStore();
    store.apply(def(numVec()));
    const event = store.apply({
      tag: "delProperty",
      device: "CCD",
      name: "EXPOSURE",
      timestamp: "2026-08-14T12:30:00",
      message: "only while connected",
    });

    // A del has no vector to carry them on, and the text is the only account of
    // why the property went away.
    expect(event?.message).toBe("only while connected");
    expect(event?.timestamp).toBe("2026-08-14T12:30:00");
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

describe("PropertyStore BLOB merging", () => {
  /**
   * A CCD image vector, with or without a payload, as the bridge sends it.
   *
   * A `def` declares the format and carries no bytes; a `set` carries the bytes
   * and usually no format, which is what makes the merge worth testing.
   */
  function blobVec(
    data: string | null = null,
    state: BlobVector["state"] = "Idle",
    format: string | null = null,
  ): BlobVector {
    return {
      kind: "blob",
      device: "CCD",
      name: "CCD1",
      state,
      perm: "ro",
      elements: [
        {
          kind: "blob",
          name: "image",
          format: data === null ? ".fits" : format,
          size: data === null ? null : 5,
          data,
        },
      ],
    };
  }

  const defBlob = (vector: BlobVector): DefVector => ({ tag: "def", vector });
  const setBlob = (vector: BlobVector): SetVector => ({ tag: "set", vector });

  it("merges a payload onto the definition and keeps the defined format", () => {
    const store = new PropertyStore();
    store.apply(defBlob(blobVec()));

    // A setBLOBVector carries the payload; the format was declared on the def.
    store.apply(setBlob(blobVec("YXN0cm8=", "Ok")));

    const cached = store.get("CCD", "CCD1") as BlobVector;
    expect(cached.elements[0]?.data).toBe("YXN0cm8=");
    expect(cached.elements[0]?.size).toBe(5);
    expect(cached.elements[0]?.format).toBe(".fits");
    expect(cached.state).toBe("Ok");
  });

  it("leaves the payload as base64 rather than decoding it", () => {
    // The store is a cache, not a decoder: a `data:` URL and `atob` both want
    // the string, and decoding here would make every frame cost a copy nobody
    // asked for. Pinned because it is the contract the React components read.
    const store = new PropertyStore();
    store.apply(defBlob(blobVec()));
    store.apply(setBlob(blobVec("YXN0cm8=", "Ok")));

    const cached = store.get("CCD", "CCD1") as BlobVector;
    expect(typeof cached.elements[0]?.data).toBe("string");
  });

  it("takes a later frame's format when the driver changes it", () => {
    // A CCD switches between .fits and .fits.fz when compression is toggled, and
    // the format is the only thing telling a browser what it just received.
    const store = new PropertyStore();
    store.apply(defBlob(blobVec()));
    store.apply(setBlob(blobVec("YXN0cm8=", "Ok")));

    store.apply(setBlob(blobVec("YXN0cm8=", "Ok", ".fits.fz")));

    expect((store.get("CCD", "CCD1") as BlobVector).elements[0]?.format).toBe(".fits.fz");
  });

  it("returns to the plain format when compression is turned back off", () => {
    // The other direction, which the test above cannot state: compression is a
    // switch a client flips both ways mid-session, and a cached `.fits.fz` left
    // over from when it was on tells the browser to hand an ordinary FITS frame
    // to an fpack decoder. Every frame carries its own format, so the last one
    // always wins - including when the last one is the plain format again.
    const store = new PropertyStore();
    store.apply(defBlob(blobVec()));
    store.apply(setBlob(blobVec("YXN0cm8=", "Ok", ".fits")));
    store.apply(setBlob(blobVec("YXN0cm8=", "Ok", ".fits.fz")));

    store.apply(setBlob(blobVec("YXN0cm8=", "Ok", ".fits")));

    expect((store.get("CCD", "CCD1") as BlobVector).elements[0]?.format).toBe(".fits");
  });

  it("replaces the cached frame rather than accumulating frames", () => {
    const store = new PropertyStore();
    store.apply(defBlob(blobVec()));
    store.apply(setBlob(blobVec("Zmlyc3Q=", "Ok")));
    store.apply(setBlob(blobVec("c2Vjb25k", "Ok")));

    const cached = store.get("CCD", "CCD1") as BlobVector;
    expect(cached.elements).toHaveLength(1);
    expect(cached.elements[0]?.data).toBe("c2Vjb25k");
  });

  it("returns a new vector so a re-render is triggered by the new frame", () => {
    // The whole store is immutable by design: React subscribers re-render on
    // reference change, so merging a frame in place would deliver an image no
    // component ever noticed had arrived.
    const store = new PropertyStore();
    store.apply(defBlob(blobVec()));
    const before = store.get("CCD", "CCD1");

    store.apply(setBlob(blobVec("YXN0cm8=", "Ok")));

    const after = store.get("CCD", "CCD1") as BlobVector;
    expect(after).not.toBe(before);
    expect((before as BlobVector).elements[0]?.data).toBeNull();
  });

  it("ignores a set whose element is not a BLOB", () => {
    // Kind confusion between a def and a set is a bridge bug, and taking the
    // value would leave `data` holding a number for every later reader.
    const store = new PropertyStore();
    store.apply(defBlob(blobVec()));

    const wrong = blobVec("YXN0cm8=", "Ok");
    (wrong.elements as unknown as IndiElement[])[0] = {
      kind: "number",
      name: "image",
      format: "%g",
      value: 7,
    };
    store.apply(setBlob(wrong));

    const cached = store.get("CCD", "CCD1") as BlobVector;
    expect(cached.elements[0]?.kind).toBe("blob");
    expect(cached.elements[0]?.data).toBeNull();
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

  // A whole-device del names no property because it takes all of them, so
  // matching its (absent) name against the filter literally silenced exactly
  // the watchers with the most to lose. Same rule in client/store.py.
  it("delivers a whole-device del to name-filtered subscribers too", () => {
    const store = new PropertyStore();
    store.subscribe(() => {}, { device: "CCD", name: "EXPOSURE" });
    store.subscribe(() => {}, { device: "Mount", name: "EXPOSURE" });

    const event: PropertyEvent = { type: "del", device: "CCD", name: null, vector: null };
    expect(store.matching(event)).toHaveLength(1); // the CCD watcher, not Mount's
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
