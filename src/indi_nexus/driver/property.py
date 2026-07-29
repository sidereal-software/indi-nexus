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
    """Accept ``ISState``/``bool``/``"On"``/``"Off"`` for a switch element value."""
    if isinstance(value, ISState):
        return value
    if isinstance(value, bool):
        return ISState.ON if value else ISState.OFF
    return ISState(value)


class BoundProperty:
    """A property vector plus the hook that pushes updates to the client."""

    def __init__(self, vector: Vector, emit: Emit) -> None:
        self._vector = vector
        self._emit = emit

    @property
    def vector(self) -> Vector:
        """The underlying (mutable) protocol model."""
        return self._vector

    @property
    def name(self) -> str:
        return self._vector.name

    @property
    def state(self) -> IPState:
        return self._vector.state

    def __getitem__(self, name: str) -> Element:
        return self._vector.element(name)

    def value(self, name: str) -> Any:
        """Return the current value of element ``name`` (``.data`` for a BLOB)."""
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
        """Assign element values by name, update state, and emit a ``set``.

        ``set(RA=1.23, DEC=4.56, state=IPState.OK)`` writes the two elements, sets
        the vector state, stamps the timestamp, and sends a single
        ``setNumberVector`` to the client. For a ``OneOfMany`` switch vector,
        turning one element On automatically turns its siblings Off.

        Elements are passed as keyword arguments. Use the positional ``values``
        dict for element names that collide with the reserved keywords
        (``state`` / ``message`` / ``timestamp``), e.g.
        ``set({"state": "Ok"}, state=IPState.OK)``.
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
        """Tell the client this property has gone away (``delProperty``)."""
        self._emit(DelProperty(device=self._vector.device, name=self._vector.name, message=message))

    def _assign(self, name: str, val: Any) -> None:
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
