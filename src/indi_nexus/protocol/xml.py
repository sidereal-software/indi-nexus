"""INDI 1.7 XML codec: models <-> canonical INDI XML.

Two directions:

* :func:`to_xml` serializes a model (``DefVector``/``SetVector``/``NewVector`` or
  a bare message) to the exact ``def*``/``set*``/``new*`` XML that ``indiserver``
  and C++ INDI clients expect.
* :class:`XMLStreamParser` consumes the raw byte stream from a socket or stdio
  pipe and yields fully-formed :data:`~indi_nexus.protocol.models.IndiMessage`
  objects as complete top-level elements arrive, reassembling messages across
  arbitrary chunk boundaries (BLOB payloads included).

Parsing is lenient by policy. The peer at the other end is somebody else's C
driver, and one element it malformed must not take down a session that is
otherwise working: an unparseable optional attribute degrades to absent, an
element whose value cannot be parsed at all is dropped and counted, and an
unmatched close tag that would end the document reopens it. What leniency never
does is invent a value - see :func:`~indi_nexus.protocol.numbers.parse_number`
for a leaf and :func:`_required` for the ``device``/``name`` a message is
nothing without.

Number values honour the INDI printf-style ``format``, including the ``%m``
sexagesimal form used for RA/Dec, so values round-trip faithfully with libindi.
That rendering is not an XML concern and lives in
:mod:`indi_nexus.protocol.numbers`; this module only calls it.
"""

from __future__ import annotations

import base64
import datetime as dt
import logging
import math
import re
from collections.abc import Iterator
from typing import cast

from lxml import etree

from indi_nexus.exceptions import ProtocolError
from indi_nexus.protocol.compression import inflate_blob, require_declared_size
from indi_nexus.protocol.enums import BLOBPolicy, IPerm, IPState, ISRule, ISState
from indi_nexus.protocol.models import (
    BLOB,
    BLOBVector,
    DefVector,
    DelProperty,
    EnableBLOB,
    GetProperties,
    IndiMessage,
    Light,
    LightVector,
    Message,
    NewVector,
    Number,
    NumberVector,
    SetVector,
    Switch,
    SwitchVector,
    Text,
    TextVector,
    Vector,
    as_utc,
)
from indi_nexus.protocol.numbers import format_number, parse_number

logger = logging.getLogger(__name__)

_TS_FORMAT = "%Y-%m-%dT%H:%M:%S"

#: Every run of whitespace, stripped out of a base64 payload before it is
#: validated (see :func:`_decode_blob`).
_WHITESPACE = re.compile(r"\s+")

#: How many bytes a peer may send without the parser completing a single
#: top-level element before :attr:`XMLStreamParser.stalled` calls the stream
#: lost. This is the backstop for a parser that has gone permanently mute -
#: lxml can be left in a state that emits no event at all (a root close landing
#: mid-start-tag does it), and the parser itself cannot see that, but a reader
#: holding "bytes went in" and "nothing came out" can.
#:
#: It has to clear the largest *legitimate* quiet stretch, which is one BLOB
#: element: a whole astronomical frame arrives over many reads with no event in
#: between. 256 MiB of base64 is a ~192 MB raw frame, comfortably above the
#: largest sensor in routine INDI use (a 61 MP 16-bit frame is 122 MB raw,
#: ~163 MB encoded). Erring high is deliberate: tripping early on a real image
#: would put a camera into a reconnect loop it never escapes, while tripping
#: late only costs the bytes discarded before recovery.
STALL_THRESHOLD_BYTES = 256 * 1024 * 1024

# vector-kind -> (VectorClass, ElementClass, XML tag stem)
_VECTOR_BY_KIND = {
    "number": (NumberVector, Number, "Number"),
    "text": (TextVector, Text, "Text"),
    "switch": (SwitchVector, Switch, "Switch"),
    "light": (LightVector, Light, "Light"),
    "blob": (BLOBVector, BLOB, "BLOB"),
}
_STEM_BY_TAGWORD = {
    "Number": "number",
    "Text": "text",
    "Switch": "switch",
    "Light": "light",
    "BLOB": "blob",
}


# --------------------------------------------------------------------------- #
# Serialization                                                                #
# --------------------------------------------------------------------------- #
def _set(el: etree._Element, key: str, value: object) -> None:
    """Set an XML attribute, skipping ``None`` and formatting datetimes.

    Parameters
    ----------
    el : lxml.etree._Element
        The element to modify.
    key : str
        The attribute name.
    value : object
        The attribute value; ``None`` is skipped and datetimes use the INDI
        timestamp format.
    """
    if value is None:
        return
    if isinstance(value, dt.datetime):
        # Normalise before formatting: the wire form carries no offset, so a
        # datetime in any other zone would be written as if its wall clock were
        # UTC. Bare is what libindi emits (indicom.c indi_timestamp() is gmtime
        # plus "%Y-%m-%dT%H:%M:%S"), so the output stays byte-identical to it.
        value = as_utc(value).strftime(_TS_FORMAT)
    el.set(key, str(value))


def _element_xml(el: object, mode: str) -> etree._Element:
    """Build a ``def*`` (full) or ``one*`` (name+value) element node.

    Parameters
    ----------
    el : object
        The element model to serialise.
    mode : str
        ``"def"`` for a full definition, otherwise a value-only ``one*`` node.

    Returns
    -------
    node : lxml.etree._Element
        The serialised element node.

    Raises
    ------
    TypeError
        Raised if ``el`` is not a known element type.
    ProtocolError
        Raised if a BLOB declares a ``.z`` format and no ``size``, where the
        uncompressed length the attribute has to carry is unknowable here. Also
        a ValueError.
    """
    prefix = "def" if mode == "def" else "one"

    if isinstance(el, Number):
        node = etree.Element(prefix + "Number")
        _set(node, "name", el.name)
        if mode == "def":
            _set(node, "label", el.label)
            _set(node, "format", el.format)
            _set(node, "min", el.min)
            _set(node, "max", el.max)
            _set(node, "step", el.step)
        node.text = format_number(el.value, el.format)
        return node

    if isinstance(el, Text):
        node = etree.Element(prefix + "Text")
        _set(node, "name", el.name)
        if mode == "def":
            _set(node, "label", el.label)
        node.text = el.value
        return node

    if isinstance(el, Switch):
        node = etree.Element(prefix + "Switch")
        _set(node, "name", el.name)
        if mode == "def":
            _set(node, "label", el.label)
        node.text = ISState(el.value).value
        return node

    if isinstance(el, Light):
        node = etree.Element(prefix + "Light")
        _set(node, "name", el.name)
        if mode == "def":
            _set(node, "label", el.label)
        node.text = IPState(el.value).value
        return node

    if isinstance(el, BLOB):
        # Before anything is written, and outside the `one*` branch below on
        # purpose: the rule is about the model, not about which shape of node
        # this happens to be building, and the JSON codec applies the same one
        # to the same model. A `def` carrying a payload it cannot describe is
        # refused here too, rather than silently serialising to XML and then
        # failing on the way to a browser.
        require_declared_size(el)
        node = etree.Element(prefix + "BLOB")
        _set(node, "name", el.name)
        if mode == "def":
            _set(node, "label", el.label)
            _set(node, "format", el.format)
        else:
            _set(node, "format", el.format)
            if el.data is not None:
                # len(data) is the right default only for a payload that is
                # neither encoded nor compressed; require_declared_size above
                # has already refused the one case where it would be a lie.
                encoded = base64.b64encode(el.data)
                _set(node, "size", el.size if el.size is not None else len(el.data))
                # `enclen` is libindi's count of base64 *characters* and must
                # exclude newlines (indiuserio.c writes what to64frombits_s
                # returns, for a single unwrapped line). We emit one line, so
                # this holds trivially. Anyone adding line wrapping has to wrap
                # at a multiple of 4 and keep the newlines out of this count:
                # libindi's from64tobits_fast skips at most one newline per
                # 4-character group, so a wrap anywhere else desynchronises its
                # decoder mid-frame.
                _set(node, "enclen", len(encoded))
                node.text = encoded.decode("ascii")
        return node

    raise TypeError(f"Unknown element type {type(el)!r}")


def _vector_xml(vector: Vector, mode: str) -> etree._Element:
    """Build a ``def*``/``set*``/``new*`` vector node with its children.

    Parameters
    ----------
    vector : Vector
        The vector model to serialise.
    mode : str
        ``"def"``, ``"set"``, or ``"new"`` - controls which attributes appear.

    Returns
    -------
    node : lxml.etree._Element
        The serialised vector node.
    """
    _, _, stem = _VECTOR_BY_KIND[vector.kind]
    node = etree.Element(f"{mode}{stem}Vector")
    _set(node, "device", vector.device)
    _set(node, "name", vector.name)

    if mode == "def":
        _set(node, "label", vector.label)
        _set(node, "group", vector.group)
        _set(node, "state", IPState(vector.state).value)
        if not isinstance(vector, LightVector):
            _set(node, "perm", IPerm(vector.perm).value)
        if isinstance(vector, SwitchVector):
            _set(node, "rule", ISRule(vector.rule).value)
        _set(node, "timeout", vector.timeout)
        _set(node, "timestamp", vector.timestamp)
    elif mode == "set":
        _set(node, "state", IPState(vector.state).value)
        _set(node, "timeout", vector.timeout)
        _set(node, "timestamp", vector.timestamp)
    else:  # new: client request carries the minimum
        _set(node, "timestamp", vector.timestamp)

    _set(node, "message", vector.message)
    for el in vector.elements:
        node.append(_element_xml(el, mode))
    return node


def _message_xml(msg: IndiMessage) -> etree._Element:
    """Build the XML node for any top-level INDI message.

    Parameters
    ----------
    msg : IndiMessage
        The message model to serialise.

    Returns
    -------
    node : lxml.etree._Element
        The serialised node.

    Raises
    ------
    TypeError
        Raised if ``msg`` is not a serialisable message type.
    """
    if isinstance(msg, (DefVector, SetVector, NewVector)):
        return _vector_xml(msg.vector, msg.tag)
    if isinstance(msg, GetProperties):
        node = etree.Element("getProperties")
        _set(node, "version", msg.version)
        _set(node, "device", msg.device)
        _set(node, "name", msg.name)
        return node
    if isinstance(msg, DelProperty):
        node = etree.Element("delProperty")
        _set(node, "device", msg.device)
        _set(node, "name", msg.name)
        _set(node, "timestamp", msg.timestamp)
        _set(node, "message", msg.message)
        return node
    if isinstance(msg, Message):
        node = etree.Element("message")
        _set(node, "device", msg.device)
        _set(node, "timestamp", msg.timestamp)
        _set(node, "message", msg.message)
        return node
    if isinstance(msg, EnableBLOB):
        node = etree.Element("enableBLOB")
        _set(node, "device", msg.device)
        _set(node, "name", msg.name)
        node.text = BLOBPolicy(msg.policy).value
        return node
    raise TypeError(f"Cannot serialize {type(msg)!r}")


def to_xml(msg: IndiMessage, *, pretty: bool = False) -> bytes:
    """Serialise an INDI message model to canonical INDI XML bytes.

    Parameters
    ----------
    msg : IndiMessage
        The message model to serialise.
    pretty : bool, optional
        Whether to pretty-print the output.

    Returns
    -------
    xml : bytes
        The encoded XML.

    Raises
    ------
    ProtocolError
        Raised if a BLOB declares a compressed ``format`` without the
        uncompressed ``size`` the wire attribute is defined as. Also a
        ValueError.
    """
    return etree.tostring(_message_xml(msg), pretty_print=pretty)


# --------------------------------------------------------------------------- #
# Deserialization                                                              #
# --------------------------------------------------------------------------- #
def _element_from_xml(node: etree._Element, kind: str) -> object:
    """Build an element model from a ``def*``/``one*`` node.

    Parameters
    ----------
    node : lxml.etree._Element
        The element XML node.
    kind : str
        The element kind (``"number"``, ``"text"``, ``"switch"``, ``"light"``,
        ``"blob"``).

    Returns
    -------
    element : object
        The parsed element model.

    Raises
    ------
    ProtocolError
        Raised if ``kind`` is not a known element kind, or if a BLOB declaring a
        ``.z`` format carries a payload that will not inflate. Also a
        ValueError, so :meth:`XMLStreamParser._convert` drops and counts the
        message rather than delivering compressed bytes as if they were the
        image.
    """
    name = node.get("name") or ""
    label = node.get("label")
    text = (node.text or "").strip()

    if kind == "number":
        return Number(
            name=name,
            label=label,
            format=node.get("format") or "%g",
            min=_optfloat(node.get("min")),
            max=_optfloat(node.get("max")),
            step=_optfloat(node.get("step")),
            value=parse_number(text) if text else 0.0,
        )
    if kind == "text":
        return Text(name=name, label=label, value=text)
    if kind == "switch":
        return Switch(name=name, label=label, value=ISState(text) if text else ISState.OFF)
    if kind == "light":
        return Light(name=name, label=label, value=IPState(text) if text else IPState.IDLE)
    if kind == "blob":
        # Attributes we do not read are ignored, which is load-bearing here: a
        # real indiserver carrying a shared-buffer driver forwards the driver's
        # `len` (the raw pre-encoding byte count) alongside the payload, because
        # SerializedMsgWithoutSharedBuffer strips `attached`/`enclen` when it
        # re-serialises for a plain TCP client and never removes `len`. Neither
        # attribute is in the 1.7 DTD; both are libindi extensions. `enclen` is
        # advisory anyway - the cdata is the payload - so nothing here consults
        # either one, and an unknown attribute never costs the element.
        blob = BLOB(
            name=name,
            label=label,
            format=node.get("format"),
            size=_optint(node.get("size")),
            data=_decode_blob(text) if text else None,
        )
        inflate_blob(blob)
        return blob
    raise ProtocolError(f"Unknown element kind {kind!r}")


def _decode_blob(text: str) -> bytes:
    """Decode a BLOB payload, refusing anything that is not really base64.

    ``base64.b64decode`` without ``validate=True`` *discards* every character
    outside the alphabet, so a corrupted payload decodes to wrong-but-plausible
    bytes - a truncated frame a client cannot tell from a real one - instead of
    taking the drop path this module documents for a value it cannot represent.

    Validating cannot simply be switched on, though: real libindi traffic
    carries a BLOB's base64 broken across lines, and ``validate=True`` counts a
    newline as an illegal character like any other, so flipping the flag alone
    would drop every genuine FITS frame. The whitespace goes first - deliberately
    the whitespace and nothing else - and what is left has to be base64 in full.

    Parameters
    ----------
    text : str
        The raw element text, as it came off the wire.

    Returns
    -------
    data : bytes
        The decoded payload.

    Raises
    ------
    binascii.Error
        Raised (as a `ValueError`, which the stream parser drops on) if the
        payload is not valid base64.
    """
    return base64.b64decode(_WHITESPACE.sub("", text), validate=True)


def _optfloat(v: str | None) -> float | None:
    """Parse an optional float attribute; absent or unparseable is `None`.

    Every field this feeds - ``min``, ``max``, ``step``, ``timeout`` - is
    ``X | None`` on the model, so "absent" is representable and an unparseable
    value can degrade to it. That matters more than it sounds: a C driver
    writes ``min=''`` for a field it never set, and refusing the attribute
    would discard the entire ``defNumberVector``, leaving a client with no
    definition to merge later ``set`` messages onto and therefore permanently
    blind to that property.

    A non-finite value degrades the same way. JSON cannot write one, so keeping
    it would put a ``min`` on the wire toward the browser that comes back as
    `None` anyway; losing it here loses it once, in the direction the model can
    describe.

    Parameters
    ----------
    v : str or None
        The raw attribute value.

    Returns
    -------
    value : float or None
        The parsed float, or `None` when absent, unparseable or non-finite.
    """
    if v is None:
        return None
    try:
        value = float(v)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _optint(v: str | None) -> int | None:
    """Parse an optional int attribute; absent or unparseable is `None`.

    Same reasoning as :func:`_optfloat`: a BLOB's ``size`` is optional on the
    model, and losing it costs less than losing the message carrying it.

    Parameters
    ----------
    v : str or None
        The raw attribute value.

    Returns
    -------
    value : int or None
        The parsed int, or `None` when absent or unparseable.
    """
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _required(node: etree._Element, key: str) -> str:
    """Return a ``#REQUIRED`` attribute, refusing an absent or empty one.

    The other half of "a leaf may degrade to a representable absence, it may
    never invent a value": ``device`` and ``name`` are not optional on the
    model, so ``node.get(key) or ""`` does not degrade anything - it invents an
    identity. A ``defNumberVector`` with no ``device`` used to land in a client's
    cache as a phantom device called ``""``, holding properties no server would
    ever update and no user asked for. Losing the message is the honest answer,
    and the stream parser counts it as dropped.

    Parameters
    ----------
    node : lxml.etree._Element
        The element carrying the attribute.
    key : str
        The attribute name.

    Returns
    -------
    value : str
        The attribute value.

    Raises
    ------
    ProtocolError
        Raised if the attribute is absent or empty. Also a ValueError.
    """
    value = node.get(key)
    if not value:
        raise ProtocolError(f"<{node.tag}> is missing the required {key!r} attribute")
    return value


def _optts(v: str | None) -> dt.datetime | None:
    """Parse an optional ISO timestamp; return `None` if absent or invalid.

    The result is left naive when the wire form was bare. Normalising to UTC is
    the model's job (:data:`~indi_nexus.protocol.models.IndiTimestamp`), and
    every caller here hands its result to a Pydantic constructor, so adding a
    second normalisation point would only give the rule somewhere else to drift.

    Parameters
    ----------
    v : str or None
        The raw timestamp attribute.

    Returns
    -------
    value : datetime or None
        The parsed timestamp, or `None`.
    """
    if not v:
        return None
    try:
        return dt.datetime.fromisoformat(v)
    except ValueError:
        return None


def _vector_from_xml(node: etree._Element, stem: str) -> Vector:
    """Build a vector model from a ``def*``/``set*``/``new*`` vector node.

    Parameters
    ----------
    node : lxml.etree._Element
        The vector XML node.
    stem : str
        The tag stem (``"Number"``, ``"Text"``, ``"Switch"``, ``"Light"``,
        ``"BLOB"``).

    Returns
    -------
    vector : Vector
        The parsed vector model.

    Raises
    ------
    ValueError
        Raised if ``device`` or ``name`` is missing, or if an element's value
        cannot be represented.
    """
    kind = _STEM_BY_TAGWORD[stem]
    # `state` is #REQUIRED on a def* and #IMPLIED on a set*/new*, where absent
    # means "unchanged". A vector is never stateless in memory, so an absent one
    # becomes the Idle default here and the absence itself is recorded on the
    # SetVector wrapper (see message_from_xml) for the cache to honour.
    state = node.get("state")
    perm_attr = node.get("perm")
    common: dict[str, object] = dict(
        device=_required(node, "device"),
        name=_required(node, "name"),
        label=node.get("label"),
        group=node.get("group"),
        state=IPState(state) if state else IPState.IDLE,
        timeout=_optfloat(node.get("timeout")),
        timestamp=_optts(node.get("timestamp")),
        message=node.get("message"),
    )
    perm = IPerm(perm_attr) if perm_attr else IPerm.RW
    children = list(node)

    if kind == "number":
        nums = [_element_from_xml(c, "number") for c in children]
        return NumberVector.model_validate({**common, "perm": perm, "elements": nums})
    if kind == "text":
        txts = [_element_from_xml(c, "text") for c in children]
        return TextVector.model_validate({**common, "perm": perm, "elements": txts})
    if kind == "switch":
        rule_attr = node.get("rule")
        rule = ISRule(rule_attr) if rule_attr else ISRule.ANY_OF_MANY
        sws = [_element_from_xml(c, "switch") for c in children]
        return SwitchVector.model_validate({**common, "perm": perm, "rule": rule, "elements": sws})
    if kind == "light":
        lights = [_element_from_xml(c, "light") for c in children]
        return LightVector.model_validate({**common, "elements": lights})
    blobs = [_element_from_xml(c, "blob") for c in children]
    return BLOBVector.model_validate({**common, "perm": perm, "elements": blobs})


def message_from_xml(node: etree._Element) -> IndiMessage | None:
    """Convert a single top-level INDI element node to a message model.

    Parameters
    ----------
    node : lxml.etree._Element
        A top-level INDI element node.

    Returns
    -------
    message : IndiMessage or None
        The parsed message, or `None` for comments/PIs or unrecognised tags.

    Raises
    ------
    ValueError
        Raised if a value the model cannot represent as absent is malformed -
        a number's text, a BLOB's base64, one of the state/permission/rule
        tokens, or a missing ``#REQUIRED`` ``device``/``name`` (see
        :func:`_required`). The caller (:meth:`XMLStreamParser._convert`) turns
        that into a dropped message.
    """
    tag = node.tag
    if not isinstance(tag, str):  # comments / PIs
        return None

    if tag == "getProperties":
        return GetProperties(
            version=node.get("version") or "1.7",
            device=node.get("device"),
            name=node.get("name"),
        )
    if tag == "delProperty":
        return DelProperty(
            device=_required(node, "device"),
            name=node.get("name"),
            timestamp=_optts(node.get("timestamp")),
            message=node.get("message"),
        )
    if tag == "message":
        return Message(
            device=node.get("device"),
            timestamp=_optts(node.get("timestamp")),
            message=node.get("message") or "",
        )
    if tag == "enableBLOB":
        text = (node.text or "").strip()
        return EnableBLOB(
            device=_required(node, "device"),
            name=node.get("name"),
            policy=BLOBPolicy(text) if text else BLOBPolicy.ALSO,
        )

    m = re.fullmatch(r"(def|set|new)(Number|Text|Switch|Light|BLOB)Vector", tag)
    if m:
        mode, stem = m.group(1), m.group(2)
        vector = _vector_from_xml(node, stem)
        if mode == "def":
            return DefVector(vector=vector)
        if mode == "set":
            return SetVector(vector=vector, state_present=node.get("state") is not None)
        return NewVector(vector=vector)

    return None


def parse_indi(data: bytes | str) -> list[IndiMessage]:
    """Parse a complete chunk of INDI XML into message models.

    Convenience wrapper over :class:`XMLStreamParser` for a self-contained chunk
    that holds one or more complete top-level elements, and it inherits that
    class's leniency: a malformed element is dropped, not raised, so a shorter
    list than expected - not an exception - is how bad input shows up here.

    Parameters
    ----------
    data : bytes or str
        The XML bytes or string to parse.

    Returns
    -------
    messages : list of IndiMessage
        Every message found in the chunk, in order.
    """
    parser = XMLStreamParser()
    return list(parser.feed(data))


class XMLStreamParser:
    """Incremental parser for the unbounded INDI element stream.

    The INDI wire is a sequence of sibling top-level elements with no enclosing
    document root, so we feed a synthetic root and emit each depth-1 element as
    it completes, clearing consumed nodes to keep memory flat.

    Nothing a peer can send makes this raise. A stream parser that throws takes
    the whole session with it - on a driver, the raise escapes the runtime's
    per-message isolation because it happens while *iterating* this generator,
    and on a client it kills the reconnect loop. So malformed input is absorbed
    and counted instead, and the counters are how a caller finds out.

    Attributes
    ----------
    dropped : int
        Top-level elements discarded because a value would not parse and the
        model had no way to say "absent". An interop signal: it means somebody's
        codec is emitting something this one will not read.
    resets : int
        Times the synthetic document had to be reopened - by :meth:`_reset` when
        a peer's unmatched close tag ended it, and by :meth:`resync` when a
        reader inferred the same failure from the silence that followed one.
        Both are the same framing violation, so they share a counter. An
        operational signal, and explicitly *not* a loss count: one reset
        typically loses the one message the close tag was embedded in, and 50
        consecutive resets can lose nothing at all.
    bytes_since_last_message : int
        Bytes fed since a top-level element last completed. Compared against
        :data:`STALL_THRESHOLD_BYTES` by :attr:`stalled`. Only a completed
        element and :meth:`resync` clear it; reopening the document does not,
        because recovering framing is not the same as producing a message.

    Both counters describe *the peer on this stream*, not the lifetime of one
    lxml object: :meth:`resync` rebuilds the parser underneath them and leaves
    them running, so a reader that rebuilds behind the caller's back does not
    quietly zero the history it is about to want.
    """

    def __init__(self) -> None:
        """Start the pull parser and open a synthetic enclosing root element."""
        self.dropped = 0
        self.resets = 0
        self.bytes_since_last_message = 0
        self._open()

    def _open(self) -> None:
        """Build a fresh pull parser and feed the synthetic root's start tag.

        ``recover=True`` is what buys tolerance for the undefined entities, NUL
        bytes, invalid UTF-8 and unclosed tags real hubs put on the wire; the
        price is that lxml never reports the unmatched close tag :meth:`feed`
        has to notice for itself.
        """
        self._parser = etree.XMLPullParser(events=("end",), recover=True, huge_tree=True)
        self._parser.feed(b"<indinexus>")

    @property
    def stalled(self) -> bool:
        """Whether bytes keep arriving but no message has come out for far too long.

        The one failure this class cannot see from the inside: lxml can be left
        in a state that emits no event at all - a root close arriving while a
        start tag is half-parsed does it, with nothing in ``error_log`` - and
        from then on every message is swallowed in silence. A reader loop holds
        both halves of the evidence, so it asks this and then either calls
        :meth:`resync` (a driver, which has only the one stdin) or drops the
        connection (a client, which can just reconnect).

        It also catches the stream that never produces anything in the first
        place - nothing but unmatched close tags, say - because reopening the
        document is not progress and leaves this counter running.
        """
        return self.bytes_since_last_message > STALL_THRESHOLD_BYTES

    def resync(self) -> None:
        """Rebuild the parser after a reader has judged the stream :attr:`stalled`.

        The remedy for a parser that has gone mute: the lxml object is thrown
        away and a fresh document opened, so the stream picks up again at the
        next well-formed element. :attr:`dropped` and :attr:`resets` survive,
        because they describe the peer on the other end and not the object being
        replaced - and a peer's malformed-input history is never more
        interesting than at the moment its stream stops saying anything.

        The stall budget does start again here, unlike after :meth:`_reset`: the
        reader has just applied the remedy, and leaving the counter above the
        threshold would report a stall on every later chunk. The reason for the
        rebuild belongs to the caller, which has the device name or the peer
        address to log it against, so this method stays quiet.
        """
        self.resets += 1
        self.bytes_since_last_message = 0
        self._open()

    def feed(self, data: bytes | str) -> Iterator[IndiMessage]:
        """Feed the next chunk of bytes and yield any completed messages.

        Parameters
        ----------
        data : bytes or str
            The next bytes or string from the stream.

        Yields
        ------
        message : IndiMessage
            Each top-level message that completed within this chunk.
        """
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.bytes_since_last_message += len(data)
        self._parser.feed(data)
        for _event, item in self._parser.read_events():
            # We only subscribed to "end" events, so the payload is always an
            # element; the lxml stubs can't narrow that, hence the cast.
            element = cast("etree._Element", item)
            parent = element.getparent()
            if parent is None:
                # Depth 0: our synthetic root just ended, which only happens
                # when the peer sent a close tag with nothing open - its own
                # "</indi>", a stray "</bogus>", even one split across two
                # chunks. lxml ends the document there and would silently
                # swallow every later element, so reopen and carry on.
                self._reset()
                # Stop draining: the depth-0 end always sorts last in the queue,
                # so nothing valid is stranded behind this break, and the events
                # after it belong to a document that no longer exists. Do not
                # "fix" this to continue.
                break
            if parent.getparent() is not None:
                continue  # deeper than depth 1: still part of a message
            msg = self._convert(element)
            # A completed top-level element means the framing still works,
            # whatever the element turned out to contain.
            self.bytes_since_last_message = 0
            if msg is not None:
                yield msg
            # Free memory: drop this element and earlier siblings.
            element.clear()
            prev = element.getprevious()
            while prev is not None:
                parent.remove(prev)
                prev = element.getprevious()

    def _convert(self, element: etree._Element) -> IndiMessage | None:
        """Convert one completed top-level element, dropping a malformed one.

        The backstop for the leaves where absence is not representable: a
        number's own text, and the ``ISState``/``IPState``/``IPerm``/``ISRule``/
        ``BLOBPolicy`` tokens. Everything optional has already degraded to
        `None` further in, so reaching here means the element cannot be
        represented at all and the honest answer is to lose it.

        Parameters
        ----------
        element : lxml.etree._Element
            The completed top-level element.

        Returns
        -------
        message : IndiMessage or None
            The parsed message, or `None` when the element was unrecognised or
            had to be dropped.
        """
        # ValueError alone, and it covers more than it looks: binascii.Error
        # (bad base64) and pydantic's ValidationError both subclass it. Not
        # TypeError - that would mean this codec is broken rather than the peer,
        # and swallowing it would hide our own data loss. Note that
        # etree.XMLSyntaxError subclasses SyntaxError, *not* ValueError, so it
        # would pass straight through here; recover=True has never been seen to
        # raise it, and this comment is where that assumption is written down.
        try:
            return message_from_xml(element)
        except ValueError as exc:
            self.dropped += 1
            # Identify the element, never quote it. The exception text embeds
            # the offending value, and that value can be a multi-megabyte BLOB
            # payload, so only the exception's type goes to the log.
            logger.warning(
                "dropped malformed <%s> device=%r name=%r (%s)",
                element.tag,
                element.get("device"),
                element.get("name"),
                type(exc).__name__,
            )
            return None

    def _reset(self) -> None:
        """Reopen the synthetic document after a peer's unmatched close tag.

        Whatever remained of the offending chunk is gone: recovering it would
        mean lexing the byte stream here to find where the token ended, which is
        exactly the framing work this class exists to leave to lxml.

        Reopening is recovery, not progress, so :attr:`bytes_since_last_message`
        keeps running - the stream still has not produced a message. Clearing it
        here (which this used to do, on the grounds that the parser is
        demonstrably alive) let a peer that sends nothing but close tags hold the
        counter at zero for good: :attr:`stalled` could never trip, and a stream
        that was never going to produce a message was never torn down.
        """
        self.resets += 1
        logger.warning("reopened the stream after an unmatched close tag (reset %d)", self.resets)
        self._open()
