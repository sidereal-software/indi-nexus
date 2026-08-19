"""FastAPI application factory for the INDIkit web bridge.

:func:`create_app` builds a FastAPI app that serves, on top of one shared
:class:`~indikit.client.IndiClient`:

* ``GET /`` - the built reference panel if present, else the debug inspector page;
* ``GET /debug`` - the self-contained debug inspector page;
* ``GET /health`` - liveness, the browser contract's version, upstream connection
  state, and counters for the slow-sink drops and the upstream parser;
* ``GET /api/devices`` and ``/api/devices/{device}[/{name}]`` - a read-only JSON
  snapshot of the property cache;
* ``WS /ws`` - the live bridge: a snapshot on connect, then streamed updates, with
  browser-sent frames forwarded upstream.

The client is injectable so tests drive the app over an in-memory transport; by
default a real TCP client to ``indiserver`` is created.

**The auth boundary runs around ``/ws`` and ``/api``.** ``/ws`` is the write
surface, and ``/api/devices/*`` is a full read of instrument state - site
coordinates, hardware inventory, mount and focuser positions - so both sit behind
the token whenever one is configured. ``/health`` stays open because the image's
``HEALTHCHECK`` calls it unauthenticated and it exposes one boolean and a handful
of counters - no addresses, no device names, and **no release version**, which
would hand an unauthenticated caller the exact build to look up advisories
against while telling a legitimate one nothing the ``protocol`` integer does not
already say; ``/``, ``/debug`` and the static panel are open-source HTML with nothing
instrument-specific in them. There is deliberately no ambient credential (no
cookie, no session), so cross-origin JavaScript cannot authenticate to ``/api`` at
all and there are no state-changing HTTP routes to protect; see
:mod:`indikit.web.security` for what guards ``/ws``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import HTTPConnection

from indikit.client import IndiClient
from indikit.protocol import Vector
from indikit.web.bridge import _MAX_BACKLOG, _MESSAGE_HISTORY, Bridge, Subscription
from indikit.web.control_frames import BRIDGE_PROTOCOL_VERSION
from indikit.web.security import WebSecurity

logger = logging.getLogger(__name__)

_STATIC = Path(__file__).parent / "static"
_PANEL = _STATIC / "panel"

#: WebSocket close code for a policy violation, used for a handshake that fails
#: the origin or token check.
_WS_POLICY_VIOLATION = 1008

#: WebSocket close code for an ordinary, expected close.
_WS_NORMAL_CLOSURE = 1000

#: WebSocket close code for "try again later", used when the bridge dropped a
#: browser that stopped keeping up. Best effort: the close frame travels the same
#: backed-up connection the drop was about, so it may never arrive.
_WS_TRY_AGAIN_LATER = 1013

#: Decimal places the ``/health`` durations are rounded to. Milliseconds are the
#: last digit that means anything for a link measured in seconds, and the raw
#: float renders as ``4211.299999999996`` in an operator's terminal.
_SECONDS_PRECISION = 3


def _seconds(value: float | None) -> float | None:
    """Round a duration for ``/health``, passing `None` through.

    Parameters
    ----------
    value : float or None
        A duration in seconds, or `None` where the field does not apply.

    Returns
    -------
    seconds : float or None
        The rounded duration, or `None`.
    """
    return None if value is None else round(value, _SECONDS_PRECISION)


def _bearer_token(conn: HTTPConnection) -> str | None:
    """Read a token from a connection's ``Authorization: Bearer`` header.

    Parameters
    ----------
    conn : HTTPConnection
        The incoming ``Request`` or ``WebSocket``; both are HTTP connections.

    Returns
    -------
    token : str or None
        The supplied token, or `None` if none was.
    """
    header = conn.headers.get("authorization")
    if header is None:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer" and value:
        return value
    return None


def _ws_token(websocket: WebSocket) -> str | None:
    """Read a token from a WebSocket handshake, allowing ``?token=``.

    The query parameter is **only** accepted here. A WebSocket opened from a
    browser cannot set a header, so for ``/ws`` it is the one form a browser has;
    that argument does not reach ``/api``, which any HTTP caller can send a
    header on, and where a token in the URL would be written into reverse-proxy
    and CDN access logs, `Referer` headers and browser history.

    Parameters
    ----------
    websocket : WebSocket
        The incoming handshake.

    Returns
    -------
    token : str or None
        The supplied token, or `None` if none was.
    """
    return _bearer_token(websocket) or websocket.query_params.get("token")


def create_app(
    *,
    client: IndiClient | None = None,
    indi_host: str = "localhost",
    indi_port: int = 7624,
    token: str | None = None,
    allowed_origins: Sequence[str] = (),
    connect_timeout: float = 10.0,
    reconnect_delay: float = 2.0,
    message_history: int = _MESSAGE_HISTORY,
    max_backlog: int = _MAX_BACKLOG,
) -> FastAPI:
    """Build the web-bridge FastAPI application.

    Nothing here reads the environment. ``indikit serve`` fills the tuning
    arguments from :class:`~indikit.settings.Settings`, so the app stays
    injectable and importing it costs no ambient configuration.

    Parameters
    ----------
    client : IndiClient, optional
        An existing client to relay (used by tests); if omitted, a real
        :class:`IndiClient` to ``indi_host``/``indi_port`` is created.
    indi_host : str, optional
        Upstream ``indiserver`` host (when ``client`` is not given).
    indi_port : int, optional
        Upstream ``indiserver`` port (when ``client`` is not given).
    connect_timeout : float, optional
        Seconds the created client waits per connection attempt (when ``client``
        is not given).
    reconnect_delay : float, optional
        Seconds the created client waits between attempts (when ``client`` is not
        given).
    message_history : int, optional
        How many recent INDI ``message`` frames the bridge replays to a newly
        attached browser.
    max_backlog : int, optional
        How many live frames a browser may fall behind by before it is dropped.
    token : str, optional
        A shared secret required on ``/ws`` and ``/api``. `None` (the default)
        leaves both open, which is what a loopback-bound development server
        wants.
    allowed_origins : Sequence of str, optional
        Browser origins accepted on ``/ws`` in addition to the server's own,
        e.g. ``http://localhost:5173`` for a Vite dev server or a separate
        front end. ``"*"`` accepts any.

    Returns
    -------
    app : FastAPI
        The configured application; its lifespan starts and stops the bridge.
    """
    indi_client = client or IndiClient(
        indi_host,
        indi_port,
        connect_timeout=connect_timeout,
        reconnect_delay=reconnect_delay,
    )
    bridge = Bridge(indi_client, message_history=message_history, max_backlog=max_backlog)
    security = WebSecurity.build(token, allowed_origins)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Start the bridge on startup and close it on shutdown."""
        await bridge.start()
        try:
            yield
        finally:
            await bridge.aclose()

    app = FastAPI(title="INDIkit web bridge", lifespan=lifespan)
    app.state.bridge = bridge
    app.state.client = indi_client
    app.state.security = security

    def require_token(request: Request) -> None:
        """Reject a request that does not carry the configured token.

        ``Authorization: Bearer`` only; see :func:`_ws_token` for why ``?token=``
        stops at the WebSocket handshake.

        Parameters
        ----------
        request : Request
            The incoming request.

        Raises
        ------
        HTTPException
            Raised with 403 when a token is configured and not supplied.
        """
        if not security.token_ok(_bearer_token(request)):
            raise HTTPException(status_code=403, detail="a valid token is required")

    api = [Depends(require_token)]

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Report liveness, the upstream link, the parser, and dropped browsers.

        Open on purpose: the container's ``HEALTHCHECK`` calls it with no
        credentials. ``dropped_slow_sinks`` is here because a browser cannot tell
        an overflow drop from a network fault, so the count has to be readable
        from the outside without scraping logs.

        **The body only ever grows.** ``status``, ``connected`` and
        ``dropped_slow_sinks`` keep their names at the top level, because a
        monitoring check somewhere is already reading them; everything since was
        added beside them rather than by nesting or renaming those three.

        ``protocol`` is the browser contract's version
        (:data:`~indikit.web.control_frames.BRIDGE_PROTOCOL_VERSION`), the
        same integer the ``hello`` frame carries. It is here so a deployment
        check can answer "will my pinned client understand this bridge" without
        opening a WebSocket. The release version is deliberately **not** here;
        see this module's docstring.

        ``coalesced_blobs`` counts images that were replaced in a browser's queue
        before it read them. The bridge delivers the latest exposure rather than
        every exposure, which is the only bounded thing it can do
        (:meth:`~indikit.web.bridge.Subscription.enqueue` argues it), and this
        is where that shows up instead of being silent. It is additive and **not**
        a ``protocol`` bump: nothing on the browser contract changed.

        While disconnected, ``upstream.uptime_seconds`` and
        ``last_message_age_seconds`` are ``null`` and ``reconnects`` keeps its
        count, while the ``parser`` block reports the **last** connection's final
        counters - stated rather than left to be discovered, because a frozen
        ``bytes_since_last_message`` on a dead link is exactly the field an
        operator would misread. The two ``_total`` fields are the durable ones.
        """
        stats = indi_client.stats
        return {
            "status": "ok",
            "protocol": BRIDGE_PROTOCOL_VERSION,
            "connected": stats.connected,
            "dropped_slow_sinks": bridge.dropped_slow_sinks,
            "coalesced_blobs": bridge.coalesced_blobs,
            "sinks_attached": bridge.sink_count(),
            "upstream": {
                "uptime_seconds": _seconds(stats.uptime_seconds),
                "reconnects": stats.reconnects,
                "last_message_age_seconds": _seconds(stats.last_message_age_seconds),
            },
            "parser": {
                "dropped": stats.dropped,
                "resets": stats.resets,
                "bytes_since_last_message": stats.bytes_since_last_message,
                "dropped_total": stats.dropped_total,
                "resets_total": stats.resets_total,
            },
        }

    @app.get("/api/devices", dependencies=api)
    async def list_devices() -> list[str]:
        """Return the names of all known devices."""
        return indi_client.store.devices()

    @app.get("/api/devices/{device}", dependencies=api)
    async def device_properties(device: str) -> dict[str, Vector]:
        """Return one device's properties as JSON, keyed by property name.

        A known device that currently publishes nothing returns ``{}``, not a
        404. It is a device that has retracted its properties - a driver that
        defines them on connect, seen while disconnected - and it is still
        listed by ``/api/devices``, so answering "unknown" here would have the
        two endpoints contradict each other.

        The annotation is the point: FastAPI serialises through it, so the
        payload is pinned by the same ``Vector`` schema the WebSocket carries
        and OpenAPI documents it as one instead of as a bare object. It is not
        free - a response model re-validates on the way out, so a large cache
        costs N validations per request - and this is the right endpoint to pay
        it on, being a snapshot rather than the live stream.
        """
        if device not in indi_client.store:
            raise HTTPException(status_code=404, detail=f"unknown device {device!r}")
        return dict(indi_client.store.device(device))

    @app.get("/api/devices/{device}/{name}", dependencies=api)
    async def one_property(device: str, name: str) -> Vector:
        """Return a single property vector as JSON."""
        vec = indi_client.store.get(device, name)
        if vec is None:
            raise HTTPException(status_code=404, detail=f"unknown property {device}.{name}")
        return vec

    async def _receive_loop(websocket: WebSocket, sub: Subscription) -> None:
        """Forward this browser's frames upstream until it disconnects.

        Parameters
        ----------
        websocket : WebSocket
            The browser's socket.
        sub : Subscription
            The browser's bridge subscription, so a rejected frame is reported
            back to it alone.
        """
        with contextlib.suppress(WebSocketDisconnect):
            while True:
                await bridge.handle_incoming(await websocket.receive_text(), sub)

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        """Stream live updates to a browser and forward its frames upstream.

        The route sends nothing itself: seeding and registration are one
        synchronous operation inside :meth:`Bridge.attach`, so no event can be
        lost in the window between them.
        """
        headers = websocket.headers
        if not security.origin_allowed(headers.get("origin"), headers.get("host")):
            # Closing before accept() answers the handshake with an HTTP error
            # rather than opening a socket and then dropping it.
            await websocket.close(code=_WS_POLICY_VIOLATION)
            return
        if not security.token_ok(_ws_token(websocket)):
            await websocket.close(code=_WS_POLICY_VIOLATION)
            return
        await websocket.accept()
        sub = bridge.attach(websocket.send_text)
        receiving = asyncio.create_task(_receive_loop(websocket, sub))
        # Racing the drop matters: a browser the bridge dropped for backlog would
        # otherwise leave this route parked in receive_text() with no pump behind
        # it, holding a socket that will never be served again.
        dropped = asyncio.create_task(sub.closed.wait())
        try:
            await asyncio.wait({receiving, dropped}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            receiving.cancel()
            dropped.cancel()
            # Awaited one at a time rather than through gather(): a cancelled
            # child's CancelledError comes up out of gather() even under
            # return_exceptions, which cancelled this route mid-cleanup. Reaping
            # them is not optional either - without it a cancellation that has
            # not been delivered yet surfaces later as "Task was destroyed but it
            # is pending!", and sub.aclose() only happens to give the loop enough
            # turns.
            for task in (receiving, dropped):
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            # Only a receive loop that already finished can have failed, and
            # that is the one whose exception nothing else would ever report.
            if receiving.done() and not receiving.cancelled():
                failure = receiving.exception()
                if failure is not None:
                    logger.error("websocket receive loop failed", exc_info=failure)
            await sub.aclose()
            # The backlog flag, not `sub.closed`: every way out of the pump sets
            # the event, so keying the code off it told an ordinary disconnect
            # racing a stale write failure to "try again later".
            code = _WS_TRY_AGAIN_LATER if sub.dropped_for_backlog else _WS_NORMAL_CLOSURE
            with contextlib.suppress(RuntimeError):
                await websocket.close(code=code)

    @app.get("/debug")
    async def debug_page() -> FileResponse:
        """Serve the self-contained debug inspector page."""
        return FileResponse(_STATIC / "debug.html")

    # Serve the built reference panel at the root when it is present (produced by
    # ``pnpm --filter @indikit/panel build``); otherwise fall back to the debug
    # page. The static mount is added last so the API/WS/debug routes above win.
    if (_PANEL / "index.html").is_file():
        app.mount("/", StaticFiles(directory=_PANEL, html=True), name="panel")
    else:

        @app.get("/")
        async def index() -> FileResponse:
            """Serve the debug page when the reference panel is not built."""
            return FileResponse(_STATIC / "debug.html")

    return app
