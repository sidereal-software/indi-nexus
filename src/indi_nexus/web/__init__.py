"""The INDINexus web bridge.

A FastAPI app that relays one shared :class:`~indi_nexus.client.IndiClient` to
browsers over a WebSocket as typed JSON, with read-only REST snapshots and a
built-in debug inspector page. See :func:`create_app`.

:class:`WebSecurity` is the access policy in front of ``/ws`` and ``/api``: an
origin allowlist and an optional shared token.

This package is the browser-facing edge and imports only downwards, towards the
client and the protocol. The in-process hub that ``indi-nexus serve --device``
runs drivers on is :class:`indi_nexus.hub.InProcessHub`, deliberately not
re-exported here: it is the driver SDK, and importing ``indi_nexus.web`` should
not drag that in.
"""

from indi_nexus.web.app import create_app
from indi_nexus.web.bridge import Bridge, Subscription
from indi_nexus.web.security import WebSecurity, is_loopback

__all__ = ["Bridge", "Subscription", "WebSecurity", "create_app", "is_loopback"]
