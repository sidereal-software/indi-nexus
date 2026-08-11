"""``IndiClient``: a reconnecting async client for ``indiserver``.

The client is a TCP peer of the C ``indiserver`` (default port 7624). It keeps a
typed :class:`~indi_nexus.client.store.PropertyStore` up to date from the inbound
stream, lets application code watch for changes and wait on conditions, and sends
updates - always as M1 typed models, never raw XML.

Concurrency is plain :mod:`asyncio`: a background connection loop reconnects with
a fixed delay, and per connection a reader task folds inbound messages into the
store (dispatching to subscribers) while a writer task drains an outbox queue. The
transport is injectable (a ``connect`` coroutine returning ``read``/``write``/
``close`` callables) so tests drive the client over in-memory streams; the default
opens a real TCP connection via :func:`indi_nexus.transport.open_tcp`. The
``close`` callable is invoked whenever a connection ends - EOF, error, or
:meth:`IndiClient.aclose` - so the OS socket never lingers between reconnects.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from indi_nexus.client.store import PropertyEvent, PropertyStore, Subscriber
from indi_nexus.protocol import (
    BLOB,
    BLOBPolicy,
    BLOBVector,
    EnableBLOB,
    GetProperties,
    IndiMessage,
    ISState,
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
    to_xml,
)
from indi_nexus.transport import CloseFn, ReadFn, WriteFn, open_tcp

Connect = Callable[[], Awaitable[tuple[ReadFn, WriteFn, CloseFn]]]
MessageCallback = Callable[[Message], object]
ConnectionCallback = Callable[[bool], object]
Predicate = Callable[[Vector], bool]

_READ_CHUNK = 65536


def _coerce_switch(value: Any) -> ISState:
    """Coerce a switch value (``ISState``/``bool``/``"On"``/``"Off"``) to ISState.

    Parameters
    ----------
    value : ISState or bool or str
        The value to coerce.

    Returns
    -------
    state : ISState
        The corresponding switch state.
    """
    if isinstance(value, ISState):
        return value
    if isinstance(value, bool):
        return ISState.ON if value else ISState.OFF
    return ISState(value)


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
        self._outbox: asyncio.Queue[IndiMessage] = asyncio.Queue()
        self._message_subs: dict[int, MessageCallback] = {}
        self._conn_subs: dict[int, ConnectionCallback] = {}
        self._sub_ids = 0

        # Replayed on every (re)connect so the server re-sends what we care about.
        self._blob_policies: dict[tuple[str, str | None], EnableBLOB] = {}

        self._loop_task: asyncio.Task[None] | None = None
        self._closing = False
        self._connected = False
        self._ready = asyncio.Event()

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
        """Stop the connection loop and drop the connection."""
        self._closing = True
        if self._loop_task is not None:
            self._loop_task.cancel()
            await asyncio.gather(self._loop_task, return_exceptions=True)
            self._loop_task = None

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

    # -- connection loop --------------------------------------------------- #
    async def _connection_loop(self) -> None:
        """Connect, serve, and reconnect until :meth:`aclose` is called."""
        while not self._closing:
            try:
                read, write, close = await self._connect()
            except (OSError, TimeoutError):
                await asyncio.sleep(self._reconnect_delay)
                continue
            self._connected = True
            self._enqueue_handshake()
            self._ready.set()
            await self._dispatch_connection(True)
            try:
                await self._run_connection(read, write)
            except (OSError, ConnectionError):
                pass
            finally:
                self._connected = False
                # Always release the socket - on EOF, error, or cancellation via
                # aclose() - so the peer sees FIN instead of a half-open socket.
                with contextlib.suppress(OSError):
                    await close()
                await self._dispatch_connection(False)
            if self._closing:
                break
            await asyncio.sleep(self._reconnect_delay)

    def _enqueue_handshake(self) -> None:
        """Queue the messages sent on every (re)connect: enumerate + BLOB policies."""
        self._outbox.put_nowait(GetProperties())
        for policy in self._blob_policies.values():
            self._outbox.put_nowait(policy)

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

        Parameters
        ----------
        read : ReadFn
            The connection's inbound-byte callable.
        """
        parser = XMLStreamParser()
        while True:
            data = await read()
            if not data:
                return
            for msg in parser.feed(data):
                await self._handle(msg)

    async def _handle(self, msg: IndiMessage) -> None:
        """Fold one inbound message into the store and dispatch callbacks.

        Parameters
        ----------
        msg : IndiMessage
            The parsed inbound message.
        """
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
            await write(to_xml(msg) + b"\n")

    @staticmethod
    async def _invoke(callback: Callable[..., object], arg: object) -> None:
        """Call a callback, awaiting it if it returns a coroutine.

        Parameters
        ----------
        callback : Callable
            The sync or async callback to invoke.
        arg : object
            The single argument passed to the callback.
        """
        result = callback(arg)
        if inspect.isawaitable(result):
            await result

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
            The matching vector.

        Raises
        ------
        TimeoutError
            Raised if the timeout elapses first.
        """
        current = self._store.get(device, name)
        if current is not None and (predicate is None or predicate(current)):
            return current

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Vector] = loop.create_future()

        def on_event(event: PropertyEvent) -> None:
            """Resolve the future when a matching vector arrives."""
            vec = event.vector
            if vec is not None and not future.done() and (predicate is None or predicate(vec)):
                future.set_result(vec)

        unsubscribe = self._store.subscribe(on_event, device=device, name=name)
        try:
            if timeout is not None:
                async with asyncio.timeout(timeout):
                    return await future
            return await future
        finally:
            unsubscribe()

    # -- sends ------------------------------------------------------------- #
    async def send(self, msg: IndiMessage) -> None:
        """Queue an arbitrary message to send upstream.

        The typed helpers (:meth:`set_number`, :meth:`get_properties`, ...) cover
        the common cases; this forwards any already-built message - used by the
        web bridge to relay a browser-authored ``new*``/``getProperties``/
        ``enableBLOB`` frame verbatim.

        Parameters
        ----------
        msg : IndiMessage
            The message to send.
        """
        self._outbox.put_nowait(msg)

    async def _send(self, msg: IndiMessage) -> None:
        """Queue one message for the writer.

        Parameters
        ----------
        msg : IndiMessage
            The message to send.
        """
        self._outbox.put_nowait(msg)

    async def get_properties(self, device: str | None = None, name: str | None = None) -> None:
        """Ask the server to (re-)send property definitions.

        Parameters
        ----------
        device : str, optional
            Restrict to one device; `None` requests every device.
        name : str, optional
            Restrict to one property; `None` requests every property.
        """
        await self._send(GetProperties(device=device, name=name))

    async def enable_blob(
        self, device: str, name: str | None = None, policy: BLOBPolicy = BLOBPolicy.ALSO
    ) -> None:
        """Set the BLOB delivery policy for a device (or one property).

        The request is remembered and replayed on every reconnect.

        Parameters
        ----------
        device : str
            The device to set the policy for.
        name : str, optional
            Restrict to one property; `None` applies to the whole device.
        policy : BLOBPolicy, optional
            Whether BLOBs are never sent, sent alongside other updates, or sent
            exclusively.
        """
        msg = EnableBLOB(device=device, name=name, policy=policy)
        self._blob_policies[(device, name)] = msg
        await self._send(msg)

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
        await self._send(NewVector(vector=vector))

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
        await self._send(NewVector(vector=vector))

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
        elements = [Switch(name=k, value=_coerce_switch(v)) for k, v in values.items()]
        vector = SwitchVector(device=device, name=name, elements=elements)
        await self._send(NewVector(vector=vector))

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
        await self._send(NewVector(vector=BLOBVector(device=device, name=name, elements=elements)))

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
