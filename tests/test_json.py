"""Round-trip tests for the INDI JSON codec (the browser wire contract)."""

from __future__ import annotations

import base64
import json
import zlib

import pytest
from pydantic import ValidationError

from indi_nexus.exceptions import ProtocolError
from indi_nexus.protocol import (
    BLOB,
    BLOBVector,
    DefVector,
    DelProperty,
    EnableBLOB,
    GetProperties,
    IPState,
    ISState,
    Message,
    NewVector,
    Number,
    NumberVector,
    SetVector,
    Switch,
    SwitchVector,
    from_json,
    to_json,
)


def _roundtrip(msg):
    """Serialise a message to JSON and parse it back."""
    return from_json(to_json(msg))


def test_number_def_roundtrips():
    """A number-vector def survives JSON serialise-then-parse with metadata."""
    vec = NumberVector(
        device="CCD",
        name="EXPOSURE",
        state=IPState.OK,
        elements=[Number(name="secs", format="%.2f", min=0, max=3600, value=1.5)],
    )
    back = _roundtrip(DefVector(vector=vec))
    assert isinstance(back, DefVector)
    assert back.vector.name == "EXPOSURE"
    assert back.vector.element("secs").value == 1.5
    assert back.vector.element("secs").max == 3600


def test_switch_set_roundtrips():
    """A switch-vector set keeps its element states through JSON."""
    vec = SwitchVector(
        device="Mount",
        name="TRACK",
        elements=[Switch(name="ON", value=ISState.ON), Switch(name="OFF", value=ISState.OFF)],
    )
    back = _roundtrip(SetVector(vector=vec))
    assert isinstance(back, SetVector)
    assert back.vector.element("ON").value == ISState.ON


def test_non_property_messages_roundtrip():
    """getProperties, message, delProperty, and enableBLOB round-trip."""
    assert isinstance(_roundtrip(GetProperties(device="CCD")), GetProperties)
    assert isinstance(_roundtrip(Message(device="CCD", message="hi")), Message)
    assert isinstance(_roundtrip(DelProperty(device="CCD", name="EXPOSURE")), DelProperty)
    assert isinstance(_roundtrip(EnableBLOB(device="CCD")), EnableBLOB)


def test_blob_payload_is_base64_in_json():
    """A BLOB's binary payload travels as base64 and decodes back to bytes."""
    payload = b"\x00\x01\x02FITS\xff"
    vec = BLOBVector(
        device="CCD", name="CCD1", elements=[BLOB(name="image", format=".fits", data=payload)]
    )
    text = to_json(SetVector(vector=vec))
    # The wire value is valid JSON with a base64 string, not raw bytes.
    obj = json.loads(text)
    assert isinstance(obj["vector"]["elements"][0]["data"], str)

    back = from_json(text)
    assert isinstance(back, SetVector)
    assert back.vector.element("image").data == payload


def test_a_blob_with_no_payload_is_null_in_json_and_stays_null():
    """A ``defBLOBVector`` carries metadata and no bytes; base64 must not invent any."""
    vec = BLOBVector(device="CCD", name="CCD1", elements=[BLOB(name="image", format=".fits")])

    obj = json.loads(to_json(DefVector(vector=vec)))
    back = _roundtrip(DefVector(vector=vec))

    assert obj["vector"]["elements"][0]["data"] is None
    assert back.vector.element("image").data is None
    assert back.vector.element("image").format == ".fits"


def test_a_blob_payload_uses_the_standard_base64_alphabet():
    """The wire alphabet is ``+``/``/``, never the URL-safe ``-``/``_``.

    Not a stylistic preference: ``atob`` and a ``data:...;base64,`` URL are both
    defined over forgiving-base64, which **rejects** ``-`` and ``_``, and the
    panel builds exactly such a URL for its download link. Pydantic's
    ``ser_json_bytes="base64"`` emits the URL-safe alphabet, so this passed only
    because our own validator happens to accept both and no consumer in the
    round-trip ever ran the browser's decoder.

    The payload is chosen so its standard encoding contains both characters.
    """
    payload = b"\xff\xfe\xfd\x03\xe0"
    assert base64.b64encode(payload) == b"//79A+A="

    vec = BLOBVector(device="CCD", name="CCD1", elements=[BLOB(name="image", data=payload)])
    data = json.loads(to_json(SetVector(vector=vec)))["vector"]["elements"][0]["data"]

    assert data == "//79A+A="
    assert "-" not in data and "_" not in data
    # The strict decoder every browser consumer effectively runs.
    assert base64.b64decode(data, validate=True) == payload


def test_a_blob_payload_is_accepted_in_either_base64_alphabet():
    """Emitting standard base64 must not narrow what we *accept*.

    A peer that has been sending URL-safe payloads - anything written against
    what this codec used to emit - keeps working, because the fix is to the
    serializer alone and ``val_json_bytes="base64"`` takes both alphabets.
    """
    payload = b"\xff\xfe\xfd\x03\xe0"
    for encode in (base64.b64encode, base64.urlsafe_b64encode):
        frame = json.dumps(
            {
                "tag": "new",
                "vector": {
                    "kind": "blob",
                    "device": "CCD",
                    "name": "UPLOAD",
                    "elements": [
                        {"kind": "blob", "name": "image", "data": encode(payload).decode()}
                    ],
                },
            }
        )

        msg = from_json(frame)

        assert isinstance(msg, NewVector)
        assert msg.vector.element("image").data == payload


def test_a_blob_payload_stays_bytes_outside_json():
    """The serializer is JSON-only; ``model_dump()`` still hands back bytes.

    Python-mode dumps feed application code, not the wire, and turning the
    payload into a string there would break every caller reading ``.data``.
    """
    vec = BLOBVector(device="CCD", name="CCD1", elements=[BLOB(name="image", data=b"\xff\xfe")])

    assert vec.model_dump()["elements"][0]["data"] == b"\xff\xfe"
    assert vec.model_dump(mode="json")["elements"][0]["data"] == "//4="


def test_a_browser_authored_blob_frame_decodes_its_base64():
    """A frame a browser wrote by hand arrives as bytes, not as the base64 string.

    This is the direction the panel writes in (an upload), and the only place the
    JSON codec has to *decode* rather than encode.
    """
    frame = (
        '{"tag":"new","vector":{"kind":"blob","device":"CCD","name":"UPLOAD",'
        '"elements":[{"kind":"blob","name":"image","format":".fits",'
        '"size":5,"data":"YXN0cm8="}]}}'
    )

    msg = from_json(frame)

    assert isinstance(msg, NewVector)
    assert msg.vector.element("image").data == b"astro"
    assert msg.vector.element("image").size == 5


def test_a_browser_blob_frame_with_broken_base64_is_refused():
    """Bad base64 fails validation rather than decoding to fewer bytes.

    The XML side already refuses a payload it cannot decode instead of silently
    discarding the offending characters; the browser side has to agree, or the
    two codecs disagree about what a valid frame is.
    """
    frame = (
        '{"tag":"new","vector":{"kind":"blob","device":"CCD","name":"UPLOAD",'
        '"elements":[{"kind":"blob","name":"image","data":"not base64!!"}]}}'
    )

    with pytest.raises(ValidationError):
        from_json(frame)


def test_a_blob_keeps_its_size_and_format_through_json():
    """The two fields a browser needs to label a download survive the trip.

    ``size`` is the uncompressed length the driver declared, which is not the
    length of the bytes when the format says compressed, so it cannot be
    reconstructed on the far side and has to travel.
    """
    vec = BLOBVector(
        device="CCD",
        name="CCD1",
        elements=[BLOB(name="image", format=".fits.fz", size=11_520, data=b"tile-compressed")],
    )

    back = _roundtrip(SetVector(vector=vec))

    assert back.vector.element("image").size == 11_520
    assert back.vector.element("image").format == ".fits.fz"
    assert back.vector.element("image").data == b"tile-compressed"


def test_the_json_codec_inflates_a_compressed_blob_like_the_xml_one():
    """Both codecs read the same wire, so both apply the ``.z`` rule.

    The asymmetry is deliberate and is the only one in this codec: a model
    holding a deflated payload serialises as it stands, because compressing is
    the driver's decision, and parsing one inflates it, because no consumer of
    these models - a Python application or a browser with no zlib of its own -
    should ever meet a payload that is not what ``format`` says it is.
    """
    raw = b"SIMPLE  =                    T" + b" " * 300
    vec = BLOBVector(
        device="CCD",
        name="CCD1",
        elements=[BLOB(name="image", format=".fits.z", size=len(raw), data=zlib.compress(raw))],
    )

    back = _roundtrip(SetVector(vector=vec))

    element = back.vector.element("image")
    assert element.data == raw
    assert element.format == ".fits"
    assert element.size == len(raw)


def test_the_json_codec_leaves_fits_tile_compression_alone():
    """``.fz`` is a container format, not a transport encoding - in both codecs."""
    payload = b"\x78\x9c-fpacked-not-deflate"
    vec = BLOBVector(
        device="CCD",
        name="CCD1",
        elements=[BLOB(name="image", format=".fits.fz", size=99_999, data=payload)],
    )

    back = _roundtrip(SetVector(vector=vec))

    assert back.vector.element("image").format == ".fits.fz"
    assert back.vector.element("image").data == payload


def test_a_corrupt_compressed_blob_is_refused_by_the_json_codec():
    """Loud here too, and for the same reason: never deliver the deflate.

    The JSON codec has no drop-and-count path - a browser frame is one message on
    a socket the bridge answers with an error frame - so the ``ProtocolError``
    comes out, and it is a `ValueError` like every other refusal here.
    """
    frame = (
        '{"tag":"set","vector":{"kind":"blob","device":"CCD","name":"CCD1",'
        '"elements":[{"kind":"blob","name":"image","format":".fits.z",'
        '"size":512,"data":"eJxub3QtZGVmbGF0ZQ=="}]}}'
    )

    with pytest.raises(ProtocolError):
        from_json(frame)


def test_browser_new_frame_parses_to_new_vector():
    """A browser-authored new* frame parses into a typed NewVector."""
    frame = (
        '{"tag":"new","vector":{"kind":"number","device":"CCD","name":"EXPOSURE",'
        '"elements":[{"kind":"number","name":"secs","value":2.0}]}}'
    )
    msg = from_json(frame)
    assert isinstance(msg, NewVector)
    assert msg.vector.element("secs").value == 2.0


@pytest.mark.parametrize(
    "frame",
    [
        "{}",
        '{"event":"connection","connected":true}',
        '{"event":"error","code":"malformed","message":"x","tag":null}',
        '{"tag":"nonesuch","device":"CCD"}',
    ],
    ids=["empty", "connection-control", "error-control", "unknown-tag"],
)
def test_an_object_with_no_known_tag_is_refused(frame):
    """A frame the codec cannot name is refused, not read as a getProperties.

    Undiscriminated, the union was not closed: ``GetProperties`` defaults every
    field and the base model ignores extras, so any of these validated as a
    ``getProperties``. The bridge then accepted a browser echoing one of its own
    control frames back up ``/ws`` and forwarded it upstream.
    """
    with pytest.raises(ValidationError):
        from_json(frame)


def test_an_invalid_frame_reports_one_branch_not_seven():
    """A frame that names its tag fails against that member alone.

    The observable proof the discriminator is declared rather than inferred:
    without it every member is tried and a single missing field comes back as
    seven parallel failures.
    """
    with pytest.raises(ValidationError) as exc:
        from_json('{"tag":"def"}')
    assert len(exc.value.errors()) == 1
    assert exc.value.errors()[0]["loc"] == ("def", "vector")
