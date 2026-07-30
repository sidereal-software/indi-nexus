"""The INDINexus web bridge.

A FastAPI app that relays one shared :class:`~indi_nexus.client.IndiClient` to
browsers over a WebSocket as typed JSON, with read-only REST snapshots and a
built-in debug inspector page. See :func:`create_app`.
"""

from indi_nexus.web.app import create_app
from indi_nexus.web.bridge import Bridge

__all__ = ["create_app", "Bridge"]
