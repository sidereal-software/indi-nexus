# `indi_nexus.web`

The FastAPI web bridge: one shared upstream `IndiClient` relayed to browsers
as typed JSON over a WebSocket, plus a REST snapshot and the bundled panel.

`/ws` is the whole write surface and `/api` is a full read of instrument state,
so both sit behind the shared token whenever one is configured, and `/ws` is
additionally checked against an `Origin` allowlist before the handshake is
accepted. `/health`, `/`, `/debug` and the static panel stay open. The policy
itself is `WebSecurity`, under [Security](#security) below.

## App

::: indi_nexus.web.app

## Bridge

::: indi_nexus.web.bridge

## Security

::: indi_nexus.web.security
