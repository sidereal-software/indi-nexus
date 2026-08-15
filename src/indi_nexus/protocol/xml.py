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
does is invent a value - see :func:`parse_number`.

Number values honour the INDI printf-style ``format``, including the ``%m``
sexagesimal form used for RA/Dec, so values round-trip faithfully with libindi.
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

logger = logging.getLogger(__name__)

_TS_FORMAT = "%Y-%m-%dT%H:%M:%S"

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
# Sexagesimal helpers (libindi f_scansexa / fs_sexa)                           #
# --------------------------------------------------------------------------- #
def parse_number(text: str) -> float:
    """Parse a number that may be decimal or sexagesimal.

    Accepts plain decimals as well as ``dd:mm:ss`` (or space-separated)
    sexagesimal forms used for RA/Dec, as libindi's ``f_scansexa`` does.

    Deliberately a superset of libindi on the ``set`` path: libindi reads a
    ``oneNumber`` with ``std::stod`` there and only uses ``f_scansexa`` on the
    ``def`` path, so *it* reads ``"10:30:00"`` in a ``setNumberVector`` as
    ``10.0``. We read sexagesimal in both, which cannot silently truncate a
    coordinate. Do not "fix" this to match: matching would mean reading 10:30
    as 10, which is a data-corruption bug wearing a compatibility badge.

    Strict on purpose, where the rest of this module is lenient: ``value`` is
    not nullable on the model, so there is no way to say "absent". Raising here
    lets the stream parser drop the whole element rather than publish a reading
    a mount would act on.

    Parameters
    ----------
    text : str
        The raw element text.

    Returns
    -------
    value : float
        The parsed value; ``0.0`` for empty input.

    Raises
    ------
    ValueError
        Raised if the text is neither a decimal nor a sexagesimal number.
    """
    s = text.strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        pass
    parts = re.split(r"[:\s]+", s)
    sign = -1.0 if parts[0].lstrip().startswith("-") else 1.0
    nums = [abs(float(p)) for p in parts if p]
    acc = 0.0
    for i, n in enumerate(nums):
        acc += n / (60**i)
    return sign * acc


def format_number(value: float, fmt: str) -> str:
    """Format a number per an INDI printf-style format.

    Handles ordinary printf conversions as well as the ``%m`` sexagesimal form
    (e.g. ``%9.6m``), field-width padded like libindi's ``fs_sexa``.

    Half-way values round *away from zero*, which is what ``fs_sexa`` does
    (``indicom.c:165`` casts ``a * fracbase + 0.5`` to an integer). Python's
    built-in `round` is half-to-*even*, so it disagrees on exactly the values
    that land on a tick boundary: at ``%10.6m`` it renders ``0.03125`` as
    ``0:01:52`` where libindi says ``0:01:53``. One arcsecond, only on exact
    halves, in the format mounts use for RA and Dec.

    One divergence from ``fs_sexa`` is kept on purpose: libindi passes a
    negative width to ``%*s`` when ``w - f < 3`` (``indicom.c:171``), which
    left-justifies instead. No real driver declares such a format, and matching
    the quirk would only preserve it.

    Parameters
    ----------
    value : float
        The number to format.
    fmt : str
        The INDI ``format`` string from the element definition.

    Returns
    -------
    text : str
        The formatted value.
    """
    m = re.fullmatch(r"%(\d+)\.(\d+)m", fmt.strip())
    if not m:
        try:
            return (fmt % value).strip()
        except (TypeError, ValueError):
            return repr(value)

    width, frac = int(m.group(1)), int(m.group(2))
    fracbase = {9: 360000, 8: 36000, 6: 3600, 5: 600}.get(frac, 60)
    neg = value < 0
    n = math.floor(abs(value) * fracbase + 0.5)
    d, f = divmod(n, fracbase)
    dd = f"{'-' if neg else ''}{d}"
    field = max(width - frac, 1)
    dd = dd.rjust(field)
    if fracbase == 60:  # dd:mm
        return f"{dd}:{f:02d}"
    if fracbase == 600:  # dd:mm.m
        return f"{dd}:{f // 10:02d}.{f % 10:1d}"
    if fracbase == 3600:  # dd:mm:ss
        return f"{dd}:{f // 60:02d}:{f % 60:02d}"
    if fracbase == 36000:  # dd:mm:ss.s
        return f"{dd}:{f // 600:02d}:{(f % 600) // 10:02d}.{f % 10:1d}"
    # dd:mm:ss.ss
    return f"{dd}:{f // 6000:02d}:{(f % 6000) // 100:02d}.{f % 100:02d}"


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
        node = etree.Element(prefix + "BLOB")
        _set(node, "name", el.name)
        if mode == "def":
            _set(node, "label", el.label)
            _set(node, "format", el.format)
        else:
            _set(node, "format", el.format)
            if el.data is not None:
                encoded = base64.b64encode(el.data)
                _set(node, "size", el.size if el.size is not None else len(el.data))
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
    ValueError
        Raised if ``kind`` is not a known element kind.
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
        data = base64.b64decode(text) if text else None
        return BLOB(
            name=name,
            label=label,
            format=node.get("format"),
            size=_optint(node.get("size")),
            data=data,
        )
    raise ValueError(f"Unknown element kind {kind!r}")


def _optfloat(v: str | None) -> float | None:
    """Parse an optional float attribute; absent or unparseable is `None`.

    Every field this feeds - ``min``, ``max``, ``step``, ``timeout`` - is
    ``X | None`` on the model, so "absent" is representable and an unparseable
    value can degrade to it. That matters more than it sounds: a C driver
    writes ``min=''`` for a field it never set, and refusing the attribute
    would discard the entire ``defNumberVector``, leaving a client with no
    definition to merge later ``set`` messages onto and therefore permanently
    blind to that property.

    Parameters
    ----------
    v : str or None
        The raw attribute value.

    Returns
    -------
    value : float or None
        The parsed float, or `None` when absent or unparseable.
    """
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


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
    """
    kind = _STEM_BY_TAGWORD[stem]
    # `state` is #REQUIRED on a def* and #IMPLIED on a set*/new*, where absent
    # means "unchanged". A vector is never stateless in memory, so an absent one
    # becomes the Idle default here and the absence itself is recorded on the
    # SetVector wrapper (see message_from_xml) for the cache to honour.
    state = node.get("state")
    perm_attr = node.get("perm")
    common: dict[str, object] = dict(
        device=node.get("device") or "",
        name=node.get("name") or "",
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
        a number's text, or one of the state/permission/rule tokens.
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
            device=node.get("device") or "",
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
            device=node.get("device") or "",
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
