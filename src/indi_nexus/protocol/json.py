"""INDI JSON codec: models <-> typed JSON for browser clients.

The INDI wire toward ``indiserver`` is XML (see :mod:`indi_nexus.protocol.xml`);
toward browsers it is JSON. Both directions serialise the *same* Pydantic models,
so the JSON contract is just the models dumped to JSON - one source of truth. The
frontend's TypeScript types are **not** generated from it: INDI 1.7 is frozen, so
``web/packages/client/src/types.ts`` is a hand-authored mirror of these models and
has to be updated in step with them.

:func:`to_json` and :func:`from_json` mirror ``to_xml`` / ``parse_indi`` over a
single :class:`pydantic.TypeAdapter` for
:data:`~indi_nexus.protocol.models.IndiMessage`. That union is **discriminated on
``tag``**, the way the element and vector unions are discriminated on ``kind``,
which is what makes it closed: a payload whose ``tag`` is missing or unknown is
refused outright rather than matched against every member in turn. Left
undiscriminated it was not closed at all - :class:`GetProperties` defaults every
field and the base model ignores extras, so ``{}`` and any other unrecognised
object validated as a ``getProperties``. BLOB payloads travel as base64
(configured on the base model).

The only thing either function does beyond (de)serialising is the ``.z`` rule
(see :mod:`indi_nexus.protocol.compression`), and it is applied here for the same
reason the XML codec applies it: these two read and write the *same* models, so a
payload one of them inflates and the other does not, or a frame one will emit and
the other refuses, is drift between two descriptions of one contract. On the way
in a zlib-compressed BLOB payload is inflated and its ``format`` loses the
suffix, so the browser at the end of this contract - which has no zlib of its own
- never meets one. On the way out a ``.z`` format with no explicit ``size`` is
refused, exactly as ``to_xml`` refuses it.

Everything :func:`to_json` writes, :func:`from_json` reads back. JSON has no
literal for NaN or the infinities, so a non-finite ``Number.value`` would be
serialised as ``null`` and then rejected on the way back in - the payload would
be unreadable by its own codec. The models refuse a non-finite ``value``
instead (see :class:`~indi_nexus.protocol.models.Number`), which puts the
failure at the point the value enters rather than on the far side of a network
hop, and the XML parser drops such an element for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator

from pydantic import TypeAdapter

from indi_nexus.protocol.compression import inflate_blob, require_declared_size
from indi_nexus.protocol.models import (
    BLOB,
    BLOBVector,
    DefVector,
    IndiMessage,
    NewVector,
    SetVector,
)

_ADAPTER: TypeAdapter[IndiMessage] = TypeAdapter(IndiMessage)


def _blobs(msg: IndiMessage) -> Iterator[BLOB]:
    """Yield the BLOB elements a message carries, if any.

    One walk for both directions, so the two rules that apply to a payload here
    - inflate on the way in, refuse an undescribed compressed one on the way out
    - cannot end up disagreeing about which elements they reach.

    Parameters
    ----------
    msg : IndiMessage
        Any INDI message.

    Yields
    ------
    element : BLOB
        Each BLOB element, or nothing at all for a message carrying none.
    """
    if isinstance(msg, (DefVector, SetVector, NewVector)) and isinstance(msg.vector, BLOBVector):
        yield from msg.vector.elements


def to_json(msg: IndiMessage) -> str:
    """Serialise an INDI message model to a JSON string.

    Parameters
    ----------
    msg : IndiMessage
        The message model to serialise.

    Returns
    -------
    text : str
        The message as JSON (a ``bytes`` BLOB payload is base64-encoded), always
        readable by :func:`from_json`.

    Raises
    ------
    ProtocolError
        Raised (also a `ValueError`) if a BLOB declares a ``.z`` format without
        the uncompressed ``size`` that attribute is defined as - the same
        refusal, from the same rule, that :func:`~indi_nexus.protocol.xml.to_xml`
        makes. Two codecs over one set of models must not disagree about which
        frames are emittable.
    """
    for el in _blobs(msg):
        require_declared_size(el)
    return _ADAPTER.dump_json(msg).decode("utf-8")


def from_json(data: str | bytes) -> IndiMessage:
    """Parse a JSON string into the matching INDI message model.

    Parameters
    ----------
    data : str or bytes
        A single JSON object with a ``tag`` field identifying the message.

    Returns
    -------
    message : IndiMessage
        The parsed, fully typed message model.

    Raises
    ------
    pydantic.ValidationError
        Raised (as a `ValueError`) if the payload is not a message this codec
        can represent. Nothing :func:`to_json` produces reaches this.
    ProtocolError
        Raised (also a `ValueError`) if a BLOB declares a ``.z`` format and its
        payload will not inflate.
    """
    msg = _ADAPTER.validate_json(data)
    # The `.z` rule is the protocol's, not XML's, so both codecs apply it on the
    # way in and neither codec's consumer ever meets a deflated payload. See
    # indi_nexus.protocol.compression.
    for el in _blobs(msg):
        inflate_blob(el)
    return msg
