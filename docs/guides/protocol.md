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

## Full model reference

Every model, field and enum: the [protocol reference](../reference/python/protocol.md).
