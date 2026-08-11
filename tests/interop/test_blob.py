"""BLOBs against the real CCD simulator.

The classic INDI interop trap: a server forwards no BLOB to a client that has not
sent ``enableBLOB`` first, so a client that never sends it sees an exposure complete
and no image arrive, with nothing in the logs to say why.

Our client replays its BLOB policies on every reconnect, which is only meaningfully
tested against a server that actually enforces the rule.
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
