"""BLOBs against the real CCD simulator.

The classic INDI interop trap: a server forwards no BLOB to a client that has not
sent ``enableBLOB`` first, so a client that never sends it sees an exposure complete
and no image arrive, with nothing in the logs to say why.

Our client replays its BLOB policies on every reconnect, which is only meaningfully
tested against a server that actually enforces the rule.

The compression cases are here for the same reason. What a payload's ``format``
means - ``.z`` is a transport encoding to inflate, ``.fz`` is a container format
to leave alone - is only settled by what real libindi puts on the wire, and the
answer turned out to be that its CCD simulator emits ``.fz`` and never ``.z``.

**None of this can move to the fast suite.** ``InProcessHub`` has no ``enableBLOB``
gate (see :mod:`indi_nexus.hub`), so every driver frame reaches a client there whether
or not it asked, and the three policies are indistinguishable. A real ``indiserver``
is the only thing that enforces them, so these tests run in Docker or not at all.
"""

from __future__ import annotations

import asyncio
import zlib

import pytest
from drivers.zlib_blob_driver import FRAME

from indi_nexus.client import IndiClient
from indi_nexus.protocol import BLOB, BLOBPolicy, BLOBVector, IPState

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


async def test_a_tile_compressed_frame_is_delivered_exactly_as_libindi_sent_it(indi_server):
    """``CCD_COMPRESSION`` on the FITS path means fpack, and fpack is not ours to undo.

    What real libindi 2.2.4 actually does with ``CCD_COMPRESSION`` enabled: the
    FITS path goes through fpack and arrives as ``.fits.fz`` with ``size`` the
    *uncompressed* FITS length, so the bytes and the number disagree by design.
    FITS tile compression is an astronomy container format rather than a
    transport encoding - no libindi client undoes it, and undoing it needs
    cfitsio - so the payload, the ``.fz`` suffix and the declared ``size`` all
    have to reach the caller untouched. This is the frame that a ``.z`` check
    written as ``endswith("z")`` would silently corrupt.
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
    assert element.format == ".fits.fz", f"expected fpack, got {element.format!r}"
    assert element.data is not None
    # fpack output is still a FITS file; what it is not is inflatable.
    assert element.data[:9] == b"SIMPLE  =", f"not FITS: {element.data[:32]!r}"
    with pytest.raises(zlib.error):
        zlib.decompress(element.data)
    assert element.size is not None and element.size > len(element.data)


async def test_the_native_transfer_format_is_not_compressed_at_all(indi_server):
    """The other half of what libindi really does, pinned so the first half is readable.

    With ``CCD_COMPRESSION`` on and the transfer format set to native, libindi
    2.2.4 sends ``.bin`` with ``size`` equal to the payload length: the switch
    does nothing here. Between this and the ``.fz`` case above, the CCD simulator
    has no path that emits the spec's ``.z`` at all, which is why the zlib case
    is covered by a driver of ours below rather than by the simulator.
    """
    server = indi_server("indi_simulator_ccd")
    client = await _connected_client(server.port)
    try:
        await client.wait_for(DEVICE, "CCD_TRANSFER_FORMAT", timeout=25)
        await client.set_switch(DEVICE, "CCD_TRANSFER_FORMAT", {"FORMAT_NATIVE": True})
        await client.wait_for(DEVICE, "CCD_COMPRESSION", timeout=25)
        await client.set_switch(DEVICE, "CCD_COMPRESSION", {"INDI_ENABLED": True})
        await client.enable_blob(DEVICE, policy=BLOBPolicy.ALSO)
        await _expose(client)
        frame = await _wait_for_frame(client, seconds=90)
    finally:
        await client.aclose()

    element = frame.elements[0]
    assert element.format == ".bin", f"expected the native format, got {element.format!r}"
    assert element.data is not None
    assert element.size == len(element.data)


async def _set_compression(client: IndiClient, *, enabled: bool) -> None:
    """Flip ``CCD_COMPRESSION`` and wait until the simulator confirms the new setting.

    Waiting for the read-back matters more here than it usually does: the switch
    decides how the *next* frame is encoded, so exposing before the driver has
    acknowledged it would race the whole point of the test.

    Parameters
    ----------
    client : IndiClient
        A connected client.
    enabled : bool
        Whether to turn compression on.
    """
    wanted = "INDI_ENABLED" if enabled else "INDI_DISABLED"
    await client.wait_for(DEVICE, "CCD_COMPRESSION", timeout=25)
    await client.set_switch(DEVICE, "CCD_COMPRESSION", {wanted: True})
    await client.wait_for(
        DEVICE,
        "CCD_COMPRESSION",
        lambda v: v.get(wanted) == "On",
        timeout=25,
    )


async def _use_a_small_frame(client: IndiClient) -> None:
    """Shrink the sensor's region of interest so a capture costs a moment, not a minute.

    The simulator's default frame is 1280x1024, and with compression on it goes
    through fpack. A test that captures three of them in sequence pays that
    three times over for nothing: what it is checking is the ``format`` on the
    wire, which a 64x64 sub-frame states exactly as well.

    Parameters
    ----------
    client : IndiClient
        A connected client.
    """
    await client.wait_for(DEVICE, "CCD_FRAME", timeout=25)
    await client.set_number(DEVICE, "CCD_FRAME", {"X": 0, "Y": 0, "WIDTH": 64, "HEIGHT": 64})


async def _capture(client: IndiClient, *, seconds: float = 60) -> BLOB:
    """Expose once and return the *next* image element to arrive.

    :func:`_wait_for_frame` cannot be reused across captures in one session: its
    predicate is satisfied the instant it is called by the frame already sitting
    in the cache, so the second capture would assert against the first. This
    subscribes first and waits for an arrival instead, and hands back a copy
    because the store overwrites the cached payload in place.

    Parameters
    ----------
    client : IndiClient
        A connected client that has asked for BLOBs.
    seconds : float, optional
        How long to wait for the frame.

    Returns
    -------
    element : BLOB
        The image element as delivered, detached from the cache.
    """
    arrived: asyncio.Queue[BLOB] = asyncio.Queue()

    def record(event) -> None:
        """Queue each image payload as it lands."""
        vector = event.vector
        if isinstance(vector, BLOBVector) and vector.elements and vector.elements[0].data:
            arrived.put_nowait(vector.elements[0].model_copy(deep=True))

    unsubscribe = client.store.subscribe(record, device=DEVICE, name="CCD1")
    try:
        await _expose(client, seconds=0.1)
        async with asyncio.timeout(seconds):
            return await arrived.get()
    finally:
        unsubscribe()


async def test_compression_disabled_delivers_a_plain_fits_frame(indi_server):
    """``INDI_DISABLED`` is stated, not inherited from a default that could move.

    Every other uncompressed case here simply never touches the switch, so all
    of them would keep passing if libindi ever shipped a build with compression
    on by default - and would then be testing the compressed path under names
    saying otherwise. Asking for it explicitly is what makes the ``.fits.fz``
    test above readable as a contrast.
    """
    server = indi_server("indi_simulator_ccd")
    client = await _connected_client(server.port)
    try:
        await _set_compression(client, enabled=False)
        await client.enable_blob(DEVICE, policy=BLOBPolicy.ALSO)
        await _expose(client)
        frame = await _wait_for_frame(client, seconds=90)
    finally:
        await client.aclose()

    element = frame.elements[0]
    assert element.format == ".fits", f"expected a plain frame, got {element.format!r}"
    assert element.data is not None
    assert element.data[:9] == b"SIMPLE  =", f"not FITS: {element.data[:32]!r}"
    # A plain FITS frame is not fpacked and not deflated: the declared length is
    # the payload's own, and there is nothing to inflate.
    assert element.size == len(element.data)
    with pytest.raises(zlib.error):
        zlib.decompress(element.data)


async def test_compression_toggles_both_ways_on_one_connection(indi_server):
    """The scenario a user actually hits: compression flipped on and off mid-session.

    Every other test in this file starts a fresh server and moves in one
    direction, which leaves the state that carries *between* frames untested.
    One connection, one ``CCD1`` property, three captures: the format has to
    change each way and, above all, must not stick. A client told ``.fits.fz``
    for a frame libindi sent as plain FITS will hand ordinary bytes to an fpack
    decoder, and nothing on the wire would say why.

    Cheap by construction: a 64x64 sub-frame and a 0.1 s exposure, on the server
    and the client this test already has running.
    """
    server = indi_server("indi_simulator_ccd")
    client = await _connected_client(server.port)
    try:
        await client.enable_blob(DEVICE, policy=BLOBPolicy.ALSO)
        await _use_a_small_frame(client)

        await _set_compression(client, enabled=False)
        first = await _capture(client)

        await _set_compression(client, enabled=True)
        second = await _capture(client)

        await _set_compression(client, enabled=False)
        third = await _capture(client)
    finally:
        await client.aclose()

    assert first.format == ".fits", f"expected a plain frame, got {first.format!r}"
    assert first.data is not None and first.data[:9] == b"SIMPLE  ="
    assert first.size == len(first.data)

    assert second.format == ".fits.fz", f"compression did not take: {second.format!r}"
    assert second.data is not None
    # fpack output is still a FITS file - what it is not is inflatable. How its
    # `size` relates to its length is the full-frame test's subject and not this
    # one's: at 64x64 the tile overhead cancels the saving out entirely.
    assert second.data[:9] == b"SIMPLE  =", f"not FITS: {second.data[:32]!r}"
    assert second.size is not None
    with pytest.raises(zlib.error):
        zlib.decompress(second.data)

    assert third.format == ".fits", f"the compressed format stuck: {third.format!r}"
    assert third.data is not None and third.data[:9] == b"SIMPLE  ="
    assert third.size == len(third.data), "the compressed frame's size outlived it"
    with pytest.raises(zlib.error):
        zlib.decompress(third.data)


async def test_a_zlib_compressed_frame_arrives_inflated_through_a_real_server(
    indi_server, python_driver
):
    """The spec's ``.z`` path, end to end over a real ``indiserver``.

    A driver of ours publishes a deflated payload as ``.fits.z`` with the
    uncompressed ``size``, because libindi's simulator never produces one (see
    the two tests above). Everything between is real: ``indiserver`` re-serialises
    the BLOB for a plain TCP client, and our client is what has to inflate it and
    strip the suffix, exactly as ``BaseDevicePrivate::setBLOB`` does for every
    libindi-based client. An application asked for a FITS file and gets one.
    """
    server = indi_server(python_driver("tests/interop/drivers/zlib_blob_driver.py"))
    device = "Deflater"
    client = IndiClient("127.0.0.1", server.port)
    try:
        await client.start()
        await client.wait_for(device, "CONNECTION", timeout=25)
        await client.set_switch(device, "CONNECTION", {"CONNECT": True})
        await client.wait_for(
            device,
            "CONNECTION",
            lambda v: v.get("CONNECT") == "On",
            timeout=25,
        )
        await client.enable_blob(device, policy=BLOBPolicy.ALSO)
        await client.wait_for(device, "IMAGE", timeout=25)
        await client.set_switch(device, "CAPTURE", {"GO": True})
        frame = await client.wait_for(
            device,
            "IMAGE",
            lambda v: isinstance(v, BLOBVector) and bool(v.elements) and bool(v.elements[0].data),
            timeout=60,
        )
    finally:
        await client.aclose()

    assert isinstance(frame, BLOBVector)
    element = frame.elements[0]
    assert element.format == ".fits", f"the .z suffix survived: {element.format!r}"
    assert element.data == FRAME
    assert element.size == len(FRAME)
