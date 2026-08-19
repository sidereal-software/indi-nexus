"""``BoundProperty``: a driver-side handle over a protocol vector.

The protocol models in :mod:`indikit.protocol.models` are pure data - they are
the shared wire contract with the frontend and must stay free of runtime
behaviour. ``BoundProperty`` is the driver-side wrapper that adds the "and now
tell the client" behaviour: mutate the vector's elements and emit the
corresponding ``setXxxVector`` in one call.

The handle is generic in its vector, so ``define_switch(...)`` hands back a
``BoundProperty[SwitchVector]`` and ``prop.vector.elements`` is a ``list[Switch]``
rather than the whole element union - reading back what you defined type-checks
without a narrowing dance.

The handle is also the only thing holding a driver's live, mutable vector, which
is why the rule that an emission is a *value* is enforced here: every message
carrying a vector out of this class carries a copy, never the live model, so
nothing the driver does next can change what has already gone on the wire. See
:meth:`BoundProperty._detached` for what that is worth and what it costs.

A driver never constructs this directly; ``Device.define_*`` returns one.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from indikit.exceptions import (
    PropertyNotFound,
    PropertyRetracted,
    ProtocolError,
    WrongPropertyKind,
)
from indikit.protocol import (
    BLOB,
    DefVector,
    DelProperty,
    Element,
    IndiMessage,
    IPState,
    ISRule,
    ISState,
    LightVector,
    Number,
    SetVector,
    Switch,
    SwitchVector,
    Text,
    Vector,
    as_utc,
    coerce_switch,
    format_number,
    indi_now,
    zlib_encoded,
)

if TYPE_CHECKING:
    from indikit.driver.device import Device

Emit = Callable[[IndiMessage], None]

#: When a `BoundProperty` puts a ``set`` on the wire. ``"always"`` emits on every
#: :meth:`BoundProperty.set`; ``"on_change"`` emits only when a value, the state
#: or the message actually differs from what the client was last told.
EmitPolicy = Literal["always", "on_change"]

#: Switch rules that allow at most one member On, so turning one On clears the
#: rest. ``AnyOfMany`` is the only rule without that invariant.
_EXCLUSIVE_RULES = (ISRule.ONE_OF_MANY, ISRule.AT_MOST_ONE)

#: What :meth:`BoundProperty.select` gives the elements it did not select. Only
#: lights and switches have an "off" value; a number or a text does not.
_UNSELECTED: dict[type, Any] = {
    LightVector: IPState.IDLE,
    SwitchVector: ISState.OFF,
}


class BoundProperty[VectorT: Vector]:
    """A property vector plus the hook that pushes updates to the client.

    Parameters
    ----------
    vector : VectorT
        The protocol vector this handle wraps and mutates in place.
    emit : Callable
        Callback that queues an outbound message on the runtime.
    policy : str, optional
        When to put a ``set`` on the wire; see :data:`EmitPolicy`.
    owner : Device, optional
        The device this property is registered with, so :meth:`delete` can
        remove it there rather than only announcing its removal. `None` for a
        handle built outside a device (a unit test over a bare vector), which
        makes :meth:`delete` announce-only.
    persist : bool, optional
        Whether this property's element values belong in the device's saved
        configuration; see `~indikit.driver.device.Device.define_config`.
    """

    def __init__(
        self,
        vector: VectorT,
        emit: Emit,
        *,
        policy: EmitPolicy = "always",
        owner: Device | None = None,
        persist: bool = False,
    ) -> None:
        """Wrap ``vector`` with the runtime's outbound-message callback."""
        self._vector = vector
        self._emit = emit
        self._policy: EmitPolicy = policy
        self._owner = owner
        self._persist = persist
        # Set by delete(): the client has been told this property is gone, so
        # anything published through this handle afterwards contradicts that.
        self._retracted = False

    @property
    def vector(self) -> VectorT:
        """The underlying (mutable) protocol model."""
        return self._vector

    @property
    def name(self) -> str:
        """The property's name."""
        return self._vector.name

    @property
    def state(self) -> IPState:
        """The property's current vector state."""
        return self._vector.state

    @property
    def persist(self) -> bool:
        """Whether this property's values belong in the saved configuration."""
        return self._persist

    def __getitem__(self, name: str) -> Element:
        """Return element ``name`` (raises :class:`PropertyNotFound` if absent)."""
        return self._vector.element(name)

    def __contains__(self, name: str) -> bool:
        """Return whether this property has an element called ``name``.

        The guard for driving a property from hardware that may report a value
        the driver has no element for::

            if reported not in self["state_message"]:
                self.log_error(f"Unknown state {reported!r}")
        """
        return any(el.name == name for el in self._vector.elements)

    def value(self, name: str) -> Any:
        """Return the current value of an element.

        Parameters
        ----------
        name : str
            The element name.

        Returns
        -------
        value : object
            The element's ``value`` (or ``data`` for a BLOB element).
        """
        el = self._vector.element(name)
        if isinstance(el, BLOB):
            return el.data
        return el.value

    def set(
        self,
        values: dict[str, Any] | None = None,
        *,
        state: IPState | None = None,
        message: str | None = None,
        timestamp: dt.datetime | None = None,
        force: bool = False,
        **kwargs: Any,
    ) -> None:
        """Assign element values, update state, and emit a ``set`` to the client.

        ``set(RA=1.23, DEC=4.56, state=IPState.OK)`` writes the two elements, sets
        the vector state, stamps the timestamp, and sends a single
        ``setNumberVector``. For a ``OneOfMany`` or ``AtMostOne`` switch vector,
        turning one element On automatically turns its siblings Off.

        Under the ``"on_change"`` emit policy the values are still written, but
        nothing goes on the wire (and the timestamp is left alone) when the
        result is identical to what the client was last told. "Identical" means
        the *wire* representation: a number whose declared ``format`` renders it
        the same way has not changed anything a client can see.

        Parameters
        ----------
        values : dict, optional
            Element values keyed by name, for names that collide with the
            reserved keywords below, e.g. ``set({"state": "Ok"}, state=IPState.OK)``.
        state : IPState, optional
            New vector state, if changing it.
        message : str, optional
            Optional message to attach to the update.
        timestamp : datetime, optional
            Update timestamp; defaults to now. INDI timestamps are UTC, so a
            naive one is read as UTC and an aware one is converted.
        force : bool, optional
            Emit even under ``"on_change"`` when nothing differs - for the
            occasional deliberate re-announcement.
        **kwargs : object
            Element values by name (the common case).

        Raises
        ------
        PropertyNotFound
            Raised if a named element is not part of this vector. Also a
            KeyError.
        ProtocolError
            Raised if a number element is given a non-finite value, which
            neither wire format can carry. Also a ValueError.
        PropertyRetracted
            Raised if the property has been retracted (see :meth:`delete`).
            Also a RuntimeError.
        """
        self._require_live()
        merged = {**(values or {}), **kwargs}
        before = self._snapshot()
        for elem_name, val in merged.items():
            self._assign(elem_name, val)
        if state is not None:
            self._vector.state = state
        if message is not None:
            self._vector.message = message
        self._publish(before, force=force, timestamp=timestamp)

    def set_all(
        self,
        value: Any,
        *,
        state: IPState | None = None,
        message: str | None = None,
        force: bool = False,
    ) -> None:
        """Assign one value to every element and emit a single ``set``.

        The reset half of the "one of N lights is lit" idiom::

            self["state_message"].set_all(IPState.IDLE)
            self["state_message"].set(**{lit: IPState.BUSY}, state=IPState.BUSY)

        Parameters
        ----------
        value : object
            The value written to every element, coerced per element kind.
        state : IPState, optional
            New vector state, if changing it.
        message : str, optional
            Optional message to attach to the update.
        force : bool, optional
            Emit even under ``"on_change"`` when nothing differs.
        """
        self.set(
            dict.fromkeys((el.name for el in self._vector.elements), value),
            state=state,
            message=message,
            force=force,
        )

    def select(
        self,
        name: str,
        value: Any,
        *,
        others: Any = None,
        state: IPState | None = None,
        message: str | None = None,
        force: bool = False,
    ) -> None:
        """Give one element ``value``, reset the rest, and emit once.

        "Exactly one of these is the current one" is the most common shape in
        INDI status reporting - a bank of lights where one shows the state the
        instrument is in, and the vector takes that light's state::

            self.light("state_message").select("domeslit_opening", IPState.BUSY)

        which is the whole idiom: the named light goes Busy, every sibling goes
        Idle, and so does the vector. Without a ``state`` the vector follows
        ``value`` when that is an :class:`IPState`.

        Parameters
        ----------
        name : str
            The element to select.
        value : object
            The value it takes.
        others : object, optional
            The value every other element takes. Defaults to ``Idle`` for a
            light vector and ``Off`` for a switch vector.
        state : IPState, optional
            New vector state. Defaults to ``value`` when that is an `IPState`,
            otherwise the state is left alone.
        message : str, optional
            Optional message to attach to the update.
        force : bool, optional
            Emit even under ``"on_change"`` when nothing differs.

        Raises
        ------
        PropertyNotFound
            Raised if ``name`` is not an element of this vector. Also a
            KeyError.
        WrongPropertyKind
            Raised for a vector kind with no natural "unselected" value, unless
            ``others`` says what it is. Also a TypeError.
        """
        if name not in self:
            raise PropertyNotFound(f"{name!r} not in {self._vector.device}.{self._vector.name}")
        if others is None:
            others = _UNSELECTED.get(type(self._vector))
            if others is None:
                raise WrongPropertyKind(
                    f"select() needs others= for a {type(self._vector).__name__}; "
                    "only light and switch vectors have a natural unselected value"
                )
        if state is None and isinstance(value, IPState):
            state = value
        self.set(
            {el.name: (value if el.name == name else others) for el in self._vector.elements},
            state=state,
            message=message,
            force=force,
        )

    def delete(self, message: str | None = None) -> None:
        """Withdraw this property: drop it from the device, then tell the client.

        Deletion is a *removal*, not just an announcement. The property leaves
        the device's registry first and the ``delProperty`` follows, so a
        ``getProperties`` arriving afterwards - a client joining late - is not
        told about a property the driver has withdrawn. That order is libindi's:
        ``INDI::DefaultDevice::deleteProperty`` calls ``removeProperty`` and only
        emits if it succeeded.

        The handle goes with the property: :meth:`set` through it afterwards
        raises rather than publishing an update for something the client has been
        told no longer exists. A property that comes back comes back through
        ``define_*``, which registers it again and hands out a fresh handle.

        Deleting twice is a no-op the second time - nothing is left to remove and
        the client has already been told - so a driver that keeps its handle can
        retract unconditionally::

            async def on_disconnect(self) -> None:
                self._cooler.delete("only while connected")

        A driver that reaches its properties by name wants
        `~indikit.driver.device.Device.delete_property` instead:
        ``self["CCD_COOLER"]`` raises :class:`PropertyNotFound` once the
        property is gone, so the name-based call is the one that can be
        repeated.

        Parameters
        ----------
        message : str, optional
            Optional explanation to include with the deletion, shown by clients
            that surface it (libindi logs it as a device message before applying
            the deletion).
        """
        if self._retracted:
            return
        self._retracted = True
        # A handle retracts exactly the property it owns, and says nothing when
        # it owns nothing: already retracted above, or superseded here by a
        # redefinition under the same name, whose ``def`` the client has already
        # seen and which a ``delProperty`` for that name would wrongly withdraw.
        if self._owner is not None and not self._owner._forget(self):
            return
        self._emit(
            DelProperty(
                device=self._vector.device,
                name=self._vector.name,
                # Stamped like every other emission: libindi's IDDelete always
                # dates the retraction, and a client logging the event has
                # nothing else to date it by.
                timestamp=indi_now(),
                message=message,
            )
        )

    def _apply_values(self, values: dict[str, Any]) -> list[str]:
        """Write saved element values into the vector, emitting nothing.

        The restore half of persistence, and deliberately **tolerant** where
        :meth:`set` is strict, because its input is a file rather than a call
        site: a configuration written by an older version of the driver names
        elements this one no longer has, and a hand-edited one carries values
        that will not take. Neither is a reason to abandon the rest of the
        property, so an element the vector does not have is ignored and one that
        refuses its value is dropped and named, while every other element
        applies.

        Nothing goes on the wire and the timestamp is untouched, so a caller can
        restore into a vector *before* its ``def`` is announced and put one
        frame on the wire instead of a default followed by a correction.

        Parameters
        ----------
        values : dict
            Element values keyed by name, as read from the saved configuration.

        Returns
        -------
        rejected : list of str
            The elements whose saved value the vector refused, in the order
            they were tried. Empty when everything applied.

        Raises
        ------
        PropertyRetracted
            Raised if the property has been retracted. Also a RuntimeError.
        """
        self._require_live()
        rejected: list[str] = []
        for name, value in values.items():
            if name not in self:
                continue
            try:
                self._assign(name, value)
            except (ValueError, TypeError):
                # ProtocolError (a non-finite number) is a ValueError, and a
                # switch value that is not a wire token comes out of
                # coerce_switch as one too. PropertyNotFound cannot reach here:
                # the membership check above already ruled it out.
                rejected.append(name)
        return rejected

    def _restore(self, values: dict[str, Any]) -> list[str]:
        """Apply saved values to a live property and publish the result.

        The mid-session half of :meth:`_apply_values`: the property has already
        been announced, so the client has to be told what it now holds. One
        ``set`` carries the whole vector, and the emit policy applies exactly as
        it does to any other update - an ``"on_change"`` property restored to
        the values it already had says nothing.

        The values arrive as a mapping and stay one. Splatting them as keyword
        arguments would work until a saved element name is not a Python
        identifier, which the protocol permits and real drivers use.

        Parameters
        ----------
        values : dict
            Element values keyed by name, as read from the saved configuration.

        Returns
        -------
        rejected : list of str
            The elements whose saved value the vector refused.

        Raises
        ------
        PropertyRetracted
            Raised if the property has been retracted. Also a RuntimeError.
        """
        before = self._snapshot()
        rejected = self._apply_values(values)
        self._publish(before, force=False)
        return rejected

    def _publish(
        self,
        before: tuple[dict[str, Any], IPState, str | None],
        *,
        force: bool,
        timestamp: dt.datetime | None = None,
    ) -> None:
        """Emit the ``set`` for changes already written, under the emit policy.

        The tail every mutating call shares, so "when does an update reach the
        wire" has one implementation rather than one per caller.

        Parameters
        ----------
        before : tuple
            The :meth:`_snapshot` taken before the values were written.
        force : bool
            Emit even under ``"on_change"`` when nothing differs.
        timestamp : datetime, optional
            Update timestamp; defaults to now.
        """
        if not force and self._policy == "on_change" and self._snapshot() == before:
            return
        # Normalise the argument, not just the default: assigning to a model
        # attribute skips the field validator that would otherwise do it, so a
        # caller's naive datetime would reach JSON unlabelled while the XML for
        # the same emission called it UTC.
        self._vector.timestamp = as_utc(timestamp) if timestamp is not None else indi_now()
        self._emit(SetVector(vector=self._detached()))

    def _require_live(self) -> None:
        """Refuse to publish through a handle whose property has been retracted.

        Raises
        ------
        PropertyRetracted
            Raised if :meth:`delete` has already run. Also a RuntimeError.
        """
        if self._retracted:
            raise PropertyRetracted(
                f"{self._vector.device}.{self._vector.name} was retracted with a delProperty; "
                "this handle is dead. Define the property again and use the handle that returns."
            )

    def _announce(self) -> None:
        """Emit this property's ``def``, describing it as it stands right now.

        ``Device`` calls this to introduce a property and to re-announce one to a
        late-joining client, rather than building the ``defXxxVector`` out of
        ``prop.vector`` itself. Routing it through the handle is what stops the
        live vector escaping: this class holds the only mutable one, so it is the
        only place that has to remember to detach a copy.
        """
        self._emit(DefVector(vector=self._detached()))

    def _detached(self) -> Vector:
        """Return a copy of the vector that later mutation cannot reach.

        An emitted message is a *value*. The runtime queues it and serialises it
        from a separate writer task, so a message still pointing at this handle's
        live vector reports whatever the driver did next, not what it published:
        the ubiquitous "go Busy, move, report Ok" pair emitted two frames that
        both said ``Ok``, and the Busy transient reached no client at all.

        The copy itself is `~indikit.protocol.models.Vector.detached`, shared
        with the client, which hands the same kind of copy to a resolved
        ``wait_for`` for the same reason.

        Returns
        -------
        vector : Vector
            A copy of the vector, sharing nothing mutable with this handle.
        """
        return self._vector.detached()

    def _snapshot(self) -> tuple[dict[str, Any], IPState, str | None]:
        """Return everything a ``set`` would tell the client, minus the timestamp.

        Compared before and after the assignment to decide whether an
        ``"on_change"`` property has anything to say, so this is the *wire*
        representation, not the in-memory one. Numbers are rendered through
        their INDI ``format``: a sensor whose raw float jitters in the twelfth
        decimal has not changed anything a client can see, and a driver
        declaring ``%.1f`` has said which digits it means. The timestamp is
        excluded deliberately - it always differs, and a fresh timestamp alone
        is not news.

        Returns
        -------
        snapshot : tuple
            The element values as the client would receive them, the vector
            state, and the vector message.
        """
        values = self._vector.values()
        for el in self._vector.elements:
            if isinstance(el, Number):
                values[el.name] = format_number(el.value, el.format)
        return values, self._vector.state, self._vector.message

    def _assign(self, name: str, val: Any) -> None:
        """Write one element value, applying per-kind coercion and switch rules.

        Parameters
        ----------
        name : str
            The element name to write.
        val : object
            The new value; coerced for switches and BLOBs.

        Raises
        ------
        PropertyNotFound
            Raised if ``name`` is not an element of this vector. Also a
            KeyError.
        ProtocolError
            Raised if a number element is given a non-finite value. Also a
            ValueError.
        """
        vec = self._vector
        el = vec.element(name)  # raises PropertyNotFound if the element is unknown
        if isinstance(el, Switch):
            state = coerce_switch(val)
            # Turning one Off needs no sibling bookkeeping under any rule:
            # AtMostOne allows zero On, and OneOfMany expects the client to name
            # the new member rather than deselect the old one.
            if (
                state == ISState.ON
                and isinstance(vec, SwitchVector)
                and vec.rule in _EXCLUSIVE_RULES
            ):
                for sw in vec.elements:
                    sw.value = ISState.ON if sw.name == name else ISState.OFF
                return
            el.value = state
            return
        if isinstance(el, BLOB):
            data = bytes(val)
            el.data = data
            # INDI's `size` is the decoded *and uncompressed* length, so the
            # payload's own length answers it only for a payload that is
            # neither. A `.z` element is handed bytes the driver deflated, and
            # writing len(data) there put the *compressed* length on the wire
            # under an attribute the spec defines as the other number - silently,
            # since it is a plausible integer. Leaving it alone means the driver
            # states it (once at define time for a fixed frame, or per frame
            # beside the compression), and a driver that states nothing gets a
            # loud refusal out of the codec instead of a wrong frame: see
            # indikit.protocol.compression.require_declared_size.
            if not zlib_encoded(el.format):
                el.size = len(data)
            return
        if isinstance(el, Text):
            # Coerce here rather than at serialisation: a text element handed a
            # number is overwhelmingly a reading being published, and INDI text
            # is text. Left raw, it would sail through assignment and then fail
            # inside the writer loop, a long way from the call that caused it.
            el.value = val if isinstance(val, str) else str(val)
            return
        if isinstance(el, Number):
            # Coerced and checked here for the same reason as the Text above,
            # and the same reason Number.value forbids a non-finite value on the
            # model: assigning to a model attribute skips validation entirely,
            # so a NaN off a sulking sensor - or a string out of a saved
            # configuration - would sail through here and fail in the writer
            # loop instead, or reach a browser as a JSON `null` that cannot be
            # read back. Failing at the call site is what names the element.
            try:
                number = float(val)
            except (TypeError, ValueError):
                raise ProtocolError(
                    f"{vec.device}.{vec.name}.{name} cannot be set to {val!r}"
                ) from None
            if not math.isfinite(number):
                raise ProtocolError(f"{vec.device}.{vec.name}.{name} cannot be set to {val!r}")
            el.value = number
            return
        el.value = val  # Light(IPState)
