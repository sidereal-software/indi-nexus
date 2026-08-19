---
search:
  boost: 2
---

# Protocol concepts

Read this page when you want to know what is on the wire. Writing a driver does not need
it: the [driver guide](writing-drivers.md) covers the vocabulary you use.

## Two encodings, one model

Canonical INDI 1.7 XML goes to `indiserver`, because that is what every other INDI program
expects. Typed JSON goes to browsers, because nothing in a browser wants to parse XML.

Both encodings come from one Python model, so they cannot drift apart. A frontend receives
the protocol itself, not a summary of it.

Three frames on that WebSocket are **not** INDI. Each carries an `event` key instead of a
`tag`, and all three are modelled in
[`indikit.web.control_frames`](../reference/python/web.md#control-frames). INDI has no
message for any of them, and a UI needs all three.

| Frame | Means |
|---|---|
| `{"event": "hello", "protocol": 1, "server": "0.2.0"}` | the first frame on every socket: which version of *this* contract the bridge speaks, and which INDIkit release is serving it. |
| `{"event": "connection", "connected": false}` | whether the *bridge* is connected to `indiserver`. Distinct from whether your browser is connected to the bridge. |
| `{"event": "error", "code": ..., "message": ..., "tag": ...}` | a frame this browser sent did not go upstream: malformed, not something a client may send, or refused because the upstream was down or busy. Sent only to the browser that sent the frame. |

Write a frame reader that **skips an `event` it does not recognise**. Any future control
frame arrives that way, so a reader that treats an unknown one as a protocol violation
breaks on the next release.

`@indikit/client` already does this. It surfaces the connection state and the protocol
version, routes the error into the message log, and drops anything else.

### Versioning the browser contract

`protocol` versions the bridge-to-browser JSON. It is unrelated to INDI's own `version`,
which is frozen at 1.7.

The number increases only for a breaking change: a field removed, renamed, or given a new
meaning. Adding an optional field does not increase it, because clients ignore keys they do
not recognise.

A mismatch is never fatal. `@indikit/client` compares the number against its own
`CLIENT_PROTOCOL_VERSION`, logs one line when they differ, and carries on. Nothing here
refuses a socket over a version skew: a panel going dark mid-session helps nobody at a
telescope.

A bridge older than the `hello` frame never sends one. Treat **the first frame that is not
a `hello`** as the answer; `@indikit/client` records `protocol: 0` at that point.

Do not wait for a `def` instead. With the upstream down and the cache empty, the first
frame is the connection frame, and no `def` ever arrives.

## def, set, new

Three things can be said about a property. All three share one shape:

| Message | Direction | Means |
|---|---|---|
| **def** | driver → client | "this property exists", with all the metadata: labels, formats, ranges, the switch rule |
| **set** | driver → client | "its values changed": just names and values |
| **new** | client → driver | "please change it": also just names and values |

A client keeps the `def` and merges later `set` messages onto it, because `set` and `new`
carry no metadata. INDIkit does that for you on both sides.

A `new` therefore usually names only the elements the client changed. Clicking one radio
button sends only that button. So read what arrived, rather than indexing into elements
that may not be there:

```python
vector.selected()             # which switch did they turn on?
vector.get(name, default)     # what value did they send, if any?
```

## Numbers and sexagesimal

Number elements carry a printf-style `format`. Alongside the usual `%.2f` forms, INDI
defines `%m` for sexagesimal: the `hh:mm:ss` notation used for right ascension and
declination. `%9.6m` means nine characters wide, showing degrees, minutes and seconds.

Both the Python codec and its TypeScript mirror *write* `%m` exactly as libindi does, down
to the field padding and the half-away-from-zero rounding. Coordinates therefore round-trip
to existing INDI software unchanged.

Reading is deliberately more permissive. libindi accepts sexagesimal on a `def` but reads a
`set` with `std::stod`, so `10:30:00` in a `setNumberVector` arrives there as `10.0`.
INDIkit parses sexagesimal on both.

Parsing both is a strict superset: anything libindi reads correctly, INDIkit reads the
same way. Do not "fix" it to match. Matching would turn a coordinate into a silently wrong
number.

## Messages and BLOBs

`message` is a timestamped log line from a device. `self.message()` sends one, and a UI's
log panel shows it.

BLOBs carry binary payloads, typically a FITS image. `indiserver` sends none of them to a
client until that client asks with `enableBLOB`, because they can be large. The Python and
TypeScript clients expose that call as `enable_blob` / `enableBlob`.

In JSON the payload is a base64 string in the **standard** alphabet (`+` and `/`), so
`atob` and a `data:application/octet-stream;base64,...` URL both accept it as it arrives.

### Compressed payloads

A BLOB's `format` is a chain of file-name suffixes saying what the bytes are. A trailing
`.z` is not part of that: it says the payload was deflated (zlib, RFC 1950) for the wire.

**INDIkit inflates those on receipt**, in both codecs. A payload that reaches a Python
`IndiClient` subscriber, a driver's `@on_new`, or a browser over the WebSocket is the file
itself: the `.z` is gone from `format`, and `size` is the inflated length. A consumer sees
`.fits`, never `.fits.z`.

libindi inflates in every client built on it, so code written against KStars behaviour sees
the same thing here.

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

A payload that declares `.z` and will not inflate **costs the message**. The message is
dropped and counted like any other malformed leaf value, the same as a `oneNumber` full of
junk. The compressed bytes are never delivered instead: a caller that asked for a `.fits`
would hand them to a FITS reader.

Compressing on **send** is not implemented, deliberately. That call belongs to the driver
author, as it does in libindi, whose `CCD_COMPRESSION` switch defaults to off. A driver
that wants to publish deflated bytes sets `format`, `data` and an explicit `size` itself.
See [publishing an image](writing-drivers.md#publishing-an-image).

### The bridge delivers the latest image, not every image

A browser that takes frames more slowly than the camera produces them does **not** build up
a queue of exposures. The bridge keeps at most one queued image per BLOB property. A new
frame replaces the one still waiting, so the browser sees the most recent.

That cannot be traded away for completeness. Three things decide it:

- The property cache overwrites a payload in place, so there is nothing behind the queue to
  replay.
- The queue is bounded by frame count. Holding every image would put gigabytes per browser
  behind one slow socket.
- The INDI 1.7 specification licenses exactly this, allowing a server to drop BLOBs
  arriving faster than a slow recipient takes them.

`indiserver` makes the same trade more bluntly, by disconnecting a client whose backlog
passes 128 MB.

Skipped images are counted as `coalesced_blobs` on [`/health`](../docker.md). A browser
cannot tell a skipped exposure from an idle camera.

**If you need every exposure, do not collect it in the browser.** Use the Python
[`IndiClient`](../reference/python/client.md) against `indiserver` over TCP. It delivers
each BLOB as it arrives and never coalesces. `examples/blob_receiver.py` is that program,
and the [examples guide](examples.md) walks through it.

## Full model reference

Every model, field and enum: the [protocol reference](../reference/python/protocol.md).
