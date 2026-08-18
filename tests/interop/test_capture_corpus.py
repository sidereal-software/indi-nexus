"""Capture real ``indiserver`` traffic as a fixture the fast suite can replay.

A nightly job that finds a parser bug is useful once. Turning the traffic that found
it into a committed fixture makes every pull request catch it from then on, without
libindi installed and without a subprocess.

Run with ``INDI_CAPTURE_CORPUS=1`` to refresh both committed fixtures:

    INDI_CAPTURE_CORPUS=1 uv run pytest tests/interop/test_capture_corpus.py

Without that variable it only checks that the committed fixtures still parse, so a
normal run neither rewrites tracked files nor depends on the network.

There are two fixtures because one capture cannot be both. ``interop_corpus.xml`` is
breadth: every simulator libindi ships, answering one ``getProperties``, so it is
definitions and nothing else. ``interop_blob_corpus.xml`` is the update path: a single
CCD driven through connect, sub-frame, ``enableBLOB`` and an exposure, so it carries
``set`` vectors, driver messages and a real FITS payload that libindi base64-encoded.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path

import pytest
from conftest import REPO_ROOT
from test_corpus import SIMULATORS

from indi_nexus.protocol import XMLStreamParser

CORPUS = REPO_ROOT / "tests" / "data" / "interop_corpus.xml"
BLOB_CORPUS = REPO_ROOT / "tests" / "data" / "interop_blob_corpus.xml"

#: The sub-frame the BLOB capture asks the CCD simulator for, in pixels. The
#: simulator's full frame is 1280x1024 at 16 bits, which is a 2.6 MB payload and a
#: 3.5 MB base64 fixture - too big to commit for what it proves. 64x64 is still a
#: real FITS file libindi wrote, header and all, at around 15 kB encoded.
BLOB_FRAME_PIXELS = 64

CCD = "CCD Simulator"


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
        with contextlib.suppress(Exception):
            await writer.wait_closed()
    return b"".join(chunks)


async def _capture_exposure(port: int, seconds: float = 90.0) -> bytes:
    """Drive one CCD exposure and return every byte the hub sent back.

    The script is the one a real imaging client runs: enumerate, connect the
    device, shrink the frame, ask for BLOBs, expose. Each step waits on a marker
    in what has arrived rather than on a sleep, so a slow machine takes longer
    instead of capturing a truncated fixture.

    Parameters
    ----------
    port : int
        The server's port.
    seconds : float, optional
        How long to allow for the whole exchange.

    Returns
    -------
    data : bytes
        Everything the server sent, from the ``getProperties`` onward.

    Raises
    ------
    AssertionError
        If a step's marker never arrived.
    """
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    chunks: list[bytes] = []

    async def pump() -> None:
        """Accumulate everything the server sends until cancelled."""
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                return
            chunks.append(chunk)

    async def send(frame: str) -> None:
        """Write one INDI frame to the hub."""
        writer.write(frame.encode())
        await writer.drain()

    async def until(marker: bytes) -> None:
        """Wait for a byte marker to appear in what has been received."""

        async def poll() -> None:
            while marker not in b"".join(chunks):  # noqa: ASYNC110 - a socket, not an event
                await asyncio.sleep(0.05)

        try:
            async with asyncio.timeout(seconds):
                await poll()
        except TimeoutError:  # pragma: no cover - a broken simulator, not the code
            raise AssertionError(f"never saw {marker!r} in {len(b''.join(chunks))} bytes") from None

    pumper = asyncio.create_task(pump())
    try:
        await send('<getProperties version="1.7"/>\n')
        await until(b'name="CONNECTION"')
        await send(
            f'<newSwitchVector device="{CCD}" name="CONNECTION">'
            '<oneSwitch name="CONNECT">On</oneSwitch>'
            '<oneSwitch name="DISCONNECT">Off</oneSwitch></newSwitchVector>\n'
        )
        # CCD_FRAME only exists once the driver is connected, so this doubles as
        # the wait for the connection to have taken.
        await until(b'name="CCD_FRAME"')
        px = BLOB_FRAME_PIXELS
        await send(
            f'<newNumberVector device="{CCD}" name="CCD_FRAME">'
            '<oneNumber name="X">0</oneNumber><oneNumber name="Y">0</oneNumber>'
            f'<oneNumber name="WIDTH">{px}</oneNumber>'
            f'<oneNumber name="HEIGHT">{px}</oneNumber></newNumberVector>\n'
        )
        await until(b'name="CCD_FRAME" state="Ok"')
        # Without this the exposure completes and no payload is ever sent: the
        # whole point of the fixture would be missing and the capture would pass.
        await send(f'<enableBLOB device="{CCD}">Also</enableBLOB>\n')
        await send(
            f'<newNumberVector device="{CCD}" name="CCD_EXPOSURE">'
            '<oneNumber name="CCD_EXPOSURE_VALUE">0.1</oneNumber></newNumberVector>\n'
        )
        await until(b"</oneBLOB>")
        # The BLOB is followed by the exposure vector settling back to Ok, which
        # is what makes the fixture end on a complete message rather than mid-tag.
        await until(b'name="CCD_EXPOSURE" state="Ok"')
    finally:
        pumper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pumper
        writer.close()
        with contextlib.suppress(Exception):
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


@pytest.mark.skipif(
    not os.environ.get("INDI_CAPTURE_CORPUS"),
    reason="set INDI_CAPTURE_CORPUS=1 to refresh the committed fixture",
)
async def test_capture_the_blob_corpus(indi_server):
    """Record a real CCD exposure, payload included, into the committed fixture."""
    server = indi_server("indi_simulator_ccd")
    data = await _capture_exposure(server.port)

    assert b"<oneBLOB" in data, "captured no BLOB; enableBLOB or the exposure did not take"
    parser = XMLStreamParser()
    messages = list(parser.feed(data))
    assert len(messages) > 20, f"only {len(messages)} messages parsed from the capture"
    assert parser.dropped == 0, "captured traffic our own parser drops; fix that before committing"

    Path(BLOB_CORPUS).parent.mkdir(parents=True, exist_ok=True)
    BLOB_CORPUS.write_bytes(data)


def test_the_committed_corpus_is_usable():
    """The fixture in the repository is present and non-trivial."""
    if not CORPUS.exists():  # pragma: no cover - only before the first capture
        pytest.skip("no corpus captured yet; run with INDI_CAPTURE_CORPUS=1")
    assert CORPUS.stat().st_size > 20_000


def test_the_committed_blob_corpus_is_usable():
    """The BLOB fixture in the repository is present and carries a payload."""
    if not BLOB_CORPUS.exists():  # pragma: no cover - only before the first capture
        pytest.skip("no BLOB corpus captured yet; run with INDI_CAPTURE_CORPUS=1")
    assert b"<oneBLOB" in BLOB_CORPUS.read_bytes()
