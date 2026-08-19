"""``IndiClient``: a reconnecting async client for ``indiserver``.

The client is a TCP peer of the C ``indiserver`` (default port 7624). It keeps a
typed :class:`~indikit.client.store.PropertyStore` up to date from the inbound
stream, lets application code watch for changes and wait on conditions, and sends
updates - always as M1 typed models, never raw XML.

Concurrency is plain :mod:`asyncio`: a background connection loop reconnects with
a fixed delay, and per connection a reader task folds inbound messages into the
store (dispatching to subscribers) while a writer task drains an outbox queue. The
transport is injectable (a ``connect`` coroutine returning ``read``/``write``/
``close`` callables) so tests drive the client over in-memory streams; the default
opens a real TCP connection via :func:`indikit.transport.open_tcp`. The
``close`` callable is invoked whenever a connection ends - EOF, error, or
:meth:`IndiClient.aclose` - so the OS socket never lingers between reconnects.

Sending is deliberately *not* buffered across connections: a send with no live
connection raises :class:`~indikit.exceptions.NotConnectedError` and the
outbox is emptied whenever a connection ends, so nothing a caller issued while
``indiserver`` was away can be delivered to an instrument minutes later. See
:meth:`IndiClient.send`.

:attr:`IndiClient.stats` is the operational read of all of that - how long this
connection has been up, how many reconnects it took to get here, and what the
parser has made of the peer - and it is what ``/health`` reports.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from indikit.client.store import PropertyEvent, PropertyStore, Subscriber
from indikit.exceptions import NotConnectedError, SendQueueFull
from indikit.logging_config import log_wire
from indikit.protocol import (
    BLOB,
    BLOBPolicy,
    BLOBVector,
    EnableBLOB,
    GetProperties,
    IndiMessage,
    Message,
    NewVector,
    Number,
    NumberVector,
    Switch,
    SwitchVector,
    Text,
    TextVector,
    Vector,
    XMLStreamParser,
    coerce_switch,
    to_xml,
)
from indikit.transport import CloseFn, ReadFn, WriteFn, open_tcp

logger = logging.getLogger(__name__)

#: How many messages may sit in the outbox waiting for the writer. The queue
#: only ever holds traffic for the connection that is up right now (see
#: :meth:`IndiClient.send`), so this is not a buffer for a down server; it is a
#: guard against a socket that has stopped draining. A client that outruns its
#: writer by this much is not going to catch up, and for instrument control a
#: command that arrives late is worse than one that fails, so the overflow
#: raises :class:`~indikit.exceptions.SendQueueFull` instead of blocking.
_OUTBOX_MAXSIZE = 256

Connect = Callable[[], Awaitable[tuple[ReadFn, WriteFn, CloseFn]]]
MessageCallback = Callable[[Message], object]
ConnectionCallback = Callable[[bool], object]
Predicate = Callable[[Vector], bool]


@dataclass(frozen=True, slots=True)
class ClientStats:
    """A point-in-time read of one client's upstream link and its parser.

    Taken as a snapshot rather than exposed as live attributes, so a caller that
    reports several of these fields - ``/health`` does - reports them all as of
    one instant.

    Attributes
    ----------
    connected : bool
        Whether there is a live connection right now.
    uptime_seconds : float or None
        How long the **current** connection has been up, and `None` while there
        is none. It is deliberately not the process's uptime: a container
        runtime already reports that, and everything else here is about the
        upstream link. It resets on every reconnect.
    reconnects : int
        How many times a connection has been **successfully** re-established
        since the client started; the first connection is not a reconnect. Failed
        attempts are not counted, so a rising number means the link is genuinely
        flapping, while a bridge that has never reached ``indiserver`` at all
        reports ``0`` with ``connected`` false - which already tells that story.
    last_message_age_seconds : float or None
        Seconds since an INDI message was last **parsed**, and `None` if none
        ever has been. It measures parsed messages rather than received bytes,
        because :attr:`bytes_since_last_message` already answers the byte
        question and the two must stay distinct: a peer dribbling malformed bytes
        must not read as healthy here. It is not reset by a reconnect - it is the
        age of the last thing this client understood, whichever connection
        carried it.
    dropped : int
        Top-level elements this connection's parser discarded because a value
        would not parse. Before the first connection, and while the client has
        never had one, this is ``0``.
    resets : int
        Times this connection's parser had to reopen its synthetic document. A
        framing signal, not a loss count. ``0`` before the first connection.
    bytes_since_last_message : int
        Bytes fed to this connection's parser since a message last came out of
        it. ``0`` before the first connection.
    dropped_total : int
        :attr:`dropped` summed over every connection since the client started,
        including the current one. This is the field that answers "has this ever
        happened", which the per-connection counters discard on every reconnect.
    resets_total : int
        :attr:`resets` summed over every connection since the client started,
        including the current one.
    """

    connected: bool
    uptime_seconds: float | None
    reconnects: int
    last_message_age_seconds: float | None
    dropped: int
    resets: int
    bytes_since_last_message: int
    dropped_total: int
    resets_total: int


class IndiClient:
    """A reconnecting client that mirrors ``indiserver`` state into a cache.

    Parameters
    ----------
    host : str, optional
        The ``indiserver`` host.
    port : int, optional
        The ``indiserver`` TCP port (7624 by default).
    connect_timeout : float, optional
        Seconds to wait for each connection attempt.
    reconnect_delay : float, optional
        Seconds to wait between a lost connection and the next attempt.
    connect : Connect, optional
        Injectable connection factory returning ``(read, write, close)``
        callables; used by tests. Defaults to a real TCP connection to
        ``host``/``port``.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 7624,
        *,
        connect_timeout: float = 10.0,
        reconnect_delay: float = 2.0,
        connect: Connect | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._connect_timeout = connect_timeout
        self._reconnect_delay = reconnect_delay
        self._connect = connect or self._default_connect

        self._store = PropertyStore()
        self._outbox: asyncio.Queue[IndiMessage] = asyncio.Queue(maxsize=_OUTBOX_MAXSIZE)
        self._message_subs: dict[int, MessageCallback] = {}
        self._conn_subs: dict[int, ConnectionCallback] = {}
        self._sub_ids = 0
        # Every future wait_for() is parked on, and what it is waiting for, so
        # aclose() can tell them the answer is never coming.
        self._waiters: dict[asyncio.Future[Vector], str] = {}

        # Replayed on every (re)connect so the server re-sends what we care about.
        self._blob_policies: dict[tuple[str, str | None], EnableBLOB] = {}

        self._loop_task: asyncio.Task[None] | None = None
        self._closing = False
        self._connected = False
        self._ready = asyncio.Event()

        # This connection's parser, `None` until the first one is established.
        # Reassigned per connection by _new_parser(); never reused across one.
        self._parser: XMLStreamParser | None = None
        # Every *earlier* parser's counters, folded in as each new one is made.
        # `self._parser`'s own counters are added at read time (see `stats`), so
        # the totals include the connection that is happening right now and stay
        # right after aclose(), when there is no next fold.
        self._dropped_total = 0
        self._resets_total = 0
        # Connections established, so reconnects = this - 1. Counting
        # establishments rather than reconnects keeps the increment
        # unconditional at the one site a connection comes up.
        self._connections = 0
        self._connected_at: float | None = None
        self._last_message_at: float | None = None

    # -- lifecycle --------------------------------------------------------- #
    async def _default_connect(self) -> tuple[ReadFn, WriteFn, CloseFn]:
        """Open the default TCP connection to the configured host and port."""
        return await open_tcp(self._host, self._port, connect_timeout=self._connect_timeout)

    async def start(self, *, wait: bool = True) -> None:
        """Start the background connection loop.

        Parameters
        ----------
        wait : bool, optional
            Whether to block until the first connection succeeds. Scripts and
            monitors want that. A long-running server that must stay responsive
            while ``indiserver`` is down passes `False` and watches
            :meth:`on_connection` instead; the loop keeps retrying either way.
        """
        if self._loop_task is None:
            self._loop_task = asyncio.create_task(self._connection_loop())
        if wait:
            await self._ready.wait()

    async def aclose(self) -> None:
        """Stop the connection loop, drop the connection, and fail the waiters.

        Every :meth:`wait_for` still parked on its future is resolved with
        :class:`~indikit.exceptions.NotConnectedError`, because nothing will
        ever read the socket again: without that, a wait with no timeout hangs
        for good and a wait with one sits out its full timeout to learn what the
        client already knows.
        """
        self._closing = True
        if self._loop_task is not None:
            self._loop_task.cancel()
            await asyncio.gather(self._loop_task, return_exceptions=True)
            self._loop_task = None
        self._fail_waiters()

    def _fail_waiters(self) -> None:
        """Resolve every pending :meth:`wait_for` future with a closed error."""
        for future, label in self._waiters.items():
            if not future.done():
                future.set_exception(NotConnectedError(f"client closed while waiting for {label}"))
        self._waiters.clear()

    async def __aenter__(self) -> IndiClient:
        """Start the client and return it once initially connected."""
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Close the client on context exit."""
        await self.aclose()

    @property
    def connected(self) -> bool:
        """Whether the client currently has a live connection."""
        return self._connected

    @property
    def stats(self) -> ClientStats:
        """A snapshot of the upstream link and this connection's parser.

        Cheap: it reads counters, so an endpoint may call it per request.

        Returns
        -------
        stats : ClientStats
            The current statistics; see that class for what each field means
            and what it reports while disconnected.
        """
        now = time.monotonic()
        parser = self._parser
        # No parser means no connection has ever been established, so every
        # parser-derived number is genuinely zero rather than unknown. `/health`
        # is reachable in that state, because the bridge starts with
        # `start(wait=False)`.
        dropped = 0 if parser is None else parser.dropped
        resets = 0 if parser is None else parser.resets
        pending = 0 if parser is None else parser.bytes_since_last_message
        return ClientStats(
            connected=self._connected,
            uptime_seconds=None if self._connected_at is None else now - self._connected_at,
            reconnects=max(self._connections - 1, 0),
            last_message_age_seconds=(
                None if self._last_message_at is None else now - self._last_message_at
            ),
            dropped=dropped,
            resets=resets,
            bytes_since_last_message=pending,
            # The live parser is added here rather than folded when it retires,
            # so the totals cover the connection in progress. Folding only on
            # retirement left `dropped_total` short of `dropped` for the whole
            # life of every connection, and permanently short after aclose().
            dropped_total=self._dropped_total + dropped,
            resets_total=self._resets_total + resets,
        )

    # -- connection loop --------------------------------------------------- #
    async def _connection_loop(self) -> None:
        """Connect, serve, and reconnect until :meth:`aclose` is called.

        This task is the whole engine: if it stops, nothing reads and nothing
        reconnects, and the client goes on reporting whatever it last cached. So
        an unexpected failure is logged rather than dying quietly in a task
        nobody awaits. It is re-raised rather than retried - a loop that retries
        a failure it does not understand can spin hot forever.
        """
        try:
            while not self._closing:
                try:
                    read, write, close = await self._connect()
                except (OSError, TimeoutError):
                    await asyncio.sleep(self._reconnect_delay)
                    continue
                self._connected = True
                self._connections += 1
                self._connected_at = time.monotonic()
                self._enqueue_handshake()
                self._ready.set()
                await self._dispatch_connection(True)
                try:
                    await self._run_connection(read, write)
                except OSError:  # ConnectionError is an OSError subclass
                    pass
                finally:
                    self._connected = False
                    self._connected_at = None
                    # Whatever is still queued was addressed to the connection
                    # that just died. Delivering it on the next one is the
                    # failure this whole guard exists to prevent - a slew or an
                    # exposure landing on hardware whose state has moved on - so
                    # it is dropped here, and send() refuses to add more until a
                    # connection is up again.
                    self._drain_outbox()
                    # Always release the socket - on EOF, error, or cancellation
                    # via aclose() - so the peer sees FIN, not a half-open socket.
                    with contextlib.suppress(OSError):
                        await close()
                    await self._dispatch_connection(False)
                if self._closing:
                    break
                await asyncio.sleep(self._reconnect_delay)
        except asyncio.CancelledError:
            raise  # aclose() cancels us; that is not a failure
        except Exception:
            logger.exception("indi client connection loop stopped")
            raise

    def _enqueue_handshake(self) -> None:
        """Queue the messages sent on every (re)connect: enumerate + BLOB policies.

        These go straight to the outbox rather than through :meth:`send`. They
        are per-*connection* state, not a user's command: they describe what
        this client wants the connection it has just opened to look like. The
        outbox was emptied when the previous connection ended and this is one
        message plus one per recorded BLOB policy - a policy per device on the
        hub, an order of magnitude under :data:`_OUTBOX_MAXSIZE` - so there is
        room for it.
        """
        self._outbox.put_nowait(GetProperties())
        for policy in self._blob_policies.values():
            self._outbox.put_nowait(policy)

    def _drain_outbox(self) -> None:
        """Discard everything queued for a connection that has ended."""
        while True:
            try:
                self._outbox.get_nowait()
            except asyncio.QueueEmpty:
                return

    async def _run_connection(self, read: ReadFn, write: WriteFn) -> None:
        """Run the reader and writer for one connection until it ends.

        Parameters
        ----------
        read : ReadFn
            The connection's inbound-byte callable.
        write : WriteFn
            The connection's outbound-byte callable.
        """
        writer_task = asyncio.create_task(self._writer_loop(write))
        try:
            await self._reader_loop(read)
        finally:
            writer_task.cancel()
            await asyncio.gather(writer_task, return_exceptions=True)

    async def _reader_loop(self, read: ReadFn) -> None:
        """Read, frame, and dispatch inbound messages until EOF.

        Returning ends the connection, which the loop above then re-establishes.
        A parser that has stopped producing messages while the peer keeps
        sending is treated as an ended connection for exactly that reason: a
        reconnect is the client's way of getting a fresh parser and a server
        that re-sends every definition.

        The parser's counters describe the connection, so they go out with it:
        the warning reports what this connection saw before it went quiet, since
        the next one starts a parser - and a history - from scratch. The running
        totals on :attr:`stats` are what survive.

        Parameters
        ----------
        read : ReadFn
            The connection's inbound-byte callable.
        """
        parser = self._new_parser()
        while True:
            data = await read()
            if not data:
                return
            for msg in parser.feed(data):
                await self._handle(msg)
            if parser.stalled:
                logger.warning(
                    "no message parsed in %d bytes from %s:%d "
                    "(%d dropped, %d resets on this connection); reconnecting to resync",
                    parser.bytes_since_last_message,
                    self._host,
                    self._port,
                    parser.dropped,
                    parser.resets,
                )
                return

    def _new_parser(self) -> XMLStreamParser:
        """Retire this connection's parser and start the next connection's.

        **A fresh parser per connection is the point.** The stall path
        (:attr:`XMLStreamParser.stalled`) ends the connection precisely so the
        reconnect hands it a parser with no half-open document in it, so keeping
        one for the client's lifetime would leave the stall recovering nothing -
        silently, and only against a peer that has actually gone mute. Holding
        it on ``self`` for :attr:`stats` to read must not quietly become that,
        which is why the assignment lives here, at the top of every
        :meth:`_reader_loop`, and nowhere else.

        The retiring parser's counters are folded into the running totals as it
        goes, because nothing else will ever see that object again.

        Returns
        -------
        parser : XMLStreamParser
            The new connection's parser, also stored as ``self._parser``.
        """
        if self._parser is not None:
            self._dropped_total += self._parser.dropped
            self._resets_total += self._parser.resets
        self._parser = XMLStreamParser()
        return self._parser

    async def _handle(self, msg: IndiMessage) -> None:
        """Fold one inbound message into the store and dispatch callbacks.

        Parameters
        ----------
        msg : IndiMessage
            The parsed inbound message.
        """
        # Stamped here, on a *parsed* message, not where bytes arrive: the
        # parser's own bytes_since_last_message covers the byte question, and a
        # peer sending nothing but junk must not look healthy on this one.
        self._last_message_at = time.monotonic()
        log_wire("<-", msg)
        event = self._store.apply(msg)
        if event is not None:
            for callback in self._store.matching(event):
                await self._invoke(callback, event)
        if isinstance(msg, Message):
            for mcb in list(self._message_subs.values()):
                await self._invoke(mcb, msg)

    async def _writer_loop(self, write: WriteFn) -> None:
        """Drain the outbox to the connection's writer until cancelled.

        Parameters
        ----------
        write : WriteFn
            The connection's outbound-byte callable.
        """
        while True:
            msg = await self._outbox.get()
            data = to_xml(msg) + b"\n"
            log_wire("->", msg, len(data))
            await write(data)

    @staticmethod
    async def _invoke(callback: Callable[..., object], arg: object) -> None:
        """Call a callback, awaiting it if it returns a coroutine.

        Every dispatch to application code funnels through here, which is why
        the isolation lives here: a subscriber that raises would otherwise come
        up through the reader and take the connection with it, so one bad
        callback would look exactly like a dropped server.
        :class:`asyncio.CancelledError` is a :class:`BaseException`, so
        :meth:`aclose`'s cancellation still propagates.

        Parameters
        ----------
        callback : Callable
            The sync or async callback to invoke.
        arg : object
            The single argument passed to the callback.
        """
        try:
            result = callback(arg)
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001 - deliberate per-callback isolation
            logger.exception("indi client subscriber %r failed", callback)

    async def _dispatch_connection(self, up: bool) -> None:
        """Notify connection-state subscribers of a transition.

        Parameters
        ----------
        up : bool
            `True` when a connection was established, `False` when it was lost.
        """
        for ccb in list(self._conn_subs.values()):
            await self._invoke(ccb, up)

    # -- reads (delegate to the store) ------------------------------------- #
    def get(self, device: str, name: str) -> Vector | None:
        """Return a cached vector, or `None` if it is not present.

        Parameters
        ----------
        device : str
            The device name.
        name : str
            The property name.

        Returns
        -------
        vector : Vector or None
            The cached vector, or `None`.
        """
        return self._store.get(device, name)

    @property
    def store(self) -> PropertyStore:
        """The underlying property cache."""
        return self._store

    def __getitem__(self, device: str) -> Any:
        """Return the cached properties of one device."""
        return self._store[device]

    # -- subscriptions ----------------------------------------------------- #
    def subscribe(
        self, callback: Subscriber, *, device: str | None = None, name: str | None = None
    ) -> Callable[[], None]:
        """Register a property-event callback (see :meth:`PropertyStore.subscribe`).

        Parameters
        ----------
        callback : Subscriber
            Called with each matching :class:`PropertyEvent`; may be sync or async.
        device : str, optional
            Restrict to one device; `None` matches every device.
        name : str, optional
            Restrict to one property; `None` matches every property.

        Returns
        -------
        unsubscribe : Callable
            Call with no arguments to remove the subscription.
        """
        return self._store.subscribe(callback, device=device, name=name)

    def on_message(self, callback: MessageCallback) -> Callable[[], None]:
        """Register a callback for inbound ``message`` notifications.

        Parameters
        ----------
        callback : Callable
            Called with each inbound :class:`Message`; may be sync or async.

        Returns
        -------
        unsubscribe : Callable
            Call with no arguments to remove the subscription.
        """
        return self._register(self._message_subs, callback)

    def on_connection(self, callback: ConnectionCallback) -> Callable[[], None]:
        """Register a callback for connect/disconnect transitions.

        Parameters
        ----------
        callback : Callable
            Called with `True` on connect and `False` on disconnect; may be async.

        Returns
        -------
        unsubscribe : Callable
            Call with no arguments to remove the subscription.
        """
        return self._register(self._conn_subs, callback)

    def _register(self, registry: dict[int, Any], callback: Any) -> Callable[[], None]:
        """Add a callback to a registry and return its unsubscribe handle.

        Parameters
        ----------
        registry : dict
            The subscriber registry to add to.
        callback : Callable
            The callback to register.

        Returns
        -------
        unsubscribe : Callable
            Call with no arguments to remove the subscription.
        """
        token = self._sub_ids
        self._sub_ids += 1
        registry[token] = callback

        def unsubscribe() -> None:
            """Remove this subscription."""
            registry.pop(token, None)

        return unsubscribe

    async def wait_for(
        self,
        device: str,
        name: str,
        predicate: Predicate | None = None,
        *,
        timeout: float | None = None,  # noqa: ASYNC109 - public API mirrors asyncio.wait_for
    ) -> Vector:
        """Wait until a property exists (and satisfies ``predicate``).

        Resolves immediately if the cached property already matches.

        What comes back is a **snapshot**, detached from the cache: the vector
        as it was at the instant the predicate held. The cached vector is
        mutated in place by every later ``set``, and a whole TCP chunk's worth
        of messages is folded in before the reader yields, so a property that
        goes ``Busy``, ``Ok``, ``Busy`` inside one chunk would satisfy a
        ``state == OK`` wait and then read back ``Busy`` to the coroutine that
        was waiting on it. Read the live vector through :meth:`get` when that is
        what you want.

        Parameters
        ----------
        device : str
            The device name.
        name : str
            The property name.
        predicate : Predicate, optional
            Called with the vector; the wait resolves when it returns `True`.
            Defaults to "exists".
        timeout : float, optional
            Seconds to wait before raising ``TimeoutError``.

        Returns
        -------
        vector : Vector
            A detached copy of the matching vector, as it was when it matched.

        Raises
        ------
        TimeoutError
            Raised if the timeout elapses first.
        NotConnectedError
            Raised if :meth:`aclose` is called while the wait is still parked.
        """
        current = self._store.get(device, name)
        if current is not None and (predicate is None or predicate(current)):
            return current.detached()

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Vector] = loop.create_future()

        def on_event(event: PropertyEvent) -> None:
            """Resolve the future with a copy of the vector that matched."""
            vec = event.vector
            if vec is not None and not future.done() and (predicate is None or predicate(vec)):
                # Copy here, not at the await: the predicate was true of this
                # object one line ago and may not be by the time the waiting
                # coroutine is scheduled.
                future.set_result(vec.detached())

        unsubscribe = self._store.subscribe(on_event, device=device, name=name)
        self._waiters[future] = f"{device}.{name}"
        try:
            if timeout is not None:
                async with asyncio.timeout(timeout):
                    return await future
            return await future
        finally:
            unsubscribe()
            self._waiters.pop(future, None)

    # -- sends ------------------------------------------------------------- #
    async def send(self, msg: IndiMessage) -> None:
        """Hand one message to the live connection's writer.

        The typed helpers (:meth:`set_number`, :meth:`get_properties`, ...) cover
        the common cases; this forwards any already-built message - used by the
        web bridge to relay a browser-authored ``new*``/``getProperties``/
        ``enableBLOB`` frame verbatim.

        **A send with no connection fails; it is never held.** This is
        instrument control: a command queued while ``indiserver`` is down would
        be delivered whenever the hub came back, minutes or hours later, to
        hardware whose state has nothing to do with the one the caller was
        reasoning about. Every send routes through here, so every one of them
        either reaches a live connection or raises. Callers that want to wait
        for the link instead can watch :meth:`on_connection`.

        Parameters
        ----------
        msg : IndiMessage
            The message to send.

        Raises
        ------
        NotConnectedError
            Raised if there is no live connection to ``indiserver``. Also a
            ConnectionError.
        SendQueueFull
            Raised if the outbox is full because the connection has stopped
            draining it. Also a RuntimeError.
        """
        if not self._connected:
            raise NotConnectedError(
                f"not connected to {self._host}:{self._port}; {type(msg).__name__} was not sent"
            )
        try:
            self._outbox.put_nowait(msg)
        except asyncio.QueueFull:
            raise SendQueueFull(
                f"outbox to {self._host}:{self._port} is full "
                f"({_OUTBOX_MAXSIZE} messages); {type(msg).__name__} was not sent"
            ) from None

    async def get_properties(self, device: str | None = None, name: str | None = None) -> None:
        """Ask the server to (re-)send property definitions.

        Parameters
        ----------
        device : str, optional
            Restrict to one device; `None` requests every device.
        name : str, optional
            Restrict to one property; `None` requests every property.
        """
        await self.send(GetProperties(device=device, name=name))

    async def enable_blob(
        self, device: str, name: str | None = None, policy: BLOBPolicy = BLOBPolicy.ALSO
    ) -> None:
        """Set the BLOB delivery policy for a device (or one property).

        The request is remembered and replayed on every reconnect.

        **The policy is recorded even when the send fails.** Unlike every other
        send here, this is not a command to an instrument: it is a standing
        subscription preference, idempotent, and already part of what the
        client replays onto each new connection. Recording it while
        disconnected is therefore the same statement as recording it while
        connected - "BLOBs from this device, please" - and the next connection
        honours it. The raise still happens, because nothing went out now, so a
        caller that wants to know the request reached the server can act on it;
        a caller that just wants BLOBs when the hub returns can ignore it.

        Parameters
        ----------
        device : str
            The device to set the policy for.
        name : str, optional
            Restrict to one property; `None` applies to the whole device.
        policy : BLOBPolicy, optional
            Whether BLOBs are never sent, sent alongside other updates, or sent
            exclusively.

        Raises
        ------
        NotConnectedError
            Raised if there is no live connection; the policy is remembered
            regardless.
        """
        msg = EnableBLOB(device=device, name=name, policy=policy)
        self._blob_policies[(device, name)] = msg
        await self.send(msg)

    async def set_number(self, device: str, name: str, values: dict[str, float]) -> None:
        """Send new number values for a property.

        Parameters
        ----------
        device : str
            The device name.
        name : str
            The property name.
        values : dict
            Mapping of element name to numeric value.
        """
        elements = [Number(name=k, value=v) for k, v in values.items()]
        vector = NumberVector(device=device, name=name, elements=elements)
        await self.send(NewVector(vector=vector))

    async def set_text(self, device: str, name: str, values: dict[str, str]) -> None:
        """Send new text values for a property.

        Parameters
        ----------
        device : str
            The device name.
        name : str
            The property name.
        values : dict
            Mapping of element name to string value.
        """
        elements = [Text(name=k, value=v) for k, v in values.items()]
        vector = TextVector(device=device, name=name, elements=elements)
        await self.send(NewVector(vector=vector))

    async def set_switch(self, device: str, name: str, values: dict[str, Any]) -> None:
        """Send new switch states for a property.

        Parameters
        ----------
        device : str
            The device name.
        name : str
            The property name.
        values : dict
            Mapping of element name to state (``ISState``, ``bool``, or ``"On"`` /
            ``"Off"``).
        """
        elements = [Switch(name=k, value=coerce_switch(v)) for k, v in values.items()]
        vector = SwitchVector(device=device, name=name, elements=elements)
        await self.send(NewVector(vector=vector))

    async def set_blob(self, device: str, name: str, values: dict[str, bytes]) -> None:
        """Send new BLOB payloads for a property.

        Parameters
        ----------
        device : str
            The device name.
        name : str
            The property name.
        values : dict
            Mapping of element name to raw ``bytes`` payload.
        """
        elements = [BLOB(name=k, data=v, size=len(v)) for k, v in values.items()]
        await self.send(NewVector(vector=BLOBVector(device=device, name=name, elements=elements)))

    def run(self) -> None:
        """Connect and process the stream until interrupted (blocking).

        A convenience entrypoint for scripts and monitors: register subscriptions
        first, then call this. Returns on ``KeyboardInterrupt``.
        """

        async def _serve() -> None:
            """Start the client and block until cancelled."""
            await self.start()
            try:
                await asyncio.Event().wait()
            finally:
                await self.aclose()

        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(_serve())
