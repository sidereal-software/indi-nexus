"""Replay recorded ``indiserver`` traffic through the parser.

The bytes in ``tests/data/`` came off a real hub (see
``tests/interop/test_capture_corpus.py``). Replaying them here gives the fast suite the
one thing it otherwise lacks: XML that nobody on this project wrote, with no libindi
installed and no subprocess.

There are two recordings, because one capture cannot be both:

``interop_corpus.xml``
    Breadth. Every simulator libindi ships, answering one ``getProperties`` over eight
    seconds, so it is definitions only - 71 ``defSwitchVector``, 30 ``defTextVector``,
    25 ``defNumberVector`` - and says nothing about the update paths.
``interop_blob_corpus.xml``
    Depth on one driver. The CCD simulator driven through connect, a 64x64 sub-frame,
    ``enableBLOB`` and an exposure, so it carries ``setNumberVector``, ``message`` and
    one ``setBLOBVector`` holding a real FITS frame that libindi base64-encoded.

Chunk boundaries are the point of the parametrised tests. A streaming parser that works
on whole messages can still break when a tag, an attribute or a multi-byte character is
split across two reads, and a real socket splits wherever it likes. A BLOB is the worst
case: 15 kB of base64 in one text node, spanning many reads with no parser event in
between, which is exactly where a payload gets truncated or silently re-decoded.

Every test also asserts the parser's leniency counters stayed at zero. The parser
absorbs malformed input rather than raising, so without that assertion a future
regression could quietly drop half the recording and still "parse" it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from indi_nexus.client.store import PropertyStore
from indi_nexus.protocol import BLOBVector, SetVector, XMLStreamParser

DATA = Path(__file__).parent / "data"
CORPUS = DATA / "interop_corpus.xml"
BLOB_CORPUS = DATA / "interop_blob_corpus.xml"

pytestmark = pytest.mark.skipif(
    not CORPUS.exists(),
    reason="no recorded corpus; capture one with tests/interop/test_capture_corpus.py",
)


def _corpus() -> bytes:
    """Return the recorded traffic.

    Returns
    -------
    data : bytes
        The raw bytes captured from a real hub.
    """
    return CORPUS.read_bytes()


def _blob_corpus() -> bytes:
    """Return the recorded CCD exposure, payload included.

    Returns
    -------
    data : bytes
        The raw bytes captured from a real hub running the CCD simulator.
    """
    return BLOB_CORPUS.read_bytes()


def _recorded_blob(data: bytes) -> BLOBVector:
    """Parse the recording and return the one BLOB vector it carries.

    Parameters
    ----------
    data : bytes
        The recorded traffic.

    Returns
    -------
    vector : BLOBVector
        The ``setBLOBVector`` the CCD simulator sent.
    """
    parser = XMLStreamParser()
    blobs = [
        m.vector
        for m in parser.feed(data)
        if isinstance(m, SetVector) and isinstance(m.vector, BLOBVector)
    ]
    assert len(blobs) == 1, f"expected exactly one recorded BLOB, got {len(blobs)}"
    assert parser.dropped == 0 and parser.resets == 0
    return blobs[0]


def test_every_recorded_message_parses():
    """The whole recording parses into messages, and they fold into a store."""
    parser = XMLStreamParser()
    messages = list(parser.feed(_corpus()))
    assert len(messages) > 100, f"only {len(messages)} messages parsed"
    assert parser.dropped == 0, "real hub traffic should need no leniency"
    assert parser.resets == 0

    store = PropertyStore()
    for message in messages:
        store.apply(message)

    devices = store.devices()
    assert len(devices) >= 5, f"expected several devices, got {devices}"
    for device in devices:
        properties = store.device(device)
        assert properties, f"{device} ended with no properties"
        for name, vector in properties.items():
            assert vector.elements, f"{device}.{name} parsed with no elements"


@pytest.mark.parametrize("size", [1, 7, 64, 511, 4096])
def test_the_corpus_parses_at_any_chunk_boundary(size):
    """Feeding the same bytes in fixed-size chunks yields the same messages.

    One byte at a time is the extreme case, and the one most likely to catch a
    parser that assumes a read contains a whole tag.
    """
    data = _corpus()

    whole = XMLStreamParser()
    expected = [type(m).__name__ for m in whole.feed(data)]

    chunked = XMLStreamParser()
    got: list[str] = []
    for start in range(0, len(data), size):
        got.extend(type(m).__name__ for m in chunked.feed(data[start : start + size]))

    assert got == expected, (
        f"chunking at {size} bytes changed the parse: {len(got)} vs {len(expected)} messages"
    )
    assert chunked.dropped == 0, f"chunking at {size} bytes made the parser drop elements"
    assert chunked.resets == 0


# --------------------------------------------------------------------------- #
# The BLOB recording: a real FITS frame libindi encoded                        #
# --------------------------------------------------------------------------- #
needs_blob_corpus = pytest.mark.skipif(
    not BLOB_CORPUS.exists(),
    reason="no recorded BLOB corpus; capture one with tests/interop/test_capture_corpus.py",
)


@needs_blob_corpus
def test_the_recorded_exposure_parses_including_its_update_traffic():
    """The CCD recording parses, and it is updates rather than definitions alone.

    The breadth corpus is a ``getProperties`` answer and nothing else, so without
    this the fast suite has never replayed a real ``setVector`` at all.
    """
    parser = XMLStreamParser()
    messages = list(parser.feed(_blob_corpus()))

    assert parser.dropped == 0, "real hub traffic should need no leniency"
    assert parser.resets == 0
    kinds = [type(m).__name__ for m in messages]
    assert kinds.count("DefVector") > 20, f"too few definitions: {kinds.count('DefVector')}"
    assert kinds.count("SetVector") > 10, f"too few updates: {kinds.count('SetVector')}"
    assert "Message" in kinds, "the driver's log messages did not survive the parse"


@needs_blob_corpus
def test_the_recorded_blob_decodes_to_the_fits_file_libindi_sent():
    """The payload is a real FITS file, at the length the driver declared.

    Nothing else in the fast suite decodes base64 that this project did not
    encode. A decoder that stripped the wrong characters, or that kept the
    payload's surrounding whitespace, lands here first: FITS is fixed-format, so
    a single byte lost or gained breaks both the signature and the block size.
    """
    vector = _recorded_blob(_blob_corpus())

    (element,) = vector.elements
    assert element.name == "CCD1"
    assert element.format == ".fits"
    assert element.data is not None
    # Every FITS file begins with this literal and is a whole number of 2880-byte
    # blocks, so a truncated or padded decode cannot satisfy both.
    assert element.data[:9] == b"SIMPLE  =", f"not FITS: {element.data[:32]!r}"
    assert len(element.data) % 2880 == 0, f"not a whole FITS block count: {len(element.data)}"
    # ``size`` is what the driver declared, independently of what we decoded.
    assert element.size == len(element.data)


@needs_blob_corpus
@pytest.mark.parametrize("size", [1, 7, 64, 511, 4096])
def test_the_recorded_blob_survives_any_chunk_boundary(size):
    """A payload split across reads decodes to exactly the same bytes.

    This is the failure mode a BLOB has and nothing else does: 15 kB of base64 in
    one text node arrives over many reads with no parser event in between, so a
    parser that decoded per-read, or that reset while it was mid-payload, still
    produces a plausible-looking frame instead of an error.
    """
    data = _blob_corpus()
    expected = _recorded_blob(data).elements[0].data

    parser = XMLStreamParser()
    payloads = [
        m.vector.elements[0].data
        for start in range(0, len(data), size)
        for m in parser.feed(data[start : start + size])
        if isinstance(m, SetVector) and isinstance(m.vector, BLOBVector)
    ]

    assert payloads == [expected], f"chunking at {size} bytes changed the decoded payload"
    assert parser.dropped == 0, f"chunking at {size} bytes made the parser drop elements"
    assert parser.resets == 0


@needs_blob_corpus
def test_the_recorded_exposure_folds_a_payload_into_the_store():
    """A ``defBLOBVector`` then a ``setBLOBVector`` leaves the cache holding the image.

    The def carries no payload and the set carries no metadata, so a client only
    ever sees the whole thing if the store merges them. Against real traffic this
    also pins the element name matching, which is where a merge silently drops a
    frame instead of failing.
    """
    parser = XMLStreamParser()
    store = PropertyStore()
    for message in parser.feed(_blob_corpus()):
        store.apply(message)

    cached = store.get("CCD Simulator", "CCD1")
    assert isinstance(cached, BLOBVector)
    assert cached.elements, "the BLOB property cached with no elements"
    assert cached["CCD1"].data == _recorded_blob(_blob_corpus()).elements[0].data
    assert cached["CCD1"].format == ".fits"
