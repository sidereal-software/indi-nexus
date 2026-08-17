# `indi_nexus.settings` and `indi_nexus.logging_config`

The `INDI_NEXUS_*` environment, and the logging INDINexus configures at an entrypoint.

`Settings` is the only reader of the `INDI_NEXUS_*` environment inside the package: no
command-line option carries its own lookup, so a variable has one meaning and one place
documenting it. Where a setting also has a flag - `--log-level`, `--wire`, `--token`,
`--allow-origin`, `--allow-insecure-bind` - the flag wins and its absence defers to the
environment.

The one reader outside the package is the Docker image's entrypoint, which reads
`INDI_NEXUS_TOKEN`, `INDI_NEXUS_ALLOW_INSECURE_BIND` and `INDI_NEXUS_ALLOWED_ORIGINS` as
fallbacks for its own `WEB_*` spellings, because it has to generate a token and print the
panel's URL with it before `serve` starts. It passes what it resolved on as flags, so
`Settings` still decides one value. See [Docker](../../docker.md) for both spellings.

Nothing reads either module implicitly: `IndiClient`, `Bridge` and `create_app` take
explicit parameters, and the entrypoints - the `indi-nexus` callback and
`indi_nexus.driver.run` - read the settings and pass the values down. Logging goes to
**stderr**, because a driver's stdout is the INDI wire.

`log_level` accepts `CRITICAL`, `ERROR`, `WARNING`, `INFO` or `DEBUG`, case-insensitive;
anything else is a usage error rather than a traceback out of `uvicorn.Config`. Wire
traffic goes to one logger for all four sites, named by `WIRE_LOGGER`
(`"indi_nexus.wire"`).

::: indi_nexus.settings

::: indi_nexus.logging_config
