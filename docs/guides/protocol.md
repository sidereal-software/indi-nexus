---
search:
  boost: 2
---

# Protocol concepts

You do not need this page to write a driver - the [driver guide](writing-drivers.md)
covers the vocabulary you use. Read this when you want to know what is happening on the
wire.

## XML to indiserver, JSON to browsers

INDINexus speaks canonical INDI 1.7 XML to `indiserver`, which is what every other INDI
program expects, and JSON to browsers.

Both encodings come from the same Python model, so they cannot drift apart. The INDI
messages a frontend receives are the protocol itself rather than a summary of it.

Three frames on that WebSocket are **not** INDI, because the protocol has no message for
any of them and a UI needs all three. They are objects with an `event` key instead of a
`tag`, and they are modelled in
[`indi_nexus.web.control_frames`](../reference/python/web.md#control-frames):

| Frame | Means |
|---|---|
| `{"event": "hello", "protocol": 1, "server": "0.2.0"}` | the first frame on every socket: which version of *this* contract the bridge speaks, and which INDINexus release is serving it. |
| `{"event": "connection", "connected": false}` | whether the *bridge* is connected to `indiserver`. Distinct from whether your browser is connected to the bridge. |
| `{"event": "error", "code": ..., "message": ..., "tag": ...}` | a frame this browser sent did not go upstream - malformed, not something a client may send, or refused because the upstream was down or busy. It is sent only to the browser that sent the frame. |

Write a frame reader that **skips an `event` it does not recognise** rather than treating
it as a protocol violation, since that is where any future control frame will arrive.
`@indi-nexus/client` already does both: it surfaces the connection state and the protocol
version, routes the error into the message log, and drops anything else.

### Versioning the browser contract

`protocol` versions the bridge-to-browser JSON only. INDI's own `version` attribute is frozen
at 1.7 and has nothing to do with it.

It is bumped **only on a breaking change** - a field removed, renamed, or given a new
meaning. Adding an optional field does not bump it, because a client that ignores an
unknown key is already handling that correctly. So a mismatch is never fatal in either
direction, and nothing in INDINexus refuses a socket over one: `@indi-nexus/client`
compares the number against its own `CLIENT_PROTOCOL_VERSION`, writes one line into the
message log when they differ, and carries on. Turning a version skew into a dark panel
mid-session helps no one at a telescope.

A bridge older than the hello frame simply never sends one. A client should treat **the
first frame that is not a `hello`** as the answer - `@indi-nexus/client` records
`protocol: 0` at that point - rather than waiting for a `def` that may never come, since
with the upstream down and the cache empty the first frame is the connection frame.

## def, set, new

Three things can be said about a property, and they share one shape:

| Message | Direction | Means |
|---|---|---|
| **def** | driver → client | "this property exists" - with all the metadata: labels, formats, ranges, the switch rule |
| **set** | driver → client | "its values changed" - just names and values |
| **new** | client → driver | "please change it" - also just names and values |

Because `set` and `new` carry no metadata, a client keeps the `def` and merges later `set`
messages onto it. INDINexus does this for you on both sides.

The consequence for driver authors is that a `new` usually names only the elements the
client changed. Clicking one radio button sends only that button. Handler code therefore
uses

```python
vector.selected()             # which switch did they turn on?
vector.get(name, default)     # what value did they send, if any?
```

rather than indexing into elements that may not be there.

## Numbers and sexagesimal

Number elements carry a printf-style `format`. Alongside the usual `%.2f` forms, INDI
defines `%m` for sexagesimal - the `hh:mm:ss` notation used for right ascension and
declination. `%9.6m` means "nine characters wide, showing degrees, minutes and seconds".

Both the Python codec and its TypeScript mirror *write* `%m` exactly as libindi does, down
to the field padding and the half-away-from-zero rounding, so coordinates round-trip to
existing INDI software unchanged.

Reading is where INDINexus is deliberately more permissive. libindi accepts sexagesimal on
a `def` but reads a `set` with `std::stod`, so a value of `10:30:00` in a `setNumberVector`
arrives there as `10.0`. INDINexus parses sexagesimal on both, which is a strict superset:
anything libindi reads correctly, we read the same way. Do not "fix" that to match - it
would turn a coordinate into a silently wrong number.

## Messages and BLOBs

`message` is a timestamped log line from a device - what `self.message()` sends, and what
a UI's log panel shows.

BLOBs carry binary payloads, typically a FITS image. They can be large, so `indiserver`
does not send them to a client until that client explicitly asks with `enableBLOB`. The
Python and TypeScript clients both expose this as `enable_blob` / `enableBlob`.

In JSON the payload is a base64 string in the **standard** alphabet (`+` and `/`), so
`atob` and a `data:application/octet-stream;base64,...` URL both accept it as it arrives.

### Compressed payloads

A BLOB's `format` is a chain of file-name suffixes saying what the bytes are. A trailing
`.z` is not part of that: it says the payload was deflated (zlib, RFC 1950) for the wire.

**INDINexus inflates those on receipt**, in both codecs. By the time a payload reaches you -
a Python `IndiClient` subscriber, a driver's `@on_new`, or a browser over the WebSocket -
it is the file itself: the `.z` is gone from `format`, and `size` is the inflated length.
A consumer sees `.fits`, never `.fits.z`. libindi inflates in every client built on it, so
code written against KStars behaviour sees the same thing here.

| `format` on the wire | What a consumer gets |
|---|---|
| `.fits` | `.fits`, untouched |
| `.fits.z` | `.fits`, inflated, `size` set to the inflated length |
| `.fits.fz` | `.fits.fz`, byte-identical |

A bare `.z` describes the encoding and nothing else, so it arrives with no `format` at all
rather than an empty one.

**`.fits.fz` is deliberately left alone.** That suffix is fpack, FITS *tile* compression:
an astronomy format living inside the FITS container, not a transport encoding. No libindi
client undoes it, undoing it would need cfitsio, and a FITS reader handles it natively.

A payload that declares `.z` and will not inflate **costs the message**. It is dropped and
counted like any other malformed leaf value, the same as a `oneNumber` full of junk. The
compressed bytes are never delivered instead - a caller that asked for a `.fits` would hand
them to a FITS reader.

Compressing on **send** is not implemented, and that is deliberate: it is the driver
author's decision, as it is in libindi, whose `CCD_COMPRESSION` switch defaults to off. A
driver that wants to publish deflated bytes sets `format`, `data` and an explicit `size`
itself; see [publishing an image](writing-drivers.md#publishing-an-image).

### The bridge delivers the latest image, not every image

A browser that takes frames more slowly than the camera produces them does **not** build up
a queue of exposures. The bridge keeps at most one queued image per BLOB property: a new
one replaces the one still waiting, and the browser sees the most recent frame.

That is deliberate and cannot be traded away for completeness. The property cache overwrites
a payload in place, so there is nothing behind the queue to replay; the queue is bounded by
frame count, so holding every image would put gigabytes per browser behind a single slow
socket; and the INDI 1.7 specification licenses exactly this, allowing a server to drop
BLOBs arriving faster than a slow recipient takes them. `indiserver` makes the same trade
more bluntly, by disconnecting a client whose backlog passes 128 MB.

Skipped images are counted as `coalesced_blobs` on
[`/health`](../docker.md), since a browser cannot tell a skipped exposure from an idle
camera.

**If you need every exposure, do not collect it in the browser.** Use the Python
[`IndiClient`](../reference/python/client.md) against `indiserver` over TCP, which delivers
each BLOB as it arrives and never coalesces. `examples/blob_receiver.py` is that program,
and the [examples guide](examples.md) walks through it.

## Full model reference

Every model, field and enum: the [protocol reference](../reference/python/protocol.md).
