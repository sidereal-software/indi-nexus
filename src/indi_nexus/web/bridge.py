"""``Bridge``: fan one shared ``IndiClient`` out to many browser WebSockets.

The bridge owns a single upstream connection to ``indiserver`` (via the M3
:class:`~indi_nexus.client.IndiClient`) and relays its activity to every connected
browser as JSON. Property changes, log messages, and connection-state transitions
are broadcast to every attached browser; a browser's inbound frames are parsed back
into typed models and forwarded upstream. A newly-attached browser is first seeded
with the current cache so it starts with full state.

Server -> browser frames are either an INDI message (``{"tag": ...}``, mirroring
the protocol models) or a small bridge **control** frame (``{"event": ...}``,
modelled in :mod:`indi_nexus.web.control_frames`) for things the INDI protocol
has no message for: the version of the browser contract, upstream connection
state, and the rejection of a frame the browser sent. The first frame on every
socket is the ``hello``, ahead of the seeded properties, so a browser knows what
it is talking to before it has to interpret anything. Browser -> server frames
are always INDI messages, and only the three a client is allowed to send.

**A browser is a subscriber, never something the upstream reader awaits.** Every
broadcast originates in :class:`IndiClient`'s single connection task - property
events and messages through the reader, the connection frame through the connection
loop - so awaiting a socket from :meth:`Bridge._broadcast` would let one browser
under TCP back-pressure stall the upstream stream for everyone, eventually stalling
the parser and tearing down a healthy connection. Instead each browser gets a
bounded queue and its own pump task, and :meth:`Bridge._broadcast` is a plain
synchronous ``def`` that appends and returns.

That same synchrony is what makes seeding atomic: :meth:`Bridge.attach` reads the
cache, builds the seed and registers the subscriber with no ``await`` anywhere
between, so no event can land in the window that used to exist between the snapshot
and the registration. **Keep ``attach`` and ``_broadcast`` synchronous** - that is
the whole argument, and a refactor that quietly makes either one a coroutine
reopens the hole.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from indi_nexus import __version__
from indi_nexus.client import IndiClient, PropertyEvent
from indi_nexus.exceptions import NotConnectedError, SendQueueFull
from indi_nexus.protocol import (
    DefVector,
    DelProperty,
    EnableBLOB,
    GetProperties,
    Message,
    NewVector,
    SetVector,
    Vector,
    from_json,
    to_json,
)
from indi_nexus.web.control_frames import (
    ConnectionFrame,
    ErrorFrame,
    HelloFrame,
    dump_frame,
)

logger = logging.getLogger(__name__)

#: An outbound sink: something that sends one text frame to a browser.
Sink = Callable[[str], Awaitable[None]]

#: How many recent ``message`` frames are kept for replay to new browsers. The
#: default for ``Bridge(message_history=...)``, which ``indi-nexus serve`` fills
#: from ``INDI_NEXUS_MESSAGE_HISTORY``.
_MESSAGE_HISTORY = 100

#: How many live frames a browser may fall behind by before it is dropped. The
#: seed is excluded and drained first, so this measures lateness rather than cache
#: size. Coalescing means a fast instrument spamming one property costs one slot,
#: so reaching this means falling behind on that many *distinct* properties and
#: messages - a wedged socket, not a slow one. The default for
#: ``Bridge(max_backlog=...)``, which ``indi-nexus serve`` fills from
#: ``INDI_NEXUS_MAX_BACKLOG``.
_MAX_BACKLOG = 512

#: The only messages a browser may send upstream. A ``def``/``set``/``message``
#: from a browser would be a client claiming to be a device.
_CLIENT_TO_SERVER = (NewVector, GetProperties, EnableBLOB)


@dataclass(slots=True)
class _Slot:
    """One queued outbound frame, addressable so a later frame can replace it.

    Attributes
    ----------
    frame : str
        The JSON text to send.
    key : tuple of str or None
        The ``(device, name)`` this frame is about, or `None` for a frame that
        is not about one property (a ``message``, a control frame).
    """

    frame: str
    key: tuple[str, str] | None = None


@dataclass(slots=True, eq=False)
class Subscription:
    """One attached browser: its seed, its queued frames, and its pump task.

    Returned by :meth:`Bridge.attach` and closed by :meth:`aclose`. Not
    constructed directly.

    Attributes
    ----------
    bridge : Bridge
        The bridge this subscription is attached to.
    sink : Sink
        The awaitable that sends one text frame to this browser.
    seed_vectors : tuple of Vector
        The cached properties to send first, held as references rather than as
        serialized JSON so N attaching browsers do not buffer N copies of the
        cache before a byte drains. They are serialized by the pump, at drain
        rate.
    seed_frames : tuple of str
        The retained ``message`` frames plus the connection frame, sent after
        the seeded properties.
    preamble : tuple of str
        Frames sent **before** the seeded properties: the ``hello``, which has
        to be the first thing on the socket because it says which contract
        everything after it is written in.
    queue : deque of _Slot
        Live frames queued since the attach, drained after the seed.
    coalescible : dict
        ``(device, name)`` -> the queued ``set`` slot a later ``set`` may
        replace.
    ready : asyncio.Event
        Set when ``queue`` is non-empty; the pump waits on it.
    closed : asyncio.Event
        Set once the pump has exited, however it exited.
    dropped_for_backlog : bool
        Set by :meth:`Bridge._drop` alone, and it is the *reason* rather than the
        fact: ``closed`` is set by every path out of the pump, so a browser that
        simply went away while a stale write was failing looks identical through
        it. The route reads this to choose its close code, and telling a browser
        "try again later" for an ordinary disconnect is a lie about why its
        socket ended.
    task : asyncio.Task or None
        The pump; assigned by :meth:`Bridge.attach` immediately after
        construction.
    """

    bridge: Bridge
    sink: Sink
    seed_vectors: tuple[Vector, ...]
    seed_frames: tuple[str, ...]
    preamble: tuple[str, ...]
    queue: deque[_Slot] = field(default_factory=deque)
    coalescible: dict[tuple[str, str], _Slot] = field(default_factory=dict)
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    dropped_for_backlog: bool = False
    task: asyncio.Task[None] | None = None

    def send_control(self, frame: str) -> None:
        """Queue a bridge control frame for this browser alone.

        Parameters
        ----------
        frame : str
            The JSON control frame to send.
        """
        self.bridge._deliver(self, frame, None)

    def enqueue(self, frame: str, key: tuple[str, str] | None) -> None:
        """Append a frame, or fold it into the queued frame for the same key.

        Parameters
        ----------
        frame : str
            The JSON text to send.
        key : tuple of str or None
            The ``(device, name)`` this frame may coalesce onto. `None` always
            appends.
        """
        if key is not None:
            queued = self.coalescible.get(key)
            if queued is not None:
                # Replacing in place keeps the frame's position in the queue, so
                # ordering against everything else is untouched. INDI `set` is
                # last-writer-wins state, so only intermediate values are lost.
                queued.frame = frame
                return
        slot = _Slot(frame, key)
        self.queue.append(slot)
        if key is not None:
            self.coalescible[key] = slot
        self.ready.set()

    def invalidate(self, device: str, name: str | None) -> None:
        """Forget the coalescible slot(s) for a property, or for a whole device.

        Called for every ``def`` and ``del``: a later ``set`` folded into a slot
        sitting *ahead* of a queued retraction or redefinition would overtake it,
        and the browser would apply them out of order. This is the correctness
        condition the whole coalescing rests on.

        Parameters
        ----------
        device : str
            The device whose queued ``set`` frames may no longer be replaced.
        name : str or None
            The property, or `None` for a whole-device ``delProperty``, which
            takes every property the device had.
        """
        if name is None:
            for key in [key for key in self.coalescible if key[0] == device]:
                del self.coalescible[key]
            return
        self.coalescible.pop((device, name), None)

    def pop(self) -> str:
        """Remove and return the next queued frame.

        Returns
        -------
        frame : str
            The JSON text to send.
        """
        slot = self.queue.popleft()
        if slot.key is not None and self.coalescible.get(slot.key) is slot:
            del self.coalescible[slot.key]
        return slot.frame

    async def aclose(self) -> None:
        """Stop this subscription's pump and deregister it. Idempotent."""
        if self.task is None:
            return
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task
        # Not only the pump's `finally`: a task cancelled before its first step
        # never runs its body at all, so the bookkeeping has to happen here too.
        self.bridge._detach(self)


class Bridge:
    """Relay between one ``IndiClient`` and many browser WebSocket sinks.

    Parameters
    ----------
    client : IndiClient
        The shared upstream client the bridge relays.
    server : str, optional
        The server version stamped into every socket's ``hello`` frame; defaults
        to :data:`indi_nexus.__version__`. A parameter rather than a lookup at
        the send site so a test can pin it, and defaulted rather than required
        because every caller in and out of this repository wants the real one.
    message_history : int, optional
        How many recent INDI ``message`` frames to replay to a newly attached
        browser; defaults to :data:`_MESSAGE_HISTORY`.
    max_backlog : int, optional
        How many live frames a browser may fall behind by before it is dropped;
        defaults to :data:`_MAX_BACKLOG`.
    """

    def __init__(
        self,
        client: IndiClient,
        server: str = __version__,
        *,
        message_history: int = _MESSAGE_HISTORY,
        max_backlog: int = _MAX_BACKLOG,
    ) -> None:
        self._client = client
        self._hello = dump_frame(HelloFrame(server=server))
        self._subs: set[Subscription] = set()
        self._dropped_slow_sinks = 0
        self._max_backlog = max_backlog
        # INDI messages are transient (not part of the property cache), so keep a
        # bounded history to prime a newly-attached browser's log.
        self._messages: deque[str] = deque(maxlen=message_history)

    @property
    def client(self) -> IndiClient:
        """The upstream client this bridge relays."""
        return self._client

    @property
    def dropped_slow_sinks(self) -> int:
        """How many browsers have been dropped for falling too far behind.

        Surfaced on ``/health`` because a browser cannot tell an overflow drop
        from a network fault - both are a closed socket it reconnects from - so
        the diagnosis has to be readable server-side without scraping logs.
        """
        return self._dropped_slow_sinks

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
        """Stop every pump and close the upstream connection.

        A pump cancelled mid-send may leave a half-written socket; this is
        shutdown, and the route that owns the socket closes it in its own
        ``finally``.
        """
        subs = list(self._subs)
        for sub in subs:
            if sub.task is not None:
                sub.task.cancel()
        await asyncio.gather(
            *(sub.task for sub in subs if sub.task is not None), return_exceptions=True
        )
        await self._client.aclose()

    # -- subscribers -------------------------------------------------------- #
    def attach(self, sink: Sink) -> Subscription:
        """Register a browser and seed it with the current cache.

        **Synchronous on purpose, and it must stay that way.** Reading the cache,
        building the seed and joining the subscriber set happen with no ``await``
        between them, so the client's task cannot run in the middle and no event
        can be lost between the snapshot and the registration. ``create_task``
        only schedules, so the pump has not started when this returns.

        The seed holds vector *references*. The property store merges a ``set``
        into the cached vector in place, so a definition serialized at pump time
        may show a newer value than the property had at attach time. That
        converges rather than corrupts: the queued ``set`` frames were serialized
        eagerly, in order, and the last one always equals the current object, so
        the browser ends on the right value and only skips intermediate ones -
        which is what INDI ``set`` means anyway. A property deleted in the window
        arrives as its definition followed by the queued ``delProperty``, in that
        order.

        The ``hello`` frame leads, ahead of the seeded properties: it names the
        contract version everything after it is written in, so it cannot follow
        the frames a browser would need it to interpret.

        Parameters
        ----------
        sink : Sink
            An awaitable that sends one text frame to the browser.

        Returns
        -------
        subscription : Subscription
            The browser's handle; close it with
            :meth:`Subscription.aclose` when the socket goes away.
        """
        store = self._client.store
        sub = Subscription(
            bridge=self,
            sink=sink,
            seed_vectors=tuple(
                vector for device in store.devices() for vector in store.device(device).values()
            ),
            seed_frames=(*self._messages, self.connection_frame(self._client.connected)),
            preamble=(self._hello,),
        )
        self._subs.add(sub)
        sub.task = asyncio.create_task(self._pump(sub), name=f"bridge-sink-{id(sub):x}")
        return sub

    def sink_count(self) -> int:
        """Return how many browsers are currently attached.

        Returns
        -------
        count : int
            The number of live subscriptions.
        """
        return len(self._subs)

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
        return dump_frame(ConnectionFrame(connected=connected))

    @property
    def hello_frame(self) -> str:
        """The ``hello`` frame this bridge leads every socket with.

        Built once at construction: it is the same text for every browser, and
        the version it carries cannot change while the process runs.
        """
        return self._hello

    async def _pump(self, sub: Subscription) -> None:
        """Drain one browser's preamble and seed, then its queue until it ends.

        The order is the contract: ``hello``, then the cached properties, then
        the retained messages and the connection frame, then live traffic.

        This is where a failing socket is noticed. :meth:`_broadcast` no longer
        touches a socket and therefore cannot observe a failure, so the
        per-subscriber pump owns that too.

        Parameters
        ----------
        sub : Subscription
            The browser to serve.
        """
        try:
            for frame in sub.preamble:
                await sub.sink(frame)
            for vector in sub.seed_vectors:
                await sub.sink(to_json(DefVector(vector=vector)))
            for frame in sub.seed_frames:
                await sub.sink(frame)
            while True:
                while sub.queue:
                    await sub.sink(sub.pop())
                sub.ready.clear()
                await sub.ready.wait()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a broken socket ends this browser only
            logger.info("browser sink failed; dropping it", exc_info=True)
        finally:
            self._detach(sub)

    def _detach(self, sub: Subscription) -> None:
        """Forget a subscription and announce that it is over. Idempotent.

        Parameters
        ----------
        sub : Subscription
            The subscription to deregister.
        """
        self._subs.discard(sub)
        sub.closed.set()

    def _deliver(self, sub: Subscription, frame: str, key: tuple[str, str] | None) -> None:
        """Queue one frame for one browser, dropping it if it is too far behind.

        Parameters
        ----------
        sub : Subscription
            The browser to queue for.
        frame : str
            The JSON text to send.
        key : tuple of str or None
            The ``(device, name)`` this frame may coalesce onto.
        """
        if sub.closed.is_set():
            # Nothing will ever drain this one again, so queueing would only grow
            # a deque nobody reads and drop it a second time on the next frame.
            return
        sub.enqueue(frame, key)
        if len(sub.queue) > self._max_backlog:
            self._drop(sub)

    def _drop(self, sub: Subscription) -> None:
        """Drop a browser that has stopped keeping up.

        Parameters
        ----------
        sub : Subscription
            The browser to drop.
        """
        self._dropped_slow_sinks += 1
        sub.dropped_for_backlog = True
        logger.warning(
            "dropping browser sink %#x: %d frames queued past a backlog of %d (%d attached)",
            id(sub),
            len(sub.queue),
            self._max_backlog,
            len(self._subs),
        )
        # Deregister here rather than leaving it to the pump's `finally`: a pump
        # cancelled before its first step never runs its body, and a browser
        # that overran its backlog inside the same turn it attached in would
        # otherwise stay registered for ever with nothing serving it.
        self._detach(sub)
        if sub.task is not None:
            sub.task.cancel()

    # -- inbound (browser -> upstream) -------------------------------------- #
    async def handle_incoming(self, text: str, sub: Subscription | None = None) -> None:
        """Parse a browser frame and forward it upstream.

        A frame that cannot be parsed, that a client is not allowed to send, or
        that the upstream refuses is reported back to the browser that sent it as
        an ``{"event": "error"}`` control frame, and the socket stays open.
        Silence would be a regression: sends used to be queued for a later
        connection, so a browser that hears nothing has no reason not to assume
        its write landed.

        Parameters
        ----------
        text : str
            A JSON INDI message from the browser.
        sub : Subscription, optional
            The sender, so a rejection reaches it alone. `None` (a caller with
            no socket, e.g. a test) logs instead.
        """
        try:
            msg = from_json(text)
        except (ValueError, TypeError):
            logger.warning("dropping malformed inbound frame: %r", text[:200])
            self._reject(sub, "malformed", "frame is not a valid INDI message", None)
            return
        if not isinstance(msg, _CLIENT_TO_SERVER):
            logger.warning("dropping browser frame a client may not send: %s", type(msg).__name__)
            self._reject(sub, "not_permitted", "a client may not send this message", msg.tag)
            return
        try:
            if isinstance(msg, EnableBLOB):
                # Through enable_blob, not send: the client records the policy
                # there and replays it on every reconnect, so a browser's BLOB
                # subscription survives an upstream restart.
                await self._client.enable_blob(msg.device, msg.name, msg.policy)
            else:
                await self._client.send(msg)
        except NotConnectedError:
            # Named, not ConnectionError/OSError: both new types keep a builtin
            # base, and catching the base would swallow unrelated failures.
            detail = (
                "not connected to indiserver; the policy is stored and will apply on reconnect"
                if isinstance(msg, EnableBLOB)
                else "not connected to indiserver; the write was not sent"
            )
            self._reject(sub, "not_connected", detail, msg.tag)
        except SendQueueFull:
            logger.warning("upstream outbox full; dropping %s from a browser", type(msg).__name__)
            self._reject(
                sub, "upstream_busy", "the upstream queue is full; the write was not sent", msg.tag
            )

    def _reject(self, sub: Subscription | None, code: str, message: str, tag: str | None) -> None:
        """Tell one browser its frame did not go upstream.

        Parameters
        ----------
        sub : Subscription or None
            The browser to tell; `None` logs instead.
        code : str
            A stable machine-readable reason.
        message : str
            Human-readable detail for a UI log.
        tag : str or None
            The rejected message's INDI tag, when it parsed.
        """
        if sub is None:
            logger.info("rejected a browser frame with no subscription: %s (%s)", code, message)
            return
        sub.send_control(dump_frame(ErrorFrame(code=code, message=message, tag=tag)))

    # -- outbound (upstream -> browsers) ------------------------------------ #
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
        if event.type == "set" and event.vector is not None:
            # The one coalescible frame kind: a `set` is last-writer-wins state,
            # so a queued one may be replaced rather than followed. Only a `del`
            # ever arrives unnamed, but the key is built defensively rather than
            # asserted, because an unkeyed frame is merely uncoalesced.
            self._broadcast(
                to_json(SetVector(vector=event.vector)),
                coalesce=None if event.name is None else (event.device, event.name),
            )
            return
        if event.type == "def" and event.vector is not None:
            frame = to_json(DefVector(vector=event.vector))
        else:  # "del"
            frame = to_json(
                DelProperty(
                    device=event.device,
                    name=event.name,
                    timestamp=event.timestamp,
                    message=event.message,
                )
            )
        self._broadcast(frame, invalidate=(event.device, event.name))

    async def _on_message(self, message: Message) -> None:
        """Record an INDI log message and broadcast it to every browser.

        Parameters
        ----------
        message : Message
            The inbound message to relay.
        """
        frame = to_json(message)
        self._messages.append(frame)
        self._broadcast(frame)

    async def _on_connection(self, connected: bool) -> None:
        """Broadcast an upstream connection-state control frame.

        Parameters
        ----------
        connected : bool
            The new connection state.
        """
        self._broadcast(self.connection_frame(connected))

    def _broadcast(
        self,
        frame: str,
        *,
        coalesce: tuple[str, str] | None = None,
        invalidate: tuple[str, str | None] | None = None,
    ) -> None:
        """Queue a frame for every attached browser.

        **Synchronous on purpose**: this runs on the upstream client's task, so
        touching a socket here would let one browser's back-pressure stall the
        stream for everyone. :meth:`IndiClient._invoke` dispatches through
        ``inspect.isawaitable``, so returning `None` from the subscribers that
        call this is already supported.

        The two keyword arguments are exclusive and cover the two things a
        property frame can do to an already-queued one.

        Parameters
        ----------
        frame : str
            The text frame to send.
        coalesce : tuple of str, optional
            The ``(device, name)`` a queued ``set`` for the same property may be
            replaced under. Only a ``set`` passes this.
        invalidate : tuple, optional
            The ``(device, name)`` - ``name`` `None` for a whole device - whose
            queued ``set`` may no longer be replaced, because this frame is a
            ``def`` or a ``del`` that a later ``set`` must not overtake.
        """
        for sub in list(self._subs):
            if invalidate is not None:
                sub.invalidate(*invalidate)
            self._deliver(sub, frame, coalesce)
