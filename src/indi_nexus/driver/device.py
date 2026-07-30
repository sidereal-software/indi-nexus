"""The ``Device`` base class - what a driver author subclasses.

A driver is a subclass of :class:`Device` that

* defines its properties in :meth:`Device.setup` (called once, when a client
  first asks what this device exposes),
* pushes updates through the :class:`BoundProperty` handles that ``define_*``
  returns - typically from ``@every`` polling jobs,
* and handles client writes with ``@on_new`` methods.

The class deliberately avoids pyINDI's libindi-C surface (``IUFind``,
``IDSetNumber``, ``IEAddTimer``); the vocabulary here is plain Python.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import inspect
from collections.abc import Callable

from indi_nexus.driver.dispatch import iter_new_handlers
from indi_nexus.driver.property import BoundProperty
from indi_nexus.protocol import (
    BLOB,
    BLOBVector,
    DefVector,
    GetProperties,
    IndiMessage,
    IPerm,
    IPState,
    ISRule,
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
    """

    #: Override to set the INDI device name. Empty means "use the class name".
    name: str = ""

    def __init__(self, name: str | None = None) -> None:
        """Initialise the device and discover its ``@on_new`` handlers.

        Parameters
        ----------
        name : str, optional
            Instance-level device name override. Falls back to the class
            :attr:`name`, then to the class name.
        """
        self._device = name or type(self).name or type(self).__name__
        self._properties: dict[str, BoundProperty] = {}
        self._new_handlers: dict[str, NewHandler] = dict(iter_new_handlers(self))
        self._emit: Emit | None = None
        self._setup_done = False
        # Set once setup() has run; periodic (@every) jobs wait on it so they
        # never touch a property before setup() defines it.
        self._setup_complete = asyncio.Event()

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

    # -- property definition ---------------------------------------------- #
    def define(self, vector: Vector) -> BoundProperty:
        """Register a property vector, emit its ``def``, and return its handle.

        Parameters
        ----------
        vector : Vector
            The vector to define. If its ``device`` is unset, this device's name
            is filled in.

        Returns
        -------
        prop : BoundProperty
            The handle used to push later updates for this property.
        """
        if not vector.device:
            vector.device = self._device
        prop = BoundProperty(vector, self._send)
        self._properties[vector.name] = prop
        self._send(DefVector(vector=vector))
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
    ) -> BoundProperty:
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
            )
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
    ) -> BoundProperty:
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
            )
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
    ) -> BoundProperty:
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
            )
        )

    def define_light(
        self,
        name: str,
        elements: list[Light],
        *,
        label: str | None = None,
        group: str | None = None,
        state: IPState = IPState.IDLE,
    ) -> BoundProperty:
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
            )
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
    ) -> BoundProperty:
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
            )
        )

    # -- property access --------------------------------------------------- #
    def property(self, name: str) -> BoundProperty:
        """Return the handle for a previously defined property.

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

    def __getitem__(self, name: str) -> BoundProperty:
        """Return the handle for property ``name`` (see :meth:`property`)."""
        return self._properties[name]

    def __contains__(self, name: str) -> bool:
        """Return whether a property named ``name`` has been defined."""
        return name in self._properties

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
            Message timestamp; defaults to now.
        """
        self._send(
            Message(
                device=self._device,
                timestamp=timestamp or dt.datetime.now(),
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

        Parameters
        ----------
        request : GetProperties
            The inbound request; its ``device`` filter is honored.
        """
        if request.device is not None and request.device != self._device:
            return
        if not self._setup_done:
            self._setup_done = True
            await self.setup()
            self._setup_complete.set()
        else:
            for prop in self._properties.values():
                self._send(DefVector(vector=prop.vector))

    async def _dispatch_new(self, vector: Vector) -> None:
        """Route a client write to its ``@on_new`` handler or the default.

        Parameters
        ----------
        vector : Vector
            The parsed vector the client asked to change.
        """
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
