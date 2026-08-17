"""The bridge's **control** frames: the non-INDI half of the browser contract.

Everything the bridge sends a browser is either an INDI message
(``{"tag": ...}``, from :mod:`indi_nexus.protocol.models`) or one of the frames
here (``{"event": ...}``), which exist for the things INDI 1.7 has no message
for: the version of the browser contract itself, the upstream connection state,
and the rejection of a frame the browser sent.

They are models rather than hand-built dictionaries for the same reason the INDI
messages are: ``web/packages/client/src/types.ts`` is a hand-authored mirror of
the Python models, and a frame assembled with ``json.dumps`` at three call sites
has no schema for that mirror to be checked against. :data:`BridgeFrame` is
discriminated on ``event`` exactly as ``IndiMessage`` is on ``tag``, so the
union is closed and ``tests/test_wire_contract.py`` can snapshot its schema.

**Versioning.** :data:`BRIDGE_PROTOCOL_VERSION` versions *this* contract - the
JSON a browser sees - and has nothing to do with INDI's own ``version``
attribute on ``getProperties``, which is frozen at 1.7. It is announced once per
socket in the :class:`HelloFrame`, ahead of every other frame, so a browser
learns what it is talking to before it has to interpret anything. A mismatch is
never fatal in either direction: INDI has always been additive-tolerant, the
client drops an ``event`` it does not know, and turning a cosmetic version skew
into a dark panel mid-session helps nobody.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

#: The browser JSON contract's own version. Bump it **only** on a breaking
#: change: a field removed, renamed, or given a new meaning. Adding an optional
#: field does not bump it, because an older client ignoring an unknown key is
#: already behaving correctly.
BRIDGE_PROTOCOL_VERSION = 1


class _Frame(BaseModel):
    """Base for every bridge control frame.

    Extras are ignored rather than forbidden, matching
    :class:`indi_nexus.protocol.models._Model`: a browser built against a newer
    bridge may hand one of these back (the debug page echoes frames), and a
    field this version does not know is not a reason to fail.
    """

    model_config = ConfigDict(extra="ignore")


class HelloFrame(_Frame):
    """The first frame on every ``/ws`` socket: what the browser is talking to.

    Attributes
    ----------
    event : str
        Always ``"hello"``.
    protocol : int
        The browser contract's version; see :data:`BRIDGE_PROTOCOL_VERSION`.
    server : str
        The INDINexus version serving this socket, for a UI to display and for a
        bug report to quote. It has **no model default on purpose**: a default
        lands in ``model_json_schema()``, so pinning ``indi_nexus.__version__``
        here would break the golden wire schema on every release. The bridge
        supplies it at construction instead.
    """

    event: Literal["hello"] = "hello"
    protocol: int = BRIDGE_PROTOCOL_VERSION
    server: str


class ConnectionFrame(_Frame):
    """The upstream ``indiserver`` link went up or down.

    Attributes
    ----------
    event : str
        Always ``"connection"``.
    connected : bool
        Whether the bridge currently has a live upstream connection.
    """

    event: Literal["connection"] = "connection"
    connected: bool


class ErrorFrame(_Frame):
    """A frame this browser sent did not go upstream.

    Sent to that browser alone, never for something the bridge accepted, and the
    socket stays open. Silence would be worse: a refused write is not retried
    anywhere, so a browser that hears nothing has no reason not to believe it
    landed.

    Attributes
    ----------
    event : str
        Always ``"error"``.
    code : str
        A stable machine-readable reason, e.g. ``"not_connected"``.
    message : str
        Human-readable detail, suitable for a UI log.
    tag : str or None
        The rejected message's INDI tag, or `None` if it never parsed.
    """

    event: Literal["error"] = "error"
    code: str
    message: str
    tag: str | None = None


#: A bridge control frame, discriminated on ``event``. Closed for the same
#: reason :data:`~indi_nexus.protocol.models.IndiMessage` is: an ``event`` this
#: version does not know is refused rather than coerced into the nearest member.
BridgeFrame = Annotated[HelloFrame | ConnectionFrame | ErrorFrame, Field(discriminator="event")]


def dump_frame(frame: BridgeFrame) -> str:
    """Serialise one control frame to the JSON text a browser receives.

    Parameters
    ----------
    frame : BridgeFrame
        The frame to serialise.

    Returns
    -------
    text : str
        The frame as compact JSON, matching what
        :func:`indi_nexus.protocol.to_json` produces for an INDI message.
    """
    return frame.model_dump_json()
