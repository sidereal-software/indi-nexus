"""INDI 1.7 XML codec: models <-> canonical INDI XML.

Two directions:

* :func:`to_xml` serializes a model (``DefVector``/``SetVector``/``NewVector`` or
  a bare message) to the exact ``def*``/``set*``/``new*`` XML that ``indiserver``
  and C++ INDI clients expect.
* :class:`XMLStreamParser` consumes the raw byte stream from a socket or stdio
  pipe and yields fully-formed :data:`~indi_nexus.protocol.models.IndiMessage`
  objects as complete top-level elements arrive. This replaces pyINDI's
  "accumulate input and retry ``etree.fromstring`` until it parses" loop and its
  separate SAX handler for BLOBs.

Number values honour the INDI printf-style ``format``, including the ``%m``
sexagesimal form used for RA/Dec, so values round-trip faithfully with libindi.
"""

from __future__ import annotations

import base64
import datetime as dt
import re
from collections.abc import Iterator
from typing import cast

from lxml import etree

from indi_nexus.protocol.enums import IPerm, IPState, ISRule, ISState
from indi_nexus.protocol.models import (
    BLOB,
    BLOBVector,
    DefVector,
    DelProperty,
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
)

_TS_FORMAT = "%Y-%m-%dT%H:%M:%S"

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
# Sexagesimal helpers (mirrors libindi f_scansexa / fs_sexa)                   #
# --------------------------------------------------------------------------- #
def parse_number(text: str) -> float:
    """Parse a number that may be decimal or sexagesimal.

    Accepts plain decimals as well as ``dd:mm:ss`` (or space-separated)
    sexagesimal forms used for RA/Dec, mirroring libindi's ``f_scansexa``.

    Parameters
    ----------
    text:
        The raw element text.

    Returns
    -------
    float
        The parsed value; ``0.0`` for empty input.
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

    Parameters
    ----------
    value:
        The number to format.
    fmt:
        The INDI ``format`` string from the element definition.

    Returns
    -------
    str
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
    n = round(abs(value) * fracbase)
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
    el:
        The element to modify.
    key:
        The attribute name.
    value:
        The attribute value; ``None`` is skipped and datetimes use the INDI
        timestamp format.
    """
    if value is None:
        return
    if isinstance(value, dt.datetime):
        value = value.strftime(_TS_FORMAT)
    el.set(key, str(value))


def _element_xml(el: object, mode: str) -> etree._Element:
    """Build a ``def*`` (full) or ``one*`` (name+value) element node.

    Parameters
    ----------
    el:
        The element model to serialise.
    mode:
        ``"def"`` for a full definition, otherwise a value-only ``one*`` node.

    Returns
    -------
    lxml.etree._Element
        The serialised element node.

    Raises
    ------
    TypeError
        If ``el`` is not a known element type.
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
    vector:
        The vector model to serialise.
    mode:
        ``"def"``, ``"set"``, or ``"new"`` - controls which attributes appear.

    Returns
    -------
    lxml.etree._Element
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
    msg:
        The message model to serialise.

    Returns
    -------
    lxml.etree._Element
        The serialised node.

    Raises
    ------
    TypeError
        If ``msg`` is not a serialisable message type.
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
    raise TypeError(f"Cannot serialize {type(msg)!r}")


def to_xml(msg: IndiMessage, *, pretty: bool = False) -> bytes:
    """Serialise an INDI message model to canonical INDI XML bytes.

    Parameters
    ----------
    msg:
        The message model to serialise.
    pretty:
        Whether to pretty-print the output.

    Returns
    -------
    bytes
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
    node:
        The element XML node.
    kind:
        The element kind (``"number"``, ``"text"``, ``"switch"``, ``"light"``,
        ``"blob"``).

    Returns
    -------
    object
        The parsed element model.

    Raises
    ------
    ValueError
        If ``kind`` is not a known element kind.
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
    """Parse an optional float attribute (``None`` stays ``None``)."""
    return None if v is None else float(v)


def _optint(v: str | None) -> int | None:
    """Parse an optional int attribute (``None`` stays ``None``)."""
    return None if v is None else int(v)


def _optts(v: str | None) -> dt.datetime | None:
    """Parse an optional ISO timestamp; return ``None`` if absent or invalid."""
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
    node:
        The vector XML node.
    stem:
        The tag stem (``"Number"``, ``"Text"``, ``"Switch"``, ``"Light"``,
        ``"BLOB"``).

    Returns
    -------
    Vector
        The parsed vector model.
    """
    kind = _STEM_BY_TAGWORD[stem]
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
    node:
        A top-level INDI element node.

    Returns
    -------
    IndiMessage or None
        The parsed message, or ``None`` for comments/PIs or unrecognised tags.
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

    m = re.fullmatch(r"(def|set|new)(Number|Text|Switch|Light|BLOB)Vector", tag)
    if m:
        mode, stem = m.group(1), m.group(2)
        vector = _vector_from_xml(node, stem)
        if mode == "def":
            return DefVector(vector=vector)
        if mode == "set":
            return SetVector(vector=vector)
        return NewVector(vector=vector)

    return None


def parse_indi(data: bytes | str) -> list[IndiMessage]:
    """Parse a complete chunk of INDI XML into message models.

    Convenience wrapper over :class:`XMLStreamParser` for a self-contained chunk
    that holds one or more complete top-level elements.

    Parameters
    ----------
    data:
        The XML bytes or string to parse.

    Returns
    -------
    list of IndiMessage
        Every message found in the chunk, in order.
    """
    parser = XMLStreamParser()
    return list(parser.feed(data))


class XMLStreamParser:
    """Incremental parser for the unbounded INDI element stream.

    The INDI wire is a sequence of sibling top-level elements with no enclosing
    document root, so we feed a synthetic root and emit each depth-1 element as
    it completes, clearing consumed nodes to keep memory flat.
    """

    def __init__(self) -> None:
        """Start the pull parser and open a synthetic enclosing root element."""
        self._parser = etree.XMLPullParser(events=("end",), recover=True, huge_tree=True)
        self._parser.feed(b"<indinexus>")

    def feed(self, data: bytes | str) -> Iterator[IndiMessage]:
        """Feed the next chunk of bytes and yield any completed messages.

        Parameters
        ----------
        data:
            The next bytes or string from the stream.

        Yields
        ------
        IndiMessage
            Each top-level message that completed within this chunk.
        """
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._parser.feed(data)
        for _event, item in self._parser.read_events():
            # We only subscribed to "end" events, so the payload is always an
            # element; the lxml stubs can't narrow that, hence the cast.
            element = cast("etree._Element", item)
            parent = element.getparent()
            # depth-1: a complete top-level INDI message (parent is our root)
            if parent is None or parent.getparent() is not None:
                continue
            msg = message_from_xml(element)
            if msg is not None:
                yield msg
            # Free memory: drop this element and earlier siblings.
            element.clear()
            prev = element.getprevious()
            while prev is not None:
                parent.remove(prev)
                prev = element.getprevious()
