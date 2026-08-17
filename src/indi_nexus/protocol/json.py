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

Everything :func:`to_json` writes, :func:`from_json` reads back. JSON has no
literal for NaN or the infinities, so a non-finite ``Number.value`` would be
serialised as ``null`` and then rejected on the way back in - the payload would
be unreadable by its own codec. The models refuse a non-finite ``value``
instead (see :class:`~indi_nexus.protocol.models.Number`), which puts the
failure at the point the value enters rather than on the far side of a network
hop, and the XML parser drops such an element for the same reason.
"""

from __future__ import annotations

from pydantic import TypeAdapter

from indi_nexus.protocol.models import IndiMessage

_ADAPTER: TypeAdapter[IndiMessage] = TypeAdapter(IndiMessage)


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
    """
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
    """
    return _ADAPTER.validate_json(data)
