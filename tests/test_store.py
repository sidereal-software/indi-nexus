"""Tests for the client-side :class:`PropertyStore` cache and subscriptions."""

from __future__ import annotations

import datetime as dt
import zlib

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
    to_xml,
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


def _blob_frame(fmt: str, data: bytes, size: int) -> BLOBVector:
    """Build the ``set`` a camera sends for one frame.

    Parameters
    ----------
    fmt : str
        The element's ``format`` suffix chain, e.g. ``.fits`` or ``.fits.fz``.
    data : bytes
        The payload exactly as it goes on the wire.
    size : int
        The declared *uncompressed* length.

    Returns
    -------
    vector : BLOBVector
        A one-element CCD1 vector ready to be wrapped in a ``SetVector``.
    """
    return BLOBVector(
        device="CCD",
        name="CCD1",
        state=IPState.OK,
        elements=[BLOB(name="image", format=fmt, data=data, size=size)],
    )


def _deliver(store: PropertyStore, vector: BLOBVector) -> BLOB:
    """Serialise one ``set``, parse it back, fold it in, and return the cached element.

    The round trip is the point: inflation happens in the codec and the merge
    happens here, so a format that survives a toggle can only be caught with
    both halves in the same pipeline.

    Parameters
    ----------
    store : PropertyStore
        The cache to fold the message into.
    vector : BLOBVector
        The vector to send as a ``set``.

    Returns
    -------
    element : BLOB
        The cached ``image`` element after the merge.
    """
    (msg,) = parse_indi(to_xml(SetVector(vector=vector)))
    store.apply(msg)
    cached = store.get("CCD", "CCD1")
    assert cached is not None
    element = cached.element("image")
    assert isinstance(element, BLOB)
    return element


def test_a_blob_format_toggles_both_ways_and_does_not_stick():
    """Turning ``CCD_COMPRESSION`` on and off again returns the cached format to ``.fits``.

    Every other BLOB test here moves in one direction, so a merge that latched a
    format - took the first one and kept it, or took a new one and never let it
    go - would pass all of them. This is the fast mirror of the toggle in
    ``tests/interop/test_blob.py``: a client that flips compression on and off
    mid-session and must be told, each time, what it has just been handed.
    ``.fz`` is the honest carrier for it, because it is what libindi's own
    simulator emits and, unlike ``.z``, it reaches the cache unaltered.
    """
    store = PropertyStore()
    store.apply(
        DefVector(
            vector=BLOBVector(
                device="CCD", name="CCD1", elements=[BLOB(name="image", format=".fits")]
            )
        )
    )
    plain, packed = b"SIMPLE  = plain", b"SIMPLE  = fpacked"

    first = _deliver(store, _blob_frame(".fits", plain, len(plain)))
    assert first.format == ".fits"
    assert first.data == plain

    # Compression on: fpack output, with `size` still the uncompressed length.
    second = _deliver(store, _blob_frame(".fits.fz", packed, len(plain)))
    assert second.format == ".fits.fz"
    assert second.data == packed
    assert second.size == len(plain)

    # And off again. This is the assertion that bites: a stale `.fits.fz` here
    # tells a browser to hand raw FITS to an fpack decoder.
    third = _deliver(store, _blob_frame(".fits", plain, len(plain)))
    assert third.format == ".fits", "the compressed format outlived the compression"
    assert third.data == plain
    assert third.size == len(plain)


def test_an_inflated_set_caches_the_stripped_format_and_the_inflated_payload():
    """A ``.z`` frame reaches the cache as ``.fits``, and the next plain frame stays plain.

    The ``.z`` half of the toggle above, where the codec and the merge both act
    on the same element: :func:`inflate_blob` rewrites ``format``, ``data`` and
    ``size`` in place on the parsed message, and the merge is what carries all
    three onto the cached definition. A merge that dropped any of them would
    leave the cache describing a frame nobody sent.
    """
    store = PropertyStore()
    store.apply(
        DefVector(
            vector=BLOBVector(
                device="CCD", name="CCD1", elements=[BLOB(name="image", format=".fits")]
            )
        )
    )
    frame = b"SIMPLE  =" + b" " * 200

    compressed = _deliver(store, _blob_frame(".fits.z", zlib.compress(frame), len(frame)))
    assert compressed.format == ".fits", "the .z suffix reached the cache"
    assert compressed.data == frame, "the cache holds deflated bytes"
    assert compressed.size == len(frame)

    plain = _deliver(store, _blob_frame(".fits", frame, len(frame)))
    assert plain.format == ".fits"
    assert plain.data == frame
    assert plain.size == len(frame)


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


def test_whole_device_delete_reaches_name_filtered_subscribers():
    """An unnamed delProperty is news for a subscriber watching one property.

    The event carries no name because the deletion takes every property with
    it, so a filter matched literally would hide the CCD's driver dying from
    exactly the code watching the CCD's exposure.
    """
    store = PropertyStore()
    store.subscribe(lambda e: None, device="CCD", name="EXPOSURE")
    store.subscribe(lambda e: None, device="Mount", name="EQUATORIAL_EOD_COORD")

    event = PropertyEvent("del", "CCD", None, None)
    assert len(store.matching(event)) == 1


def test_unsubscribe_stops_delivery():
    """The unsubscribe handle removes the subscription."""
    store = PropertyStore()
    unsub = store.subscribe(lambda e: None)
    event = PropertyEvent("def", "CCD", "EXPOSURE", None)
    assert len(store.matching(event)) == 1
    unsub()
    assert store.matching(event) == []
