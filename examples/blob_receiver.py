#!/usr/bin/env python3
"""A client that takes an exposure and writes the image to disk - the BLOB half.

``examples/ccd_device.py`` shows how a driver *publishes* a BLOB. This is the
other end, and it exists for one line in :func:`receive`::

    await client.enable_blob(device, "CCD1")

**Without that call ``indiserver`` forwards no BLOB at all, and reports no
error.** The exposure runs, the driver publishes the image, the hub drops it,
and the client waits out its timeout on a frame it was never going to be sent.
That silence is the single most common reason an image "never arrives" in INDI,
and the policy is per device (optionally per property), sticky, and replayed by
:class:`~indi_nexus.client.IndiClient` on every reconnect.

Run it against a camera. This speaks INDI over TCP, so it wants a real ``indiserver``
rather than ``serve --device``, which puts its drivers behind the web bridge::

    indiserver ./examples/ccd_device.py           # terminal 1
    python examples/blob_receiver.py --seconds 2  # terminal 2

The logic lives in :func:`receive` (which takes an already-connected client) and
the pure :func:`save_frame`, so both are importable and unit-testable.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from indi_nexus.client import IndiClient
from indi_nexus.protocol import BLOBVector, ISState, Vector, indi_now

#: The camera this script drives by default (libindi's standard CCD name).
DEFAULT_DEVICE = "CCD Simulator"

#: The standard INDI image BLOB property, and the exposure that produces it.
IMAGE_PROPERTY = "CCD1"
EXPOSURE_PROPERTY = "CCD_EXPOSURE"


def save_frame(vector: BLOBVector, directory: Path) -> Path:
    """Write the first carried payload of a BLOB vector to a file.

    The payload arrives already decoded: base64 is a wire concern the codec
    owns, so ``BLOB.data`` is bytes and ``BLOB.format`` is the file suffix the
    driver declared (``".fits"`` for a camera).

    Parameters
    ----------
    vector : BLOBVector
        The BLOB vector as it arrived from the driver.
    directory : Path
        Where to write; created if it does not exist.

    Returns
    -------
    path : Path
        The file that was written.

    Raises
    ------
    ValueError
        Raised if no element of the vector carries a payload, which is what a
        BLOB property looks like before its first image.
    """
    for element in vector.elements:
        if not element.data:
            continue
        directory.mkdir(parents=True, exist_ok=True)
        stamp = (vector.timestamp or indi_now()).strftime("%Y%m%dT%H%M%S")
        path = directory / f"{vector.name}_{stamp}{element.format or '.bin'}"
        path.write_bytes(element.data)
        return path
    raise ValueError(f"{vector.device}.{vector.name} carried no BLOB payload")


async def receive(
    client: IndiClient,
    device: str = DEFAULT_DEVICE,
    *,
    directory: Path = Path("frames"),
    seconds: float = 1.0,
    timeout: float = 60.0,  # noqa: ASYNC109 - forwarded to wait_for, which mirrors asyncio
) -> Path:
    """Take one exposure on ``device`` and save the image it sends back.

    Parameters
    ----------
    client : IndiClient
        An already-connected client.
    device : str, optional
        The camera's INDI device name.
    directory : Path, optional
        Where the saved image goes.
    seconds : float, optional
        The exposure duration to request.
    timeout : float, optional
        Seconds to wait for each step before giving up.

    Returns
    -------
    path : Path
        The file the image was written to.

    Raises
    ------
    TimeoutError
        Raised if the camera does not appear, connect, or deliver an image in
        time.
    ValueError
        Raised if the delivered vector carries no payload.
    """
    await client.wait_for(device, IMAGE_PROPERTY, timeout=timeout)

    # Ask for BLOBs before anything can produce one. Skip this and everything
    # below still runs, still reports success at every step, and still never
    # sees an image: indiserver filters BLOBs out by default and says nothing.
    await client.enable_blob(device, IMAGE_PROPERTY)

    await client.set_switch(device, "CONNECTION", {"CONNECT": True})
    await client.wait_for(device, "CONNECTION", _connected, timeout=timeout)

    await client.set_number(device, EXPOSURE_PROPERTY, {"CCD_EXPOSURE_VALUE": seconds})
    vector = await client.wait_for(device, IMAGE_PROPERTY, _carries_payload, timeout=timeout)
    if not isinstance(vector, BLOBVector):  # a driver publishing a non-BLOB under this name
        raise ValueError(f"{device}.{IMAGE_PROPERTY} is a {vector.kind} property, not a BLOB")
    return save_frame(vector, directory)


def _connected(vector: Vector) -> bool:
    """Return whether a CONNECTION vector reports the device as connected.

    Parameters
    ----------
    vector : Vector
        The cached vector offered by :meth:`~indi_nexus.client.IndiClient.wait_for`.

    Returns
    -------
    connected : bool
        `True` once the ``CONNECT`` member is On.
    """
    return vector.get("CONNECT") is ISState.ON


def _carries_payload(vector: Vector) -> bool:
    """Return whether a vector is a BLOB vector with bytes in it.

    Parameters
    ----------
    vector : Vector
        The cached vector offered by :meth:`~indi_nexus.client.IndiClient.wait_for`.

    Returns
    -------
    carries : bool
        `True` once at least one element holds a decoded payload.
    """
    return isinstance(vector, BLOBVector) and any(element.data for element in vector.elements)


async def _amain(host: str, port: int, device: str, directory: Path, seconds: float) -> None:
    """Connect to ``indiserver``, expose once, and report where the image went.

    Parameters
    ----------
    host : str
        The ``indiserver`` host.
    port : int
        The ``indiserver`` port.
    device : str
        The camera's INDI device name.
    directory : Path
        Where the saved image goes.
    seconds : float
        The exposure duration to request.
    """
    async with IndiClient(host, port) as client:
        path = await receive(client, device, directory=directory, seconds=seconds)
    print(f"wrote {path} ({path.stat().st_size} bytes)")


def main() -> None:
    """Parse command-line arguments and take one exposure."""
    parser = argparse.ArgumentParser(description="Save one image from an INDI camera.")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=7624)
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--directory", type=Path, default=Path("frames"))
    parser.add_argument("--seconds", type=float, default=1.0)
    args = parser.parse_args()
    asyncio.run(_amain(args.host, args.port, args.device, args.directory, args.seconds))


if __name__ == "__main__":
    main()
