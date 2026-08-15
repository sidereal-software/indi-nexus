"""The ``Device`` base class - what a driver author subclasses.

A driver is a subclass of :class:`Device` that

* defines its properties in :meth:`Device.setup` (called once, when a client
  first asks what this device exposes),
* pushes updates through the :class:`BoundProperty` handles that ``define_*``
  returns - typically from ``@every`` polling jobs,
* and handles client writes with ``@on_new`` methods.

The vocabulary is plain Python rather than the libindi C surface (``IUFind``,
``IDSetNumber``, ``IEAddTimer``).
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import inspect
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, cast

from indi_nexus.driver.dispatch import iter_new_handlers, on_new
from indi_nexus.driver.property import BoundProperty, EmitPolicy
from indi_nexus.protocol import (
    BLOB,
    BLOBVector,
    GetProperties,
    IndiMessage,
    IPerm,
    IPState,
    ISRule,
    ISState,
    Light,
    LightVector,
    Message,
    Number,
    NumberVector,
    Switch,
    SwitchVector,
    Text,
    TextVector,
    Vector,
    indi_now,
)

Emit = Callable[[IndiMessage], None]
NewHandler = Callable[[Vector], object]


class Device:
    """Base class for an INDI driver device.

    Subclass it, set :attr:`name` (optional; defaults to the class name), and
    override :meth:`setup`.

    Attributes
    ----------
    name : str
        Class attribute; override to set the INDI device name. Empty means "use
        the class name".
    serialize_dispatch : bool
        Class attribute; whether periodic ticks and client writes are run under
        a per-device lock so they never interleave. On by default.
    """

    #: Override to set the INDI device name. Empty means "use the class name".
    name: str = ""

    #: Whether ``@every`` ticks and ``@on_new`` handlers are mutually excluded.
    #:
    #: A tick that awaits - and any tick that talks to hardware should, via
    #: :meth:`off_thread` - yields the event loop mid-flight, so without this a
    #: client write can land between a tick's read and the properties it
    #: publishes from that read. The tick then overwrites the write's effect
    #: with state gathered *before* it: a button springs back out, a target
    #: reverts. The lock is held across the whole tick and the whole handler, so
    #: each sees a settled device; it also serialises hardware access, which a
    #: single serial port or socket wants anyway. The cost is that a client
    #: write waits for an in-flight tick - usually the correct trade.
    #:
    #: Set to `False` for a device whose ticks and handlers provably do not
    #: share state, or one that must answer writes during a long tick.
    serialize_dispatch: bool = True

    def __init__(self, name: str | None = None) -> None:
        """Initialise the device and discover its ``@on_new`` handlers.

        Parameters
        ----------
        name : str, optional
            Instance-level device name override. Falls back to the class
            :attr:`name`, then to the class name.
        """
        self._device = name or type(self).name or type(self).__name__
        self._properties: dict[str, BoundProperty[Any]] = {}
        # iter_new_handlers walks the MRO subclass-first, so keep the *first*
        # handler per property name: a subclass @on_new shadows any base-class
        # handler for the same property (e.g. the built-in CONNECTION one).
        self._new_handlers: dict[str, NewHandler] = {}
        for prop_name, method in iter_new_handlers(self):
            self._new_handlers.setdefault(prop_name, method)
        self._emit: Emit | None = None
        self._setup_done = False
        # Set once setup() has run; periodic (@every) jobs wait on it so they
        # never touch a property before setup() defines it.
        self._setup_complete = asyncio.Event()
        # Guards ticks against handlers; see the serialize_dispatch docstring.
        self._dispatch_lock = asyncio.Lock()

    # -- identity ---------------------------------------------------------- #
    @property
    def device(self) -> str:
        """The resolved INDI device name."""
        return self._device

    def __repr__(self) -> str:
        """Return a debug representation naming the class and device."""
        return f"<{type(self).__name__} device={self._device!r}>"

    # -- lifecycle hooks (override these) ---------------------------------- #
    async def setup(self) -> None:
        """Define the device's properties. Called once, on first ``getProperties``.

        Override and call ``self.define_*`` here. The base implementation does
        nothing.
        """

    async def on_new_default(self, vector: Vector) -> None:
        """Handle a client write to a property with no ``@on_new`` handler.

        The default is to ignore it. Override for a catch-all.

        Parameters
        ----------
        vector : Vector
            The parsed vector the client asked to change.
        """

    async def on_connect(self) -> None:
        """Open the device's link. Called when a client turns CONNECT on.

        Override to open your serial/network connection and define any
        properties that only exist while connected. The base implementation
        does nothing. Only used with :meth:`define_connection`.
        """

    async def on_disconnect(self) -> None:
        """Close the device's link. Called when a client turns DISCONNECT on.

        Override to halt motion and close your serial/network connection. The
        base implementation does nothing. Only used with
        :meth:`define_connection`.
        """

    # -- connection --------------------------------------------------------- #
    def define_connection(
        self, *, label: str = "Connection", group: str = "Main Control"
    ) -> BoundProperty[SwitchVector]:
        """Define the standard INDI ``CONNECTION`` switch (initially off).

        Call this first in :meth:`setup` and the device gains the standard
        connect/disconnect lifecycle for free: the built-in handler flips the
        switch, calls :meth:`on_connect`/:meth:`on_disconnect`, and announces
        the transition; :attr:`connected` and :meth:`require_connected` read
        the state, and ``@every(..., when_connected=True)`` jobs pause while
        disconnected. (libindi's ``INDI::DefaultDevice`` provides the same
        property implicitly; here it is one explicit line.)

        Parameters
        ----------
        label : str, optional
            The property label shown by clients.
        group : str, optional
            The property group (tab) shown by clients.

        Returns
        -------
        prop : BoundProperty
            The handle for the CONNECTION property.
        """
        return self.define_switch(
            "CONNECTION",
            [
                Switch(name="CONNECT", label="Connect", value=ISState.OFF),
                Switch(name="DISCONNECT", label="Disconnect", value=ISState.ON),
            ],
            rule=ISRule.ONE_OF_MANY,
            label=label,
            group=group,
        )

    @property
    def connected(self) -> bool:
        """Whether the device link is up.

        `True` when the ``CONNECTION`` switch is on - or always, for a device
        that has no ``CONNECTION`` property (no connection semantics).
        """
        prop = self._properties.get("CONNECTION")
        if prop is None:
            return True
        return prop.vector.get("CONNECT") is ISState.ON

    def require_connected(self) -> bool:
        """Return whether commands may run, logging the standard error if not.

        The one-line guard for ``@on_new`` handlers::

            if not self.require_connected():
                return

        Returns
        -------
        allowed : bool
            `True` when connected (or connection-less); otherwise `False`
            after sending the standard "not connected" error message.
        """
        if self.connected:
            return True
        self.log_error(f"{self._device} is not connected.")
        return False

    @on_new("CONNECTION")
    async def _on_connection_write(self, vector: SwitchVector) -> None:
        """Apply a client's connect/disconnect request (built-in handler).

        Flips the switch, runs the :meth:`on_connect`/:meth:`on_disconnect`
        hook, and announces the transition. A hook that raises - the usual way
        for hardware to report that it is not there - rolls the switch back and
        leaves the property in ``Alert`` with the reason attached, so the device
        never sits claiming a link it does not have. A subclass
        ``@on_new("CONNECTION")`` handler shadows this entirely; a device without
        a ``CONNECTION`` property falls through to :meth:`on_new_default`.
        """
        if "CONNECTION" not in self:
            await self.on_new_default(vector)
            return
        connect = vector.selected() == "CONNECT"
        prop = self._properties["CONNECTION"]
        member = "CONNECT" if connect else "DISCONNECT"
        prop.set({member: ISState.ON}, state=IPState.BUSY)
        try:
            await (self.on_connect() if connect else self.on_disconnect())
        except Exception as exc:  # noqa: BLE001 - reported to the client below
            rollback = "DISCONNECT" if connect else "CONNECT"
            prop.set({rollback: ISState.ON}, state=IPState.ALERT)
            self.log_error(f"{self._device} failed to {member.lower()}: {exc}")
            return
        prop.set(state=IPState.OK)
        self.message(f"{self._device} is {'connected' if connect else 'disconnected'}.")

    # -- property definition ---------------------------------------------- #
    def define[VectorT: Vector](
        self, vector: VectorT, *, emit: EmitPolicy = "always"
    ) -> BoundProperty[VectorT]:
        """Register a property vector, emit its ``def``, and return its handle.

        Parameters
        ----------
        vector : VectorT
            The vector to define. If its ``device`` is unset, this device's name
            is filled in.
        emit : str, optional
            When later ``set`` calls reach the wire; see
            `~indi_nexus.driver.property.EmitPolicy`.

        Returns
        -------
        prop : BoundProperty
            The handle used to push later updates for this property, typed by
            the vector kind that was defined.
        """
        if not vector.device:
            vector.device = self._device
        prop = BoundProperty(vector, self._send, policy=emit)
        self._properties[vector.name] = prop
        prop._announce()
        return prop

    def define_number(
        self,
        name: str,
        elements: list[Number],
        *,
        label: str | None = None,
        group: str | None = None,
        state: IPState = IPState.IDLE,
        perm: IPerm = IPerm.RW,
        timeout: float | None = None,
        emit: EmitPolicy = "always",
    ) -> BoundProperty[NumberVector]:
        """Define a number vector property.

        Parameters
        ----------
        name : str
            The property name.
        elements : list of Number
            The number elements the vector contains.
        label : str, optional
            Display label.
        group : str, optional
            GUI group the property belongs to.
        state : IPState, optional
            Initial vector state.
        perm : IPerm, optional
            Client access permission.
        timeout : float, optional
            Worst-case update time, in seconds.
        emit : str, optional
            When later ``set`` calls reach the wire; see
            `~indi_nexus.driver.property.EmitPolicy`.

        Returns
        -------
        prop : BoundProperty
            The handle for the newly defined property.
        """
        return self.define(
            NumberVector(
                device=self._device,
                name=name,
                label=label,
                group=group,
                state=state,
                perm=perm,
                timeout=timeout,
                elements=elements,
            ),
            emit=emit,
        )

    def define_text(
        self,
        name: str,
        elements: list[Text],
        *,
        label: str | None = None,
        group: str | None = None,
        state: IPState = IPState.IDLE,
        perm: IPerm = IPerm.RW,
        timeout: float | None = None,
        emit: EmitPolicy = "always",
    ) -> BoundProperty[TextVector]:
        """Define a text vector property.

        Parameters
        ----------
        name : str
            The property name.
        elements : list of Text
            The text elements the vector contains.
        label : str, optional
            Display label.
        group : str, optional
            GUI group the property belongs to.
        state : IPState, optional
            Initial vector state.
        perm : IPerm, optional
            Client access permission.
        timeout : float, optional
            Worst-case update time, in seconds.
        emit : str, optional
            When later ``set`` calls reach the wire; see
            `~indi_nexus.driver.property.EmitPolicy`.

        Returns
        -------
        prop : BoundProperty
            The handle for the newly defined property.
        """
        return self.define(
            TextVector(
                device=self._device,
                name=name,
                label=label,
                group=group,
                state=state,
                perm=perm,
                timeout=timeout,
                elements=elements,
            ),
            emit=emit,
        )

    def define_switch(
        self,
        name: str,
        elements: list[Switch],
        *,
        rule: ISRule = ISRule.ANY_OF_MANY,
        label: str | None = None,
        group: str | None = None,
        state: IPState = IPState.IDLE,
        perm: IPerm = IPerm.RW,
        timeout: float | None = None,
        emit: EmitPolicy = "always",
    ) -> BoundProperty[SwitchVector]:
        """Define a switch vector property.

        Parameters
        ----------
        name : str
            The property name.
        elements : list of Switch
            The switch elements the vector contains.
        rule : ISRule, optional
            The switch constraint (e.g. ``OneOfMany``).
        label : str, optional
            Display label.
        group : str, optional
            GUI group the property belongs to.
        state : IPState, optional
            Initial vector state.
        perm : IPerm, optional
            Client access permission.
        timeout : float, optional
            Worst-case update time, in seconds.
        emit : str, optional
            When later ``set`` calls reach the wire; see
            `~indi_nexus.driver.property.EmitPolicy`.

        Returns
        -------
        prop : BoundProperty
            The handle for the newly defined property.
        """
        return self.define(
            SwitchVector(
                device=self._device,
                name=name,
                label=label,
                group=group,
                state=state,
                perm=perm,
                rule=rule,
                timeout=timeout,
                elements=elements,
            ),
            emit=emit,
        )

    def define_light(
        self,
        name: str,
        elements: list[Light],
        *,
        label: str | None = None,
        group: str | None = None,
        state: IPState = IPState.IDLE,
        emit: EmitPolicy = "always",
    ) -> BoundProperty[LightVector]:
        """Define a light vector property.

        Lights are always read-only in INDI, so there is no ``perm`` argument.

        Parameters
        ----------
        name : str
            The property name.
        elements : list of Light
            The light elements the vector contains.
        label : str, optional
            Display label.
        group : str, optional
            GUI group the property belongs to.
        state : IPState, optional
            Initial vector state.
        emit : str, optional
            When later ``set`` calls reach the wire; see
            `~indi_nexus.driver.property.EmitPolicy`.

        Returns
        -------
        prop : BoundProperty
            The handle for the newly defined property.
        """
        return self.define(
            LightVector(
                device=self._device,
                name=name,
                label=label,
                group=group,
                state=state,
                elements=elements,
            ),
            emit=emit,
        )

    def define_blob(
        self,
        name: str,
        elements: list[BLOB],
        *,
        label: str | None = None,
        group: str | None = None,
        state: IPState = IPState.IDLE,
        perm: IPerm = IPerm.RW,
        timeout: float | None = None,
        emit: EmitPolicy = "always",
    ) -> BoundProperty[BLOBVector]:
        """Define a BLOB vector property.

        Parameters
        ----------
        name : str
            The property name.
        elements : list of BLOB
            The BLOB elements the vector contains.
        label : str, optional
            Display label.
        group : str, optional
            GUI group the property belongs to.
        state : IPState, optional
            Initial vector state.
        perm : IPerm, optional
            Client access permission.
        timeout : float, optional
            Worst-case update time, in seconds.
        emit : str, optional
            When later ``set`` calls reach the wire; see
            `~indi_nexus.driver.property.EmitPolicy`.

        Returns
        -------
        prop : BoundProperty
            The handle for the newly defined property.
        """
        return self.define(
            BLOBVector(
                device=self._device,
                name=name,
                label=label,
                group=group,
                state=state,
                perm=perm,
                timeout=timeout,
                elements=elements,
            ),
            emit=emit,
        )

    # -- property access --------------------------------------------------- #
    def property(self, name: str) -> BoundProperty[Any]:
        """Return the handle for a previously defined property.

        A lookup by name cannot know the vector kind, so the handle it returns
        is untyped in its vector. When you need ``prop.vector`` to narrow - to
        iterate elements, say - use :meth:`number`, :meth:`text`, :meth:`switch`,
        :meth:`light` or :meth:`blob` instead, or keep the handle that
        ``define_*`` returned.

        Parameters
        ----------
        name : str
            The property name passed to a ``define_*`` call.

        Returns
        -------
        prop : BoundProperty
            The handle for that property.

        Raises
        ------
        KeyError
            Raised if no property with that name has been defined.
        """
        return self._properties[name]

    def __getitem__(self, name: str) -> BoundProperty[Any]:
        """Return the handle for property ``name`` (see :meth:`property`)."""
        return self._properties[name]

    def __contains__(self, name: str) -> bool:
        """Return whether a property named ``name`` has been defined."""
        return name in self._properties

    def _typed[VectorT: Vector](self, name: str, kind: type[VectorT]) -> BoundProperty[VectorT]:
        """Return the handle for ``name``, checking it wraps a ``kind`` vector.

        Parameters
        ----------
        name : str
            The property name.
        kind : type
            The vector class the caller expects.

        Returns
        -------
        prop : BoundProperty
            The handle, now typed by ``kind``.

        Raises
        ------
        KeyError
            Raised if no property with that name has been defined.
        TypeError
            Raised if the property is of a different vector kind.
        """
        prop = self._properties[name]
        if not isinstance(prop.vector, kind):
            raise TypeError(
                f"{self._device}.{name} is a {type(prop.vector).__name__}, not a {kind.__name__}"
            )
        return cast("BoundProperty[VectorT]", prop)

    def number(self, name: str) -> BoundProperty[NumberVector]:
        """Return the handle for a number property, typed as such.

        Parameters
        ----------
        name : str
            The property name.

        Returns
        -------
        prop : BoundProperty
            The handle, with ``prop.vector.elements`` typed ``list[Number]``.
        """
        return self._typed(name, NumberVector)

    def text(self, name: str) -> BoundProperty[TextVector]:
        """Return the handle for a text property, typed as such.

        Parameters
        ----------
        name : str
            The property name.

        Returns
        -------
        prop : BoundProperty
            The handle, with ``prop.vector.elements`` typed ``list[Text]``.
        """
        return self._typed(name, TextVector)

    def switch(self, name: str) -> BoundProperty[SwitchVector]:
        """Return the handle for a switch property, typed as such.

        Parameters
        ----------
        name : str
            The property name.

        Returns
        -------
        prop : BoundProperty
            The handle, with ``prop.vector.elements`` typed ``list[Switch]``.
        """
        return self._typed(name, SwitchVector)

    def light(self, name: str) -> BoundProperty[LightVector]:
        """Return the handle for a light property, typed as such.

        Parameters
        ----------
        name : str
            The property name.

        Returns
        -------
        prop : BoundProperty
            The handle, with ``prop.vector.elements`` typed ``list[Light]``.
        """
        return self._typed(name, LightVector)

    def blob(self, name: str) -> BoundProperty[BLOBVector]:
        """Return the handle for a BLOB property, typed as such.

        Parameters
        ----------
        name : str
            The property name.

        Returns
        -------
        prop : BoundProperty
            The handle, with ``prop.vector.elements`` typed ``list[BLOB]``.
        """
        return self._typed(name, BLOBVector)

    # -- talking to hardware ------------------------------------------------ #
    @staticmethod
    async def off_thread[T](func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
        """Run a blocking call in a worker thread and await its result.

        Instrument libraries are overwhelmingly synchronous - ``pyserial``, a
        vendor SDK, a ``requests`` session. Calling one directly from an
        ``async def`` compiles, reads fine and blocks the event loop for its
        whole duration: the driver stops answering ``indiserver``, every other
        property freezes, and nothing reports an error. Route it through here
        instead::

            reading = await self.off_thread(self._hardware.read_all)
            self["telemetry"].set(**reading, state=IPState.OK)

        Only the blocking call belongs in the thread. Keep property writes on
        the event loop, as above: the outbox behind ``set`` is an
        :class:`asyncio.Queue`, which is not thread-safe.

        Parameters
        ----------
        func : Callable
            The blocking callable to run.
        *args : object
            Positional arguments for ``func``.
        **kwargs : object
            Keyword arguments for ``func``.

        Returns
        -------
        result : T
            Whatever ``func`` returned.
        """
        return await asyncio.to_thread(func, *args, **kwargs)

    # -- client messaging -------------------------------------------------- #
    def message(
        self, text: str, *, level: str = "INFO", timestamp: dt.datetime | None = None
    ) -> None:
        """Send a free-form log/notification ``message`` to the client.

        Parameters
        ----------
        text : str
            The message body.
        level : str, optional
            A severity label prefixed to the text (e.g. ``INFO``, ``ERROR``).
        timestamp : datetime, optional
            Message timestamp; defaults to now. INDI timestamps are UTC, so a
            naive one is read as UTC and an aware one is converted.
        """
        self._send(
            Message(
                device=self._device,
                timestamp=timestamp or indi_now(),
                message=f"[{level}] {text}",
            )
        )

    def log_error(self, text: str) -> None:
        """Send an ``ERROR``-level :meth:`message`.

        Parameters
        ----------
        text : str
            The error text.
        """
        self.message(text, level="ERROR")

    # -- runtime plumbing (called by DriverRuntime) ------------------------ #
    def _guard(self) -> AbstractAsyncContextManager[None]:
        """Return the mutual exclusion ticks and inbound dispatch run under.

        The runtime wraps each ``@every`` tick in this; :meth:`_dispatch_new` and
        :meth:`_dispatch_get_properties` enter it themselves, so any caller -
        the runtime, a test harness, the in-process bridge - gets the same
        guarantee. See :attr:`serialize_dispatch`.

        Returns
        -------
        guard : AbstractAsyncContextManager
            The device lock, or a no-op context when serialisation is off.
        """
        if not self.serialize_dispatch:
            return contextlib.nullcontext()
        return self._dispatch_lock

    def _bind(self, emit: Emit) -> None:
        """Attach the runtime's outbound-message callback to this device.

        Parameters
        ----------
        emit : Callable
            Callback the device uses to queue outbound messages.
        """
        self._emit = emit

    def _send(self, msg: IndiMessage) -> None:
        """Queue one outbound message, requiring an attached runtime.

        Parameters
        ----------
        msg : IndiMessage
            The message to send.

        Raises
        ------
        RuntimeError
            Raised if the device is not attached to a runtime.
        """
        if self._emit is None:
            raise RuntimeError(
                "Device is not attached to a runtime; define/send only works while serving"
            )
        self._emit(msg)

    async def _dispatch_get_properties(self, request: GetProperties) -> None:
        """Handle a ``getProperties``: run :meth:`setup` once, else re-announce.

        A request naming a *different* device is ignored, per the INDI spec (a
        driver answers only for its own device; ``device`` absent means "all").
        The first matching request runs :meth:`setup`; later ones (a late-joining
        client) re-emit the ``def`` for every property already defined.

        A :meth:`setup` that **raises** - hardware absent at boot, the ordinary
        case - is not a terminal state:

        * The ``@every`` gate is released either way. A driver whose periodic
          jobs never run is dead while still looking alive to ``indiserver``,
          and nothing but those jobs is left to notice the hardware appearing.
          A tick that then fails is isolated and reported per tick, so the
          failure is loud instead of invisible - and a job written to reconnect
          can heal the device on its own.
        * The attempt is not latched, so a later ``getProperties`` retries it,
          and the failed attempt leaves nothing behind: whatever it defined
          before it raised is retracted with a ``delProperty`` and dropped, so
          the retry starts from the state the device was in before it. This is
          the rule :meth:`_on_connection_write` already follows for a hook that
          raises - roll back, do not half-commit - and it is what a probing
          setup needs ("channel 1 found, channel 2 found, channel 3 timed
          out"): without it, channel 2 stays defined for the life of the
          process and is re-announced to every client that joins later, even
          though the retry never defines it again.

        A handle captured during the failed attempt is retracted along with its
        property, and :meth:`BoundProperty.set` on a retracted handle raises
        rather than publish an update for something the client has been told is
        gone. Reach properties through ``self["NAME"]`` rather than caching what
        a ``define_*`` returned across a failure.

        The exception itself still propagates, so the runtime reports it to the
        client.

        Parameters
        ----------
        request : GetProperties
            The inbound request; its ``device`` filter is honored.
        """
        if request.device is not None and request.device != self._device:
            return
        async with self._guard():
            if not self._setup_done:
                # Latched before the await, not after: a second getProperties
                # arriving mid-setup must not start setup() a second time.
                self._setup_done = True
                announced = dict(self._properties)
                try:
                    await self.setup()
                except Exception as exc:
                    self._roll_back_setup(announced, exc)
                    self._setup_done = False  # let a later getProperties retry
                    raise
                finally:
                    self._setup_complete.set()
            else:
                for prop in self._properties.values():
                    prop._announce()

    def _roll_back_setup(self, announced: dict[str, BoundProperty[Any]], exc: Exception) -> None:
        """Undo the property definitions of a :meth:`setup` attempt that raised.

        The device goes back to ``announced`` and the client is brought back in
        line with it: every property the attempt introduced is retracted with a
        ``delProperty``, because the client has already seen its ``def`` and
        dropping it here alone would leave a panel rendering a property the
        driver no longer has, and the restored set is re-announced, which is the
        same repeated ``def`` a late-joining client gets.

        Identity, not name, decides what the attempt introduced. In practice
        ``announced`` is empty - a setup that succeeded is never retried - but a
        property defined outside :meth:`setup`, by an ``@every`` job that got in
        first, must survive a failed attempt whether or not the attempt happened
        to redefine its name.

        Parameters
        ----------
        announced : dict
            The properties as they stood before the attempt began, keyed by
            name. The device is restored to exactly this mapping.
        exc : Exception
            The failure, quoted to the client on each retraction so the panel
            says why the property went away.
        """
        for name, prop in self._properties.items():
            if announced.get(name) is not prop:
                prop.delete(message=f"{self._device} setup failed: {exc}")
        self._properties = announced
        for prop in announced.values():
            prop._announce()

    async def _dispatch_new(self, vector: Vector) -> None:
        """Route a client write to its ``@on_new`` handler or the default.

        A write addressed to a *different* device is ignored, matching libindi
        drivers' ``strcmp(dev, getDeviceName())`` guard. ``indiserver`` routes
        writes so this rarely triggers there, but a hub that broadcasts to
        several drivers on one stream (e.g. ``indi-nexus serve --device``) relies
        on it - without the guard every driver would react to every write.

        Parameters
        ----------
        vector : Vector
            The parsed vector the client asked to change.
        """
        if vector.device != self._device:
            return
        async with self._guard():
            handler = self._new_handlers.get(vector.name)
            result = handler(vector) if handler is not None else self.on_new_default(vector)
            if inspect.isawaitable(result):
                await result

    # -- entrypoint -------------------------------------------------------- #
    @classmethod
    def run(cls, name: str | None = None) -> None:
        """Run this device as an ``indiserver`` stdio driver until stdin closes.

        Parameters
        ----------
        name : str, optional
            Device-name override passed to the constructor.
        """
        from indi_nexus.driver.runtime import run

        run(cls(name=name))
