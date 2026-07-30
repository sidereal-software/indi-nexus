"""``BoundProperty``: a driver-side handle over a protocol vector.

The protocol models in :mod:`indi_nexus.protocol.models` are pure data - they are
the shared wire contract with the frontend and must stay free of runtime
behaviour. ``BoundProperty`` is the driver-side wrapper that adds the "and now
tell the client" behaviour: mutate the vector's elements and emit the
corresponding ``setXxxVector`` in one call.

A driver never constructs this directly; ``Device.define_*`` returns one.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

from indi_nexus.protocol import (
    BLOB,
    DelProperty,
    Element,
    IndiMessage,
    IPState,
    ISRule,
    ISState,
    SetVector,
    Switch,
    SwitchVector,
    Vector,
)

Emit = Callable[[IndiMessage], None]


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


class BoundProperty:
    """A property vector plus the hook that pushes updates to the client.

    Parameters
    ----------
    vector : Vector
        The protocol vector this handle wraps and mutates in place.
    emit : Callable
        Callback that queues an outbound message on the runtime.
    """

    def __init__(self, vector: Vector, emit: Emit) -> None:
        """Wrap ``vector`` with the runtime's outbound-message callback."""
        self._vector = vector
        self._emit = emit

    @property
    def vector(self) -> Vector:
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
        **kwargs: Any,
    ) -> None:
        """Assign element values, update state, and emit a ``set`` to the client.

        ``set(RA=1.23, DEC=4.56, state=IPState.OK)`` writes the two elements, sets
        the vector state, stamps the timestamp, and sends a single
        ``setNumberVector``. For a ``OneOfMany`` switch vector, turning one element
        On automatically turns its siblings Off.

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
        **kwargs : object
            Element values by name (the common case).
        """
        merged = {**(values or {}), **kwargs}
        for elem_name, val in merged.items():
            self._assign(elem_name, val)
        if state is not None:
            self._vector.state = state
        if message is not None:
            self._vector.message = message
        self._vector.timestamp = timestamp or dt.datetime.now()
        self._emit(SetVector(vector=self._vector))

    def delete(self, message: str | None = None) -> None:
        """Tell the client this property has gone away (``delProperty``).

        Parameters
        ----------
        message : str, optional
            Optional explanation to include with the deletion.
        """
        self._emit(DelProperty(device=self._vector.device, name=self._vector.name, message=message))

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
            if (
                isinstance(vec, SwitchVector)
                and vec.rule == ISRule.ONE_OF_MANY
                and state == ISState.ON
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
        el.value = val  # Number(float) | Text(str) | Light(IPState)
