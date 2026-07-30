"""Tests for the client-side :class:`PropertyStore` cache and subscriptions."""

from __future__ import annotations

from indi_nexus.client.store import PropertyEvent, PropertyStore
from indi_nexus.protocol import (
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


def test_del_removes_one_property():
    """Deleting a named property drops it (and the now-empty device)."""
    store = PropertyStore()
    store.apply(DefVector(vector=_numvec()))
    event = store.apply(DelProperty(device="CCD", name="EXPOSURE"))

    assert event is not None and event.type == "del"
    assert store.get("CCD", "EXPOSURE") is None
    assert "CCD" not in store


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
