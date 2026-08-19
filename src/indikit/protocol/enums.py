"""INDI protocol enumerations.

Each enum subclasses :class:`enum.StrEnum`, so a member *is* the exact token used
on the INDI wire (e.g. ``IPState.OK == "Ok"`` is ``True``) and Pydantic serialises
it to that token directly.

:func:`coerce_switch` lives here too, because every caller-facing API that takes
a switch value has to accept the same three spellings of it.
"""

from __future__ import annotations

from enum import StrEnum


class _StrEnum(StrEnum):
    """Base for the wire enums: value lookups tolerate surrounding whitespace.

    :class:`~enum.StrEnum` already makes each member its own string value and
    provides ``__str__``; this base only adds the lenient lookup below.
    """

    @classmethod
    def _missing_(cls, value: object) -> _StrEnum | None:
        """Resolve a wire token to a member, ignoring surrounding whitespace.

        Parameters
        ----------
        value : object
            The raw value looked up, e.g. ``"Ok "`` straight off the wire.

        Returns
        -------
        member : _StrEnum or None
            The matching member, or `None` to let `~enum.Enum` raise.
        """
        if isinstance(value, str):
            stripped = value.strip()
            for member in cls:
                if member.value == stripped:
                    return member
        return None


class IPState(_StrEnum):
    """State of a vector property (the coloured status light in a GUI)."""

    IDLE = "Idle"
    OK = "Ok"
    BUSY = "Busy"
    ALERT = "Alert"


class IPerm(_StrEnum):
    """Client access permission for a vector property."""

    RO = "ro"
    WO = "wo"
    RW = "rw"


class ISRule(_StrEnum):
    """Constraint on how many switches in a switch vector may be On."""

    ONE_OF_MANY = "OneOfMany"
    AT_MOST_ONE = "AtMostOne"
    ANY_OF_MANY = "AnyOfMany"


class ISState(_StrEnum):
    """On/Off state of a single switch."""

    OFF = "Off"
    ON = "On"


class BLOBPolicy(_StrEnum):
    """How ``indiserver`` should deliver BLOBs to a client.

    A client must send an ``enableBLOB`` with one of these policies before
    ``indiserver`` will forward any BLOB; the default on the wire is ``Never``.
    """

    NEVER = "Never"
    ALSO = "Also"
    ONLY = "Only"


def coerce_switch(value: ISState | bool | str) -> ISState:
    """Coerce a caller-supplied switch value into an :class:`ISState`.

    Every API that takes a switch value from application code - the driver's
    ``BoundProperty.set``, the client's ``set_switch``, the test harness's
    ``write`` - accepts the same three spellings, because ``POWER=True`` is what
    a caller writes and ``"On"`` is what the wire calls it. This is the one
    implementation of that rule.

    Parameters
    ----------
    value : ISState or bool or str
        An `ISState`, a `bool` (`True` -> On), or a wire token (``"On"`` /
        ``"Off"``).

    Returns
    -------
    state : ISState
        The corresponding switch state.

    Raises
    ------
    ValueError
        Raised if a string names no switch state.
    """
    # ISState first: it is a str subclass, so the str branch would swallow it.
    if isinstance(value, ISState):
        return value
    if isinstance(value, bool):
        return ISState.ON if value else ISState.OFF
    return ISState(value)
