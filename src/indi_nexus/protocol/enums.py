"""INDI protocol enumerations.

Each enum mixes in ``str`` so its members *are* the exact tokens used on the INDI
wire (e.g. ``IPState.OK == "Ok"`` is ``True``) and Pydantic serializes them to
those tokens directly. This replaces pyINDI's ``INDIEnumMember(int)`` trick,
which subclassed ``int`` and overloaded ``__eq__`` to compare against strings.

(``enum.StrEnum`` would be the idiomatic choice but is only available on
Python 3.11+; the ``str, Enum`` mixin is the equivalent for our 3.10 floor.)
"""

from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    """A string-valued enum whose members compare and serialize as their value."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)

    @classmethod
    def _missing_(cls, value: object) -> _StrEnum | None:
        # Be lenient with surrounding whitespace coming off the wire.
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
