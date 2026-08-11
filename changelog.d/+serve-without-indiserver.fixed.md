`indi-nexus serve` now starts even when `indiserver` is unreachable, instead of hanging
in startup with no output. The panel loads and reports a disconnected state, and the
bridge connects on its own once `indiserver` appears. `IndiClient.start()` gained a `wait`
keyword for this; its default is unchanged, so scripts and monitors still block until the
first connection.
