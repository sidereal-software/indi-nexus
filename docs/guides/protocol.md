# Protocol concepts

INDINexus speaks canonical INDI 1.7 XML on the `indiserver` wire and typed
JSON to browsers - the same Pydantic models serialize to both, so the JSON *is*
the frontend contract.

## Vectors and elements

A **property** is a *vector* of named elements: `NumberVector`, `TextVector`,
`SwitchVector`, `LightVector`, `BLOBVector`, discriminated on `kind`. Each
carries a `state` (Idle / Ok / Busy / Alert - the coloured badge in a UI) and,
except lights, a `perm` (ro / wo / rw).

## def, set, new

The protocol's three intents share one data shape, so they are thin wrappers
around a vector:

- **def** (driver to client): "this property exists" - carries full metadata
  (labels, formats, min/max, switch rule).
- **set** (driver to client): "its values/state changed" - carries only names
  and values; clients *merge* onto the earlier def.
- **new** (client to driver): "please change it" - also names and values only,
  and often only *some* elements (a `OneOfMany` click sends just the selected
  member).

That partial-write asymmetry is why handler code uses `vector.selected()` and
`vector.get(name, default)` rather than indexing blindly.

## Numbers and sexagesimal

Number elements carry a printf-style `format`; the `%m` forms (`%9.6m`) are
INDI's sexagesimal notation for RA/Dec, rendered `hh:mm:ss`. Both the Python
codec (`format_number`/`parse_number`) and the TypeScript mirror
(`formatNumber`) implement it byte-for-byte like libindi.

## Messages and BLOBs

`message` carries a device's timestamped log line. BLOBs (image payloads)
travel base64 and are only forwarded once a client sends `enableBLOB`.

## Full model reference

See the [protocol reference](../reference/python/protocol.md).
