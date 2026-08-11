`indi-nexus serve --device module:Class` runs drivers inside the web process, so a driver
can be tried on screen with only `pip install indi-nexus` and no `indiserver` to install
first. Repeat the flag for several devices.

It is a development convenience, not a hub: it serves one client and stops with the
command. `indiserver` remains what anything real runs under, and `serve` without
`--device` connects to it exactly as before. This replaces `examples/demo_bridge.py`,
whose hub now lives in the package as `indi_nexus.web.InProcessHub`.
