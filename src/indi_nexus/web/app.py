"""FastAPI application factory for the INDINexus web bridge.

:func:`create_app` builds a FastAPI app that serves, on top of one shared
:class:`~indi_nexus.client.IndiClient`:

* ``GET /`` - the built reference panel if present, else the debug inspector page;
* ``GET /debug`` - the self-contained debug inspector page;
* ``GET /health`` - liveness and upstream connection state;
* ``GET /api/devices`` and ``/api/devices/{device}[/{name}]`` - a read-only JSON
  snapshot of the property cache;
* ``WS /ws`` - the live bridge: a snapshot on connect, then streamed updates, with
  browser-sent frames forwarded upstream.

The client is injectable so tests drive the app over an in-memory transport; by
default a real TCP client to ``indiserver`` is created.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from indi_nexus.client import IndiClient
from indi_nexus.web.bridge import Bridge

_STATIC = Path(__file__).parent / "static"
_PANEL = _STATIC / "panel"


def create_app(
    *,
    client: IndiClient | None = None,
    indi_host: str = "localhost",
    indi_port: int = 7624,
) -> FastAPI:
    """Build the web-bridge FastAPI application.

    Parameters
    ----------
    client : IndiClient, optional
        An existing client to relay (used by tests); if omitted, a real
        :class:`IndiClient` to ``indi_host``/``indi_port`` is created.
    indi_host : str, optional
        Upstream ``indiserver`` host (when ``client`` is not given).
    indi_port : int, optional
        Upstream ``indiserver`` port (when ``client`` is not given).

    Returns
    -------
    app : FastAPI
        The configured application; its lifespan starts and stops the bridge.
    """
    indi_client = client or IndiClient(indi_host, indi_port)
    bridge = Bridge(indi_client)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Start the bridge on startup and close it on shutdown."""
        await bridge.start()
        try:
            yield
        finally:
            await bridge.aclose()

    app = FastAPI(title="INDINexus web bridge", lifespan=lifespan)
    app.state.bridge = bridge
    app.state.client = indi_client

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Report liveness and whether the upstream client is connected."""
        return {"status": "ok", "connected": indi_client.connected}

    @app.get("/api/devices")
    async def list_devices() -> list[str]:
        """Return the names of all known devices."""
        return indi_client.store.devices()

    @app.get("/api/devices/{device}")
    async def device_properties(device: str) -> dict[str, Any]:
        """Return one device's properties as JSON, keyed by property name.

        A known device that currently publishes nothing returns ``{}``, not a
        404. It is a device that has retracted its properties - a driver that
        defines them on connect, seen while disconnected - and it is still
        listed by ``/api/devices``, so answering "unknown" here would have the
        two endpoints contradict each other.
        """
        if device not in indi_client.store:
            raise HTTPException(status_code=404, detail=f"unknown device {device!r}")
        props = indi_client.store.device(device)
        return {name: vec.model_dump(mode="json") for name, vec in props.items()}

    @app.get("/api/devices/{device}/{name}")
    async def one_property(device: str, name: str) -> dict[str, Any]:
        """Return a single property vector as JSON."""
        vec = indi_client.store.get(device, name)
        if vec is None:
            raise HTTPException(status_code=404, detail=f"unknown property {device}.{name}")
        return vec.model_dump(mode="json")

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        """Stream live updates to a browser and forward its frames upstream."""
        await websocket.accept()
        for frame in bridge.snapshot():
            await websocket.send_text(frame)
        await websocket.send_text(bridge.connection_frame(indi_client.connected))
        bridge.add_sink(websocket.send_text)
        try:
            while True:
                await bridge.handle_incoming(await websocket.receive_text())
        except WebSocketDisconnect:
            pass
        finally:
            bridge.remove_sink(websocket.send_text)

    @app.get("/debug")
    async def debug_page() -> FileResponse:
        """Serve the self-contained debug inspector page."""
        return FileResponse(_STATIC / "debug.html")

    # Serve the built reference panel at the root when it is present (produced by
    # ``pnpm --filter @indi-nexus/panel build``); otherwise fall back to the debug
    # page. The static mount is added last so the API/WS/debug routes above win.
    if (_PANEL / "index.html").is_file():
        app.mount("/", StaticFiles(directory=_PANEL, html=True), name="panel")
    else:

        @app.get("/")
        async def index() -> FileResponse:
            """Serve the debug page when the reference panel is not built."""
            return FileResponse(_STATIC / "debug.html")

    return app
