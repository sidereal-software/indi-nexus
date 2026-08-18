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
import logging
from collections.abc import Callable, Coroutine
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any, cast

from indi_nexus.driver.config import (
    ConfigDocument,
    config_path,
    read_document,
    remove_document,
    values_of,
    write_document,
)
from indi_nexus.driver.dispatch import iter_new_handlers, on_new
from indi_nexus.driver.property import BoundProperty, EmitPolicy
from indi_nexus.exceptions import (
    ConfigError,
    DeviceNotServing,
    PropertyNotFound,
    WrongPropertyKind,
)
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

logger = logging.getLogger(__name__)

Emit = Callable[[IndiMessage], None]
NewHandler = Callable[[Vector], object]

#: The standard INDI configuration property, and the three actions this SDK
#: implements on it. ``CONFIG_DEFAULT`` is libindi's fourth member and is
#: deliberately absent: "reset to the defaults" is what the code already says,
#: and a driver that wants it withdraws the saved file with ``CONFIG_PURGE``
#: and restarts, rather than the SDK inventing a second definition of default.
CONFIG_PROCESS = "CONFIG_PROCESS"
CONFIG_LOAD = "CONFIG_LOAD"
CONFIG_SAVE = "CONFIG_SAVE"
CONFIG_PURGE = "CONFIG_PURGE"

#: The read-only property that answers "what does Save actually write?", and the
#: element carrying the answer: the persisted property names, separated by
#: spaces. libindi cannot answer that question at all - its subset is chosen in
#: ``saveConfigItems``, a C++ virtual no client can read over the wire - which is
#: why a panel has to apologise for every libindi driver. Here ``persist=True``
#: is declared at define time, so the answer is data and the driver publishes it.
#:
#: **The name is namespaced deliberately.** ``CONFIG_PERSISTED`` sits in the same
#: flat property namespace libindi's own ``CONFIG_*`` properties do, and INDI's
#: selling point is that everybody's clients talk to everybody's drivers. Once
#: this has shipped, this SDK, the panel and any third-party consumer all key on
#: the name, so a later collision could only be resolved by breaking all three
#: together. The prefix costs nothing and makes that impossible.
CONFIG_PERSISTED = "NEXUS_CONFIG_PERSISTED"
CONFIG_PERSISTED_NAMES = "PROPERTIES"

#: Vector kinds that cannot be persisted. A light is a status readout the driver
#: computes - restoring one would put a stale judgement on screen with nothing
#: behind it - and a BLOB is an image, which is not configuration and would put
#: an unbounded payload into a text file.
_UNPERSISTABLE = (LightVector, BLOBVector)


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
        # This device's configuration as it stands right now: element values
        # keyed by property name, for every property declared persist=True. It
        # is one authoritative map rather than a cache of the file, and the four
        # rules in define_config's docstring are the whole of its behaviour.
        self._config_values: dict[str, dict[str, Any]] = {}
        # Where that configuration is written. Injected by whatever is serving
        # the device (the runtime, the harness); `None` until then, and `None`
        # afterwards on a machine with no resolvable configuration directory.
        self._config_dir: Path | None = None
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

    # -- configuration ------------------------------------------------------ #
    def define_config(
        self, *, label: str = "Configuration", group: str = "Options"
    ) -> BoundProperty[SwitchVector]:
        """Define the standard INDI ``CONFIG_PROCESS`` switch.

        Three momentary actions - ``CONFIG_LOAD``, ``CONFIG_SAVE`` and
        ``CONFIG_PURGE`` - wired to :meth:`load_config`, :meth:`save_config` and
        :meth:`purge_config` by a built-in handler, which a subclass
        ``@on_new("CONFIG_PROCESS")`` shadows the way it shadows the
        ``CONNECTION`` one. Every libindi driver publishes this property, so a
        client already knows what the buttons do.

        **This defines a property and does no I/O.** Restoring the saved
        configuration at startup is one explicit line in :meth:`setup`::

            async def setup(self) -> None:
                self.define_connection()
                self.define_config()
                self.define_number("GEOGRAPHIC_COORD", [...], persist=True)
                with contextlib.suppress(ConfigError):
                    await self.load_config()   # a first run has nothing saved

        Where that line goes is not a correctness question - :meth:`load_config`
        applies to every persisted property already defined *and* stays in place
        for every one defined after it, an ``on_connect``'s included - but the
        two orders differ in one visible way. Load **before** the persisted
        ``define_*`` calls and each property is announced once, already holding
        its saved value. Load after them, as above, and each is announced with
        its built-in default and corrected a moment later, in exchange for
        :meth:`on_config_loaded` being handed the names while the properties are
        all there.

        What is saved is chosen per property, at define time, with
        ``persist=True``. Values only, never definitions: labels, permissions
        and limits belong to the code, which is the only thing that knows what
        this version of the driver publishes. Lights and BLOBs cannot be
        persisted at all.

        Because that choice is declarative, the device can **tell a client what
        Save writes**, which no libindi driver can: a read-only
        ``NEXUS_CONFIG_PERSISTED`` text property whose ``PROPERTIES`` element
        lists the persisted property names, separated by spaces. It is published
        once :meth:`setup` returns, so it names the whole set rather than
        growing an element at a time, and updated whenever the membership really
        changes - a persisted property defined on connect, or withdrawn on
        disconnect. A device that persists nothing publishes it **empty**: "this
        driver saves nothing" and "this driver cannot tell you" are different
        answers, and only the property being absent means the second.

        The device keeps one authoritative map of its configuration, and four
        rules govern it:

        * :meth:`load_config` merges the file into it, applies it to every
          persisted property currently defined, and leaves it in place for the
          ones defined afterwards.
        * ``define_*(persist=True)`` applies it before announcing the property,
          so startup puts one frame on the wire and not a default followed by a
          correction.
        * Withdrawing a persisted property captures its current values into it
          first, so defining the property again restores what the operator had
          rather than what is on disk.
        * :meth:`save_config` refreshes it from every live persisted property
          and then writes the whole of it, so a Save taken while a connect-time
          property is withdrawn does not erase that property's values.

        **Two drivers sharing one configuration directory and one device name
        overwrite each other**, last writer wins. Nothing can arbitrate that
        across processes, and two devices answering to one name is already
        unresolvable for a client; libindi has the identical property with
        ``$HOME/.indi/<device>_config.xml``.

        Parameters
        ----------
        label : str, optional
            The property label shown by clients.
        group : str, optional
            The property group (tab) shown by clients.

        Returns
        -------
        prop : BoundProperty
            The handle for the CONFIG_PROCESS property.
        """
        return self.define_switch(
            CONFIG_PROCESS,
            [
                Switch(name=CONFIG_LOAD, label="Load"),
                Switch(name=CONFIG_SAVE, label="Save"),
                Switch(name=CONFIG_PURGE, label="Purge"),
            ],
            rule=ISRule.AT_MOST_ONE,
            label=label,
            group=group,
        )

    def _publish_persisted(self) -> None:
        """Define ``NEXUS_CONFIG_PERSISTED``, once :meth:`setup` has returned.

        Called by :meth:`_dispatch_get_properties` after a successful
        :meth:`setup`, and only for a device that defined ``CONFIG_PROCESS`` -
        without a Save button there is nothing for the list to describe. Doing
        it here rather than from each ``define_*(persist=True)`` call is what
        makes the property arrive stating the whole set: publishing per property
        would announce a list that is wrong until the last persisted define, and
        put a ``set`` on the wire for each one.

        It carries the ``CONFIG_PROCESS`` group so the two stay in the same tab,
        and ``emit="on_change"`` so a define-delete-define cycle that leaves the
        membership as it was says nothing.
        """
        if CONFIG_PROCESS not in self._properties or CONFIG_PERSISTED in self._properties:
            return
        self.define_text(
            CONFIG_PERSISTED,
            [
                Text(
                    name=CONFIG_PERSISTED_NAMES,
                    label="Properties",
                    value=self._persisted_names(),
                )
            ],
            label="Saved properties",
            group=self._properties[CONFIG_PROCESS].vector.group,
            perm=IPerm.RO,
            state=IPState.OK,
            emit="on_change",
        )

    def _refresh_persisted(self) -> None:
        """Restate ``NEXUS_CONFIG_PERSISTED`` after the membership may have moved.

        A no-op until the property exists, which is what keeps the persisted
        ``define_*`` calls inside :meth:`setup` silent: they run before
        :meth:`_publish_persisted`, and the value it publishes already accounts
        for them. Afterwards this is the path that keeps a connect-time
        persisted property honest in both directions.
        """
        prop = self._properties.get(CONFIG_PERSISTED)
        if prop is None:
            return
        prop.set({CONFIG_PERSISTED_NAMES: self._persisted_names()})

    def _persisted_names(self) -> str:
        """Return the persisted property names as the wire carries them.

        Returns
        -------
        names : str
            The names of every persisted property defined right now, in the
            order they were defined, separated by single spaces. Empty when the
            device persists nothing, which is a statement rather than a gap.
        """
        return " ".join(name for name, prop in self._properties.items() if prop.persist)

    async def on_config_loaded(self, names: list[str]) -> None:
        """React to a configuration that has just been restored.

        Called by :meth:`load_config` after the values are in the properties and
        on the wire, with the properties it actually applied to. The default
        does nothing, which is right for a driver whose configuration is only
        read when it is used.

        Override it when a restored value has to *become* true of the hardware -
        a focuser that must physically move to the position it was saved at, a
        filter wheel that must turn. The shape that works is to keep the body of
        the corresponding ``@on_new`` handler in a method of its own and call it
        from both places, so the restore does exactly what a client write would
        do; ``examples/openmeteo_device.py`` is the worked version.

        Parameters
        ----------
        names : list of str
            The properties the load applied values to.
        """

    async def load_config(self) -> None:
        """Restore this device's saved configuration and apply it.

        Reads the file, merges it into the device's configuration, publishes a
        ``set`` for every persisted property that is defined right now, and then
        calls :meth:`on_config_loaded`. Properties defined afterwards pick their
        values up as they are defined.

        Raises
        ------
        ConfigError
            Raised if there is nothing saved, or the configuration cannot be
            located or read. Also an OSError. A first run has nothing saved, so
            a :meth:`setup` that calls this handles the failure rather than
            letting it roll the whole attempt back.
        """
        path = self._config_file()
        document = await self.off_thread(read_document, path)
        self._config_values.update(document.properties)
        applied: list[str] = []
        rejected: list[str] = []
        for name, values in document.properties.items():
            prop = self._properties.get(name)
            if prop is None or not prop.persist:
                # A property this version of the driver no longer publishes, or
                # one that is not defined yet. Its values stay in the map, so a
                # later define_* still restores them and a Save keeps them.
                continue
            refused = prop._restore(values)
            applied.append(name)
            rejected += [f"{name}.{element}" for element in refused]
        self.message(self._loaded_message(applied, rejected))
        await self.on_config_loaded(applied)

    def _loaded_message(self, applied: list[str], rejected: list[str]) -> str:
        """Return the client-facing summary of one completed load.

        Parameters
        ----------
        applied : list of str
            The properties the load wrote values into.
        rejected : list of str
            Qualified element names whose saved value would not take.

        Returns
        -------
        text : str
            One sentence, naming the rejected elements when there are any -
            they are the half a reader has to act on.
        """
        if applied:
            text = f"Restored {len(applied)} propert{'y' if len(applied) == 1 else 'ies'}."
        else:
            # A load written *before* the persisted define_* calls, which is the
            # order that announces each property once. Nothing has been applied
            # yet, and nothing has gone wrong.
            text = "Configuration loaded; its values apply as the properties are defined."
        if rejected:
            text += f" These saved values were refused: {', '.join(rejected)}."
        return text

    async def save_config(self) -> None:
        """Write this device's current configuration to disk.

        Every persisted property that is defined right now is read into the
        device's configuration first, and then the whole configuration is
        written - including properties that are not defined at the moment,
        whose values were captured when they were withdrawn. That is what makes
        a Save taken while the instrument is disconnected preserve the
        connect-time properties instead of erasing them.

        The file is replaced whole, so there is no read-modify-write to lose an
        update to a second process.

        Raises
        ------
        ConfigError
            Raised if the configuration cannot be located or written. Also an
            OSError.
        """
        path = self._config_file()
        for name, prop in self._properties.items():
            if prop.persist:
                self._config_values[name] = values_of(prop.vector)
        document = ConfigDocument(device=self._device, properties=dict(self._config_values))
        await self.off_thread(write_document, path, document)
        self.message("Configuration saved.")

    async def purge_config(self) -> None:
        """Delete this device's saved configuration file.

        Purging what is not there succeeds: the operator asked for there to be
        no saved configuration, and afterwards there is none.

        The device's *live* configuration is untouched, deliberately. Purge says
        "forget the file", not "forget the values the properties are holding",
        and clearing the map would throw away the last known values of any
        property that happens to be withdrawn right now.

        Raises
        ------
        ConfigError
            Raised if the configuration cannot be located, or a file is there
            and cannot be removed. Also an OSError.
        """
        path = self._config_file()
        await self.off_thread(remove_document, path)
        self.message("Saved configuration purged.")

    def _config_file(self) -> Path:
        """Return the file this device's configuration lives in.

        Returns
        -------
        path : Path
            The configuration file, which need not exist.

        Raises
        ------
        ConfigError
            Raised if no configuration directory could be resolved, or the
            device name cannot be a filename. Also an OSError.
        """
        if self._config_dir is None:
            raise ConfigError(
                f"{self._device} has nowhere to keep its configuration; set INDI_NEXUS_CONFIG_DIR"
            )
        return config_path(self._config_dir, self._device)

    @on_new(CONFIG_PROCESS)
    async def _on_config_write(self, vector: SwitchVector) -> None:
        """Run the configuration action a client selected (built-in handler).

        Reports the way :meth:`_on_connection_write` does - ``Busy``, act, then
        ``Ok`` or ``Alert`` with the reason - and then differs from it in one
        way that matters: **every member is reset to Off**. ``CONNECTION`` is
        state, so it leaves a member on; ``CONFIG_PROCESS`` is a momentary
        action, and under ``AtMostOne`` a member left on stays selected forever,
        which a panel renders as a button stuck in its pressed position.
        libindi calls ``IUResetSwitch`` here for the same reason.

        The failure it catches is therefore **any** failure, not just
        :class:`~indi_nexus.ConfigError`. The likeliest one is not the
        filesystem at all: :meth:`on_config_loaded` is a documented extension
        point, so an exception out of a driver author's override is expected
        rather than exceptional here - and letting it past would skip the reset
        and leave exactly the stuck button this handler exists to prevent.
        """
        if CONFIG_PROCESS not in self:
            await self.on_new_default(vector)
            return
        prop = self._properties[CONFIG_PROCESS]
        action = vector.selected()
        if action not in _CONFIG_ACTIONS:
            # No member selected (AtMostOne permits it), or one this SDK does
            # not implement. There is nothing to do and nothing to report.
            prop.set_all(ISState.OFF, state=IPState.IDLE)
            return
        prop.set({action: ISState.ON}, state=IPState.BUSY)
        try:
            # Each action reports its own outcome, because each knows something
            # different worth saying - how much was restored, that nothing was
            # saved yet. All that is left here is the state of the switch.
            await _CONFIG_ACTIONS[action](self)
        except Exception as exc:  # noqa: BLE001 - reported to the client below
            prop.set_all(ISState.OFF, state=IPState.ALERT)
            self.log_error(f"{_CONFIG_LABELS[action]} failed: {exc}")
            return
        prop.set_all(ISState.OFF, state=IPState.OK)

    # -- property definition ---------------------------------------------- #
    def define[VectorT: Vector](
        self, vector: VectorT, *, emit: EmitPolicy = "always", persist: bool = False
    ) -> BoundProperty[VectorT]:
        """Register a property vector, emit its ``def``, and return its handle.

        A ``persist=True`` property is restored from the device's saved
        configuration **before** its ``def`` goes out, so a driver that comes up
        with a configuration on disk announces the saved values directly rather
        than announcing a default and correcting it a moment later. The order is
        the point: two frames would leave every client briefly holding a value
        the operator replaced weeks ago, and a panel showing it.

        Parameters
        ----------
        vector : VectorT
            The vector to define. If its ``device`` is unset, this device's name
            is filled in.
        emit : str, optional
            When later ``set`` calls reach the wire; see
            `~indi_nexus.driver.property.EmitPolicy`.
        persist : bool, optional
            Whether this property's element values belong in the device's saved
            configuration; see :meth:`define_config`.

        Returns
        -------
        prop : BoundProperty
            The handle used to push later updates for this property, typed by
            the vector kind that was defined.

        Raises
        ------
        ValueError
            Raised if ``persist=True`` is asked for on a light or BLOB vector,
            or on a property whose name contains whitespace.
        """
        if not vector.device:
            vector.device = self._device
        if persist and isinstance(vector, _UNPERSISTABLE):
            raise ValueError(
                f"{self._device}.{vector.name} is a {type(vector).__name__} and cannot be "
                "persisted: a light is a judgement the driver recomputes and a BLOB is not "
                "configuration"
            )
        # Nothing in INDI forbids whitespace in a property name - models.py puts
        # no pattern on `name` and the 1.7 DTD types it CDATA - so this guard is
        # not a restatement of the protocol. It is what makes the space-separated
        # NEXUS_CONFIG_PERSISTED encoding unambiguous: one name with a space in
        # it and every client reading that list sees two properties, neither of
        # which exists. It binds only persisted names, because they are the only
        # ones that list carries.
        if persist and any(character.isspace() for character in vector.name):
            raise ValueError(
                f"{self._device}.{vector.name!r} cannot be persisted: whitespace in the name "
                f"would be indistinguishable from a separator in {CONFIG_PERSISTED}"
            )
        prop = BoundProperty(vector, self._send, policy=emit, owner=self, persist=persist)
        self._properties[vector.name] = prop
        if persist:
            self._restore(prop)
        prop._announce()
        if persist:
            # After the announcement, so the list never names a property the
            # client has not been told about yet.
            self._refresh_persisted()
        return prop

    def _restore(self, prop: BoundProperty[Any]) -> None:
        """Write any configured values into a property that is about to be announced.

        Parameters
        ----------
        prop : BoundProperty
            The freshly registered handle, not yet announced.
        """
        values = self._config_values.get(prop.name)
        if not values:
            return
        rejected = prop._apply_values(values)
        if rejected:
            logger.warning(
                "%s.%s: saved values for %s were refused and left at their defaults",
                self._device,
                prop.name,
                ", ".join(rejected),
            )

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
        persist: bool = False,
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
        persist : bool, optional
            Whether this property's element values belong in the device's saved
            configuration; see :meth:`define_config`.

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
            persist=persist,
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
        persist: bool = False,
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
        persist : bool, optional
            Whether this property's element values belong in the device's saved
            configuration; see :meth:`define_config`.

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
            persist=persist,
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
        persist: bool = False,
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
        persist : bool, optional
            Whether this property's element values belong in the device's saved
            configuration; see :meth:`define_config`.

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
            persist=persist,
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
        persist: bool = False,
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
        persist : bool, optional
            Whether this property's element values belong in the device's saved
            configuration; see :meth:`define_config`.

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
            persist=persist,
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
        persist: bool = False,
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
        persist : bool, optional
            Whether this property's element values belong in the device's saved
            configuration; see :meth:`define_config`.

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
            persist=persist,
        )

    def delete_property(self, name: str, message: str | None = None) -> None:
        """Withdraw a property by name, or do nothing if there is no such property.

        The counterpart to ``define_*``, and the shape a property that only
        exists while the instrument is reachable wants::

            async def on_connect(self) -> None:
                self.define_number("CCD_COOLER", [Number(name="TEMPERATURE")])

            async def on_disconnect(self) -> None:
                self.delete_property("CCD_COOLER", "only while connected")

        The property is dropped from the device *and* retracted with a
        ``delProperty``, so a client that joins after this is not told about it;
        defining it again on the next connect starts the cycle over with a fresh
        handle. That is the whole life of an INDI property: defined, deleted and
        defined again, once per connection, for as long as the driver runs.

        An unknown name is deliberately silent - no message on the wire, no
        exception. That is what makes the call above safe to run on every
        disconnect, including the disconnect that follows a connect which never
        got as far as defining anything, and it is what libindi's
        ``INDI::DefaultDevice::deleteProperty`` does (``removeProperty`` fails,
        and the error it fills in is never read).

        No property is protected, ``CONNECTION`` included; libindi guards none
        of them here either. A device that deletes its ``CONNECTION`` becomes a
        device without connection semantics, and :attr:`connected` reports `True`
        for it from then on.

        Parameters
        ----------
        name : str
            The property to withdraw.
        message : str, optional
            Optional explanation to include with the deletion.
        """
        prop = self._properties.get(name)
        if prop is None:
            return
        prop.delete(message)

    def _forget(self, prop: BoundProperty[Any]) -> bool:
        """Drop one handle's property from the registry, reporting whether it did.

        A persisted property's current values are captured into the device's
        configuration on the way out, which is what makes the ordinary
        connect/disconnect cycle behave: the property comes back on the next
        connect holding what the operator last set it to, not what happened to
        be on disk when the driver started, and a Save taken while it is
        withdrawn still writes it. ``NEXUS_CONFIG_PERSISTED`` stops naming it at
        the same moment even so: it answers "which of the properties you can see
        does Save write", and a client that has just been sent a ``delProperty``
        for this one can see it no longer. The values a Save keeps for it come
        from the map, not from a property anybody could point at.

        Called by :meth:`BoundProperty.delete` so that removal and announcement
        stay in one place, and so the announcement can follow the removal rather
        than assume it. Identity decides, not the name: a property redefined
        under the same name has already replaced this handle in the registry, so
        a late ``delete`` on the superseded handle owns nothing - it must neither
        drop the replacement nor tell the client the name is gone, which would
        retract the replacement in every client's cache.
        :meth:`_roll_back_setup` distinguishes handles the same way.

        Parameters
        ----------
        prop : BoundProperty
            The handle being retracted.

        Returns
        -------
        removed : bool
            Whether this handle was the registered one and has now been dropped.
        """
        if self._properties.get(prop.name) is not prop:
            return False
        if prop.persist:
            self._config_values[prop.name] = values_of(prop.vector)
        del self._properties[prop.name]
        if prop.persist:
            # Ahead of the ``delProperty`` the caller is about to emit, as the
            # definition path restates it after the ``def``: both orders err the
            # same way, so a client never holds a list that claims Save covers a
            # property it cannot see.
            self._refresh_persisted()
        return True

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
        PropertyNotFound
            Raised if no property with that name has been defined. Also a
            KeyError, so mapping-style handling still applies.
        """
        return self._lookup(name)

    def __getitem__(self, name: str) -> BoundProperty[Any]:
        """Return the handle for property ``name`` (see :meth:`property`)."""
        return self._lookup(name)

    def _lookup(self, name: str) -> BoundProperty[Any]:
        """Return the handle registered under ``name``.

        The one place a property name is resolved, so "no such property" reads
        the same however it was asked for.

        Parameters
        ----------
        name : str
            The property name.

        Returns
        -------
        prop : BoundProperty
            The registered handle.

        Raises
        ------
        PropertyNotFound
            Raised if no property with that name has been defined.
        """
        prop = self._properties.get(name)
        if prop is None:
            raise PropertyNotFound(f"{self._device} has no property {name!r}")
        return prop

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
        PropertyNotFound
            Raised if no property with that name has been defined. Also a
            KeyError.
        WrongPropertyKind
            Raised if the property is of a different vector kind. Also a
            TypeError.
        """
        prop = self._lookup(name)
        if not isinstance(prop.vector, kind):
            raise WrongPropertyKind(
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

    def _bind(self, emit: Emit, *, config_dir: Path | None = None) -> None:
        """Attach the runtime's outbound-message callback to this device.

        The configuration directory arrives the same way and for the same
        reason: it is a property of whatever is serving the device, resolved
        once at the process entrypoint, and a device that read it for itself
        would put ambient environment inside a library object.

        Parameters
        ----------
        emit : Callable
            Callback the device uses to queue outbound messages.
        config_dir : Path or None, optional
            Where this device's saved configuration lives. `None` leaves the
            persistence methods raising :class:`~indi_nexus.ConfigError`.
        """
        self._emit = emit
        self._config_dir = config_dir

    def _send(self, msg: IndiMessage) -> None:
        """Queue one outbound message, requiring an attached runtime.

        Parameters
        ----------
        msg : IndiMessage
            The message to send.

        Raises
        ------
        DeviceNotServing
            Raised if the device is not attached to a runtime. Also a
            RuntimeError.
        """
        if self._emit is None:
            raise DeviceNotServing(
                "Device is not attached to a runtime; define/send only works while serving"
            )
        self._emit(msg)

    async def _dispatch_get_properties(self, request: GetProperties) -> None:
        """Handle a ``getProperties``: run :meth:`setup` once, else re-announce.

        A request naming a *different* device is ignored, per the INDI spec (a
        driver answers only for its own device; ``device`` absent means "all").
        The first matching request runs :meth:`setup`; later ones (a late-joining
        client) re-emit the ``def`` for every property already defined.

        A device that defined ``CONFIG_PROCESS`` publishes
        ``NEXUS_CONFIG_PERSISTED`` here too, once :meth:`setup` has returned and
        the persisted set is settled - see :meth:`_publish_persisted`.

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
                    # Inside the try, so a device that cannot publish its
                    # persisted list rolls back with the rest of the attempt
                    # rather than serving a configuration surface it never
                    # finished describing.
                    self._publish_persisted()
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

        What rolls back is what the attempt *defined*. A property the attempt
        **deleted** stays deleted: a retraction cannot be taken back, because the
        handle behind it is dead and reinstating it would put a property in the
        registry that re-announces to every later client and raises on the first
        :meth:`BoundProperty.set`.

        Parameters
        ----------
        announced : dict
            The properties as they stood before the attempt began, keyed by
            name. The device is restored to those of them still live.
        exc : Exception
            The failure, quoted to the client on each retraction so the panel
            says why the property went away.
        """
        survived = {
            name: prop for name, prop in announced.items() if self._properties.get(name) is prop
        }
        # Snapshot the items: delete() unregisters the property as it retracts
        # it, so iterating the live mapping would mutate it mid-loop.
        for name, prop in list(self._properties.items()):
            if announced.get(name) is not prop:
                prop.delete(message=f"{self._device} setup failed: {exc}")
        self._properties = survived
        for prop in survived.values():
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


#: What each ``CONFIG_PROCESS`` member does. Declared after the class because
#: the values are its own unbound methods, and kept as a table rather than a
#: chain of ``if``\ s so the membership test and the dispatch cannot disagree
#: about which actions exist.
_CONFIG_ACTIONS: dict[str, Callable[[Device], Coroutine[Any, Any, None]]] = {
    CONFIG_LOAD: Device.load_config,
    CONFIG_SAVE: Device.save_config,
    CONFIG_PURGE: Device.purge_config,
}

#: How each action is named when it fails, for the client-facing error.
_CONFIG_LABELS = {
    CONFIG_LOAD: "Loading the configuration",
    CONFIG_SAVE: "Saving the configuration",
    CONFIG_PURGE: "Purging the configuration",
}
