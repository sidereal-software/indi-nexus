"""BLOBs against the real CCD simulator.

The classic INDI interop trap: a server forwards no BLOB to a client that has not
sent ``enableBLOB`` first, so a client that never sends it sees an exposure complete
and no image arrive, with nothing in the logs to say why.

Our client replays its BLOB policies on every reconnect, which is only meaningfully
tested against a server that actually enforces the rule.

**None of this can move to the fast suite.** ``InProcessHub`` has no ``enableBLOB``
gate (see :mod:`indi_nexus.hub`), so every driver frame reaches a client there whether
or not it asked, and the three policies are indistinguishable. A real ``indiserver``
is the only thing that enforces them, so these tests run in Docker or not at all.
"""

from __future__ import annotations

import asyncio

from indi_nexus.client import IndiClient
from indi_nexus.protocol import BLOBPolicy, BLOBVector, IPState

DEVICE = "CCD Simulator"


async def _connected_client(port: int) -> IndiClient:
    """Return a started client with the CCD simulator connected.

    Parameters
    ----------
    port : int
        The server's port.

    Returns
    -------
    client : IndiClient
        A live client; the caller closes it.
    """
    client = IndiClient("127.0.0.1", port)
    await client.start()
    await client.wait_for(DEVICE, "CONNECTION", timeout=25)
    await client.set_switch(DEVICE, "CONNECTION", {"CONNECT": True})
    await client.wait_for(
        DEVICE,
        "CONNECTION",
        lambda v: v.get("CONNECT") == "On",
        timeout=25,
    )
    return client


async def _expose(client: IndiClient, seconds: float = 1.0) -> None:
    """Start one exposure on the connected CCD simulator.

    Parameters
    ----------
    client : IndiClient
        A connected client.
    seconds : float, optional
        The exposure length to request.
    """
    await client.wait_for(DEVICE, "CCD_EXPOSURE", timeout=25)
    await client.set_number(DEVICE, "CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": seconds})


async def _wait_for_frame(client: IndiClient, seconds: float = 60) -> BLOBVector:
    """Wait until an image payload lands in the cache and return its vector.

    Parameters
    ----------
    client : IndiClient
        A connected client that has asked for BLOBs.
    seconds : float, optional
        How long to wait.

    Returns
    -------
    vector : BLOBVector
        The CCD1 vector, payload included.
    """
    vector = await client.wait_for(
        DEVICE,
        "CCD1",
        lambda v: isinstance(v, BLOBVector) and bool(v.elements) and bool(v.elements[0].data),
        timeout=seconds,
    )
    assert isinstance(vector, BLOBVector)
    return vector


async def test_exposure_delivers_a_real_fits_blob(indi_server):
    """A BLOB requested with enable_blob arrives, and the bytes are a real FITS file."""
    server = indi_server("indi_simulator_ccd")
    client = await _connected_client(server.port)
    try:
        await client.enable_blob(DEVICE, policy=BLOBPolicy.ALSO)
        await client.wait_for(DEVICE, "CCD_EXPOSURE", timeout=25)
        await client.set_number(DEVICE, "CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": 1.0})

        blob = await client.wait_for(
            DEVICE,
            "CCD1",
            lambda v: isinstance(v, BLOBVector) and bool(v.elements) and v.elements[0].data,
            timeout=60,
        )
    finally:
        await client.aclose()

    assert isinstance(blob, BLOBVector)
    element = blob.elements[0]
    assert element.data is not None
    # FITS files begin with the literal "SIMPLE  =". If base64 decoding or the
    # chunked read were wrong, this is where it shows.
    assert element.data[:9] == b"SIMPLE  =", f"not FITS: {element.data[:32]!r}"
    assert element.format == ".fits"
    # size is the *uncompressed* length the driver declared.
    assert element.size and element.size > 1000


async def test_no_blob_arrives_without_enable_blob(indi_server):
    """Without enable_blob the exposure completes and no payload is delivered.

    This is the failure mode the API exists to prevent, so it is worth pinning:
    if a future change started sending enableBLOB implicitly, the guarantee that a
    monitoring client is not flooded with images would go with it.
    """
    server = indi_server("indi_simulator_ccd")
    client = await _connected_client(server.port)
    try:
        await client.wait_for(DEVICE, "CCD_EXPOSURE", timeout=25)
        await client.set_number(DEVICE, "CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": 1.0})
        # Let the exposure finish and then some.
        await client.wait_for(
            DEVICE,
            "CCD_EXPOSURE",
            lambda v: v.state is not IPState.BUSY,
            timeout=60,
        )
        await asyncio.sleep(2)
        vector = client.get(DEVICE, "CCD1")
    finally:
        await client.aclose()

    # The property may be defined, but it must not carry data.
    if vector is not None and isinstance(vector, BLOBVector) and vector.elements:
        assert not vector.elements[0].data, "a BLOB arrived without enableBLOB"


async def test_the_never_policy_withholds_the_payload(indi_server):
    """``Never`` is a real request, not just the absence of one.

    Distinct from the "never asked" case below it: a client that has been
    receiving frames and then asks to stop - a panel closing an image view, say -
    has to actually stop receiving megabytes per exposure. Sending the frame is
    the ordinary INDI failure here, since a hub that only checks "has this client
    ever sent enableBLOB" treats the opt-out as an opt-in.
    """
    server = indi_server("indi_simulator_ccd")
    client = await _connected_client(server.port)
    try:
        await client.enable_blob(DEVICE, policy=BLOBPolicy.NEVER)
        await _expose(client)
        await client.wait_for(
            DEVICE,
            "CCD_EXPOSURE",
            lambda v: v.state is not IPState.BUSY,
            timeout=60,
        )
        # The exposure is over; give the frame every chance to arrive anyway.
        await asyncio.sleep(2)
        vector = client.get(DEVICE, "CCD1")
    finally:
        await client.aclose()

    if vector is not None and isinstance(vector, BLOBVector) and vector.elements:
        assert not vector.elements[0].data, "a BLOB arrived under the Never policy"


async def test_the_only_policy_delivers_the_frame_and_nothing_else(indi_server):
    """``Only`` is what a dedicated image consumer asks for, and it costs the rest.

    The exposure countdown is a ``setNumberVector`` every second, so a hub
    honouring ``Only`` goes quiet on everything but the image. A client that
    treated ``Only`` as ``Also`` would look identical until someone wondered why
    a second connection existed at all.
    """
    server = indi_server("indi_simulator_ccd")
    client = await _connected_client(server.port)
    non_blob: list[str] = []
    try:
        await client.wait_for(DEVICE, "CCD_EXPOSURE", timeout=25)
        await client.enable_blob(DEVICE, policy=BLOBPolicy.ONLY)

        # Subscribe only now, so the definitions that arrived during connect are
        # not counted: the policy governs what comes next, not what already came.
        def record(event) -> None:
            """Note every update that is not an image."""
            if event.vector is not None and not isinstance(event.vector, BLOBVector):
                non_blob.append(f"{event.device}.{event.name}")

        client.store.subscribe(record, device=DEVICE)
        await _expose(client, seconds=2.0)
        frame = await _wait_for_frame(client)
    finally:
        await client.aclose()

    assert frame.elements[0].data
    assert non_blob == [], f"Only still delivered non-BLOB updates: {sorted(set(non_blob))}"


async def test_a_full_frame_exposure_arrives_whole(indi_server):
    """A megabyte payload spans hundreds of reads, which nothing synthetic does.

    The 64x64 recording in the fast suite proves the decode; this proves the read
    loop underneath it, where a frame is assembled from as many TCP segments as
    the kernel feels like and one lost boundary truncates the image.
    """
    server = indi_server("indi_simulator_ccd")
    client = await _connected_client(server.port)
    try:
        await client.enable_blob(DEVICE, policy=BLOBPolicy.ALSO)
        await _expose(client)
        frame = await _wait_for_frame(client, seconds=90)
    finally:
        await client.aclose()

    element = frame.elements[0]
    assert element.data is not None
    assert element.data[:9] == b"SIMPLE  =", f"not FITS: {element.data[:32]!r}"
    # The simulator's default frame is 1280x1024 at 16 bits: a couple of megabytes,
    # far past any single read.
    assert len(element.data) > 1_000_000, f"only {len(element.data)} bytes"
    assert element.size == len(element.data), "declared and decoded lengths disagree"
    # FITS is a whole number of 2880-byte blocks; a truncated read cannot be.
    assert len(element.data) % 2880 == 0


async def test_a_compressed_frame_keeps_the_format_that_explains_it(indi_server):
    """The payload is delivered as sent, so ``format`` is what makes it readable.

    With compression on, libindi sends ``.fits.fz`` (FITS tile compression) and
    ``size`` is the *uncompressed* length, so the bytes and the number disagree by
    design. This package does not decompress anything - not ``.fz``, and not the
    ``.z`` zlib convention in the INDI spec either - so a caller has only the
    format string to tell it what it is holding. If that were normalised away, or
    if ``size`` were rewritten to match the payload, an image would silently
    become unopenable bytes.
    """
    server = indi_server("indi_simulator_ccd")
    client = await _connected_client(server.port)
    try:
        await client.wait_for(DEVICE, "CCD_COMPRESSION", timeout=25)
        await client.set_switch(DEVICE, "CCD_COMPRESSION", {"INDI_ENABLED": True})
        await client.wait_for(
            DEVICE,
            "CCD_COMPRESSION",
            lambda v: v.get("INDI_ENABLED") == "On",
            timeout=25,
        )
        await client.enable_blob(DEVICE, policy=BLOBPolicy.ALSO)
        await _expose(client)
        frame = await _wait_for_frame(client, seconds=90)
    finally:
        await client.aclose()

    element = frame.elements[0]
    assert element.format is not None
    assert element.format.endswith(".fz"), f"expected a compressed format, got {element.format!r}"
    assert element.data is not None
    assert element.size is not None and element.size > 0
