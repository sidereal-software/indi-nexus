"""Tests for the INDI protocol core: enums, models, and the XML codec."""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import time

import pytest
from lxml import etree

from indi_nexus.protocol import (
    BLOB,
    BLOBPolicy,
    BLOBVector,
    DefVector,
    DelProperty,
    EnableBLOB,
    GetProperties,
    IPerm,
    IPState,
    ISRule,
    ISState,
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
    XMLStreamParser,
    as_utc,
    indi_now,
    parse_indi,
    slugify,
    to_json,
    to_xml,
)
from indi_nexus.protocol import xml as xml_module
from indi_nexus.protocol.xml import (
    _element_from_xml,
    _element_xml,
    format_number,
    message_from_xml,
    parse_number,
)


# --------------------------------------------------------------------------- #
# Enums                                                                        #
# --------------------------------------------------------------------------- #
def test_enum_compares_and_serializes_as_wire_token():
    """Enum members equal, construct from, and stringify to their wire token."""
    assert IPState.OK == "Ok"
    assert IPState("Ok") is IPState.OK
    assert ISState.ON.value == "On"
    assert str(IPerm.RW) == "rw"


def test_enum_tolerates_whitespace_from_wire():
    """Enum lookup ignores surrounding whitespace on wire tokens."""
    assert IPState(" Busy ") is IPState.BUSY
    assert ISState("On\n") is ISState.ON


def test_enum_rejects_unknown_tokens():
    """A token that matches no member (even stripped) raises ValueError."""
    with pytest.raises(ValueError):
        IPState("Nope")
    with pytest.raises(ValueError):
        ISState(3)


# --------------------------------------------------------------------------- #
# Sexagesimal formatting / parsing                                            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value,fmt,expected",
    [
        (10.5, "%5.3m", "10:30"),
        (10.5, "%8.5m", " 10:30.0"),
        (10.5, "%8.6m", "10:30:00"),
        (-10.5, "%8.6m", "-10:30:00"),
        (10.5, "%11.8m", " 10:30:00.0"),
        (10.5, "%12.9m", " 10:30:00.00"),
        (12.582777778, "%9.6m", " 12:34:58"),  # width-9 field pads the degrees (libindi-faithful)
        (1.0, "%.2f", "1.00"),
        # Values landing exactly on half a tick, where half-to-even and
        # half-away-from-zero part company. Every expectation below was taken
        # from compiled libindi (fs_sexa, indicom.c:165) - they are the spec
        # here, not a preference, so do not "correct" them to Python's round().
        (0.03125, "%10.6m", "   0:01:53"),
        (-0.03125, "%10.6m", "  -0:01:53"),
        (0.15625, "%9.6m", "  0:09:23"),
        (0.1875, "%8.5m", "  0:11.3"),
        (0.375, "%7.3m", "   0:23"),
    ],
)
def test_format_number(value, fmt, expected):
    """Formatting matches the expected printf / sexagesimal output."""
    assert format_number(value, fmt) == expected


def test_format_number_falls_back_to_repr_for_bad_formats():
    """An unusable format string falls back to the value's repr."""
    assert format_number(1.5, "%q") == "1.5"  # ValueError from printf
    assert format_number(1.5, "no-placeholder") == "1.5"  # TypeError from printf


def test_parse_number_empty_returns_zero():
    """Empty or whitespace-only element text parses to 0.0."""
    assert parse_number("") == 0.0
    assert parse_number("   ") == 0.0


@pytest.mark.parametrize(
    "text,expected",
    [
        ("10:30:00", 10.5),
        ("-10:30:00", -10.5),
        ("12 34 58", pytest.approx(12.582777, abs=1e-4)),
        ("3.14", 3.14),
    ],
)
def test_parse_number(text, expected):
    """Parsing handles decimal and sexagesimal inputs."""
    assert parse_number(text) == expected


def test_sexagesimal_roundtrip():
    """A value survives format-then-parse through the sexagesimal form."""
    original = 23.456
    text = format_number(original, "%9.6m")
    assert parse_number(text) == pytest.approx(original, abs=1e-3)


# --------------------------------------------------------------------------- #
# def / set / new round-trips                                                 #
# --------------------------------------------------------------------------- #
def _reparse(msg):
    """Serialise then parse back a single message.

    Parameters
    ----------
    msg : IndiMessage
        The message model to round-trip.

    Returns
    -------
    result : IndiMessage
        The message parsed back from the serialised XML.
    """
    (result,) = parse_indi(to_xml(msg))
    return result


def test_number_vector_def_roundtrip():
    """A number-vector def survives serialise-then-parse with its metadata."""
    vec = NumberVector(
        device="CCD",
        name="EXPOSURE",
        label="Exposure",
        group="Main",
        state=IPState.OK,
        perm=IPerm.RW,
        elements=[
            Number(name="CCD_EXP", label="Seconds", format="%.2f", min=0, max=3600, value=1.5)
        ],
    )
    back = _reparse(DefVector(vector=vec))
    assert isinstance(back, DefVector)
    assert back.vector.name == "EXPOSURE"
    assert back.vector.perm == IPerm.RW
    el = back.vector["CCD_EXP"]
    assert el.value == 1.5
    assert el.max == 3600


def test_switch_vector_keeps_rule_and_state():
    """A switch-vector def preserves its rule and per-switch state."""
    vec = SwitchVector(
        device="Mount",
        name="TRACK",
        rule=ISRule.ONE_OF_MANY,
        elements=[
            Switch(name="ON", value=ISState.ON),
            Switch(name="OFF", value=ISState.OFF),
        ],
    )
    back = _reparse(DefVector(vector=vec))
    assert back.vector.rule == ISRule.ONE_OF_MANY
    assert back.vector["ON"].value == ISState.ON
    assert back.vector["OFF"].value == ISState.OFF


def test_light_vector_has_no_perm_attribute_on_wire():
    """A light vector serialises without a perm attribute (lights are RO)."""
    vec = LightVector(
        device="Dome",
        name="STATUS",
        elements=[Light(name="OPEN", value=IPState.OK)],
    )
    xml = to_xml(DefVector(vector=vec)).decode()
    assert "perm" not in xml
    back = _reparse(DefVector(vector=vec))
    assert isinstance(back.vector, LightVector)
    assert back.vector["OPEN"].value == IPState.OK


def test_text_set_roundtrip():
    """A text-vector set survives serialise-then-parse."""
    vec = TextVector(device="Focuser", name="INFO", elements=[Text(name="MODEL", value="ZWO")])
    back = _reparse(SetVector(vector=vec))
    assert isinstance(back, SetVector)
    assert back.vector["MODEL"].value == "ZWO"


def test_set_vector_omits_def_only_metadata():
    """A set message emits one* nodes without def-only element metadata."""
    vec = NumberVector(
        device="CCD",
        name="TEMP",
        elements=[Number(name="T", format="%.1f", min=-40, max=40, value=-10.0)],
    )
    xml = to_xml(SetVector(vector=vec)).decode()
    assert "oneNumber" in xml
    assert "min=" not in xml  # min/max/format only belong in def
    assert "-10.0" in xml


def test_new_vector_from_client():
    """A client new-vector serialises to newXxxVector and parses back."""
    vec = NumberVector(device="CCD", name="EXPOSURE", elements=[Number(name="CCD_EXP", value=5.0)])
    xml = to_xml(NewVector(vector=vec)).decode()
    assert xml.startswith("<newNumberVector")
    back = _reparse(NewVector(vector=vec))
    assert isinstance(back, NewVector)
    assert back.vector["CCD_EXP"].value == 5.0


def test_element_lookup_raises_keyerror_for_unknown_name():
    """Vector element lookup names the missing element and property."""
    vec = NumberVector(device="CCD", name="EXPOSURE", elements=[Number(name="secs", value=1.0)])
    with pytest.raises(KeyError, match="CCD.EXPOSURE"):
        vec.element("missing")


def test_def_blob_vector_carries_element_metadata():
    """A BLOB def serialises label/format on defBLOB nodes and round-trips."""
    vec = BLOBVector(
        device="CCD",
        name="CCD1",
        elements=[BLOB(name="image", label="Image", format=".fits")],
    )
    xml = to_xml(DefVector(vector=vec)).decode()
    assert "<defBLOB" in xml
    assert 'label="Image"' in xml
    assert 'format=".fits"' in xml
    back = _reparse(DefVector(vector=vec))
    assert isinstance(back.vector, BLOBVector)
    assert back.vector["image"].format == ".fits"


def test_serialising_unknown_element_type_raises():
    """_element_xml rejects an object that is no known element model."""
    with pytest.raises(TypeError):
        _element_xml(object(), "def")


def test_serialising_unknown_message_type_raises():
    """to_xml rejects an object that is no known message model."""
    with pytest.raises(TypeError):
        to_xml(object())


def test_parsing_unknown_element_kind_raises():
    """_element_from_xml rejects an unknown element kind."""
    with pytest.raises(ValueError):
        _element_from_xml(etree.Element("oneThing"), "thing")


def test_blob_base64_roundtrip():
    """BLOB binary payloads survive base64 encode/decode with their size."""
    payload = b"\x00\x01\x02FITSDATA\xff"
    vec = BLOBVector(
        device="CCD",
        name="CCD1",
        elements=[BLOB(name="image", format=".fits", data=payload)],
    )
    back = _reparse(SetVector(vector=vec))
    assert back.vector["image"].data == payload
    assert back.vector["image"].size == len(payload)


# --------------------------------------------------------------------------- #
# Non-property messages                                                        #
# --------------------------------------------------------------------------- #
def test_get_properties_roundtrip():
    """A device/name-scoped getProperties round-trips its fields."""
    back = _reparse(GetProperties(device="CCD", name="EXPOSURE"))
    assert isinstance(back, GetProperties)
    assert back.device == "CCD"
    assert back.name == "EXPOSURE"


def test_get_properties_all_devices():
    """A bare getProperties serialises with a version and no device."""
    xml = to_xml(GetProperties()).decode()
    assert xml.startswith("<getProperties")
    assert "version=" in xml


def test_message_and_delproperty():
    """Message and delProperty messages round-trip to their model types."""
    assert isinstance(_reparse(Message(device="CCD", message="hello")), Message)
    d = _reparse(DelProperty(device="CCD", name="EXPOSURE"))
    assert isinstance(d, DelProperty)
    assert d.name == "EXPOSURE"


def test_enable_blob_roundtrip():
    """An enableBLOB message serialises its policy as element text and round-trips."""
    xml = to_xml(EnableBLOB(device="CCD", policy=BLOBPolicy.ALSO)).decode()
    assert xml.startswith("<enableBLOB")
    assert ">Also<" in xml
    back = _reparse(EnableBLOB(device="CCD", name="CCD1", policy=BLOBPolicy.ONLY))
    assert isinstance(back, EnableBLOB)
    assert back.device == "CCD"
    assert back.name == "CCD1"
    assert back.policy == BLOBPolicy.ONLY


def test_enable_blob_defaults_to_also_when_empty():
    """A bodyless enableBLOB parses back to the default Also policy."""
    (back,) = parse_indi("<enableBLOB device='CCD'></enableBLOB>")
    assert isinstance(back, EnableBLOB)
    assert back.policy == BLOBPolicy.ALSO


# --------------------------------------------------------------------------- #
# Streaming parser                                                             #
# --------------------------------------------------------------------------- #
def test_stream_parser_across_chunk_boundaries():
    """The stream parser reassembles a message fed one byte at a time."""
    vec = NumberVector(device="CCD", name="EXPOSURE", elements=[Number(name="CCD_EXP", value=1.0)])
    blob = to_xml(DefVector(vector=vec))
    parser = XMLStreamParser()
    out = []
    # feed one byte at a time to prove reassembly works
    for i in range(len(blob)):
        out.extend(parser.feed(blob[i : i + 1]))
    assert len(out) == 1
    assert isinstance(out[0], DefVector)
    assert out[0].vector["CCD_EXP"].value == 1.0


def test_stream_parser_multiple_messages_one_feed():
    """The stream parser emits every message present in one fed chunk."""
    a = to_xml(Message(message="one"))
    b = to_xml(Message(message="two"))
    parser = XMLStreamParser()
    out = list(parser.feed(a + b))
    assert [m.message for m in out] == ["one", "two"]


def test_stream_parser_is_valid_xml_output():
    """to_xml always produces well-formed, parseable XML."""
    vec = SwitchVector(
        device="Mount", name="PARK", elements=[Switch(name="PARK", value=ISState.ON)]
    )
    # to_xml must always produce well-formed, parseable XML
    etree.fromstring(to_xml(DefVector(vector=vec)))


def test_invalid_timestamp_attribute_parses_as_none():
    """A malformed timestamp attribute is dropped rather than failing parse."""
    (back,) = parse_indi(
        "<setNumberVector device='CCD' name='EXPOSURE' timestamp='not-a-date'>"
        "<oneNumber name='secs'>1</oneNumber></setNumberVector>"
    )
    assert isinstance(back, SetVector)
    assert back.vector.timestamp is None
    assert back.vector["secs"].value == 1.0


def test_comment_nodes_yield_no_message():
    """message_from_xml returns None for comment/PI nodes."""
    assert message_from_xml(etree.Comment("noise")) is None


def test_unknown_top_level_tag_is_skipped():
    """An unrecognised top-level element is skipped, later messages parse."""
    out = parse_indi(b"<wibble attr='x'>text</wibble><getProperties version='1.7'/>")
    assert len(out) == 1
    assert isinstance(out[0], GetProperties)


def test_vector_get_reads_values_tolerantly():
    """get() returns a named element's value, a default when absent, BLOB data."""
    vec = NumberVector(device="CCD", name="EXPOSURE", elements=[Number(name="secs", value=1.5)])
    assert vec.get("secs") == 1.5
    assert vec.get("missing") is None
    assert vec.get("missing", 7.0) == 7.0

    blob = BLOBVector(device="CCD", name="IMAGE", elements=[BLOB(name="frame", data=b"abc")])
    assert blob.get("frame") == b"abc"


def test_vector_values_maps_names_to_values():
    """values() returns the elements as a name-to-value mapping."""
    vec = SwitchVector(
        device="D",
        name="power",
        elements=[Switch(name="on", value=ISState.ON), Switch(name="off", value=ISState.OFF)],
    )
    assert vec.values() == {"on": ISState.ON, "off": ISState.OFF}


def test_switch_vector_selected_returns_first_on_or_none():
    """selected() names the On member of a (possibly partial) switch write."""
    partial = SwitchVector(
        device="D", name="power", elements=[Switch(name="off", value=ISState.ON)]
    )
    assert partial.selected() == "off"

    deselect = SwitchVector(
        device="D", name="power", elements=[Switch(name="a", value=ISState.OFF)]
    )
    assert deselect.selected() is None


# --------------------------------------------------------------------------- #
# Naming helpers                                                               #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Domeslit State", "domeslit_state"),
        ("Upperdome IO Byte", "upperdome_io_byte"),
        ("Wind Speed", "wind_speed"),
        ("Already_slugged", "already_slugged"),
        ("  padded   out  ", "padded_out"),
        ("Single", "single"),
    ],
)
def test_slugify_maps_labels_to_element_names(label, expected):
    """Lowercase the label and collapse whitespace runs into underscores."""
    assert slugify(label) == expected


def test_from_labels_builds_one_element_per_label():
    """from_labels names each element from its label and keeps the label."""
    lights = Light.from_labels(["Link Up", "Sensors"])

    assert [(light.name, light.label) for light in lights] == [
        ("link_up", "Link Up"),
        ("sensors", "Sensors"),
    ]
    assert all(light.value is IPState.IDLE for light in lights)


def test_from_labels_accepts_a_custom_naming_function():
    """A driver whose hardware keys differ can supply its own mapping."""
    texts = Text.from_labels(["Wind Speed"], name=lambda label: label.upper().replace(" ", "-"))

    assert texts[0].name == "WIND-SPEED"


def test_from_labels_is_typed_per_element_kind():
    """Each element class builds its own kind, so the vector accepts them."""
    numbers = Number.from_labels(["Focus Position"])
    vector = NumberVector(device="D", name="p", elements=numbers)

    assert vector.element("focus_position").value == 0.0


def test_from_labels_round_trips_through_the_wire():
    """Elements built from labels serialise and parse back unchanged."""
    vector = LightVector(device="D", name="status", elements=Light.from_labels(["Link Up"]))
    parsed = parse_indi(to_xml(DefVector(vector=vector)))[0]

    assert parsed.vector.elements[0].name == "link_up"
    assert parsed.vector.elements[0].label == "Link Up"


# --------------------------------------------------------------------------- #
# Lenient parsing: a malformed element must not stop the stream                #
# --------------------------------------------------------------------------- #
#: A number whose text cannot be a float. ``value`` is not nullable on the model,
#: so there is nothing to degrade to and the whole element has to go.
_BAD_NUMBER = (
    "<setNumberVector device='CCD' name='EXPOSURE'>"
    "<oneNumber name='secs'>not-a-number</oneNumber></setNumberVector>"
)


def test_a_malformed_value_costs_its_own_message_and_nothing_else():
    """The junk message is dropped and counted; the next one still arrives.

    Before this, the ``ValueError`` escaped mid-iteration of ``feed()`` - past
    the driver runtime's per-message isolation and past the client's reconnect
    loop - so one bad element from somebody else's driver killed the process.
    """
    parser = XMLStreamParser()

    out = list(parser.feed(_BAD_NUMBER + "<message message='still here'/>"))

    assert [m.message for m in out] == ["still here"]
    assert parser.dropped == 1
    assert parser.resets == 0


def test_a_malformed_value_is_dropped_at_any_chunk_boundary():
    """Fed one byte at a time, the same chunk drops exactly one element."""
    data = (_BAD_NUMBER + "<message message='still here'/>").encode()
    parser = XMLStreamParser()

    out = []
    for i in range(len(data)):
        out.extend(parser.feed(data[i : i + 1]))

    assert [m.message for m in out] == ["still here"]
    assert parser.dropped == 1


@pytest.mark.parametrize(
    "frame",
    [
        _BAD_NUMBER,
        "<setSwitchVector device='CCD' name='MODE'>"
        "<oneSwitch name='a'>Maybe</oneSwitch></setSwitchVector>",
        "<defNumberVector device='CCD' name='EXPOSURE' state='Sideways' perm='rw'>"
        "<defNumber name='secs'>1</defNumber></defNumberVector>",
    ],
)
def test_every_unrepresentable_leaf_drops_rather_than_raises(frame):
    """Numbers and wire tokens have no "absent" to fall back to, so they drop."""
    parser = XMLStreamParser()

    assert list(parser.feed(frame)) == []
    assert parser.dropped == 1


def test_a_dropped_element_is_logged_without_its_payload(caplog):
    """The log names the element, never quotes it: a bad BLOB can be tens of MB."""
    payload = "SECRET" + "A" * 27  # 33 base64 characters: 4n+1 never decodes
    frame = (
        "<setBLOBVector device='CCD' name='CCD1'>"
        f"<oneBLOB name='image' size='9' format='.fits'>{payload}</oneBLOB>"
        "</setBLOBVector>"
    )
    parser = XMLStreamParser()

    with caplog.at_level(logging.WARNING, logger="indi_nexus.protocol.xml"):
        assert list(parser.feed(frame)) == []

    assert parser.dropped == 1
    assert "SECRET" not in caplog.text
    assert "setBLOBVector" in caplog.text
    assert "CCD1" in caplog.text


def test_an_unparseable_optional_attribute_costs_only_that_attribute():
    """``min=''`` - what a C driver emits for an unset field - keeps the def.

    Dropping the whole ``defNumberVector`` here is far more expensive than it
    looks: a client that never saw the definition ignores every later ``set``
    for that property, so it stays blind to it until the next reconnect.
    """
    (msg,) = parse_indi(
        "<defNumberVector device='CCD' name='EXPOSURE' state='Ok' perm='rw'>"
        "<defNumber name='secs' format='%.2f' min='' max='3600' step='junk'>1.5</defNumber>"
        "</defNumberVector>"
    )

    assert isinstance(msg, DefVector)
    element = msg.vector["secs"]
    assert element.min is None
    assert element.step is None
    assert element.max == 3600
    assert element.value == 1.5


def test_an_unparseable_blob_size_costs_only_the_size():
    """``size`` is optional on the model, and the payload is the point anyway."""
    (msg,) = parse_indi(
        "<setBLOBVector device='CCD' name='CCD1'>"
        "<oneBLOB name='image' size='' format='.fits'>QUJD</oneBLOB></setBLOBVector>"
    )

    assert isinstance(msg, SetVector)
    assert msg.vector["image"].size is None
    assert msg.vector["image"].data == b"ABC"


# --------------------------------------------------------------------------- #
# Lenient parsing: an unmatched close tag must not mute the stream             #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("closer", [b"</indinexus>", b"</bogus>"])
def test_an_unmatched_close_tag_reopens_the_stream(closer):
    """Any close tag at depth 1 ends the lxml document, whatever it is named.

    A peer sending its own document's close - or any stray one - would otherwise
    leave the parser silently emitting nothing for the rest of the session.
    """
    parser = XMLStreamParser()
    assert [m.message for m in parser.feed(to_xml(Message(message="before")))] == ["before"]

    assert list(parser.feed(closer)) == []

    assert [m.message for m in parser.feed(to_xml(Message(message="after")))] == ["after"]
    assert parser.resets == 1
    assert parser.dropped == 0


def test_a_close_tag_split_across_chunks_is_still_recovered():
    """The token arriving in two reads is the same event, seen later."""
    parser = XMLStreamParser()

    assert list(parser.feed(b"</indi")) == []
    assert list(parser.feed(b"nexus>")) == []

    assert [m.message for m in parser.feed(to_xml(Message(message="after")))] == ["after"]
    assert parser.resets == 1


def test_the_rest_of_the_offending_chunk_is_lost():
    """Known and accepted: bytes after the close tag in the *same* read are gone.

    Recovering them would mean lexing the chunk here to find where the token
    ended, which is the framing work this parser exists to leave to lxml. Pinned
    so it reads as a decision rather than a regression somebody should chase.
    """
    parser = XMLStreamParser()

    out = list(parser.feed(to_xml(Message(message="a")) + b"</indinexus>"))
    out += list(parser.feed(to_xml(Message(message="b"))))

    assert [m.message for m in out] == ["a", "b"]

    parser = XMLStreamParser()
    swallowed = list(
        parser.feed(
            to_xml(Message(message="a")) + b"</indinexus>" + to_xml(Message(message="lost"))
        )
    )
    swallowed += list(parser.feed(to_xml(Message(message="c"))))

    assert [m.message for m in swallowed] == ["a", "c"]
    assert parser.resets == 1


def test_a_close_tag_inside_an_open_vector_self_heals():
    """At depth 2 lxml just closes the vector, so there is nothing to recover."""
    parser = XMLStreamParser()

    out = list(
        parser.feed(
            "<setNumberVector device='CCD' name='EXPOSURE'>"
            "<oneNumber name='secs'>1</oneNumber></indinexus>"
        )
    )
    out += list(parser.feed(to_xml(Message(message="after"))))

    assert isinstance(out[0], SetVector)
    assert out[0].vector["secs"].value == 1.0
    assert out[1].message == "after"
    assert parser.resets == 0


def test_resets_counts_framing_violations_not_lost_messages():
    """50 consecutive resets can lose nothing at all, which is why they are separate."""
    parser = XMLStreamParser()

    for _ in range(50):
        assert list(parser.feed(b"</indinexus>")) == []

    assert parser.resets == 50
    assert parser.dropped == 0
    assert [m.message for m in parser.feed(to_xml(Message(message="fine")))] == ["fine"]


# --------------------------------------------------------------------------- #
# The stall backstop                                                           #
# --------------------------------------------------------------------------- #
def test_a_stream_of_nothing_but_close_tags_still_trips_the_stall(monkeypatch):
    """Reopening is recovery, not progress, so it does not buy the peer more silence.

    Frequent resets stay harmless - see
    ``test_resets_counts_framing_violations_not_lost_messages`` - but a reset
    used to zero the stall budget, which pinned ``bytes_since_last_message``
    near zero for a peer that only ever sent close tags: the one stream
    guaranteed never to produce a message was the one that could never be
    called lost.
    """
    monkeypatch.setattr(xml_module, "STALL_THRESHOLD_BYTES", 32)
    parser = XMLStreamParser()

    for _ in range(4):  # 12 bytes each, and not a message between them
        assert list(parser.feed(b"</indinexus>")) == []

    assert parser.resets == 4
    assert parser.stalled


def test_a_completed_element_clears_the_stall_counter():
    """The counter measures "bytes in, nothing out", so any element resets it."""
    parser = XMLStreamParser()

    list(parser.feed(b"<setNumberVector device='CCD' name='EXPOSURE'"))
    assert parser.bytes_since_last_message > 0
    assert not parser.stalled

    list(parser.feed(b"><oneNumber name='secs'>1</oneNumber></setNumberVector>"))
    assert parser.bytes_since_last_message == 0


def test_a_parser_muted_mid_start_tag_is_caught_by_the_byte_counter(monkeypatch):
    """The one break the parser cannot see from the inside.

    A root close arriving while a start tag is half-parsed emits no depth-0
    event and leaves ``error_log`` empty, so :meth:`_reset` never fires and the
    stream goes quiet for good. The reader's evidence is arithmetic: bytes keep
    going in and nothing comes out.
    """
    monkeypatch.setattr(xml_module, "STALL_THRESHOLD_BYTES", 32)
    parser = XMLStreamParser()

    list(parser.feed(b"<setNumberVector device='CCD' name='EXPOSURE'"))
    list(parser.feed(b"</indinexus>"))
    assert parser.resets == 0  # invisible to the parser itself

    for _ in range(4):
        assert list(parser.feed(to_xml(Message(message="lost")))) == []

    assert parser.stalled


def test_a_resync_rebuilds_the_parser_without_forgetting_the_peer(monkeypatch):
    """The counters describe the stream, so the rebuild that fixes it keeps them.

    A driver cannot reconnect, so its reader replaces the parser object in
    place - and used to drop ``dropped`` and ``resets`` on the floor with it,
    at exactly the moment a peer's malformed-input history is most interesting.
    """
    monkeypatch.setattr(xml_module, "STALL_THRESHOLD_BYTES", 32)
    parser = XMLStreamParser()
    assert list(parser.feed(_BAD_NUMBER)) == []  # dropped: 1
    assert list(parser.feed(b"</indinexus>")) == []  # reset: 1
    list(parser.feed(b"<setNumberVector device='CCD' name='EXPOSURE'"))
    list(parser.feed(b"</indinexus>"))  # closes that element, then lxml goes quiet for good
    for _ in range(4):
        assert list(parser.feed(to_xml(Message(message="lost")))) == []
    assert parser.stalled

    parser.resync()

    assert not parser.stalled
    assert parser.dropped == 1
    assert parser.resets == 2  # the reopen the reader inferred counts as one too
    assert [m.message for m in parser.feed(to_xml(Message(message="after")))] == ["after"]


# --------------------------------------------------------------------------- #
# Timestamps: UTC in both directions                                           #
# --------------------------------------------------------------------------- #
def test_a_naive_timestamp_is_read_as_utc():
    """A bare INDI timestamp means UTC; guessing a local zone would invent an instant."""
    msg = Message(message="hi", timestamp=dt.datetime(2026, 1, 1, 12, 0, 0))

    assert msg.timestamp == dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)


def test_a_timestamp_in_another_zone_is_converted_to_utc():
    """An aware datetime keeps its instant and changes its wall clock."""
    plus_five = dt.timezone(dt.timedelta(hours=5))
    msg = Message(message="hi", timestamp=dt.datetime(2026, 1, 1, 12, 0, tzinfo=plus_five))

    assert msg.timestamp == dt.datetime(2026, 1, 1, 7, 0, tzinfo=dt.UTC)
    assert 'timestamp="2026-01-01T07:00:00"' in to_xml(msg).decode()


def test_as_utc_labels_the_naive_and_converts_the_aware():
    """The one normalisation point, used by the models and by driver writes alike."""
    assert as_utc(dt.datetime(2026, 1, 1, 12, 0)) == dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)
    assert as_utc(dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)) == dt.datetime(
        2026, 1, 1, 12, 0, tzinfo=dt.UTC
    )


def test_indi_now_is_aware_utc_at_whole_seconds():
    """Truncated because the XML format is: otherwise one emission disagrees with itself."""
    now = indi_now()

    assert now.tzinfo is dt.UTC
    assert now.microsecond == 0


def test_the_xml_timestamp_is_bare_and_the_json_one_is_zulu():
    """Each wire gets the form its readers require, from the same instant.

    The XML stays byte-identical to libindi's ``indi_timestamp()`` (gmtime, no
    offset, no ``Z``). The JSON must carry the ``Z``: ECMAScript reads an
    offsetless string as *local* time, so the panel's ``new Date(timestamp)``
    would silently shift every log line by the viewer's own zone.
    """
    msg = Message(message="hi", timestamp=dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC))

    assert 'timestamp="2026-01-01T12:00:00"' in to_xml(msg).decode()

    stamp = json.loads(to_json(msg))["timestamp"]
    assert stamp == "2026-01-01T12:00:00Z"
    # The Z is what makes this an instant: against a naive datetime the
    # subtraction below is a TypeError, which is what the JSON used to produce.
    assert dt.datetime.fromisoformat(stamp) - dt.datetime(
        2026, 1, 1, 11, 0, tzinfo=dt.UTC
    ) == dt.timedelta(hours=1)


def test_a_timestamp_round_trips_through_xml_as_the_same_instant():
    """Serialise, parse back, and the model still holds aware UTC."""
    msg = Message(device="CCD", message="hi", timestamp=dt.datetime(2026, 1, 1, 12, 0))

    (back,) = parse_indi(to_xml(msg))

    assert back.timestamp == dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)


def test_a_bare_wire_timestamp_is_utc_whatever_zone_the_reader_runs_in():
    """The reading of a peer's timestamp cannot depend on where we are hosted."""
    original = os.environ.get("TZ")
    os.environ["TZ"] = "America/Los_Angeles"
    time.tzset()  # process-global; the finally below puts it back
    try:
        (back,) = parse_indi("<message message='hi' timestamp='2026-01-01T12:00:00'/>")

        assert back.timestamp == dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)
        assert indi_now().tzinfo is dt.UTC
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()


# --------------------------------------------------------------------------- #
# `state` is #IMPLIED on a set                                                 #
# --------------------------------------------------------------------------- #
def test_a_stateless_set_records_that_state_was_absent():
    """``state`` is #IMPLIED on every set*Vector and means "no change if absent".

    The absence has to be carried across the parse boundary or it cannot be
    honoured downstream, and it rides on the wrapper so that a cached vector's
    ``state`` stays non-nullable for everything that reads one.
    """
    (msg,) = parse_indi(
        "<setNumberVector device='CCD' name='EXPOSURE'>"
        "<oneNumber name='secs'>2</oneNumber></setNumberVector>"
    )

    assert isinstance(msg, SetVector)
    assert msg.state_present is False
    assert msg.vector.state is IPState.IDLE  # the parse default, not a claim


def test_a_set_that_carries_state_says_so():
    """A state on the wire is a state change, and the flag reports it as one."""
    (msg,) = parse_indi(
        "<setNumberVector device='CCD' name='EXPOSURE' state='Busy'>"
        "<oneNumber name='secs'>2</oneNumber></setNumberVector>"
    )

    assert isinstance(msg, SetVector)
    assert msg.state_present is True
    assert msg.vector.state is IPState.BUSY


def test_our_own_sets_always_carry_state_on_the_wire():
    """Round-trip: this codec always writes a state, so a parse back says present."""
    vec = NumberVector(
        device="CCD", name="EXPOSURE", state=IPState.ALERT, elements=[Number(name="secs", value=2)]
    )

    back = _reparse(SetVector(vector=vec))

    assert isinstance(back, SetVector)
    assert back.state_present is True
    assert back.vector.state is IPState.ALERT


def test_membership_finds_elements_that_exist():
    """``name in vector`` answers truthfully for present and absent elements.

    Regression test for a silent wrong answer: with ``__getitem__`` defined and no
    ``__contains__``, Python fell back to indexing 0, 1, 2 ... against a name
    lookup, so membership returned False for an element that was present. The
    interop suite found it by writing the obvious thing.
    """
    vector = NumberVector(
        device="Mount",
        name="EQUATORIAL_EOD_COORD",
        elements=[Number(name="RA", value=1.0), Number(name="DEC", value=2.0)],
    )
    assert "RA" in vector
    assert "DEC" in vector
    assert "AZ" not in vector
    assert 0 not in vector
