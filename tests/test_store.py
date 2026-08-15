"""Tests for the client-side :class:`PropertyStore` cache and subscriptions."""

from __future__ import annotations

import datetime as dt

from indi_nexus.client.store import PropertyEvent, PropertyStore
from indi_nexus.protocol import (
    BLOB,
    BLOBVector,
    DefVector,
    DelProperty,
    IPState,
    ISRule,
    ISState,
    Message,
    Number,
    NumberVector,
    SetVector,
    Switch,
    SwitchVector,
    parse_indi,
)


def _numvec(value: float = 1.0, state: IPState = IPState.IDLE) -> NumberVector:
    """Build a one-element number vector for the CCD EXPOSURE property."""
    return NumberVector(
        device="CCD",
        name="EXPOSURE",
        state=state,
        elements=[Number(name="secs", format="%.2f", min=0, max=3600, value=value)],
    )


def test_def_stores_the_vector():
    """Applying a def caches the full vector under device and name."""
    store = PropertyStore()
    event = store.apply(DefVector(vector=_numvec()))

    assert event is not None
    assert event.type == "def"
    assert store.get("CCD", "EXPOSURE") is not None
    assert "CCD" in store
    assert store.devices() == ["CCD"]


def test_set_merges_value_and_state_onto_def():
    """A set copies element values and state onto the cached definition."""
    store = PropertyStore()
    store.apply(DefVector(vector=_numvec(value=1.0)))
    event = store.apply(SetVector(vector=_numvec(value=2.5, state=IPState.OK)))

    assert event is not None and event.type == "set"
    cached = store.get("CCD", "EXPOSURE")
    assert cached is not None
    assert cached.element("secs").value == 2.5
    assert cached.state == IPState.OK
    # Metadata from the def is preserved (set does not carry it).
    assert cached.element("secs").max == 3600


def test_set_before_def_is_ignored():
    """A set for an undefined property changes nothing and returns None."""
    store = PropertyStore()
    assert store.apply(SetVector(vector=_numvec())) is None
    assert store.get("CCD", "EXPOSURE") is None


def test_set_skips_elements_never_defined():
    """A set naming an unknown element merges the known ones and skips it."""
    store = PropertyStore()
    store.apply(DefVector(vector=_numvec(value=1.0)))
    rogue = NumberVector(
        device="CCD",
        name="EXPOSURE",
        elements=[Number(name="ghost", value=9.0), Number(name="secs", value=2.0)],
    )
    store.apply(SetVector(vector=rogue))

    cached = store.get("CCD", "EXPOSURE")
    assert cached is not None
    assert cached.element("secs").value == 2.0
    try:
        cached.element("ghost")
        raise AssertionError("unknown element must not be added by a set")
    except KeyError:
        pass


def test_set_merges_blob_payload_onto_def():
    """A BLOB set copies data, size, and format onto the cached definition."""
    store = PropertyStore()
    store.apply(
        DefVector(
            vector=BLOBVector(device="CCD", name="CCD1", elements=[BLOB(name="image")]),
        )
    )
    payload = b"\x00FITS\xff"
    update = BLOBVector(
        device="CCD",
        name="CCD1",
        state=IPState.OK,
        elements=[BLOB(name="image", format=".fits", data=payload, size=len(payload))],
    )
    store.apply(SetVector(vector=update))

    cached = store.get("CCD", "CCD1")
    assert cached is not None
    el = cached.element("image")
    assert el.data == payload
    assert el.size == len(payload)
    assert el.format == ".fits"

    # A later set without a format keeps the previously merged one.
    store.apply(
        SetVector(
            vector=BLOBVector(
                device="CCD",
                name="CCD1",
                elements=[BLOB(name="image", data=b"x", size=1)],
            )
        )
    )
    assert cached.element("image").format == ".fits"
    assert cached.element("image").data == b"x"


def test_set_carries_timeout_and_message():
    """A set's timeout and message are copied onto the cached vector."""
    store = PropertyStore()
    store.apply(DefVector(vector=_numvec()))
    update = _numvec(value=3.0, state=IPState.BUSY)
    update.timeout = 30.0
    update.message = "exposing"
    store.apply(SetVector(vector=update))

    cached = store.get("CCD", "EXPOSURE")
    assert cached is not None
    assert cached.timeout == 30.0
    assert cached.message == "exposing"


def test_a_stateless_set_leaves_the_cached_state_alone():
    """``state`` is #IMPLIED on a set*Vector: absent means "no change".

    The value update still lands. Before this, the parse default (``Idle``) was
    copied over the cached state, so a property the device had latched into
    ``Alert`` quietly went green on its next reading.
    """
    store = PropertyStore()
    store.apply(DefVector(vector=_numvec(state=IPState.ALERT)))

    store.apply(SetVector(vector=_numvec(value=7.0), state_present=False))

    cached = store.get("CCD", "EXPOSURE")
    assert cached is not None
    assert cached.state is IPState.ALERT
    assert cached.element("secs").value == 7.0


def test_a_stateless_set_parsed_off_the_wire_preserves_the_state():
    """The same rule, end to end from XML, since the loss happens at parse."""
    store = PropertyStore()
    store.apply(DefVector(vector=_numvec(state=IPState.ALERT)))

    (update,) = parse_indi(
        "<setNumberVector device='CCD' name='EXPOSURE'>"
        "<oneNumber name='secs'>7</oneNumber></setNumberVector>"
    )
    store.apply(update)

    cached = store.get("CCD", "EXPOSURE")
    assert cached is not None
    assert cached.state is IPState.ALERT
    assert cached.element("secs").value == 7.0


def test_a_set_that_carries_state_still_updates_it():
    """The guard must not make the cache deaf to a real state change."""
    store = PropertyStore()
    store.apply(DefVector(vector=_numvec(state=IPState.ALERT)))

    store.apply(SetVector(vector=_numvec(value=7.0, state=IPState.OK)))

    cached = store.get("CCD", "EXPOSURE")
    assert cached is not None
    assert cached.state is IPState.OK


def test_getitem_and_iteration_expose_devices():
    """Indexing and iterating the store mirror the device mapping."""
    store = PropertyStore()
    store.apply(DefVector(vector=_numvec()))

    assert "EXPOSURE" in store["CCD"]
    assert list(iter(store)) == ["CCD"]


def test_del_removes_one_property_and_keeps_the_device():
    """Deleting the last property leaves the device present and empty.

    "This device is here and currently publishes nothing" is where a driver that
    defines its properties on connect sits while disconnected, and it is not the
    same as the device being gone - which is what an unnamed delProperty means,
    and the only thing that should drop a device. A panel has to be able to tell
    the two apart. libindi's own client keeps the device here too.
    """
    store = PropertyStore()
    store.apply(DefVector(vector=_numvec()))
    event = store.apply(DelProperty(device="CCD", name="EXPOSURE"))

    assert event is not None and event.type == "del"
    assert store.get("CCD", "EXPOSURE") is None
    assert "CCD" in store
    assert store.device("CCD") == {}
    assert store.devices() == ["CCD"]


def test_del_carries_its_message_and_timestamp_onto_the_event():
    """A deletion's explanation survives into the event subscribers see.

    The text is the only account of *why* a property went away - a driver writes
    real content there - and a ``del`` event has no vector to carry it on, so it
    rides on the event or it is lost before it reaches a UI.
    """
    store = PropertyStore()
    store.apply(DefVector(vector=_numvec()))
    stamped = dt.datetime(2026, 8, 14, 12, 30, tzinfo=dt.UTC)

    event = store.apply(
        DelProperty(
            device="CCD", name="EXPOSURE", timestamp=stamped, message="only while connected"
        )
    )

    assert event is not None
    assert event.message == "only while connected"
    assert event.timestamp == stamped


def test_a_def_or_set_event_carries_no_deletion_message():
    """Only a del sets the event message; a def or set keeps it on the vector."""
    store = PropertyStore()
    definition = store.apply(DefVector(vector=_numvec()))
    update = store.apply(SetVector(vector=_numvec(2.0)))

    assert definition is not None and definition.message is None
    assert definition.timestamp is None
    assert update is not None and update.message is None
    assert update.timestamp is None


def test_del_whole_device():
    """Deleting with no name drops every property of the device."""
    store = PropertyStore()
    store.apply(DefVector(vector=_numvec()))
    store.apply(
        DefVector(
            vector=SwitchVector(
                device="CCD",
                name="CONNECTION",
                rule=ISRule.ONE_OF_MANY,
                elements=[Switch(name="CONNECT", value=ISState.OFF)],
            )
        )
    )
    event = store.apply(DelProperty(device="CCD"))

    assert event is not None and event.type == "del" and event.name is None
    assert "CCD" not in store


def test_del_unknown_returns_none():
    """Deleting something not cached returns None."""
    store = PropertyStore()
    assert store.apply(DelProperty(device="CCD", name="EXPOSURE")) is None


def test_del_unknown_property_on_known_device_returns_none():
    """Deleting a property the device never defined changes nothing."""
    store = PropertyStore()
    store.apply(DefVector(vector=_numvec()))
    assert store.apply(DelProperty(device="CCD", name="OTHER")) is None
    assert store.get("CCD", "EXPOSURE") is not None


def test_non_property_message_is_ignored():
    """A message does not change the cache and yields no event."""
    store = PropertyStore()
    assert store.apply(Message(device="CCD", message="hi")) is None


def test_subscribe_matches_by_device_and_name():
    """matching() returns callbacks whose device/name filters fit the event."""
    store = PropertyStore()
    store.subscribe(lambda e: None, device="CCD", name="EXPOSURE")
    store.subscribe(lambda e: None, device="Mount")
    store.subscribe(lambda e: None)  # wildcard: all events

    event = PropertyEvent("set", "CCD", "EXPOSURE", None)
    assert len(store.matching(event)) == 2  # exact + wildcard, not the Mount one


def test_unsubscribe_stops_delivery():
    """The unsubscribe handle removes the subscription."""
    store = PropertyStore()
    unsub = store.subscribe(lambda e: None)
    event = PropertyEvent("def", "CCD", "EXPOSURE", None)
    assert len(store.matching(event)) == 1
    unsub()
    assert store.matching(event) == []
