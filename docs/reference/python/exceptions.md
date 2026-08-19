# `indikit.exceptions`

Everything INDIkit raises on purpose derives from `IndiError`, so one `except`
catches the whole library. Every type **also** derives from the builtin that was
raised at that site before the hierarchy existed - `ProtocolError` is a
`ValueError`, `PropertyNotFound` is a `KeyError`, `NotConnectedError` is a
`ConnectionError` - so existing `except` clauses keep catching exactly what they
caught before.

These are the types named in every `Raises` section elsewhere in this reference.

::: indikit.exceptions
