"""``Bridge``: fan one shared ``IndiClient`` out to many browser WebSockets.

The bridge owns a single upstream connection to ``indiserver`` (via the M3
:class:`~indi_nexus.client.IndiClient`) and relays its activity to every connected
browser as JSON. Property changes, log messages, and connection-state transitions
are broadcast to all registered sinks; a browser's inbound frames are parsed back
into typed models and forwarded upstream. A newly-connected browser first receives
a snapshot of the current cache so it starts with full state.

Server -> browser frames are either an INDI message (``{"tag": ...}``, mirroring
the protocol models) or a small bridge **control** frame (``{"event": ...}``) for
UI affordances the INDI protocol has no message for, e.g. upstream connection
state. Browser -> server frames are always INDI messages.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from collections.abc import Awaitable, Callable

from indi_nexus.client import IndiClient, PropertyEvent
from indi_nexus.protocol import DefVector, DelProperty, Message, SetVector, to_json

logger = logging.getLogger(__name__)

#: An outbound sink: something that sends one text frame to a browser.
Sink = Callable[[str], Awaitable[None]]

#: How many recent ``message`` frames are kept for replay to new browsers.
_MESSAGE_HISTORY = 100


class Bridge:
    """Relay between one ``IndiClient`` and many browser WebSocket sinks.

    Parameters
    ----------
    client : IndiClient
        The shared upstream client the bridge relays.
    """

    def __init__(self, client: IndiClient) -> None:
        self._client = client
        self._sinks: set[Sink] = set()
        # INDI messages are transient (not part of the property cache), so keep a
        # bounded history to prime a newly-connected browser's log.
        self._messages: deque[str] = deque(maxlen=_MESSAGE_HISTORY)

    @property
    def client(self) -> IndiClient:
        """The upstream client this bridge relays."""
        return self._client

    async def start(self) -> None:
        """Subscribe to the client and open its upstream connection.

        Returns once the connection attempt is under way rather than once it
        succeeds: the bridge has to come up whether or not ``indiserver`` is
        reachable, so a browser gets the panel and a disconnected indicator
        instead of a server that never finishes starting. The client keeps
        retrying in the background and announces the connection when it lands.
        """
        self._client.subscribe(self._on_event)
        self._client.on_message(self._on_message)
        self._client.on_connection(self._on_connection)
        await self._client.start(wait=False)

    async def aclose(self) -> None:
        """Close the upstream connection."""
        await self._client.aclose()

    # -- sinks ------------------------------------------------------------- #
    def add_sink(self, sink: Sink) -> None:
        """Register a browser sink to receive broadcasts.

        Parameters
        ----------
        sink : Sink
            An awaitable that sends one text frame to the browser.
        """
        self._sinks.add(sink)

    def remove_sink(self, sink: Sink) -> None:
        """Remove a previously registered sink.

        Parameters
        ----------
        sink : Sink
            The sink to remove.
        """
        self._sinks.discard(sink)

    def snapshot(self) -> list[str]:
        """Return the current cache and recent messages as JSON frames.

        Returns
        -------
        frames : list of str
            One ``defXxxVector`` JSON frame per cached property, followed by the
            retained ``message`` frames (oldest first), for priming a
            newly-connected browser.
        """
        store = self._client.store
        frames: list[str] = []
        for device in store.devices():
            for vector in store.device(device).values():
                frames.append(to_json(DefVector(vector=vector)))
        frames.extend(self._messages)
        return frames

    @staticmethod
    def connection_frame(connected: bool) -> str:
        """Build the control frame announcing upstream connection state.

        Parameters
        ----------
        connected : bool
            Whether the bridge is connected to ``indiserver``.

        Returns
        -------
        frame : str
            A JSON control frame (``{"event": "connection", ...}``).
        """
        return json.dumps({"event": "connection", "connected": connected})

    # -- inbound (browser -> upstream) ------------------------------------- #
    async def handle_incoming(self, text: str) -> None:
        """Parse a browser frame and forward it upstream.

        Malformed frames are logged and dropped rather than closing the socket.

        Parameters
        ----------
        text : str
            A JSON INDI message from the browser.
        """
        from indi_nexus.protocol import from_json

        try:
            msg = from_json(text)
        except (ValueError, TypeError):
            logger.warning("dropping malformed inbound frame: %r", text[:200])
            return
        await self._client.send(msg)

    # -- outbound (upstream -> browsers) ----------------------------------- #
    async def _on_event(self, event: PropertyEvent) -> None:
        """Broadcast a property change as the matching INDI message.

        The ``del`` frame is rebuilt from the event rather than forwarded, so it
        carries the deletion's ``message`` and ``timestamp`` explicitly. Both are
        the only account the browser gets of a property going away - the driver
        writes real text there ("only while connected", or why a ``setup``
        rolled back) - and a frame reassembled without them silently drops it.

        Parameters
        ----------
        event : PropertyEvent
            The cache change to relay.
        """
        if event.type == "def" and event.vector is not None:
            frame = to_json(DefVector(vector=event.vector))
        elif event.type == "set" and event.vector is not None:
            frame = to_json(SetVector(vector=event.vector))
        else:  # "del"
            frame = to_json(
                DelProperty(
                    device=event.device,
                    name=event.name,
                    timestamp=event.timestamp,
                    message=event.message,
                )
            )
        await self._broadcast(frame)

    async def _on_message(self, message: Message) -> None:
        """Record an INDI log message and broadcast it to all sinks.

        Parameters
        ----------
        message : Message
            The inbound message to relay.
        """
        frame = to_json(message)
        self._messages.append(frame)
        await self._broadcast(frame)

    async def _on_connection(self, connected: bool) -> None:
        """Broadcast an upstream connection-state control frame.

        Parameters
        ----------
        connected : bool
            The new connection state.
        """
        await self._broadcast(self.connection_frame(connected))

    async def _broadcast(self, frame: str) -> None:
        """Send a frame to every sink, dropping any that fail.

        Parameters
        ----------
        frame : str
            The text frame to send.
        """
        dead: list[Sink] = []
        for sink in list(self._sinks):
            try:
                await sink(frame)
            except Exception:  # noqa: BLE001 - a broken sink must not stall the rest
                dead.append(sink)
        for sink in dead:
            self._sinks.discard(sink)
