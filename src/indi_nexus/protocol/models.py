"""Typed Pydantic models for INDI properties and wire messages.

Design notes
------------
* A *vector* (``NumberVector`` etc.) is the canonical, in-memory representation
  of a property. It carries the full metadata plus its elements. A driver holds
  vectors; a client caches them and applies incoming updates onto them.

* Element metadata (``format``/``min``/``max``/``step`` on numbers, ``rule`` on
  switch vectors, ...) is only present in a ``def`` message. In ``set`` and
  ``new`` messages the wire carries just ``name`` + value per element. We model
  that by making the metadata fields optional with defaults, so the same element
  class round-trips through both contexts. Clients are expected to merge ``set``
  values onto the previously-defined vector, which is standard INDI behavior.

* The ``def`` / ``set`` / ``new`` distinction is a wire *intent*, not a
  different data shape, so it is expressed by the thin event wrappers at the
  bottom of this module rather than by duplicating every vector five times.

* Every timestamp is UTC. INDI requires it (white paper p.5) and libindi writes
  a bare, offset-less ``%Y-%m-%dT%H:%M:%S``, so :data:`IndiTimestamp` normalises
  whatever a caller or a peer supplies into an aware UTC datetime in one place -
  the model - rather than at each of the codecs.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from typing import Annotated, Any, Literal, Self, cast

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from indi_nexus.protocol.enums import BLOBPolicy, IPerm, IPState, ISRule, ISState

INDI_VERSION = "1.7"


def slugify(label: str) -> str:
    """Return the conventional INDI element name for a display label.

    INDI names are machine identifiers and labels are display text, so the two
    differ by exactly this transformation in most drivers: ``"Domeslit State"``
    becomes ``"domeslit_state"``. The default key for :meth:`_Element.from_labels`.

    Parameters
    ----------
    label : str
        The human-readable label.

    Returns
    -------
    name : str
        The label lowercased with runs of whitespace collapsed to underscores.
    """
    return "_".join(label.lower().split())


# --------------------------------------------------------------------------- #
# Timestamps                                                                   #
# --------------------------------------------------------------------------- #
def as_utc(value: dt.datetime) -> dt.datetime:
    """Return a datetime as aware UTC, reading a naive one *as* UTC.

    A bare INDI timestamp carries no offset and means UTC, so that is what a
    naive datetime is taken to be. Guessing a local offset for an unknown peer
    would invent information: the same string would mean a different instant
    depending on where the reader happens to be running.

    Parameters
    ----------
    value : datetime
        The datetime to normalise. Naive values are labelled UTC; aware values
        in another zone are converted.

    Returns
    -------
    value : datetime
        The same instant, expressed in UTC with ``tzinfo`` set.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)


def indi_now() -> dt.datetime:
    """Return the current time the way INDI stamps one: aware UTC, whole seconds.

    Truncated to the second because that is the resolution the XML format has:
    keeping microseconds would let one emission disagree with itself, the JSON
    carrying a precision the XML for the same message had already dropped.

    Returns
    -------
    now : datetime
        The current UTC time with a zero microsecond field.
    """
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


#: A wire timestamp: whatever is supplied, held as aware UTC. The static type is
#: still :class:`datetime.datetime`, so annotations and type checking are
#: unaffected; only the validated value changes.
IndiTimestamp = Annotated[dt.datetime, AfterValidator(as_utc)]


class _Model(BaseModel):
    """Shared config: ignore unknown wire attributes, base64 BLOB bytes in JSON."""

    model_config = ConfigDict(
        extra="ignore",
        use_enum_values=False,
        # BLOB payloads are binary; encode/decode them as base64 in JSON so the
        # browser wire contract stays valid JSON (the XML codec base64s too).
        ser_json_bytes="base64",
        val_json_bytes="base64",
    )


# --------------------------------------------------------------------------- #
# Elements                                                                    #
# --------------------------------------------------------------------------- #
class _Element(_Model):
    """Fields shared by every property element; not used on its own."""

    name: str
    label: str | None = None

    @classmethod
    def from_labels(
        cls, labels: Iterable[str], *, name: Callable[[str], str] = slugify
    ) -> list[Self]:
        """Build one element per display label, naming each with ``name``.

        The bulk constructor for the two shapes that recur in every driver: a
        group of status lights, and a table of read-only values. Each element
        takes its kind's default value, which ``set`` then fills in::

            self.define_light("state", Light.from_labels(STATE_LABELS))

        Parameters
        ----------
        labels : iterable of str
            The display labels, in definition order.
        name : Callable, optional
            Maps a label to its element name; :func:`slugify` by default.

        Returns
        -------
        elements : list of Self
            One element of this class per label.
        """
        return [cls(name=name(label), label=label) for label in labels]


class Number(_Element):
    """A single numeric element (``defNumber`` / ``oneNumber``)."""

    kind: Literal["number"] = "number"
    format: str = "%g"
    min: float | None = None
    max: float | None = None
    step: float | None = None
    value: float = 0.0


class Text(_Element):
    """A single text element (``defText`` / ``oneText``)."""

    kind: Literal["text"] = "text"
    value: str = ""


class Switch(_Element):
    """A single switch element (``defSwitch`` / ``oneSwitch``)."""

    kind: Literal["switch"] = "switch"
    value: ISState = ISState.OFF


class Light(_Element):
    """A single light element (``defLight`` / ``oneLight``). Read-only status."""

    kind: Literal["light"] = "light"
    value: IPState = IPState.IDLE


class BLOB(_Element):
    """A single BLOB element (``defBLOB`` / ``oneBLOB``).

    ``data`` holds the decoded binary payload; the base64/size framing lives in
    the codec, not the model.
    """

    kind: Literal["blob"] = "blob"
    format: str | None = None
    size: int | None = None
    data: bytes | None = None


Element = Annotated[
    Number | Text | Switch | Light | BLOB,
    Field(discriminator="kind"),
]


# --------------------------------------------------------------------------- #
# Vectors                                                                      #
# --------------------------------------------------------------------------- #
class _Vector(_Model):
    """Fields shared by every property vector; not used on its own."""

    device: str
    name: str
    label: str | None = None
    group: str | None = None
    state: IPState = IPState.IDLE
    timeout: float | None = None
    timestamp: IndiTimestamp | None = None
    message: str | None = None

    def element(self, name: str) -> Element:
        """Return the child element with a given name.

        Parameters
        ----------
        name : str
            The element name to look up.

        Returns
        -------
        element : Element
            The matching element.

        Raises
        ------
        KeyError
            Raised if no element with that name exists in this vector.
        """
        for el in self.elements:  # type: ignore[attr-defined]
            if el.name == name:
                return cast("Element", el)
        raise KeyError(f"{name!r} not in {self.device}.{self.name}")

    def __getitem__(self, name: str) -> Element:
        """Return element ``name`` (see :meth:`element`)."""
        return self.element(name)

    def __contains__(self, name: object) -> bool:
        """Return whether this vector carries an element with that name.

        Defining ``__getitem__`` without this leaves ``"RA" in vector`` to Python's
        old iteration fallback, which indexes 0, 1, 2 ... against a lookup that
        wants names. That does not raise, it just answers `False` for an element
        that is right there - the worst possible failure for a membership test,
        because the calling code looks correct.

        Parameters
        ----------
        name : object
            The element name to look for.

        Returns
        -------
        present : bool
            Whether an element of that name exists.
        """
        return any(el.name == name for el in self.elements)  # type: ignore[attr-defined]

    def get(self, name: str, default: Any = None) -> Any:
        """Return the value of element ``name``, or ``default`` when absent.

        The tolerant companion to :meth:`element`: a client's ``set``/``new``
        may name only some elements, so handlers read requested values with a
        fallback - ``ra = vector.get("RA", current_ra)``. BLOB elements yield
        their payload (``data``).

        Parameters
        ----------
        name : str
            The element name to look up.
        default : object, optional
            Returned when no element with that name exists.

        Returns
        -------
        value : object
            The element's value (or BLOB payload), or ``default``.
        """
        for el in self.elements:  # type: ignore[attr-defined]
            if el.name == name:
                return el.data if isinstance(el, BLOB) else el.value
        return default

    def values(self) -> dict[str, Any]:
        """Return the elements as a name-to-value mapping (payloads for BLOBs).

        Returns
        -------
        values : dict
            Element values keyed by element name.
        """
        return {
            el.name: (el.data if isinstance(el, BLOB) else el.value)
            for el in self.elements  # type: ignore[attr-defined]
        }


class NumberVector(_Vector):
    """A vector of numeric elements (``defNumberVector`` / ``setNumberVector``)."""

    kind: Literal["number"] = "number"
    perm: IPerm = IPerm.RW
    elements: list[Number] = Field(default_factory=list)


class TextVector(_Vector):
    """A vector of text elements (``defTextVector`` / ``setTextVector``)."""

    kind: Literal["text"] = "text"
    perm: IPerm = IPerm.RW
    elements: list[Text] = Field(default_factory=list)


class SwitchVector(_Vector):
    """A vector of switch elements with a selection ``rule``."""

    kind: Literal["switch"] = "switch"
    perm: IPerm = IPerm.RW
    rule: ISRule = ISRule.ANY_OF_MANY
    elements: list[Switch] = Field(default_factory=list)

    def selected(self) -> str | None:
        """Return the name of the first element that is On, or `None`.

        The idiomatic way to read a ``OneOfMany``/``AtMostOne`` client write:
        such a write names the newly selected member (often *only* that
        member), so the question is "which element is On in this request" -
        never "what is element X", which raises when X was not sent.

        Returns
        -------
        name : str or None
            The first On element's name, or `None` when none is On (an
            ``AtMostOne`` deselect).
        """
        for el in self.elements:
            if el.value is ISState.ON:
                return el.name
        return None


class LightVector(_Vector):
    """A vector of read-only light elements (no ``perm``; lights are always RO)."""

    kind: Literal["light"] = "light"
    elements: list[Light] = Field(default_factory=list)


class BLOBVector(_Vector):
    """A vector of BLOB elements (binary payloads)."""

    kind: Literal["blob"] = "blob"
    perm: IPerm = IPerm.RW
    elements: list[BLOB] = Field(default_factory=list)


Vector = Annotated[
    NumberVector | TextVector | SwitchVector | LightVector | BLOBVector,
    Field(discriminator="kind"),
]


# --------------------------------------------------------------------------- #
# Non-property messages                                                        #
# --------------------------------------------------------------------------- #
class GetProperties(_Model):
    """Client -> device/server request to enumerate properties."""

    tag: Literal["getProperties"] = "getProperties"
    version: str = INDI_VERSION
    device: str | None = None
    name: str | None = None


class DelProperty(_Model):
    """Notification that a property (or a whole device) has gone away."""

    tag: Literal["delProperty"] = "delProperty"
    device: str
    name: str | None = None
    timestamp: IndiTimestamp | None = None
    message: str | None = None


class Message(_Model):
    """A free-form log/notification message."""

    tag: Literal["message"] = "message"
    device: str | None = None
    timestamp: IndiTimestamp | None = None
    message: str = ""


class EnableBLOB(_Model):
    """Client -> server request controlling BLOB delivery.

    ``indiserver`` withholds BLOBs from a client until it sends this; the policy
    applies to one device (and optionally one property when ``name`` is set).
    """

    tag: Literal["enableBLOB"] = "enableBLOB"
    device: str
    name: str | None = None
    policy: BLOBPolicy = BLOBPolicy.ALSO


# --------------------------------------------------------------------------- #
# Wire events: def / set / new intent wrappers around a vector                 #
# --------------------------------------------------------------------------- #
class DefVector(_Model):
    """A property definition (device -> client)."""

    tag: Literal["def"] = "def"
    vector: Vector


class SetVector(_Model):
    """A value update to an already-defined property (device -> client).

    Attributes
    ----------
    state_present : bool
        Whether the wire message actually carried a ``state``. It is
        ``#IMPLIED`` on every ``set*Vector`` (white paper p.7) and means "no
        change if absent", where on a ``def*Vector`` it is ``#REQUIRED``. The
        absence has to survive the parse or it cannot be honoured later, and it
        rides here rather than on the vector because a vector's ``state`` is
        never absent in memory - a cached property is always in some state, and
        making the field nullable would push a `None` into every consumer of a
        cached vector to no purpose.
    """

    tag: Literal["set"] = "set"
    vector: Vector
    state_present: bool = True


class NewVector(_Model):
    """A client's request to change a property's value (client -> device)."""

    tag: Literal["new"] = "new"
    vector: Vector


IndiMessage = DefVector | SetVector | NewVector | GetProperties | DelProperty | Message | EnableBLOB
