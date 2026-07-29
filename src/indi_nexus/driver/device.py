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

import datetime as dt
import inspect
from collections.abc import Callable

from indi_nexus.driver.dispatch import iter_new_handlers
from indi_nexus.driver.property import BoundProperty
from indi_nexus.protocol import (
    BLOB,
    BLOBVector,
    DefVector,
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
    """

    #: Override to set the INDI device name. Empty means "use the class name".
    name: str = ""

    def __init__(self, name: str | None = None) -> None:
        self._device = name or type(self).name or type(self).__name__
        self._properties: dict[str, BoundProperty] = {}
        self._new_handlers: dict[str, NewHandler] = dict(iter_new_handlers(self))
        self._emit: Emit | None = None
        self._setup_done = False

    # -- identity ---------------------------------------------------------- #
    @property
    def device(self) -> str:
        """The resolved INDI device name."""
        return self._device

    def __repr__(self) -> str:
        return f"<{type(self).__name__} device={self._device!r}>"

    # -- lifecycle hooks (override these) ---------------------------------- #
    async def setup(self) -> None:
        """Define the device's properties. Called once, on first ``getProperties``.

        Override and call ``self.define_*`` here.
        """

    async def on_new_default(self, vector: Vector) -> None:
        """Handle a client write to a property with no ``@on_new`` handler.

        The default is to ignore it. Override for a catch-all.
        """

    # -- property definition ---------------------------------------------- #
    def define(self, vector: Vector) -> BoundProperty:
        """Register ``vector`` and emit its ``def``; return its handle.

        If the vector has no device set, this device's name is filled in.
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
        # Lights are always read-only in INDI, so there is no perm argument.
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
        """Return the handle for a previously defined property."""
        return self._properties[name]

    def __getitem__(self, name: str) -> BoundProperty:
        return self._properties[name]

    def __contains__(self, name: str) -> bool:
        return name in self._properties

    # -- client messaging -------------------------------------------------- #
    def message(
        self, text: str, *, level: str = "INFO", timestamp: dt.datetime | None = None
    ) -> None:
        """Send a free-form log/notification ``message`` to the client."""
        self._send(
            Message(
                device=self._device,
                timestamp=timestamp or dt.datetime.now(),
                message=f"[{level}] {text}",
            )
        )

    def log_error(self, text: str) -> None:
        """Convenience for an ``ERROR``-level :meth:`message`."""
        self.message(text, level="ERROR")

    # -- runtime plumbing (called by DriverRuntime) ------------------------ #
    def _bind(self, emit: Emit) -> None:
        self._emit = emit

    def _send(self, msg: IndiMessage) -> None:
        if self._emit is None:
            raise RuntimeError(
                "Device is not attached to a runtime; define/send only works while serving"
            )
        self._emit(msg)

    async def _dispatch_get_properties(self) -> None:
        if not self._setup_done:
            self._setup_done = True
            await self.setup()
        else:
            # A late-joining client: re-announce everything we already have.
            for prop in self._properties.values():
                self._send(DefVector(vector=prop.vector))

    async def _dispatch_new(self, vector: Vector) -> None:
        handler = self._new_handlers.get(vector.name)
        result = handler(vector) if handler is not None else self.on_new_default(vector)
        if inspect.isawaitable(result):
            await result

    # -- entrypoint -------------------------------------------------------- #
    @classmethod
    def run(cls, name: str | None = None) -> None:
        """Run this device as an ``indiserver`` stdio driver until stdin closes."""
        from indi_nexus.driver.runtime import run

        run(cls(name=name))
