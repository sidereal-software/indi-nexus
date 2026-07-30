"""INDI JSON codec: models <-> typed JSON for browser clients.

The INDI wire toward ``indiserver`` is XML (see :mod:`indi_nexus.protocol.xml`);
toward browsers it is JSON. Both directions serialise the *same* Pydantic models,
so the JSON contract is just the models dumped to JSON - one source of truth, and
the frontend's TypeScript types can be generated from the model JSON schema.

:func:`to_json` and :func:`from_json` mirror ``to_xml`` / ``parse_indi``. The
:data:`~indi_nexus.protocol.models.IndiMessage` union is discriminated by each
member's ``tag`` literal, so a single :class:`pydantic.TypeAdapter` round-trips
any message. BLOB payloads travel as base64 (configured on the base model).
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
        The message as JSON (a ``bytes`` BLOB payload is base64-encoded).
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
    """
    return _ADAPTER.validate_json(data)
