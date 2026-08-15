"""Replay recorded ``indiserver`` traffic through the parser.

The bytes in ``tests/data/interop_corpus.xml`` came off a real hub running every
simulator libindi ships (see ``tests/interop/test_capture_corpus.py``). Replaying
them here gives the fast suite the one thing it otherwise lacks: XML that nobody on
this project wrote, with no libindi installed and no subprocess.

Chunk boundaries are the point of the second test. A streaming parser that works on
whole messages can still break when a tag, an attribute or a multi-byte character is
split across two reads, and a real socket splits wherever it likes.

Both tests also assert the parser's leniency counters stayed at zero. The parser
absorbs malformed input rather than raising, so without that assertion a future
regression could quietly drop half the recording and still "parse" it.

What this corpus does *not* cover: it is an 8-second capture taken right after
``getProperties``, so it is definitions only - 71 ``defSwitchVector``, 30
``defTextVector``, 25 ``defNumberVector``, and no ``set``, ``message``,
``delProperty`` or BLOB at all. It says nothing about the update paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from indi_nexus.client.store import PropertyStore
from indi_nexus.protocol import XMLStreamParser

CORPUS = Path(__file__).parent / "data" / "interop_corpus.xml"

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
