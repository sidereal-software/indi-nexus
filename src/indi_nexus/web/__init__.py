"""The INDINexus web bridge.

A FastAPI app that relays one shared :class:`~indi_nexus.client.IndiClient` to
browsers over a WebSocket as typed JSON, with read-only REST snapshots and a
built-in debug inspector page. See :func:`create_app`.

:class:`WebSecurity` is the access policy in front of ``/ws`` and ``/api``: an
origin allowlist and an optional shared token.

The non-INDI frames the bridge sends - ``hello``, ``connection``, ``error`` -
are modelled in :mod:`indi_nexus.web.control_frames`, whose
:data:`~indi_nexus.web.control_frames.BRIDGE_PROTOCOL_VERSION` versions the
browser JSON contract.

This package is the browser-facing edge and imports only downwards, towards the
client and the protocol. The in-process hub that ``indi-nexus serve --device``
runs drivers on is :class:`indi_nexus.hub.InProcessHub`, deliberately not
re-exported here: it is the driver SDK, and importing ``indi_nexus.web`` should
not drag that in.
"""

from indi_nexus.web.app import create_app
from indi_nexus.web.bridge import Bridge, Subscription
from indi_nexus.web.control_frames import (
    BRIDGE_PROTOCOL_VERSION,
    BridgeFrame,
    ConnectionFrame,
    ErrorFrame,
    HelloFrame,
    dump_frame,
)
from indi_nexus.web.security import WebSecurity, is_loopback

__all__ = [
    "BRIDGE_PROTOCOL_VERSION",
    "Bridge",
    "BridgeFrame",
    "ConnectionFrame",
    "ErrorFrame",
    "HelloFrame",
    "Subscription",
    "WebSecurity",
    "create_app",
    "dump_frame",
    "is_loopback",
]
