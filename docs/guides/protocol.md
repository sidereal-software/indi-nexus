# Protocol concepts

You do not need this page to write a driver - the [driver guide](writing-drivers.md)
covers the vocabulary you actually use. Read this when you want to know what is happening
on the wire.

## One model, two encodings

INDINexus speaks canonical INDI 1.7 **XML** to `indiserver`, which is what every other
INDI program expects. It speaks **JSON** to browsers, because that is what browsers want.

Both come from the same Python model, so the two can never drift apart, and the JSON your
frontend receives is exactly the protocol - not a summary of it.

## def, set, new

Three things can be said about a property, and they share one shape:

| Message | Direction | Means |
|---|---|---|
| **def** | driver → client | "this property exists" - with all the metadata: labels, formats, ranges, the switch rule |
| **set** | driver → client | "its values changed" - just names and values |
| **new** | client → driver | "please change it" - also just names and values |

Because `set` and `new` carry no metadata, a client keeps the `def` and merges later `set`
messages onto it. INDINexus does this for you on both sides.

The important consequence is for driver authors: **a `new` usually names only the elements
the client actually touched.** Clicking one radio button sends only that button. This is
why handler code uses

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
