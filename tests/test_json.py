"""Round-trip tests for the INDI JSON codec (the browser wire contract)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

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
