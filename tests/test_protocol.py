"""Tests for the INDI protocol core: enums, models, and the XML codec."""

from __future__ import annotations

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
    parse_indi,
    to_xml,
)
from indi_nexus.protocol.xml import format_number, parse_number


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


# --------------------------------------------------------------------------- #
# Sexagesimal formatting / parsing                                            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value,fmt,expected",
    [
        (10.5, "%5.3m", "10:30"),
        (10.5, "%8.6m", "10:30:00"),
        (-10.5, "%8.6m", "-10:30:00"),
        (12.582777778, "%9.6m", " 12:34:58"),  # width-9 field pads the degrees (libindi-faithful)
        (1.0, "%.2f", "1.00"),
    ],
)
def test_format_number(value, fmt, expected):
    """Formatting matches the expected printf / sexagesimal output."""
    assert format_number(value, fmt) == expected


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
    """message and delProperty messages round-trip to their model types."""
    assert isinstance(_reparse(Message(device="CCD", message="hello")), Message)
    d = _reparse(DelProperty(device="CCD", name="EXPOSURE"))
    assert isinstance(d, DelProperty)
    assert d.name == "EXPOSURE"


def test_enable_blob_roundtrip():
    """enableBLOB serialises its policy as element text and round-trips."""
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
