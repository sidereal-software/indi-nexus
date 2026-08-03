"""``BoundProperty``: a driver-side handle over a protocol vector.

The protocol models in :mod:`indi_nexus.protocol.models` are pure data - they are
the shared wire contract with the frontend and must stay free of runtime
behaviour. ``BoundProperty`` is the driver-side wrapper that adds the "and now
tell the client" behaviour: mutate the vector's elements and emit the
corresponding ``setXxxVector`` in one call.

The handle is generic in its vector, so ``define_switch(...)`` hands back a
``BoundProperty[SwitchVector]`` and ``prop.vector.elements`` is a ``list[Switch]``
rather than the whole element union - reading back what you defined type-checks
without a narrowing dance.

A driver never constructs this directly; ``Device.define_*`` returns one.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, Literal

from indi_nexus.protocol import (
    BLOB,
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
)
from indi_nexus.protocol.xml import format_number

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


def _coerce_switch(value: Any) -> ISState:
    """Coerce a user-supplied switch value into an :class:`ISState`.

    Parameters
    ----------
    value : ISState or bool or str
        An `~indi_nexus.protocol.ISState`, a `bool` (`True` -> On), or a wire
        string (``"On"`` / ``"Off"``).

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
    """

    def __init__(self, vector: VectorT, emit: Emit, *, policy: EmitPolicy = "always") -> None:
        """Wrap ``vector`` with the runtime's outbound-message callback."""
        self._vector = vector
        self._emit = emit
        self._policy: EmitPolicy = policy

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

    def __getitem__(self, name: str) -> Element:
        """Return element ``name`` (raises :class:`KeyError` if absent)."""
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
            Update timestamp; defaults to now.
        force : bool, optional
            Emit even under ``"on_change"`` when nothing differs - for the
            occasional deliberate re-announcement.
        **kwargs : object
            Element values by name (the common case).
        """
        merged = {**(values or {}), **kwargs}
        before = self._snapshot()
        for elem_name, val in merged.items():
            self._assign(elem_name, val)
        if state is not None:
            self._vector.state = state
        if message is not None:
            self._vector.message = message
        if not force and self._policy == "on_change" and self._snapshot() == before:
            return
        self._vector.timestamp = timestamp or dt.datetime.now()
        self._emit(SetVector(vector=self._vector))

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
        KeyError
            Raised if ``name`` is not an element of this vector.
        TypeError
            Raised for a vector kind with no natural "unselected" value, unless
            ``others`` says what it is.
        """
        if name not in self:
            raise KeyError(f"{name!r} not in {self._vector.device}.{self._vector.name}")
        if others is None:
            others = _UNSELECTED.get(type(self._vector))
            if others is None:
                raise TypeError(
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
        """Tell the client this property has gone away (``delProperty``).

        Parameters
        ----------
        message : str, optional
            Optional explanation to include with the deletion.
        """
        self._emit(DelProperty(device=self._vector.device, name=self._vector.name, message=message))

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
        KeyError
            Raised if ``name`` is not an element of this vector.
        """
        vec = self._vector
        el = vec.element(name)  # raises KeyError if the element is unknown
        if isinstance(el, Switch):
            state = _coerce_switch(val)
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
            el.size = len(data)
            return
        if isinstance(el, Text):
            # Coerce here rather than at serialisation: a text element handed a
            # number is overwhelmingly a reading being published, and INDI text
            # is text. Left raw, it would sail through assignment and then fail
            # inside the writer loop, a long way from the call that caused it.
            el.value = val if isinstance(val, str) else str(val)
            return
        el.value = val  # Number(float) | Light(IPState)
