# `indikit.web`

The FastAPI web bridge: one shared upstream `IndiClient` relayed to browsers
as typed JSON over a WebSocket, plus a REST snapshot and the bundled panel.

`/ws` is the whole write surface and `/api` is a full read of instrument state,
so both sit behind the shared token whenever one is configured, and `/ws` is
additionally checked against an `Origin` allowlist before the handshake is
accepted. `/health`, `/`, `/debug` and the static panel stay open. The policy
itself is `WebSecurity`, under [Security](#security) below.

## App

::: indikit.web.app

## Bridge

::: indikit.web.bridge

## Control frames

The non-INDI half of the browser contract: `hello`, `connection` and `error`,
plus `BRIDGE_PROTOCOL_VERSION`, the version of that contract. See
[Protocol concepts](../../guides/protocol.md#versioning-the-browser-contract)
for what a client does with a version mismatch.

::: indikit.web.control_frames

## Security

::: indikit.web.security
