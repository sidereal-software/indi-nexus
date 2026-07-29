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
    """Parse a number that may be decimal or sexagesimal (``dd:mm:ss``)."""
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
    """Format ``value`` per an INDI printf format, including ``%m`` sexagesimal."""
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
    if value is None:
        return
    if isinstance(value, dt.datetime):
        value = value.strftime(_TS_FORMAT)
    el.set(key, str(value))


def _element_xml(el: object, mode: str) -> etree._Element:
    """Build a ``def*`` (full) or ``one*`` (name+value) element node."""
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
    """Serialize an INDI message model to canonical INDI XML bytes."""
    return etree.tostring(_message_xml(msg), pretty_print=pretty)


# --------------------------------------------------------------------------- #
# Deserialization                                                              #
# --------------------------------------------------------------------------- #
def _get(el: etree._Element, key: str) -> str | None:
    return el.get(key)


def _element_from_xml(node: etree._Element, kind: str) -> object:
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
    return None if v is None else float(v)


def _optint(v: str | None) -> int | None:
    return None if v is None else int(v)


def _optts(v: str | None) -> dt.datetime | None:
    if not v:
        return None
    try:
        return dt.datetime.fromisoformat(v)
    except ValueError:
        return None


def _vector_from_xml(node: etree._Element, stem: str) -> Vector:
    kind = _STEM_BY_TAGWORD[stem]
    common: dict[str, object] = dict(
        device=node.get("device") or "",
        name=node.get("name") or "",
        label=node.get("label"),
        group=node.get("group"),
        state=IPState(node.get("state")) if node.get("state") else IPState.IDLE,
        timeout=_optfloat(node.get("timeout")),
        timestamp=_optts(node.get("timestamp")),
        message=node.get("message"),
    )
    perm = IPerm(node.get("perm")) if node.get("perm") else IPerm.RW
    children = list(node)

    if kind == "number":
        nums = [_element_from_xml(c, "number") for c in children]
        return NumberVector.model_validate({**common, "perm": perm, "elements": nums})
    if kind == "text":
        txts = [_element_from_xml(c, "text") for c in children]
        return TextVector.model_validate({**common, "perm": perm, "elements": txts})
    if kind == "switch":
        rule = ISRule(node.get("rule")) if node.get("rule") else ISRule.ANY_OF_MANY
        sws = [_element_from_xml(c, "switch") for c in children]
        return SwitchVector.model_validate(
            {**common, "perm": perm, "rule": rule, "elements": sws}
        )
    if kind == "light":
        lights = [_element_from_xml(c, "light") for c in children]
        return LightVector.model_validate({**common, "elements": lights})
    blobs = [_element_from_xml(c, "blob") for c in children]
    return BLOBVector.model_validate({**common, "perm": perm, "elements": blobs})


def message_from_xml(node: etree._Element) -> IndiMessage | None:
    """Convert a single top-level INDI element node to a message model."""
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
    """Parse a complete chunk of INDI XML (one or more top-level elements)."""
    parser = XMLStreamParser()
    return list(parser.feed(data))


class XMLStreamParser:
    """Incremental parser for the unbounded INDI element stream.

    The INDI wire is a sequence of sibling top-level elements with no enclosing
    document root, so we feed a synthetic root and emit each depth-1 element as
    it completes, clearing consumed nodes to keep memory flat.
    """

    def __init__(self) -> None:
        self._parser = etree.XMLPullParser(events=("end",), recover=True, huge_tree=True)
        self._parser.feed(b"<indinexus>")

    def feed(self, data: bytes | str) -> Iterator[IndiMessage]:
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
