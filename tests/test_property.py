"""Tests for ``BoundProperty``: switch rules, emit policy, and bulk writes.

These exercise the handle in isolation - a vector plus a list to emit into - so
each assertion is about what the driver would have told the client, with no
runtime or transport in the way.
"""

from __future__ import annotations

import datetime as dt
import zlib

import pytest

from indi_nexus.driver.property import BoundProperty
from indi_nexus.exceptions import ProtocolError
from indi_nexus.protocol import (
    BLOB,
    BLOBVector,
    DelProperty,
    IndiMessage,
    IPState,
    ISRule,
    ISState,
    Light,
    LightVector,
    Number,
    NumberVector,
    SetVector,
    Switch,
    SwitchVector,
    Text,
    TextVector,
    to_xml,
)


def _switches(rule: ISRule) -> tuple[BoundProperty[SwitchVector], list[IndiMessage]]:
    """Return a three-member switch property under ``rule``, plus its outbox."""
    vector = SwitchVector(
        device="Dev",
        name="commands",
        rule=rule,
        elements=[
            Switch(name="a", value=ISState.ON),
            Switch(name="b"),
            Switch(name="c"),
        ],
    )
    emitted: list[IndiMessage] = []
    return BoundProperty(vector, emitted.append), emitted


def _numbers(policy: str = "always") -> tuple[BoundProperty[NumberVector], list[IndiMessage]]:
    """Return a two-element number property under ``policy``, plus its outbox."""
    vector = NumberVector(
        device="Dev",
        name="coords",
        elements=[Number(name="ra", value=1.0), Number(name="dec", value=2.0)],
    )
    emitted: list[IndiMessage] = []
    return BoundProperty(vector, emitted.append, policy=policy), emitted  # type: ignore[arg-type]


def _blobs(policy: str = "always") -> tuple[BoundProperty[BLOBVector], list[IndiMessage]]:
    """Return a one-element BLOB property under ``policy``, plus its outbox."""
    vector = BLOBVector(
        device="Dev",
        name="CCD1",
        elements=[BLOB(name="image", format=".fits")],
    )
    emitted: list[IndiMessage] = []
    return BoundProperty(vector, emitted.append, policy=policy), emitted  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Switch rules                                                                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rule", [ISRule.ONE_OF_MANY, ISRule.AT_MOST_ONE])
def test_exclusive_rules_clear_siblings(rule: ISRule) -> None:
    """Both exclusive rules allow at most one On, so turning one On clears the rest."""
    prop, _ = _switches(rule)

    prop.set(b=ISState.ON)

    assert prop.vector.values() == {"a": ISState.OFF, "b": ISState.ON, "c": ISState.OFF}


def test_any_of_many_leaves_siblings_alone() -> None:
    """AnyOfMany has no exclusivity invariant, so siblings are untouched."""
    prop, _ = _switches(ISRule.ANY_OF_MANY)

    prop.set(b=ISState.ON)

    assert prop.vector.values() == {"a": ISState.ON, "b": ISState.ON, "c": ISState.OFF}


@pytest.mark.parametrize("rule", [ISRule.ONE_OF_MANY, ISRule.AT_MOST_ONE, ISRule.ANY_OF_MANY])
def test_turning_one_off_touches_only_that_member(rule: ISRule) -> None:
    """An explicit Off applies to its own member under every rule."""
    prop, _ = _switches(rule)

    prop.set(a=False)

    assert prop.vector.values() == {"a": ISState.OFF, "b": ISState.OFF, "c": ISState.OFF}


def test_switch_values_accept_bools_and_wire_strings() -> None:
    """A switch takes an ISState, a bool, or the wire token."""
    prop, _ = _switches(ISRule.ANY_OF_MANY)

    prop.set(a=False, b=True, c="On")

    assert prop.vector.values() == {"a": ISState.OFF, "b": ISState.ON, "c": ISState.ON}


# --------------------------------------------------------------------------- #
# Emit policy                                                                  #
# --------------------------------------------------------------------------- #
def test_always_policy_emits_every_time() -> None:
    """The default policy puts a set on the wire even when nothing moved."""
    prop, emitted = _numbers()

    prop.set(ra=1.0)
    prop.set(ra=1.0)

    assert len(emitted) == 2


def test_on_change_policy_is_silent_when_nothing_differs() -> None:
    """An on_change property re-sent identical values says nothing."""
    prop, emitted = _numbers("on_change")

    prop.set(ra=1.0, dec=2.0)  # already the current values

    assert emitted == []


def test_on_change_policy_emits_when_a_value_moves() -> None:
    """A changed element is news, so it goes out."""
    prop, emitted = _numbers("on_change")

    prop.set(ra=1.0, dec=2.0)
    prop.set(ra=5.0, dec=2.0)

    assert len(emitted) == 1
    assert isinstance(emitted[0], SetVector)
    assert emitted[0].vector.get("ra") == 5.0


def test_on_change_policy_emits_when_only_the_state_moves() -> None:
    """A state transition with unchanged values is still news."""
    prop, emitted = _numbers("on_change")

    prop.set(ra=1.0, state=IPState.BUSY)

    assert len(emitted) == 1
    assert emitted[0].vector.state is IPState.BUSY  # type: ignore[union-attr]


def test_on_change_policy_emits_when_only_the_message_moves() -> None:
    """An attached message with unchanged values is still news."""
    prop, emitted = _numbers("on_change")

    prop.set(message="slewing")

    assert len(emitted) == 1


def test_on_change_policy_leaves_the_timestamp_alone_when_silent() -> None:
    """A suppressed set does not restamp the vector; nothing was published."""
    prop, _ = _numbers("on_change")
    # Aware, because set() normalises a caller's timestamp to UTC: an aware
    # value compared against a naive one is quietly False rather than an error.
    stamped = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.UTC)
    prop.set(ra=9.0, timestamp=stamped)

    prop.set(ra=9.0)

    assert prop.vector.timestamp == stamped


def test_on_change_policy_ignores_jitter_below_the_declared_format() -> None:
    """A sensor twitching under its own format has told the client nothing."""
    vector = NumberVector(
        device="Dev",
        name="weather",
        elements=[Number(name="temp", format="%.1f", value=11.0)],
    )
    emitted: list[IndiMessage] = []
    prop = BoundProperty(vector, emitted.append, policy="on_change")

    prop.set(temp=11.00004)  # renders "11.0", exactly as before

    assert emitted == []
    assert prop.value("temp") == 11.00004  # the reading is still recorded


def test_on_change_policy_emits_once_jitter_crosses_the_format() -> None:
    """Movement the client can actually see is published."""
    vector = NumberVector(
        device="Dev",
        name="weather",
        elements=[Number(name="temp", format="%.1f", value=11.0)],
    )
    emitted: list[IndiMessage] = []
    prop = BoundProperty(vector, emitted.append, policy="on_change")

    prop.set(temp=11.06)  # renders "11.1"

    assert len(emitted) == 1


def test_force_overrides_the_on_change_policy() -> None:
    """force=True re-announces a property that has nothing new to say."""
    prop, emitted = _numbers("on_change")

    prop.set(ra=1.0, force=True)

    assert len(emitted) == 1


def test_on_change_policy_still_writes_the_values() -> None:
    """Suppressing the emit must not suppress the assignment."""
    prop, emitted = _numbers("on_change")

    prop.set(ra=7.0)
    emitted.clear()
    prop.set(ra=7.0)

    assert prop.value("ra") == 7.0
    assert emitted == []


# --------------------------------------------------------------------------- #
# BLOB payloads                                                                #
# --------------------------------------------------------------------------- #
def test_publishing_a_blob_stores_the_bytes_and_their_length() -> None:
    """``size`` is derived on assignment, so a driver never has to keep it in step."""
    prop, emitted = _blobs()

    prop.set(image=b"\x00FITS\xff", state=IPState.OK)

    element = prop.vector.element("image")
    assert element.data == b"\x00FITS\xff"
    assert element.size == 6
    assert prop.value("image") == b"\x00FITS\xff"
    (msg,) = emitted
    assert isinstance(msg, SetVector)
    assert msg.vector.get("image") == b"\x00FITS\xff"


def test_a_compressed_element_keeps_the_size_its_driver_declared() -> None:
    """For a ``.z`` payload, ``len(data)`` is the wrong number and the driver knows it.

    INDI's ``size`` is the decoded *and uncompressed* length. Deriving it from
    the bytes is right for the ordinary frame above and silently wrong here: it
    would put deflate's output length on the wire under an attribute defined as
    the other number, and it is a plausible integer, so nothing downstream would
    question it. The driver states it once - the uncompressed length of a frame
    does not change with how well it compressed - and publishing keeps it.
    """
    prop, emitted = _blobs()
    element = prop.vector.element("image")
    element.format = ".fits.z"
    element.size = 9000

    prop.set(image=zlib.compress(b"FITS" * 2250), state=IPState.OK)

    assert element.size == 9000
    assert to_xml(emitted[0]).count(b'size="9000"') == 1


def test_a_compressed_element_with_no_declared_size_fails_loudly_at_the_codec() -> None:
    """The driver that says nothing gets an error, not a wrong frame.

    The counterpart to the test above: with ``size`` left unwritten there is no
    number to put on the wire, so the refusal happens where the frame would have
    been serialised - which the runtime's writer reports and drops, rather than
    emitting a spec-violating ``size`` nothing would ever notice.
    """
    prop, emitted = _blobs()
    prop.vector.element("image").format = ".fits.z"

    prop.set(image=zlib.compress(b"FITS" * 2250), state=IPState.OK)

    assert prop.vector.element("image").size is None
    with pytest.raises(ProtocolError, match="uncompressed length"):
        to_xml(emitted[0])


@pytest.mark.parametrize(
    "payload",
    [bytearray(b"frame"), memoryview(b"frame"), b"frame"],
    ids=["bytearray", "memoryview", "bytes"],
)
def test_a_blob_payload_is_copied_into_immutable_bytes(payload) -> None:
    """A driver hands over the buffer it just read; the handle must not alias it.

    A camera SDK reads into one reusable buffer per exposure. Stored by
    reference, the next exposure would rewrite the payload of a message already
    queued for the client - a frame that is neither the one announced nor
    detectably wrong.
    """
    prop, emitted = _blobs()

    prop.set(image=payload)
    if isinstance(payload, bytearray):
        payload[0:5] = b"XXXXX"  # the driver reusing its buffer

    assert prop.value("image") == b"frame"
    assert isinstance(prop.value("image"), bytes)
    assert emitted[0].vector.get("image") == b"frame"  # type: ignore[union-attr]


def test_on_change_policy_suppresses_a_repeated_identical_frame() -> None:
    """The policy compares payloads, so a static scene does not re-send its image.

    Worth pinning because the comparison runs over whole frames: an
    implementation that compared object identity instead would emit every time,
    and one that compared only element *names* would never emit again.
    """
    prop, emitted = _blobs("on_change")

    prop.set(image=b"same-frame")
    prop.set(image=b"same-frame")

    assert len(emitted) == 1


def test_on_change_policy_emits_when_the_frame_changes() -> None:
    """A new image is news even when everything around it is unchanged."""
    prop, emitted = _blobs("on_change")

    prop.set(image=b"frame-one")
    prop.set(image=b"frame-two")

    assert len(emitted) == 2
    assert emitted[1].vector.get("image") == b"frame-two"  # type: ignore[union-attr]


def test_on_change_policy_emits_when_only_the_state_moves_for_a_blob() -> None:
    """Exposure done with the same frame still has to reach the client.

    The state is what an imaging client waits on, so suppressing this would hang
    a caller that is watching for the vector to leave Busy.
    """
    prop, emitted = _blobs("on_change")

    prop.set(image=b"frame", state=IPState.BUSY)
    prop.set(image=b"frame", state=IPState.OK)

    assert len(emitted) == 2
    assert emitted[1].vector.state is IPState.OK


# --------------------------------------------------------------------------- #
# Emissions are values, not views                                              #
# --------------------------------------------------------------------------- #
def test_an_emitted_set_is_detached_from_the_live_vector() -> None:
    """What was published stays published, whatever the driver does next.

    The runtime serialises an emission from its own task, long after the handler
    that produced it has moved on, so a message holding the handle's live vector
    reports the driver's end state rather than the transition it announced.
    """
    prop, emitted = _numbers()

    prop.set(ra=1.0, state=IPState.BUSY)
    prop.set(ra=9.0, state=IPState.OK)

    first, second = emitted
    assert isinstance(first, SetVector)
    assert isinstance(second, SetVector)
    assert (first.vector.state, first.vector.get("ra")) == (IPState.BUSY, 1.0)
    assert (second.vector.state, second.vector.get("ra")) == (IPState.OK, 9.0)


def test_an_emitted_vector_survives_a_later_element_write() -> None:
    """The copy reaches the elements, not just the fields on the vector itself."""
    prop, emitted = _numbers()

    prop.set(ra=1.0)
    prop.vector.element("ra").value = 42.0  # the driver, mutating its own model

    assert emitted[0].vector.get("ra") == 1.0  # type: ignore[union-attr]


def test_an_emitted_blob_payload_survives_the_next_frame() -> None:
    """A camera reuses one handle for every frame, so the copy has to reach the bytes.

    ``detached`` copies elements but relies on every element field being an
    immutable scalar rebound on assignment. That is true of `bytes` today and is
    the assumption a mutable payload buffer would break, publishing frame two
    inside the message announcing frame one.
    """
    prop, emitted = _blobs()

    prop.set(image=b"frame-one")
    prop.set(image=b"frame-two")

    first, second = emitted
    assert first.vector.get("image") == b"frame-one"  # type: ignore[union-attr]
    assert second.vector.get("image") == b"frame-two"  # type: ignore[union-attr]


def test_an_emitted_vector_keeps_its_own_element_list() -> None:
    """Adding an element to the live vector does not retro-fit an old emission."""
    prop, emitted = _numbers()

    prop.set(ra=1.0)
    prop.vector.elements.append(Number(name="epoch", value=2000.0))

    assert "epoch" not in emitted[0].vector  # type: ignore[union-attr]
    assert "epoch" in prop.vector


# --------------------------------------------------------------------------- #
# set_all                                                                      #
# --------------------------------------------------------------------------- #
def test_set_all_writes_every_element_in_one_emit() -> None:
    """set_all is the reset half of the "one of N lights is lit" idiom."""
    vector = LightVector(
        device="Dev",
        name="state",
        elements=[Light(name=n, value=IPState.BUSY) for n in ("x", "y", "z")],
    )
    emitted: list[IndiMessage] = []
    prop = BoundProperty(vector, emitted.append)

    prop.set_all(IPState.IDLE, state=IPState.IDLE)

    assert prop.vector.values() == dict.fromkeys(("x", "y", "z"), IPState.IDLE)
    assert len(emitted) == 1
    assert prop.state is IPState.IDLE


# --------------------------------------------------------------------------- #
# select                                                                       #
# --------------------------------------------------------------------------- #
def _lights() -> tuple[BoundProperty[LightVector], list[IndiMessage]]:
    """Return a three-light property plus its outbox."""
    vector = LightVector(
        device="Dev",
        name="state_message",
        elements=Light.from_labels(["Idle", "Opening", "Closing"]),
    )
    emitted: list[IndiMessage] = []
    return BoundProperty(vector, emitted.append), emitted


def test_select_lights_one_and_clears_the_rest() -> None:
    """The whole "one of N lights is lit" idiom in one call."""
    prop, emitted = _lights()

    prop.select("opening", IPState.BUSY)

    assert prop.vector.values() == {
        "idle": IPState.IDLE,
        "opening": IPState.BUSY,
        "closing": IPState.IDLE,
    }
    assert len(emitted) == 1


def test_select_takes_the_vector_state_from_the_lit_light() -> None:
    """A light's state is the vector's state, so it does not need repeating."""
    prop, _ = _lights()

    prop.select("closing", IPState.ALERT)

    assert prop.state is IPState.ALERT


def test_select_state_can_be_overridden() -> None:
    """An explicit state wins over the inferred one."""
    prop, _ = _lights()

    prop.select("opening", IPState.BUSY, state=IPState.OK)

    assert prop.state is IPState.OK
    assert prop.value("opening") is IPState.BUSY


def test_select_clears_switch_siblings_to_off() -> None:
    """On a switch vector the unselected value is Off, whatever the rule."""
    prop, _ = _switches(ISRule.ANY_OF_MANY)

    prop.select("c", ISState.ON)

    assert prop.vector.values() == {"a": ISState.OFF, "b": ISState.OFF, "c": ISState.ON}


def test_select_leaves_switch_state_alone_by_default() -> None:
    """ISState is not an IPState, so a switch select infers no vector state."""
    prop, _ = _switches(ISRule.ANY_OF_MANY)
    prop.set(state=IPState.OK)

    prop.select("b", ISState.ON)

    assert prop.state is IPState.OK


def test_select_accepts_an_explicit_others_value() -> None:
    """others= overrides the per-kind default."""
    prop, _ = _lights()

    prop.select("idle", IPState.OK, others=IPState.BUSY)

    assert prop.value("opening") is IPState.BUSY


def test_select_rejects_an_unknown_element() -> None:
    """Selecting something the vector does not have is a bug, so it raises."""
    prop, _ = _lights()

    with pytest.raises(KeyError):
        prop.select("nope", IPState.OK)


def test_select_needs_others_for_a_kind_with_no_off_value() -> None:
    """A number vector has no natural unselected value, so select asks for one."""
    prop, _ = _numbers()

    with pytest.raises(TypeError, match="needs others="):
        prop.select("ra", 1.0)

    prop.select("ra", 1.0, others=0.0)
    assert prop.vector.values() == {"ra": 1.0, "dec": 0.0}


def test_contains_reports_membership() -> None:
    """`in` answers "does the hardware's value have a light here?"."""
    prop, _ = _lights()

    assert "opening" in prop
    assert "snowing" not in prop


# --------------------------------------------------------------------------- #
# Text coercion                                                                #
# --------------------------------------------------------------------------- #
def test_text_elements_coerce_non_strings() -> None:
    """A reading published to a text element is rendered, not left to explode."""
    vector = TextVector(device="Dev", name="readings", elements=[Text(name="count")])
    emitted: list[IndiMessage] = []
    prop = BoundProperty(vector, emitted.append)

    prop.set(count=3)

    assert prop.value("count") == "3"
    # ...and it survives the trip to the wire, which a raw int would not.
    assert b">3<" in to_xml(emitted[0])


# --------------------------------------------------------------------------- #
# Non-finite numbers                                                           #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_number_is_refused_at_the_call_site(value: float) -> None:
    """Same reasoning as the text coercion: fail here, not in the writer loop.

    Assigning to a model attribute skips the validation ``Number.value`` carries,
    so a NaN from a sulking sensor would reach the wire - as a JSON ``null`` the
    browser codec cannot read back, and as whatever an integer ``format`` makes
    of it in XML.
    """
    prop, emitted = _numbers()

    with pytest.raises(ValueError, match="Dev.coords.ra"):
        prop.set(ra=value)

    assert emitted == []
    assert prop.value("ra") == 1.0


# --------------------------------------------------------------------------- #
# Retraction                                                                   #
# --------------------------------------------------------------------------- #
def test_a_retracted_handle_refuses_to_publish() -> None:
    """The handle dies with the property, loudly rather than silently.

    The client has been told the property is gone, so a ``set`` through the old
    handle would put an update on the wire for something that does not exist -
    which is what a driver holding a handle across a rolled-back ``setup()``
    would otherwise do.
    """
    vector = NumberVector(device="Dev", name="coords", elements=[Number(name="ra")])
    emitted: list[IndiMessage] = []
    prop = BoundProperty(vector, emitted.append)

    prop.delete("no hardware")

    with pytest.raises(RuntimeError, match="retracted"):
        prop.set(ra=1.0)
    assert len(emitted) == 1  # the delProperty, and nothing after it


def test_deleting_twice_emits_one_del_property() -> None:
    """A repeated retraction is a silent no-op, not a second announcement.

    Every libindi driver retracts unconditionally in its disconnect branch, so
    the second disconnect of a session must cost nothing. Emitting again would
    tell the client a property it has already forgotten has gone away twice.
    """
    vector = NumberVector(device="Dev", name="coords", elements=[Number(name="ra")])
    emitted: list[IndiMessage] = []
    prop = BoundProperty(vector, emitted.append)

    prop.delete("no hardware")
    prop.delete("no hardware")

    assert len(emitted) == 1


def test_a_deletion_carries_a_timestamp() -> None:
    """A delProperty is dated, like every other emission.

    ``set`` stamps the vector and libindi's ``IDDelete`` stamps the retraction;
    ours used to send neither a timestamp nor anything else a client could date
    the event by.
    """
    vector = NumberVector(device="Dev", name="coords", elements=[Number(name="ra")])
    emitted: list[IndiMessage] = []
    prop = BoundProperty(vector, emitted.append)

    prop.delete()

    (msg,) = emitted
    assert isinstance(msg, DelProperty)
    assert msg.timestamp is not None
    assert msg.timestamp.tzinfo is not None  # INDI timestamps are UTC
