# `indikit.settings` and `indikit.logging_config`

The `INDIKIT_*` environment, and the logging INDIkit configures at an entrypoint.

`Settings` is the only reader of the `INDIKIT_*` environment inside the package: no
command-line option carries its own lookup, so a variable has one meaning and one place
documenting it. Where a setting also has a flag - `--log-level`, `--wire`, `--token`,
`--allow-origin`, `--allow-insecure-bind` - the flag wins and its absence defers to the
environment.

The one reader outside the package is the Docker image's entrypoint, which reads
`INDIKIT_TOKEN`, `INDIKIT_ALLOW_INSECURE_BIND` and `INDIKIT_ALLOWED_ORIGINS` as
fallbacks for its own `WEB_*` spellings, because it has to generate a token and print the
panel's URL with it before `serve` starts. It passes what it resolved on as flags, so
`Settings` still decides one value. See [Docker](../../docker.md) for both spellings.

Nothing reads either module implicitly: `IndiClient`, `Bridge` and `create_app` take
explicit parameters, and the entrypoints - the `indikit` callback and
`indikit.driver.run` - read the settings and pass the values down. Logging goes to
**stderr**, because a driver's stdout is the INDI wire.

`log_level` accepts `CRITICAL`, `ERROR`, `WARNING`, `INFO` or `DEBUG`, case-insensitive;
anything else is a usage error rather than a traceback out of `uvicorn.Config`. Wire
traffic goes to one logger for all four sites, named by `WIRE_LOGGER`
(`"indikit.wire"`).

::: indikit.settings

::: indikit.logging_config
