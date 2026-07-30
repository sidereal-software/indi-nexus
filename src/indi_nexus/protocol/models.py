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
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from indi_nexus.protocol.enums import IPerm, IPState, ISRule, ISState

INDI_VERSION = "1.7"


class _Model(BaseModel):
    """Shared config: ignore unknown wire attributes, allow enum values."""

    model_config = ConfigDict(extra="ignore", use_enum_values=False)


# --------------------------------------------------------------------------- #
# Elements                                                                    #
# --------------------------------------------------------------------------- #
class _Element(_Model):
    """Fields shared by every property element; not used on its own."""

    name: str
    label: str | None = None


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
    timestamp: dt.datetime | None = None
    message: str | None = None

    def element(self, name: str) -> Element:
        """Return the child element with a given name.

        Parameters
        ----------
        name:
            The element name to look up.

        Returns
        -------
        Element
            The matching element.

        Raises
        ------
        KeyError
            If no element with that name exists in this vector.
        """
        for el in self.elements:  # type: ignore[attr-defined]
            if el.name == name:
                return cast("Element", el)
        raise KeyError(f"{name!r} not in {self.device}.{self.name}")

    def __getitem__(self, name: str) -> Element:
        """Return element ``name`` (see :meth:`element`)."""
        return self.element(name)


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
    timestamp: dt.datetime | None = None
    message: str | None = None


class Message(_Model):
    """A free-form log/notification message."""

    tag: Literal["message"] = "message"
    device: str | None = None
    timestamp: dt.datetime | None = None
    message: str = ""


# --------------------------------------------------------------------------- #
# Wire events: def / set / new intent wrappers around a vector                 #
# --------------------------------------------------------------------------- #
class DefVector(_Model):
    """A property definition (device -> client)."""

    tag: Literal["def"] = "def"
    vector: Vector


class SetVector(_Model):
    """A value update to an already-defined property (device -> client)."""

    tag: Literal["set"] = "set"
    vector: Vector


class NewVector(_Model):
    """A client's request to change a property's value (client -> device)."""

    tag: Literal["new"] = "new"
    vector: Vector


IndiMessage = DefVector | SetVector | NewVector | GetProperties | DelProperty | Message
