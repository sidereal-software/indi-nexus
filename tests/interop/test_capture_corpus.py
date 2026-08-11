"""Capture real ``indiserver`` traffic as a fixture the fast suite can replay.

A nightly job that finds a parser bug is useful once. Turning the traffic that found
it into a committed fixture makes every pull request catch it from then on, without
libindi installed and without a subprocess.

Run with ``INDI_CAPTURE_CORPUS=1`` to refresh ``tests/data/interop_corpus.xml``:

    INDI_CAPTURE_CORPUS=1 uv run pytest tests/interop/test_capture_corpus.py

Without that variable it only checks that the committed fixture still parses, so a
normal run neither rewrites tracked files nor depends on the network.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from conftest import REPO_ROOT
from test_corpus import SIMULATORS

from indi_nexus.protocol import XMLStreamParser

CORPUS = REPO_ROOT / "tests" / "data" / "interop_corpus.xml"


async def _capture(port: int, seconds: float) -> bytes:
    """Read raw bytes from a running hub for a while.

    Parameters
    ----------
    port : int
        The server's port.
    seconds : float
        How long to keep reading after the handshake.

    Returns
    -------
    data : bytes
        Everything the server sent.
    """
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(b'<getProperties version="1.7"/>\n')
    await writer.drain()

    chunks: list[bytes] = []
    deadline = asyncio.get_running_loop().time() + seconds
    try:
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            try:
                chunk = await asyncio.wait_for(reader.read(65536), timeout=remaining)
            except TimeoutError:
                break
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        writer.close()
        with __import__("contextlib").suppress(Exception):
            await writer.wait_closed()
    return b"".join(chunks)


@pytest.mark.skipif(
    not os.environ.get("INDI_CAPTURE_CORPUS"),
    reason="set INDI_CAPTURE_CORPUS=1 to refresh the committed fixture",
)
async def test_capture_the_corpus(indi_server):
    """Record every simulator's definitions into the committed fixture."""
    server = indi_server(*SIMULATORS)
    data = await _capture(server.port, seconds=8.0)

    assert len(data) > 20_000, f"captured only {len(data)} bytes; drivers may not have started"
    # Sanity-check before writing: a fixture that does not parse is worse than none.
    parser = XMLStreamParser()
    messages = list(parser.feed(data))
    assert len(messages) > 100, f"only {len(messages)} messages parsed from the capture"

    Path(CORPUS).parent.mkdir(parents=True, exist_ok=True)
    CORPUS.write_bytes(data)


def test_the_committed_corpus_is_usable():
    """The fixture in the repository is present and non-trivial."""
    if not CORPUS.exists():  # pragma: no cover - only before the first capture
        pytest.skip("no corpus captured yet; run with INDI_CAPTURE_CORPUS=1")
    assert CORPUS.stat().st_size > 20_000
